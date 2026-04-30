"""
gbp_agent.py — Google Business Profile Post Agent

Writes and publishes 2 posts per week across all 3 Coulisse Heir outlets.
Posts are tailored per location (not copy-paste identical) and rotated
through 3 types: What's New, Offer, Event.

Schedule: Tuesday + Friday (aligned with WP posting days)

Outlets:
  - Jurong Point (#02-20F) — west side, HDB heartland, families + workers
  - Pasir Ris Mall (#B1-16) — east side, family-oriented, community feel
  - Junction 8 Bishan (#02-31) — central, mixed demographic, professionals

Flow:
  1. Council selects post type + topic for the week
  2. GBPAgent writes 3 localised versions (one per outlet)
  3. Posts go through same WhatsApp YES/NO approval gate
  4. YES → published to all 3 GBP listings via API simultaneously
  5. NO  → saved to report for manual posting

GBP API access required: https://developers.google.com/my-business
OAuth2 credentials (not service account — GBP requires user-level OAuth).
"""

import os
import json
import aiohttp
import asyncio
from datetime import datetime, date
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow


# ── Outlet definitions ─────────────────────────────────────────────────────────
OUTLETS = [
    {
        "name": "Jurong Point",
        "location_name": "Coulisse Heir Jurong Point",
        "location_id_env": "GBP_LOCATION_ID_JURONG",
        "address": "1 Jurong West Central 2, #02-20F, Singapore 648886",
        "personality": "heartland HDB community, young families, working adults commuting via Jurong East MRT",
        "local_hook": "Jurong Point shoppers and Jurong East MRT commuters",
    },
    {
        "name": "Pasir Ris",
        "location_name": "Coulisse Heir Pasir Ris Mall",
        "location_id_env": "GBP_LOCATION_ID_PASIRRIS",
        "address": "7 Pasir Ris Central, #B1-16, Singapore 519612",
        "personality": "family-oriented east side community, relaxed pace, residents near Downtown East",
        "local_hook": "Pasir Ris and Tampines residents",
    },
    {
        "name": "Bishan",
        "location_name": "Coulisse Heir Junction 8 Bishan",
        "location_id_env": "GBP_LOCATION_ID_BISHAN",
        "address": "9 Bishan Place, #02-31, Singapore 579837",
        "personality": "central Singapore, mixed demographic, professionals and young adults near Bishan MRT",
        "local_hook": "Bishan, Ang Mo Kio, and Toa Payoh residents",
    },
]

# Post type rotation — alternates each run
POST_TYPES = ["STANDARD", "OFFER", "EVENT"]

# GBP API scopes
SCOPES = ["https://www.googleapis.com/auth/business.manage"]

# Token file (stores OAuth refresh token after first login)
TOKEN_FILE = "config/gbp_token.json"
CREDENTIALS_FILE = "config/gbp_oauth_credentials.json"

# Posting schedule
POST_DAYS = ["tuesday", "friday"]


