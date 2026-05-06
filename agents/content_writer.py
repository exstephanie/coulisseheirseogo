"""
Content Writer Agent — Writes a blog post using real business data.

Single Claude call that weaves real customer reviews and service details
into SEO-optimized content. No pricing in articles. Includes a
6-point quality gate with auto-fix loop (max 3 retries).
"""

import os
import json
import logging
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger("coulissehair.content_writer")

MAX_RETRIES = 3


@dataclass
class QualityResult:
    passed: bool
    failures: list[str]
    word_count: int


class ContentWriter:
    def __init__(self, brand: str = "coulissehair"):
        self.brand = brand
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")

    async def write(self, plan: dict, brand_voice: str = "") -> dict:
        """Write a blog post from a content plan. Returns article dict or error."""
        if not self.api_key:
            return {"error": "ANTHROPIC_API_KEY not set"}

        review_quotes = plan.get("review_quotes", [])
        services_data = plan.get("services_data", [])

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"Writing article (attempt {attempt}/{MAX_RETRIES})...")

            prompt = self._build_prompt(plan, review_quotes, services_data, brand_voice)

            try:
                html = await self._call_claude(prompt)
            except aiohttp.ClientError as e:
                logger.error(f"Claude API error on attempt {attempt}: {e}")
                if attempt == MAX_RETRIES:
                    return {"error": f"Claude API failed after {MAX_RETRIES} attempts: {e}"}
                continue

            # Run quality gate
            quality = self._quality_check(html, plan, review_quotes)

            if quality.passed:
                logger.info(f"Quality gate PASSED (attempt {attempt}, {quality.word_count} words)")
                meta_desc = plan.get("meta_description", "")
                return {
                    "html": html,
                    "title": plan.get("title", ""),
                    "target_keyword": plan.get("target_keyword", ""),
                    "meta_description": meta_desc,
                    "word_count": quality.word_count,
                    "attempts": attempt,
                    "quality_passed": True,
                }

            logger.warning(
                f"Quality gate FAILED (attempt {attempt}): {', '.join(quality.failures)}"
            )

            if attempt < MAX_RETRIES:
                # Build fix prompt for next attempt
                plan["_fix_instructions"] = (
                    f"The previous article failed quality checks: {', '.join(quality.failures)}. "
                    f"Please fix these specific issues in the next version."
                )

        # All retries exhausted
        logger.error(f"Quality gate failed after {MAX_RETRIES} attempts")
        return {
            "html": html,
            "title": plan.get("title", ""),
            "target_keyword": plan.get("target_keyword", ""),
            "meta_description": plan.get("meta_description", ""),
            "word_count": quality.word_count,
            "attempts": MAX_RETRIES,
            "quality_passed": False,
            "quality_failures": quality.failures,
            "needs_manual_review": True,
        }

    def _build_prompt(self, plan: dict, reviews: list, services: list, brand_voice: str) -> str:
        """Build the article generation prompt."""
        review_block = ""
        if reviews:
            review_block = "REAL CUSTOMER REVIEWS TO QUOTE (use these verbatim with attribution):\n"
            for i, r in enumerate(reviews, 1):
                review_block += f'{i}. [{r["rating"]}★] "{r["text"]}" — {r["reviewer"]}\n'

        service_block = ""
        if services:
            service_block = "SERVICES TO MENTION (by name only — do NOT include pricing):\n"
            for s in services:
                service_block += f'- {s["name"]}: {s["description"][:80]}\n'

        fix_instructions = plan.get("_fix_instructions", "")
        fix_block = f"\nIMPORTANT FIX REQUIRED:\n{fix_instructions}\n" if fix_instructions else ""

        # Shorten keyword to max 4 words for AIOSEO compatibility
        keyword = plan.get("target_keyword", "")
        keyword_words = keyword.split()
        if len(keyword_words) > 4:
            keyword = " ".join(keyword_words[:4])

        return f"""Write a blog post for Coulisse Heir's website.
This article MUST score 70+ on AIOSEO TruSEO plugin. Follow every rule below.

TITLE: {plan.get("title", "")}
FOCUS KEYPHRASE (max 4 words): {keyword}
OUTLINE:
{chr(10).join(f"- {h}" for h in plan.get("outline", []))}

{review_block}
{service_block}
BRAND VOICE:
{brand_voice[:400]}
{fix_block}
AIOSEO OPTIMIZATION RULES (mandatory):
1. Write 900-1800 words of HTML content
2. Use the EXACT focus keyphrase "{keyword}" in:
   - The very FIRST sentence of the article
   - At least ONE <h2> heading (exact match)
   - Naturally throughout the body (0.5-2% density, roughly every 200 words)
3. Add at least 1 internal link: <a href="https://coulisseheir.com/services/">our services</a> or similar
4. Add at least 1 external link to a credible source (e.g., hair care study, Singapore climate data)
5. Quote at least 2 real customer reviews with attribution (use <blockquote>)
6. Do NOT include any pricing or dollar amounts — focus on the experience and outcome
7. End with a clear call-to-action (book appointment, visit outlet, WhatsApp)

READABILITY RULES (mandatory for AIOSEO score):
8. Keep paragraphs SHORT: under 120 words each. Many should be 2-3 sentences.
9. Keep sentences around 20 words average. Mix short punchy sentences with longer ones.
10. Use ACTIVE voice, not passive. "Our stylists create" not "Styles are created by"
11. Use transition words: "however", "for example", "in addition", "as a result", "meanwhile"
12. Do NOT start consecutive sentences with the same word
13. Add <h2> or <h3> subheadings every 250-300 words

HTML RULES:
14. Use <h2>, <h3>, <p>, <blockquote>, <strong>, <ul>/<li>, <a> tags
15. Do NOT include <h1> (WordPress adds the title as H1)
16. Do NOT wrap in <html>, <head>, or <body> tags
17. Add alt text to any <img> tags that includes the focus keyphrase

Return ONLY the HTML content, no markdown, no code fences."""

    def _quality_check(self, html: str, plan: dict, reviews: list) -> QualityResult:
        """Quality gate aligned with AIOSEO TruSEO scoring criteria."""
        import re
        failures = []
        html_lower = html.lower()
        word_count = len(html.split())

        # Shorten keyword to max 4 words (AIOSEO requirement)
        keyword = plan.get("target_keyword", "").lower()
        keyword_words = keyword.split()
        if len(keyword_words) > 4:
            keyword = " ".join(keyword_words[:4])

        # --- CONTENT LENGTH ---
        if word_count < 900:
            failures.append(f"Too short: {word_count} words (minimum 900)")
        elif word_count > 2500:
            failures.append(f"Too long: {word_count} words (maximum 2000)")

        # --- KEYPHRASE CHECKS (AIOSEO Basic SEO) ---
        if keyword:
            # Keyphrase in first paragraph
            first_p_end = html_lower.find("</p>")
            if first_p_end > 0 and keyword not in html_lower[:first_p_end]:
                failures.append(f"Keyphrase '{keyword}' missing from first paragraph")

            # Keyphrase in at least 1 H2 subheading
            h2_matches = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.IGNORECASE)
            keyword_in_h2 = sum(1 for h in h2_matches if keyword in h.lower())
            if keyword_in_h2 < 1:
                failures.append(f"Keyphrase not in any H2 heading (need at least 1)")

            # Keyphrase density (0.5% - 2.5%)
            keyword_count = html_lower.count(keyword)
            if word_count > 0:
                density = (keyword_count * len(keyword.split())) / word_count * 100
                if density < 0.5:
                    failures.append(f"Keyphrase density too low ({density:.1f}%, need 0.5-2.5%)")
                elif density > 2.5:
                    failures.append(f"Keyphrase density too high ({density:.1f}%, need 0.5-2.5%)")

        # --- LINKS (AIOSEO Basic SEO) ---
        internal_links = len(re.findall(r'<a[^>]+href=["\']https?://coulissehair\.com\.sg', html, re.IGNORECASE))
        if internal_links < 1:
            failures.append("No internal link to coulisseheir.com (need at least 1)")

        external_links = len(re.findall(r'<a[^>]+href=["\']https?://', html, re.IGNORECASE)) - internal_links
        if external_links < 1:
            failures.append("No external link (need at least 1 credible external source)")

        # --- READABILITY (AIOSEO Readability) ---
        # Subheading distribution: H2/H3 every ~300 words
        headings = re.findall(r"<h[23][^>]*>", html, re.IGNORECASE)
        if word_count > 300 and len(headings) < (word_count // 350):
            failures.append(f"Need more subheadings ({len(headings)} found, need ~{word_count // 300})")

        # Paragraph length check: no paragraph over 120 words
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL)
        long_paras = [len(p.split()) for p in paragraphs if len(p.split()) > 120]
        if long_paras:
            failures.append(f"{len(long_paras)} paragraph(s) over 120 words (AIOSEO readability)")

        # --- CONTENT QUALITY ---
        # Review quotes present
        if reviews:
            blockquote_count = html_lower.count("<blockquote")
            min_quotes = min(2, len(reviews))
            if blockquote_count < min_quotes:
                failures.append(f"Only {blockquote_count}/{min_quotes} review quotes")

        # Pricing must NOT appear
        if "$" in html or "SGD" in html:
            failures.append("Pricing found in article — remove all dollar amounts and SGD references")

        # CTA present
        cta_signals = ["book", "appointment", "visit", "call", "whatsapp", "contact"]
        if not any(signal in html_lower for signal in cta_signals):
            failures.append("No call-to-action found")

        return QualityResult(
            passed=len(failures) == 0,
            failures=failures,
            word_count=word_count,
        )

    async def _call_claude(self, prompt: str) -> str:
        """Make a single Claude API call for content generation."""
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
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise aiohttp.ClientError(f"Claude API {resp.status}: {error[:200]}")
                data = await resp.json()
                return data["content"][0]["text"].strip()
