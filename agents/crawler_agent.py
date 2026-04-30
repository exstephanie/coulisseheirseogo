"""
Crawler Agent — Audits coulisseheir.com for on-page SEO issues.
Checks meta titles, descriptions, H1s, image alt text, internal links, schema.
"""

import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


class CrawlerAgent:
    def __init__(self, site_url: str, max_pages: int = 20):
        self.site_url = site_url.rstrip("/")
        self.max_pages = max_pages
        self.visited = set()
        self.pages_data = []
        self.redirects = []

    async def run(self) -> dict:
        """Crawl the site and return SEO audit results."""
        try:
            async with aiohttp.ClientSession(
                headers={"User-Agent": "UHairSEOBot/1.0 (SEO Audit)"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as session:
                await self._crawl_page(session, self.site_url)

            # Check for llms.txt
            llms_txt_exists = False
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"{self.site_url}/llms.txt") as r:
                        llms_txt_exists = r.status == 200
            except Exception:
                pass

            issues = self._analyse_issues()
            if not llms_txt_exists:
                issues["missing_llms_txt"] = True
            if self.redirects:
                issues["permanent_redirects"] = self.redirects
            return {
                "pages_crawled": len(self.pages_data),
                "issues": issues,
                "pages": self.pages_data,
                "score": self._calculate_score(issues),
                "redirects": self.redirects,
                "llms_txt": llms_txt_exists,
            }
        except Exception as e:
            return {"error": str(e), "pages_crawled": 0, "issues": {}, "pages": [], "score": 0}

    async def _crawl_page(self, session, url: str, depth: int = 0):
        """Recursively crawl pages up to max_pages."""
        if url in self.visited or len(self.visited) >= self.max_pages:
            return
        if not url.startswith(self.site_url):
            return

        self.visited.add(url)

        try:
            async with session.get(url, allow_redirects=False) as check_resp:
                if check_resp.status in (301, 302):
                    location = check_resp.headers.get("Location", "")
                    self.redirects.append({"from": url, "to": location, "status": check_resp.status})

            async with session.get(url) as response:
                if response.content_type and "html" not in response.content_type:
                    return

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                page_data = self._extract_seo_data(url, soup, response.status)
                self.pages_data.append(page_data)

                # Only follow links from first 2 levels
                if depth < 2:
                    links = self._extract_internal_links(soup, url)
                    tasks = [self._crawl_page(session, link, depth + 1) for link in links]
                    await asyncio.gather(*tasks, return_exceptions=True)

        except Exception:
            pass

    def _extract_seo_data(self, url: str, soup: BeautifulSoup, status: int) -> dict:
        """Extract all SEO-relevant data from a page."""
        # Meta title
        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else ""

        # Meta description
        meta_desc = soup.find("meta", {"name": "description"})
        description = meta_desc.get("content", "").strip() if meta_desc else ""

        # H1 tags
        h1s = [h.get_text().strip() for h in soup.find_all("h1")]

        # H2 tags
        h2s = [h.get_text().strip() for h in soup.find_all("h2")]

        # Images without alt text
        images = soup.find_all("img")
        images_missing_alt = [
            img.get("src", "")[:80]
            for img in images
            if not img.get("alt") or img.get("alt", "").strip() == ""
        ]

        # Canonical tag
        canonical = soup.find("link", {"rel": "canonical"})
        canonical_url = canonical.get("href", "") if canonical else ""

        # Schema markup
        schema_tags = soup.find_all("script", {"type": "application/ld+json"})
        has_schema = len(schema_tags) > 0

        # Word count (approximate)
        body = soup.find("body")
        text = body.get_text(separator=" ") if body else ""
        word_count = len(re.findall(r"\w+", text))

        # Internal links count
        internal_links = self._extract_internal_links(soup, url)

        # Empty anchor text links
        empty_anchor_links = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            has_img = a.find("img")
            if not text and not has_img:
                empty_anchor_links.append(a["href"][:100])

        # Text-to-HTML ratio
        html_length = len(str(soup))
        text_length = len(text)
        text_html_ratio = round(text_length / html_length * 100, 1) if html_length > 0 else 0

        # Semantic HTML check (counts of semantic elements)
        semantic_tags = ["article", "section", "nav", "aside", "header", "footer", "main"]
        semantic_count = sum(len(soup.find_all(tag)) for tag in semantic_tags)

        # Incoming internal links (populated later in _analyse_issues)
        # Check for unminified JS/CSS
        scripts = soup.find_all("script", src=True)
        styles = soup.find_all("link", rel="stylesheet")
        unminified_js = [s["src"] for s in scripts if ".min." not in s.get("src", "")]
        unminified_css = [s["href"] for s in styles if ".min." not in s.get("href", "")]

        return {
            "url": url,
            "status": status,
            "title": title,
            "title_length": len(title),
            "description": description,
            "description_length": len(description),
            "h1s": h1s,
            "h2s": h2s[:5],
            "images_total": len(images),
            "images_no_alt": len(images_missing_alt),
            "images_missing_alt": images_missing_alt,
            "canonical": canonical_url,
            "has_schema": has_schema,
            "word_count": word_count,
            "internal_links": len(internal_links),
            "internal_links_count": len(internal_links),
            "empty_anchor_links": empty_anchor_links,
            "text_html_ratio": text_html_ratio,
            "semantic_count": semantic_count,
            "unminified_js": len(unminified_js),
            "unminified_css": len(unminified_css),
        }

    def _extract_internal_links(self, soup: BeautifulSoup, current_url: str) -> list:
        """Extract all internal links from a page."""
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(current_url, href)
            parsed = urlparse(full_url)
            # Keep only same-domain, no fragments/query strings
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            if clean_url.startswith(self.site_url) and clean_url not in self.visited:
                links.append(clean_url)
        return list(set(links))

    def _analyse_issues(self) -> dict:
        """Categorise all issues found across pages."""
        issues = {
            "missing_title": [],
            "title_too_long": [],      # >60 chars
            "title_too_short": [],     # <30 chars
            "missing_description": [],
            "description_too_long": [], # >160 chars
            "description_too_short": [], # <70 chars
            "missing_h1": [],
            "multiple_h1": [],
            "images_missing_alt": [],
            "missing_schema": [],
            "thin_content": [],        # <300 words
            "missing_canonical": [],
            "empty_anchor_links": [],
            "low_text_html_ratio": [],   # <10%
            "low_semantic_html": [],     # no semantic tags
            "unminified_assets": [],     # unminified JS/CSS
            "low_internal_links": [],    # only 1 incoming internal link
        }

        # Count incoming internal links per URL
        incoming_links = {}
        for page in self.pages_data:
            for a_url in self._extract_internal_links(
                BeautifulSoup(f"<div></div>", "html.parser"), page["url"]
            ):
                pass  # placeholder
        # Build incoming link count from crawled data
        all_urls = {p["url"] for p in self.pages_data}
        incoming_count = {url: 0 for url in all_urls}
        for page in self.pages_data:
            # Re-count links pointing to other crawled pages
            for other_url in all_urls:
                if other_url != page["url"] and other_url in str(page.get("_raw_links", [])):
                    incoming_count[other_url] = incoming_count.get(other_url, 0) + 1

        for page in self.pages_data:
            url = page["url"]

            if not page["title"]:
                issues["missing_title"].append(url)
            elif page["title_length"] > 60:
                issues["title_too_long"].append({"url": url, "title": page["title"], "length": page["title_length"]})
            elif page["title_length"] < 30:
                issues["title_too_short"].append({"url": url, "title": page["title"], "length": page["title_length"]})

            if not page["description"]:
                issues["missing_description"].append(url)
            elif page["description_length"] > 160:
                issues["description_too_long"].append({"url": url, "length": page["description_length"]})
            elif page["description_length"] < 70:
                issues["description_too_short"].append({"url": url, "length": page["description_length"]})

            if not page["h1s"]:
                issues["missing_h1"].append(url)
            elif len(page["h1s"]) > 1:
                issues["multiple_h1"].append({"url": url, "h1s": page["h1s"]})

            if page["images_missing_alt"]:
                issues["images_missing_alt"].append({
                    "url": url,
                    "count": len(page["images_missing_alt"]),
                    "examples": page["images_missing_alt"][:3],
                })

            if not page["has_schema"]:
                issues["missing_schema"].append(url)

            if page["word_count"] < 300:
                issues["thin_content"].append({"url": url, "word_count": page["word_count"]})

            if not page["canonical"]:
                issues["missing_canonical"].append(url)

            # New checks matching SEMrush
            if page.get("empty_anchor_links"):
                issues["empty_anchor_links"].append({
                    "url": url,
                    "count": len(page["empty_anchor_links"]),
                    "examples": page["empty_anchor_links"][:3],
                })

            if page.get("text_html_ratio", 100) < 10:
                issues["low_text_html_ratio"].append({
                    "url": url,
                    "ratio": page["text_html_ratio"],
                })

            if page.get("semantic_count", 0) == 0:
                issues["low_semantic_html"].append(url)

            unminified = page.get("unminified_js", 0) + page.get("unminified_css", 0)
            if unminified > 0:
                issues["unminified_assets"].append({
                    "url": url,
                    "count": unminified,
                })

            if page.get("internal_links_count", 0) <= 1 and url != self.site_url:
                issues["low_internal_links"].append(url)

        return issues

    def _calculate_score(self, issues: dict) -> int:
        """Calculate overall SEO score (0-100)."""
        if not self.pages_data:
            return 0

        total_pages = len(self.pages_data)
        deductions = 0

        weights = {
            "missing_title": 15,
            "missing_description": 10,
            "missing_h1": 10,
            "multiple_h1": 5,
            "images_missing_alt": 8,
            "missing_schema": 8,
            "thin_content": 7,
            "title_too_long": 5,
            "description_too_long": 5,
            "title_too_short": 5,
            "description_too_short": 5,
            "missing_canonical": 7,
            "empty_anchor_links": 5,
            "low_text_html_ratio": 6,
            "low_semantic_html": 4,
            "unminified_assets": 5,
            "low_internal_links": 5,
        }

        for issue_type, weight in weights.items():
            issue_count = len(issues.get(issue_type, []))
            ratio = min(issue_count / total_pages, 1.0)
            deductions += weight * ratio

        return max(0, round(100 - deductions))
