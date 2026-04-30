"""
Vercel serverless function: trigger the publish workflow with one click.

Called from the approval email's "Approve & Publish" button.
"""

import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "danielncy/coulisseheirseogo").strip()

HTML_SUCCESS = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Publishing...</title>
<style>body{font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#f5f5f5;margin:0;}
.card{background:white;border-radius:16px;padding:48px;max-width:400px;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,0.08);}
h1{color:#28a745;font-size:1.5rem;}p{color:#666;line-height:1.6;}</style></head>
<body><div class="card">
<h1>Publishing to WordPress</h1>
<p>The article is being published with a featured image. This takes about 2 minutes.</p>
<p>You'll see it appear in WordPress shortly.</p>
</div></body></html>"""

HTML_ERROR = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Error</title>
<style>body{font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#f5f5f5;margin:0;}
.card{background:white;border-radius:16px;padding:48px;max-width:400px;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,0.08);}
h1{color:#c5221f;font-size:1.5rem;}p{color:#666;line-height:1.6;}</style></head>
<body><div class="card">
<h1>Something went wrong</h1>
<p>ERROR_MSG</p>
</div></body></html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """One-click publish from email link."""
        if not GITHUB_TOKEN:
            self._html(500, HTML_ERROR.replace("ERROR_MSG", "Server not configured. Contact Daniel."))
            return

        try:
            payload = json.dumps({
                "ref": "main",
            }).encode("utf-8")

            req = Request(
                f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/publish.yml/dispatches",
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                },
            )

            try:
                resp = urlopen(req, timeout=10)
                resp.close()
            except HTTPError as e:
                if e.code == 204:
                    pass  # 204 No Content = success for workflow_dispatch
                else:
                    raise

            self._html(200, HTML_SUCCESS)

        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            self._html(500, HTML_ERROR.replace("ERROR_MSG", f"GitHub API error: {e.code}"))
        except Exception as e:
            self._html(500, HTML_ERROR.replace("ERROR_MSG", str(e)))

    def _html(self, code: int, content: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))
