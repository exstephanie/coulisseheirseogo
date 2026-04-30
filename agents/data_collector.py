"""
Data Collector Agent — Fetches reviews, clusters them, and pulls GSC data.

Responsible for populating and maintaining the vault/ data files that
all other agents read from.

Review sources (in priority order):
1. GBP API (automated, if available)
2. Manual CSV import from vault/{brand}/reviews_import.csv
3. Cached reviews.json from previous run
"""

import os
import json
import csv
import logging
import tempfile
from datetime import datetime
from pathlib import Path

import aiohttp

from agents.gsc_agent import GSCAgent

logger = logging.getLogger("coulissehair.data_collector")

# Fixed taxonomy for review classification
REVIEW_TAXONOMY = [
    "anti-frizz-results",
    "keratin-treatment",
    "rebonding-experience",
    "digital-perm",
    "pricing-value",
    "stylist-skill",
    "first-time-visit",
    "humidity-hair-problems",
    "wedding-event-prep",
    "scalp-hair-loss",
    "colour-highlights",
    "salon-ambience-service",
    "kids-family",
    "maintenance-aftercare",
]


def _atomic_write_json(path: Path, data) -> None:
    """Write JSON atomically: write to temp file, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def _read_json(path: Path) -> dict | list:
    """Read and validate JSON from vault file."""
    if not path.exists():
        raise FileNotFoundError(f"Vault file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Vault file is empty: {path}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Vault file has invalid JSON: {path} — {e}") from e


class DataCollector:
    def __init__(self, brand: str = "coulissehair", site_url: str = ""):
        self.brand = brand
        self.vault_dir = Path(f"vault/{brand}")
        self.site_url = site_url or os.getenv("SITE_URL", "https://coulisseheir.com/")
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")

    async def run(self) -> dict:
        """Collect all data: reviews, clusters, GSC."""
        results = {}

        # 1. Fetch/import reviews
        logger.info("Fetching reviews...")
        try:
            reviews = await self._fetch_reviews()
            results["reviews"] = {
                "total": len(reviews),
                "new": results.get("new_reviews", 0),
            }
        except Exception as e:
            logger.error(f"Review fetch failed: {e}")
            results["reviews"] = {"error": str(e)}

        # 2. Cluster reviews (delta only)
        logger.info("Clustering reviews...")
        try:
            clusters = await self._cluster_reviews()
            results["clusters"] = {
                "total_clusters": len(clusters.get("clusters", {})),
                "total_reviews_clustered": sum(
                    len(v) for v in clusters.get("clusters", {}).values()
                ),
            }
        except Exception as e:
            logger.error(f"Clustering failed: {e}")
            results["clusters"] = {"error": str(e)}

        # 3. Pull GSC data
        logger.info("Pulling GSC data...")
        try:
            gsc = GSCAgent(self.site_url)
            gsc_data = await gsc.run()
            results["gsc"] = gsc_data
        except Exception as e:
            logger.error(f"GSC fetch failed: {e}")
            results["gsc"] = {"error": str(e)}

        # 4. Check vault staleness
        results["staleness"] = self._check_staleness()

        return results

    async def _fetch_reviews(self) -> list:
        """Fetch reviews: try GBP API first, fall back to CSV import, then cache."""
        reviews_path = self.vault_dir / "reviews.json"
        existing = []
        if reviews_path.exists():
            try:
                existing = _read_json(reviews_path)
            except (ValueError, FileNotFoundError):
                existing = []

        existing_ids = {r.get("review_id") for r in existing if r.get("review_id")}

        # Try CSV import (manual export from GBP dashboard)
        csv_path = self.vault_dir / "reviews_import.csv"
        if csv_path.exists():
            new_from_csv = self._import_csv(csv_path, existing_ids)
            if new_from_csv:
                logger.info(f"Imported {len(new_from_csv)} new reviews from CSV")
                existing.extend(new_from_csv)
                _atomic_write_json(reviews_path, existing)
                # Archive the CSV so it's not re-imported
                archive_path = self.vault_dir / f"reviews_import_{datetime.now().strftime('%Y%m%d')}.csv.done"
                csv_path.rename(archive_path)

        if not existing:
            logger.warning("No reviews in vault. Export reviews from GBP dashboard to vault/coulissehair/reviews_import.csv")

        return existing

    def _import_csv(self, csv_path: Path, existing_ids: set) -> list:
        """Parse reviews from a CSV export."""
        new_reviews = []
        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Flexible column mapping for GBP/Takeout exports
                    review_id = (
                        row.get("review_id")
                        or row.get("Review ID")
                        or row.get("id")
                        or f"csv-{hash(row.get('text', '') + row.get('reviewer', ''))}"
                    )
                    if review_id in existing_ids:
                        continue

                    review = {
                        "review_id": str(review_id),
                        "reviewer_name": row.get("reviewer") or row.get("Reviewer") or row.get("name") or "Anonymous",
                        "rating": int(row.get("rating") or row.get("Rating") or row.get("stars") or 5),
                        "text": row.get("text") or row.get("Review Text") or row.get("comment") or "",
                        "date": row.get("date") or row.get("Date") or row.get("create_time") or "",
                        "reply": row.get("reply") or row.get("Owner Reply") or "",
                        "source": "csv_import",
                        "imported_at": datetime.now().isoformat(),
                        "cluster": None,
                    }
                    if review["text"]:  # Skip star-only reviews
                        new_reviews.append(review)
        except (csv.Error, UnicodeDecodeError) as e:
            logger.error(f"CSV parse error: {e}")

        return new_reviews

    async def _cluster_reviews(self) -> dict:
        """Classify unclustered reviews into topic clusters using Claude."""
        reviews_path = self.vault_dir / "reviews.json"
        clusters_path = self.vault_dir / "review_clusters.json"

        reviews = _read_json(reviews_path) if reviews_path.exists() else []
        clusters = _read_json(clusters_path) if clusters_path.exists() else {
            "taxonomy": REVIEW_TAXONOMY,
            "clusters": {},
            "last_clustered": None,
            "total_reviews": 0,
        }

        # Find unclustered reviews
        unclustered = [r for r in reviews if not r.get("cluster")]
        if not unclustered:
            logger.info("All reviews already clustered")
            return clusters

        logger.info(f"Classifying {len(unclustered)} unclustered reviews...")

        # Batch classify with Claude (up to 50 at a time to manage token usage)
        for batch_start in range(0, len(unclustered), 50):
            batch = unclustered[batch_start:batch_start + 50]
            classifications = await self._classify_batch(batch)

            for review, category in zip(batch, classifications):
                review["cluster"] = category
                if category not in clusters["clusters"]:
                    clusters["clusters"][category] = []
                clusters["clusters"][category].append({
                    "review_id": review["review_id"],
                    "text": review["text"][:200],
                    "rating": review["rating"],
                    "reviewer": review["reviewer_name"],
                    "date": review.get("date", ""),
                })

        clusters["last_clustered"] = datetime.now().isoformat()
        clusters["total_reviews"] = len(reviews)

        # Save both files atomically
        _atomic_write_json(reviews_path, reviews)
        _atomic_write_json(clusters_path, clusters)

        return clusters

    async def _classify_batch(self, reviews: list) -> list[str]:
        """Classify a batch of reviews into taxonomy categories using Claude."""
        if not self.api_key:
            logger.warning("No ANTHROPIC_API_KEY — using keyword-based classification")
            return [self._keyword_classify(r["text"]) for r in reviews]

        reviews_text = "\n".join(
            f'{i+1}. [{r["rating"]}★] "{r["text"][:150]}"'
            for i, r in enumerate(reviews)
        )

        prompt = f"""Classify each review into exactly ONE category from this list:
{json.dumps(REVIEW_TAXONOMY)}

