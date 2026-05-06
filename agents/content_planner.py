"""
Content Planner Agent — Selects the best topic for this week's blog post.

Uses a single Claude call with GSC data + review clusters + vault data
to pick the topic most likely to rank. Replaces the 5-persona council.

Topic scoring: keyword_opportunity x review_volume x recency
"""

import os
import json
import logging
from pathlib import Path

import aiohttp

logger = logging.getLogger("coulissehair.content_planner")


class ContentPlanner:
    def __init__(self, brand: str = "coulissehair", gsc_data: dict = None):
        self.brand = brand
        self.vault_dir = Path(f"vault/{brand}")
        self.gsc_data = gsc_data or {}
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")

    async def plan(self) -> dict:
        """Select topic and create content brief."""
        # Load vault data
        clusters = self._load_json("review_clusters.json")
        services = self._load_json("services.json")
        brand_voice = self._load_text("brand_voice.md")
        _raw = self._load_json("used_reviews.json") or {}
        used_reviews = {"used_ids": [], "used_clusters": [], **_raw}

        # Load pre-approved topics list
        topics_data = self._load_json("content_topics.json") or {}
        all_topics = topics_data.get("topics", [])
        available_topics = [t for t in all_topics if not t.get("used", False)]

        # Build context for Claude
        quick_wins = self.gsc_data.get("quick_wins", [])[:10]
        recent_clusters = used_reviews.get("used_clusters", [])[-3:]
        cluster_summary = self._summarize_clusters(clusters, exclude=recent_clusters)

        if not available_topics and not quick_wins:
            logger.warning("No topics available and no GSC data — using fallback topic")
            return self._fallback_plan(services)

        # Build topics block for prompt
        if available_topics:
            priority_topics = [t for t in available_topics if t.get("priority", False)]
            regular_topics = [t for t in available_topics if not t.get("priority", False)]
            topics_block = "AVAILABLE ARTICLE TOPICS (you MUST pick one from this list):\n"
            if priority_topics:
                topics_block += "\n⭐ PRIORITY topics — pick from these first before considering others:\n"
                for t in priority_topics:
                    topics_block += f'- id: "{t["id"]}" | title: "{t["title"]}" | keyword: "{t["target_keyword"]}" | angle: {t["angle"]}\n'
            if regular_topics:
                topics_block += "\nOther available topics (only if no priority topic fits):\n"
                for t in regular_topics:
                    topics_block += f'- id: "{t["id"]}" | title: "{t["title"]}" | keyword: "{t["target_keyword"]}" | angle: {t["angle"]}\n'
        else:
            topics_block = "No pre-approved topics remaining — choose a new on-brand topic."

        prompt = f"""You are an SEO content planner for Coulisse Heir, a luxury scalp wellness sanctuary in Singapore.

BRAND VOICE (read carefully — this defines what topics are and are NOT allowed):
{brand_voice[:2000]}

STRICT CONTENT RULES:
- NEVER write about anti-frizz, frizz control, humidity, or hair smoothing — that is a competitor brand
- NEVER use "hair rescue" as a topic — that is not a Coulisse Heir service
- NEVER suggest haircuts, colouring, rebonding, or keratin straightening
- NEVER include specific pricing or dollar amounts in the article
- ALWAYS focus on: scalp wellness, scalp reset, self-care rituals, stress and hair, private pods, restoration
- Target audience: women seeking luxury scalp wellness experiences, not quick fixes

{topics_block}

GSC QUICK-WIN KEYWORDS (use these to inform which topic will rank best):
{json.dumps(quick_wins[:8], indent=2) if quick_wins else "No GSC data yet."}

REVIEW CLUSTERS (topics customers talk about, with review count):
{cluster_summary}

SERVICES OFFERED (mention by name only — no pricing):
{self._format_services(services)}

RECENTLY COVERED (do NOT repeat these clusters):
{', '.join(recent_clusters) if recent_clusters else 'None yet — this is the first article.'}

YOUR TASK:
Pick ONE topic from AVAILABLE ARTICLE TOPICS above that:
1. Best matches current GSC opportunities (if data exists) or will help a Singapore woman find Coulisse Heir
2. Is DIFFERENT from recently covered clusters
3. Aligns with the brand voice and content pillars

Return a JSON object with:
{{
  "topic_id": "the id field from the chosen topic",
  "title": "Blog post title (use or refine the topic's title)",
  "target_keyword": "use the exact target_keyword from the chosen topic",
  "cluster": "which review cluster to pull quotes from",
  "angle": "what makes this post unique",
  "reviews_to_include": 3,
  "services_to_mention": ["service names to reference — NO pricing"],
  "outline": ["H2 heading 1", "H2 heading 2", "H2 heading 3", "H2 heading 4"],
  "meta_description": "120-160 chars, MUST contain the exact target_keyword"
}}

Return ONLY the JSON object."""

        try:
            result = await self._call_claude(prompt)
            # Strip markdown code fences if present
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                clean = clean.rsplit("```", 1)[0].strip()
            plan = json.loads(clean)

            # Attach review quotes from the selected cluster (excluding used ones)
            used_ids = set(used_reviews.get("used_ids", []))
            plan["review_quotes"] = self._get_review_quotes(
                clusters, plan.get("cluster", ""), plan.get("reviews_to_include", 3),
                exclude_ids=used_ids,
            )
            plan["services_data"] = [
                s for s in services
                if s["name"] in plan.get("services_to_mention", [])
            ]

            # Mark topic as used in content_topics.json
            chosen_id = plan.get("topic_id", "")
            if chosen_id and all_topics:
                for t in all_topics:
                    if t["id"] == chosen_id:
                        t["used"] = True
                        break
                self._save_json("content_topics.json", {"topics": all_topics})

            # Track what we used so next article is different
            new_used_ids = [r.get("review_id", "") for r in plan["review_quotes"] if r.get("review_id")]
            used_reviews["used_ids"].extend(new_used_ids)
            used_reviews["used_clusters"].append(plan.get("cluster", ""))
            # Keep only last 50 used review IDs and last 10 clusters
            used_reviews["used_ids"] = used_reviews["used_ids"][-50:]
            used_reviews["used_clusters"] = used_reviews["used_clusters"][-10:]
            self._save_json("used_reviews.json", used_reviews)

            logger.info(f"Topic selected: {plan.get('title', 'Unknown')} (id: {chosen_id})")
            return plan

        except json.JSONDecodeError as e:
            logger.error(f"Claude returned invalid JSON: {e}")
            return self._fallback_plan(services)
        except aiohttp.ClientError as e:
            logger.error(f"Claude API error: {e}")
            return self._fallback_plan(services)

    def _format_services(self, services: list) -> str:
        """Format services for the prompt."""
        items = []
        for s in services[:6]:
            items.append({
                "name": s["name"],
                "price_from": s["price_from"],
                "keywords": s.get("keywords", []),
            })
        return json.dumps(items, indent=2)

    def _summarize_clusters(self, clusters: dict, exclude: list = None) -> str:
        """Summarize clusters for the prompt, deprioritizing recently used ones."""
        exclude = exclude or []
        lines = []
        for category, reviews in clusters.get("clusters", {}).items():
            if reviews:
                sample = reviews[0].get("text", "")[:80]
                tag = " (RECENTLY USED — pick something else)" if category in exclude else ""
                lines.append(f"- {category}: {len(reviews)} reviews{tag} (e.g., \"{sample}...\")")
        return "\n".join(lines) if lines else "No review clusters available yet."

    def _save_json(self, filename: str, data) -> None:
        """Save data to a vault JSON file."""
        path = self.vault_dir / filename
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _get_review_quotes(self, clusters: dict, cluster_name: str, count: int, exclude_ids: set = None) -> list:
        """Get top review quotes from a cluster, excluding previously used ones."""
        reviews = clusters.get("clusters", {}).get(cluster_name, [])
        exclude_ids = exclude_ids or set()

        # Filter out already-used reviews
        available = [r for r in reviews if r.get("review_id", "") not in exclude_ids]

        # If all reviews in this cluster were used, allow reuse but prefer unused
        if not available:
            available = reviews

        # Prefer 4-5 star reviews with longer text
        sorted_reviews = sorted(
            available,
            key=lambda r: (r.get("rating", 0), len(r.get("text", ""))),
            reverse=True,
        )
        return [
            {
                "review_id": r.get("review_id", ""),
                "text": r["text"],
                "reviewer": r.get("reviewer", "Customer"),
                "rating": r.get("rating", 5),
            }
            for r in sorted_reviews[:count]
        ]

    def _fallback_plan(self, services: list) -> dict:
        """Generate a basic plan when no review or GSC data is available."""
        top_service = services[0] if services else {
            "name": "Scalp Treatment",
            "keywords": ["scalp treatment singapore"],
        }
        return {
            "title": f"Scalp Treatment Singapore: Why Self-Care Begins at the Scalp",
            "target_keyword": top_service.get("keywords", ["scalp treatment singapore"])[0],
            "cluster": "scalp-wellness",
            "angle": "Scalp wellness as the foundation of beautiful hair — introducing the Coulisse Heir sanctuary experience",
            "reviews_to_include": 0,
            "services_to_mention": [top_service["name"]],
            "outline": [
                "Why Scalp Health Is the Foundation of Beautiful Hair",
                "Signs Your Scalp Needs Professional Care",
                "What to Expect from a Luxury Scalp Ritual",
                "Experience Scalp Wellness at Coulisse Heir, ION Orchard",
            ],
            "meta_description": f"Discover luxury scalp treatment in Singapore at Coulisse Heir. Private pods, bespoke scalp restoration rituals at ION Orchard.",
            "review_quotes": [],
            "services_data": [top_service],
            "fallback": True,
        }

    async def _call_claude(self, prompt: str) -> str:
        """Make a single Claude API call."""
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise aiohttp.ClientError(f"Claude API {resp.status}: {error[:200]}")
                data = await resp.json()
                return data["content"][0]["text"].strip()

    def _load_json(self, filename: str) -> dict | list:
        """Load a JSON vault file."""
        path = self.vault_dir / filename
        if not path.exists():
            return {} if filename.endswith("clusters.json") else []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Invalid vault file {filename}: {e}")
            return {} if filename.endswith("clusters.json") else []

    def _load_text(self, filename: str) -> str:
        """Load a text vault file."""
        path = self.vault_dir / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
