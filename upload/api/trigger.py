"""
Vercel serverless function: trigger the SEO agent workflow on demand.

Calls GitHub Actions workflow_dispatch to run the weekly pipeline immediately.
"""

import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "danielncy/coulisseheirseogo").strip()


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not GITHUB_TOKEN:
            self._respond(500, {"success": False, "error": "GITHUB_TOKEN not configured"})
            return

        try:
            payload = json.dumps({
                "ref": "main",
                "inputs": {"mode": "weekly"},
            }).encode("utf-8")

            req = Request(
                f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/seo_pdca.yml/dispatches",
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                },
            )

            resp = urlopen(req, timeout=10)
            resp.close()
            self._respond(200, {
                "success": True,
                "message": "Article generation triggered. Check your email in ~5 minutes.",
            })

        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            # 204 is actually success for workflow_dispatch
            if e.code == 204:
                self._respond(200, {
                    "success": True,
                    "message": "Article generation triggered. Check your email in ~5 minutes.",
                })
            else:
                self._respond(500, {"success": False, "error": f"GitHub API error: {e.code} - {body}"})
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