Reviews:
{reviews_text}

Return a JSON array of category strings, one per review, in the same order.
Example: ["anti-frizz-results", "pricing-value", "stylist-skill"]
Return ONLY the JSON array, no other text."""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "temperature": 0,
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Claude API error: {resp.status}")
                        return [self._keyword_classify(r["text"]) for r in reviews]
                    data = await resp.json()
                    text = data["content"][0]["text"].strip()
                    # Parse JSON array from response
                    categories = json.loads(text)
                    # Validate each category
                    return [
                        c if c in REVIEW_TAXONOMY else "salon-ambience-service"
                        for c in categories
                    ]
        except (aiohttp.ClientError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Classification API error: {e}")
            return [self._keyword_classify(r["text"]) for r in reviews]

    def _keyword_classify(self, text: str) -> str:
        """Fallback keyword-based classification when Claude is unavailable."""
        text_lower = text.lower()
        keyword_map = {
            "anti-frizz-results": ["frizz", "frizzy", "smooth", "anti-frizz"],
            "keratin-treatment": ["keratin"],
            "rebonding-experience": ["rebond", "straight"],
            "digital-perm": ["perm", "curl", "wave"],
            "pricing-value": ["price", "cheap", "expensive", "worth", "value", "cost", "affordable"],
            "stylist-skill": ["stylist", "hairdresser", "skill", "professional", "expert"],
            "first-time-visit": ["first time", "first visit", "new customer"],
            "humidity-hair-problems": ["humid", "weather", "rain", "sweat"],
            "wedding-event-prep": ["wedding", "bridal", "event", "dinner"],
            "scalp-hair-loss": ["scalp", "dandruff", "hair loss", "thinning"],
            "colour-highlights": ["colour", "color", "highlight", "dye", "balayage"],
            "kids-family": ["kid", "child", "daughter", "son", "family"],
            "maintenance-aftercare": ["maintain", "aftercare", "shampoo", "last"],
        }
        for category, keywords in keyword_map.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return "salon-ambience-service"

    def _check_staleness(self) -> dict:
        """Check if vault files are stale."""
        warnings = []
        for filename in ["services.json", "stylists.json", "faqs.json"]:
            filepath = self.vault_dir / filename
            if filepath.exists():
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                days_old = (datetime.now() - mtime).days
                if days_old > 90:
                    warnings.append(f"{filename} is {days_old} days old — update recommended")
            else:
                warnings.append(f"{filename} is missing")

        reviews_path = self.vault_dir / "reviews.json"
        if reviews_path.exists():
            reviews = _read_json(reviews_path) if reviews_path.stat().st_size > 2 else []
            if not reviews:
                warnings.append("reviews.json is empty — import reviews from GBP dashboard")
        else:
            warnings.append("reviews.json does not exist")

        return {"warnings": warnings, "stale": len(warnings) > 0}
