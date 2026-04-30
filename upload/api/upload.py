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
GITHUB_REPO = os.environ.get("GITHUB_REPO", "danielncy/coulisseheirseogo").strip()
REVIEW_FILE_PATH = "vault/coulissehair/reviews_import.csv"

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
            # Parse multipart form data
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._respond(400, {"success": False, "error": "Expected multipart/form-data"})
                return

            # Read the body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            # Extract the file from multipart data
            boundary = content_type.split("boundary=")[1].encode()
            parts = body.split(b"--" + boundary)
            zip_bytes = None
            for part in parts:
                if b"filename=" in part and b".zip" in part:
                    # Find the start of file data (after double newline)
                    header_end = part.find(b"\r\n\r\n")
                    if header_end != -1:
                        zip_bytes = part[header_end + 4:]
                        # Remove trailing \r\n
                        if zip_bytes.endswith(b"\r\n"):
                            zip_bytes = zip_bytes[:-2]
                    break

            if not zip_bytes:
                self._respond(400, {"success": False, "error": "No ZIP file found in upload"})
                return

            # Parse reviews from ZIP
            new_reviews = parse_reviews_from_zip(zip_bytes)
            if not new_reviews:
                self._respond(200, {"success": False, "error": "No reviews found in the ZIP. Make sure you exported Google Business Profile data."})
                return

            # Check for duplicates against existing reviews
            existing_ids = get_existing_review_ids()
            unique_reviews = [r for r in new_reviews if r["review_id"] not in existing_ids]

            # Merge: keep existing + add new
            if existing_ids and unique_reviews:
                # Fetch existing CSV, parse, merge
                try:
                    data = github_api("GET", f"contents/{REVIEW_FILE_PATH}")
                    existing_csv = base64.b64decode(data["content"]).decode("utf-8")
                    reader = csv.DictReader(io.StringIO(existing_csv))
                    all_reviews = list(reader) + unique_reviews
                except HTTPError:
                    all_reviews = new_reviews
            elif not existing_ids:
                all_reviews = new_reviews
                unique_reviews = new_reviews
            else:
                all_reviews = new_reviews  # All duplicates, but overwrite with fresh data
                unique_reviews = []

            # Convert to CSV and commit
            csv_content = reviews_to_csv(all_reviews)
            message = f"data: import {len(unique_reviews)} new reviews ({len(all_reviews)} total) [via upload]"
            commit_reviews(csv_content, message)

            self._respond(200, {
                "success": True,
                "reviews_count": len(all_reviews),
                "new_count": len(unique_reviews),
                "duplicates_skipped": len(new_reviews) - len(unique_reviews),
            })

        except zipfile.BadZipFile:
            self._respond(400, {"success": False, "error": "Invalid ZIP file. Please upload the file from Google Takeout."})
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")[:200]
            self._respond(500, {"success": False, "error": f"GitHub API error: {e.code} - {error_body}"})
        except Exception as e:
            self._respond(500, {"success": False, "error": f"Server error: {str(e)}"})

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