class GBPAgent:
    def __init__(self, council_plan: dict, gsc_data: dict):
        self.council_plan = council_plan
        self.gsc_data = gsc_data
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.account_name = os.getenv("GBP_ACCOUNT_NAME", "")  # e.g. accounts/123456789
        self.credentials = None

    # ── Main entry point ───────────────────────────────────────────────────────

    async def run(self) -> dict:
        """
        Generate 2 GBP posts per week for each outlet.
        Returns dict with posts + publish results.
        """
        if not self._should_post_today():
            today = datetime.now().strftime("%A")
            return {
                "skipped": True,
                "reason": f"Today ({today}) is not a GBP posting day (Tue/Fri)",
            }

        # Determine post type for this run
        post_type = self._get_post_type_for_today()

        # Get topic direction from council plan
        topic = self._extract_gbp_topic()
        print(f"   📍 GBP post type: {post_type} | Topic: {topic}")

        # Write localised posts for each outlet
        outlet_posts = []
        for outlet in OUTLETS:
            print(f"   ✍️  Writing post for {outlet['name']}...")
            post = await self._write_post(outlet, post_type, topic)
            if post:
                outlet_posts.append({"outlet": outlet, "post": post})

        return {
            "skipped": False,
            "post_type": post_type,
            "topic": topic,
            "outlet_posts": outlet_posts,
            "post_day": datetime.now().strftime("%A"),
            "ready_to_publish": True,
        }

    async def publish_all(self, outlet_posts: list) -> list:
        """
        Publish approved posts to all 3 GBP listings.
        Called by the WhatsApp webhook after Daniel replies YES.
        """
        self.credentials = self._load_credentials()
        if not self.credentials:
            return [{"error": "GBP OAuth credentials not found. See GBP_SETUP.md"}]

        results = []
        for item in outlet_posts:
            outlet = item["outlet"]
            post_data = item["post"]
            location_id = os.getenv(outlet["location_id_env"], "")

            if not location_id:
                results.append({
                    "outlet": outlet["name"],
                    "success": False,
                    "error": f"Location ID not set. Add {outlet['location_id_env']} to .env",
                })
                continue

            print(f"   📤 Publishing to {outlet['name']}...")
            result = await self._publish_post(location_id, post_data)
            results.append({"outlet": outlet["name"], **result})

        return results

    # ── Content writing ────────────────────────────────────────────────────────

    async def _write_post(self, outlet: dict, post_type: str, topic: str) -> dict | None:
        """Write a single localised GBP post for one outlet."""

        type_instructions = {
            "STANDARD": (
                "A 'What's New' update post. 150-300 characters. "
                "Share a useful hair tip, a seasonal insight, or a service highlight. "
                "End with a soft CTA (no phone numbers — Google rejects posts with phone numbers)."
            ),
            "OFFER": (
                "A promotional offer post. 150-250 characters for the offer text. "
                "Include: what the offer is, who it's for, how to redeem (link only, no phone number). "
                "Add a coupon code if relevant. CTA: 'Book Now'."
            ),
            "EVENT": (
                "An event post. Must include a title (max 58 chars), start date, end date. "
                "150-250 char description. Could be a free consultation day, a treatment demo, "
                "or a seasonal campaign. CTA: 'Learn More' or 'Book'."
            ),
        }

        # Singapore seasonal context
        month = datetime.now().month
        season_context = {
            12: "year-end festive season, people want to look great for CNY prep",
            1: "Chinese New Year approaching — hair treatments in demand",
            2: "post-CNY, people resuming routines",
            6: "school holidays, families have more time",
            7: "Great Singapore Sale season",
        }.get(month, "typical Singapore weather — hot and humid year-round")

        prompt = f"""You write Google Business Profile posts for Coulisse Heir, an anti-frizz hair specialist.

OUTLET: {outlet['location_name']}
ADDRESS: {outlet['address']}
AUDIENCE: {outlet['personality']}
LOCAL HOOK: {outlet['local_hook']}

POST TYPE: {post_type}
INSTRUCTIONS: {type_instructions[post_type]}

THIS WEEK'S TOPIC: {topic}
SEASONAL CONTEXT: {season_context}

HARD RULES (Google will reject posts that break these):
- NO phone numbers anywhere in the post
- NO "call us" CTAs — use booking link or "visit us" instead
- No spam, no false claims
- Booking link: https://coulisseheir.com/book-now/

BRAND VOICE:
- Warm, expert, Singapore-localised
- Reference humidity, HDB life, local context naturally
- Anti-frizz specialist positioning
- Soft and helpful, not pushy

Return ONLY this JSON:
{{
  "summary": "<the post text, ready to publish>",
  "call_to_action": {{
    "action_type": "<BOOK | LEARN_MORE | SIGN_UP | ORDER | SHOP>",
    "url": "https://coulisseheir.com/book-now/"
  }},
  "event_title": "<only for EVENT type, max 58 chars, else null>",
  "event_start": "<only for EVENT type, ISO date e.g. 2025-03-14, else null>",
  "event_end": "<only for EVENT type, ISO date e.g. 2025-03-16, else null>",
  "offer_coupon": "<only for OFFER type, short code e.g. UHAIR20, else null>",
  "offer_terms": "<only for OFFER type, short terms e.g. 'New customers only', else null>",
  "char_count": <integer>,
  "localisation_note": "<one sentence on what makes this version specific to this outlet>"
}}"""

        result = await self._call_claude(prompt, max_tokens=600)
        try:
            clean = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            parsed = json.loads(clean)
            parsed["post_type"] = post_type
            parsed["outlet_name"] = outlet["name"]
            return parsed
        except Exception:
            return None

    def _extract_gbp_topic(self) -> str:
        """Pull the GBP post topic from the council's weekly plan."""
        pdca = self.council_plan.get("pdca_plan", {})
        do_section = pdca.get("do", {})
        gbp_ideas = do_section.get("gbp_post_ideas", [])

        if gbp_ideas:
            # Use the first idea as this week's topic
            return gbp_ideas[0] if isinstance(gbp_ideas[0], str) else str(gbp_ideas[0])

        # Fallback: derive from weekly theme
        plan = pdca.get("plan", {})
        theme = plan.get("week_theme", "")
        focus = plan.get("primary_focus", "")
        if theme:
            return f"{theme} — {focus}" if focus else theme

        # Last fallback: use top quick-win keyword
        quick_wins = self.gsc_data.get("quick_wins", [])
        if quick_wins:
            return quick_wins[0].get("keyword", "anti-frizz hair treatment Singapore")

        return "anti-frizz hair treatment Singapore"

    def _get_post_type_for_today(self) -> str:
        """
        Rotate post types:
        - Tuesday = STANDARD (What's New) or EVENT
        - Friday = OFFER or STANDARD
        Alternates weekly using week number.
        """
        week_num = date.today().isocalendar()[1]
        day = datetime.now().strftime("%A").lower()

        if day == "tuesday":
            return "EVENT" if week_num % 2 == 0 else "STANDARD"
        else:  # Friday
            return "OFFER" if week_num % 3 == 0 else "STANDARD"

    def _should_post_today(self) -> bool:
        today = datetime.now().strftime("%A").lower()
        return today in POST_DAYS

    # ── GBP API publishing ─────────────────────────────────────────────────────

    async def _publish_post(self, location_id: str, post_data: dict) -> dict:
        """
        Publish a single post to a GBP location via the API.
        Endpoint: POST /v4/{location_name}/localPosts
        """
        if not self.credentials or not self.account_name:
            return {"success": False, "error": "Not authenticated"}

        url = f"https://mybusiness.googleapis.com/v4/{self.account_name}/locations/{location_id}/localPosts"

        payload = self._build_api_payload(post_data)

        headers = {
            "Authorization": f"Bearer {self.credentials.token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    result = await resp.json()
                    if resp.status in (200, 201):
                        return {
                            "success": True,
                            "post_name": result.get("name", ""),
                            "state": result.get("state", ""),
                            "search_url": result.get("searchUrl", ""),
                        }
                    else:
                        error_msg = result.get("error", {}).get("message", f"HTTP {resp.status}")
                        return {"success": False, "error": error_msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _build_api_payload(self, post_data: dict) -> dict:
        """Convert our post dict into the GBP API payload format."""
        post_type = post_data.get("post_type", "STANDARD")
        summary = post_data.get("summary", "")
        cta = post_data.get("call_to_action", {})

        payload = {
            "languageCode": "en-US",
            "summary": summary,
            "callToAction": {
                "actionType": cta.get("action_type", "BOOK"),
                "url": cta.get("url", "https://coulisseheir.com/book-now/"),
            },
        }

        if post_type == "OFFER":
            payload["topicType"] = "OFFER"
            if post_data.get("offer_coupon"):
                payload["offer"] = {
                    "couponCode": post_data["offer_coupon"],
                    "redeemOnlineUrl": "https://coulisseheir.com/book-now/",
                    "termsConditions": post_data.get("offer_terms", ""),
                }

        elif post_type == "EVENT":
            payload["topicType"] = "EVENT"
            if post_data.get("event_title"):
                event_start = post_data.get("event_start", date.today().isoformat())
                event_end = post_data.get("event_end", event_start)
                payload["event"] = {
                    "title": post_data["event_title"],
                    "schedule": {
                        "startDate": self._parse_date(event_start),
                        "startTime": {"hours": 10, "minutes": 30},
                        "endDate": self._parse_date(event_end),
                        "endTime": {"hours": 21, "minutes": 0},
                    },
                }

        else:
            payload["topicType"] = "STANDARD"

        return payload

    def _parse_date(self, iso_date: str) -> dict:
        """Convert ISO date string to GBP API date object."""
        try:
            d = date.fromisoformat(iso_date)
            return {"year": d.year, "month": d.month, "day": d.day}
        except Exception:
            today = date.today()
            return {"year": today.year, "month": today.month, "day": today.day}

    # ── OAuth helpers ──────────────────────────────────────────────────────────

    def _load_credentials(self) -> Credentials | None:
        """Load OAuth2 credentials, refreshing if expired."""
        if not os.path.exists(TOKEN_FILE):
            print(f"   ⚠️  GBP token not found at {TOKEN_FILE}. Run: python gbp_auth.py")
            return None

        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save refreshed token
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
            except Exception as e:
                print(f"   ⚠️  Token refresh failed: {e}. Re-run: python gbp_auth.py")
                return None

        return creds

    # ── Claude API ─────────────────────────────────────────────────────────────

    async def _call_claude(self, prompt: str, max_tokens: int = 600) -> str:
        if not self.api_key:
            return "{}"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=body,
                ) as resp:
                    data = await resp.json()
                    return data["content"][0]["text"]
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'
