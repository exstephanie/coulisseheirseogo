"""
Run locally to extract reviews from a Google Takeout ZIP and save to vault.
Usage: python3 parse_reviews_local.py ~/Downloads/takeout-XXXX.zip
"""
import sys
import json
import csv
import io
import zipfile
from pathlib import Path

RATING_MAP = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
OUTPUT = Path("vault/coulissehair/reviews_import.csv")


BRAND_FILTER = "coulisse"  # Only process files with this word in the path (case-insensitive)


def parse(zip_path: str) -> list[dict]:
    reviews = []
    seen = set()
    with zipfile.ZipFile(zip_path) as zf:
        all_review_files = [n for n in zf.namelist() if "reviews" in n.lower() and n.endswith(".json")]
        review_files = [n for n in all_review_files if BRAND_FILTER in n.lower()]
        skipped = len(all_review_files) - len(review_files)
        print(f"Found {len(all_review_files)} review file(s) total — using {len(review_files)} matching '{BRAND_FILTER}' ({skipped} other brands skipped)")
        for name in review_files:
            print(f"  Reading: {name}")
            try:
                data = json.loads(zf.read(name))
                items = data.get("reviews", []) if isinstance(data, dict) else data
                for r in items:
                    rid = r.get("name", "").split("/")[-1]
                    if rid in seen or not r.get("comment", "").strip():
                        continue
                    seen.add(rid)
                    reviews.append({
                        "review_id": rid,
                        "reviewer": r.get("reviewer", {}).get("displayName", "Anonymous"),
                        "rating": RATING_MAP.get(r.get("starRating", "FIVE"), 5),
                        "text": r.get("comment", "").strip(),
                        "date": r.get("createTime", "")[:10],
                    })
            except Exception as e:
                print(f"  Skipped {name}: {e}")
    reviews.sort(key=lambda x: x["date"], reverse=True)
    return reviews


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 parse_reviews_local.py /path/to/takeout.zip")
        sys.exit(1)

    zip_path = sys.argv[1]
    reviews = parse(zip_path)

    if not reviews:
        print("No reviews found. Make sure you exported Google Business Profile data.")
        sys.exit(1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["review_id", "reviewer", "rating", "text", "date"])
        writer.writeheader()
        writer.writerows(reviews)

    print(f"\nDone! {len(reviews)} reviews saved to {OUTPUT}")
    print("Next: git add vault/coulissehair/reviews_import.csv && git commit -m 'data: import reviews' && git push")
