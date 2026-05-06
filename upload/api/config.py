"""
Vercel serverless function: serve brand config to the frontend.

Set these environment variables in Vercel per project:
  BRAND_NAME      — display name, e.g. "Coulisse Heir"
  BRAND_SLUG      — vault folder name, e.g. "coulissehair"
  BRAND_FILTER    — ZIP file filter keyword, e.g. "coulisse"
  BRAND_LOCATION  — location label, e.g. "ION Orchard"
"""

import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        config = {
            "brand_name": os.environ.get("BRAND_NAME", "Brand").strip(),
            "brand_slug": os.environ.get("BRAND_SLUG", "brand").strip(),
            "brand_filter": os.environ.get("BRAND_FILTER", "").strip(),
            "brand_location": os.environ.get("BRAND_LOCATION", "").strip(),
        }
        body = json.dumps(config).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
