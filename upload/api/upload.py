"""
Vercel serverless function: parse Google Takeout ZIP and commit reviews to GitHub.

Receives a ZIP file upload, extracts Google Business Profile review JSON files,
parses them into CSV format, and commits to the coulisseheirseogo repo via GitHub API.
"""

import json
import csv
import io
import zipfile
import base64
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()
BRAND_SLUG = os.environ.get("BRAND_SLUG", "brand").strip()
REVIEW_FILE_PATH = f"vault/{BRAND_SLUG}/reviews_import.csv"

RATING_MAP = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def parse_reviews_from_zip(zip_bytes: bytes) -> list[dict]:
    """Extract and parse all reviews from a Google Takeout ZIP."""
    reviews = []
    seen_ids = set()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if "reviews" not in name or not name.endswith(".json"):
                continue
            try:
                data = json.loads(zf.read(name))
                review_list = data.get("reviews", []) if isinstance(data, dict) else data
                for r in review_list:
                    rid = r.get("name", "").split("/")[-1]
                    if rid in seen_ids:
                        continue
                    seen_ids.add(rid)

                    comment = r.get("comment", "")
                    if not comment.strip():
                        continue

                    reviews.append({
                        "review_id": rid,
                        "reviewer": r.get("reviewer", {}).get("displayName", "Anonymous"),
                        "rating": RATING_MAP.get(r.get("starRating", "FIVE"), 5),
                        "text": comment,
                        "date": r.get("createTime", "")[:10],
                    })
            except (json.JSONDecodeError, KeyError):
                continue

    reviews.sort(key=lambda x: x["date"], reverse=True)
    return reviews


def reviews_to_csv(reviews: list[dict]) -> str:
    """Convert reviews list to CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["review_id", "reviewer", "rating", "text", "date"])
    writer.writeheader()
    writer.writerows(reviews)
    return output.getvalue()


def github_api(method: str, endpoint: str, body: dict = None) -> dict:
    """Make a GitHub API request."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    })
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_existing_review_ids() -> set:
    """Fetch existing reviews from the repo to detect duplicates."""
    try:
        data = github_api("GET", f"contents/{REVIEW_FILE_PATH}")
        content = base64.b64decode(data["content"]).decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        return {row["review_id"] for row in reader if row.get("review_id")}
    except (HTTPError, KeyError):
        return set()


def commit_reviews(csv_content: str, message: str) -> dict:
    """Commit the CSV file to GitHub."""
    # Get current file SHA (needed for update)
    sha = None
    try:
        data = github_api("GET", f"contents/{REVIEW_FILE_PATH}")
        sha = data.get("sha")
    except HTTPError:
        pass

    body = {
        "message": message,
        "content": base64.b64encode(csv_content.encode("utf-8")).decode("utf-8"),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha

    return github_api("PUT", f"contents/{REVIEW_FILE_PATH}", body)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            # Accept pre-parsed CSV sent as JSON from the browser (new flow)
            if "application/json" in content_type:
                payload = json.loads(body.decode("utf-8"))
                incoming_csv = payload.get("csv", "")
                if not incoming_csv:
                    self._respond(400, {"success": False, "error": "No CSV data received"})
                    return

                reader = csv.DictReader(io.StringIO(incoming_csv))
                new_reviews = list(reader)
                if not new_reviews:
                    self._respond(200, {"success": False, "error": "No reviews found in the data."})
                    return

                existing_ids = get_existing_review_ids()
                unique_reviews = [r for r in new_reviews if r.get("review_id") not in existing_ids]

                if existing_ids and unique_reviews:
                    try:
                        data = github_api("GET", f"contents/{REVIEW_FILE_PATH}")
                        existing_csv = base64.b64decode(data["content"]).decode("utf-8")
                        existing_rows = list(csv.DictReader(io.StringIO(existing_csv)))
                        all_reviews = existing_rows + unique_reviews
                    except HTTPError:
                        all_reviews = new_reviews
                else:
                    all_reviews = new_reviews
                    unique_reviews = new_reviews if not existing_ids else unique_reviews

                csv_content = reviews_to_csv(all_reviews)
                message = f"data: import {len(unique_reviews)} new reviews ({len(all_reviews)} total) [via upload]"
                commit_reviews(csv_content, message)

                self._respond(200, {
                    "success": True,
                    "reviews_count": len(all_reviews),
                    "new_count": len(unique_reviews),
                })
                return

            self._respond(400, {"success": False, "error": "Expected application/json"})

        except Exception as e:
            self._respond(500, {"success": False, "error": str(e)})

    def _respond(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
