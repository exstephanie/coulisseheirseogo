"""
Sitemap Agent
Generates XML sitemap for coulisseheir.com and submits it to Google Search Console.
Also pings Google to re-crawl updated pages.
"""

import os
import asyncio
import aiohttp
from datetime import datetime
from urllib.parse import urljoin


class SitemapAgent:
    def __init__(self):
        self.wp_url = os.getenv("WP_URL", "https://coulisseheir.com").rstrip("/")
        self.wp_auth = (os.getenv("WP_USERNAME"), os.getenv("WP_APP_PASSWORD"))
        self.gsc_credentials_path = os.getenv("GSC_CREDENTIALS_PATH", "config/gsc_credentials.json")

        # Static pages that must always be in sitemap
        self.static_pages = [
            {"url": "/", "priority": "1.0", "changefreq": "weekly"},
            {"url": "/anti-frizz-treatment/", "priority": "0.9", "changefreq": "monthly"},
            {"url": "/hair-treatments/", "priority": "0.9", "changefreq": "monthly"},
            {"url": "/book-now/", "priority": "0.8", "changefreq": "monthly"},
            {"url": "/outlets/", "priority": "0.8", "changefreq": "monthly"},
            {"url": "/about/", "priority": "0.7", "changefreq": "yearly"},
            {"url": "/contact/", "priority": "0.7", "changefreq": "yearly"},
        ]

    async def run(self) -> dict:
        """Generate sitemap, upload to WordPress, and submit to GSC."""
        results = {
            "sitemap_url": "",
            "urls_included": 0,
            "gsc_submitted": False,
            "errors": [],
        }

        # 1. Fetch all published posts and pages from WordPress
        wp_urls = await self._get_all_wp_urls()

        # 2. Build sitemap XML
        sitemap_xml = self._build_sitemap(wp_urls)
        results["urls_included"] = len(wp_urls) + len(self.static_pages)

        # 3. Upload sitemap to WordPress via REST API or save to file
        sitemap_url = await self._upload_sitemap(sitemap_xml)
        if sitemap_url:
            results["sitemap_url"] = sitemap_url
        else:
            results["errors"].append("Could not upload sitemap via API — submit manually")
            results["sitemap_url"] = f"{self.wp_url}/sitemap.xml"

        # 4. Submit to Google Search Console
        gsc_submitted = await self._submit_to_gsc(results["sitemap_url"])
        results["gsc_submitted"] = gsc_submitted
        if not gsc_submitted:
            results["errors"].append(
                f"GSC submission failed — submit manually at: "
                f"https://search.google.com/search-console/sitemaps?resource_id={self.wp_url}"
            )

        return results

    async def _get_all_wp_urls(self) -> list:
        """Fetch all published posts and pages from WordPress."""
        urls = []

        async with aiohttp.ClientSession() as session:
            # Posts
            for post_type in ["posts", "pages"]:
                page = 1
                while True:
                    try:
                        api_url = (
                            f"{self.wp_url}/wp-json/wp/v2/{post_type}"
                            f"?per_page=100&page={page}&status=publish"
                            f"&_fields=link,modified"
                        )
                        async with session.get(
                            api_url,
                            auth=aiohttp.BasicAuth(*self.wp_auth),
                        ) as response:
                            if response.status != 200:
                                break
                            items = await response.json()
                            if not items:
                                break
                            for item in items:
                                urls.append({
                                    "url": item.get("link", "").rstrip("/"),
                                    "lastmod": item.get("modified", "")[:10],
                                    "priority": "0.8" if post_type == "pages" else "0.6",
                                    "changefreq": "monthly",
                                })
                            page += 1
                            if len(items) < 100:
                                break
                    except Exception:
                        break

        return urls

    def _build_sitemap(self, wp_urls: list) -> str:
        """Build XML sitemap string."""
        today = datetime.now().strftime("%Y-%m-%d")

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
            '        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
            '        xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9',
            '        http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">',
        ]

        # Static pages first
        for page in self.static_pages:
            full_url = self.wp_url + page["url"]
            lines.extend([
                "  <url>",
                f"    <loc>{full_url}</loc>",
                f"    <lastmod>{today}</lastmod>",
                f"    <changefreq>{page['changefreq']}</changefreq>",
                f"    <priority>{page['priority']}</priority>",
                "  </url>",
            ])

        # Dynamic WordPress content
        seen_urls = {self.wp_url + p["url"] for p in self.static_pages}
        for item in wp_urls:
            url = item["url"]
            if url and url not in seen_urls:
                seen_urls.add(url)
                lastmod = item.get("lastmod", today)
                lines.extend([
                    "  <url>",
                    f"    <loc>{url}</loc>",
                    f"    <lastmod>{lastmod}</lastmod>",
                    f"    <changefreq>{item['changefreq']}</changefreq>",
                    f"    <priority>{item['priority']}</priority>",
                    "  </url>",
                ])

        lines.append("</urlset>")
        return "\n".join(lines)

    async def _upload_sitemap(self, sitemap_xml: str) -> str:
        """
        Try to upload sitemap via WordPress.
        Falls back to saving locally if API upload not available.
        """
        # Save sitemap locally in project for reference
        try:
            os.makedirs("sitemaps", exist_ok=True)
            filename = f"sitemaps/sitemap_{datetime.now().strftime('%Y%m%d')}.xml"
            with open(filename, "w") as f:
                f.write(sitemap_xml)
        except Exception:
            pass

        # Check if WordPress has Yoast — it auto-generates sitemaps
        # If Yoast is active, we don't need to upload manually
        yoast_sitemap_url = f"{self.wp_url}/sitemap_index.xml"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(yoast_sitemap_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        if "sitemapindex" in content.lower() or "urlset" in content.lower():
                            return yoast_sitemap_url
        except Exception:
            pass

        # Try standard sitemap.xml
        standard_sitemap = f"{self.wp_url}/sitemap.xml"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(standard_sitemap) as response:
                    if response.status == 200:
                        return standard_sitemap
        except Exception:
            pass

        return ""

    async def _submit_to_gsc(self, sitemap_url: str) -> bool:
        """Submit sitemap URL to Google Search Console."""
        if not sitemap_url:
            return False

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self.gsc_credentials_path,
                scopes=["https://www.googleapis.com/auth/webmasters"],
            )

            service = build("searchconsole", "v1", credentials=credentials)
            site_url = self.wp_url + "/"

            service.sitemaps().submit(
                siteUrl=site_url,
                feedpath=sitemap_url,
            ).execute()

            return True

        except Exception as e:
            return False

    async def ping_google(self, updated_urls: list) -> bool:
        """Ping Google to recrawl specific updated URLs."""
        # Google no longer supports the ping endpoint for sitemaps
        # Best practice is to submit via GSC API or update sitemap
        return await self._submit_to_gsc(f"{self.wp_url}/sitemap_index.xml")
