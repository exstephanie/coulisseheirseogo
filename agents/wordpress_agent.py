"""
wordpress_agent.py — WordPress REST API Publisher v3

Simplified publisher. Receives finished HTML from the content writer agent
and posts it as a draft via the WP REST API. Email approval triggers
publish_post() to flip the draft to published.

No content generation, no council review, no day-of-week scheduling.
"""

import json
import logging
import os
import base64

import aiohttp

logger = logging.getLogger("coulissehair.publisher")


class Publisher:
    """Publish pre-written HTML to WordPress as a draft."""

    def __init__(self) -> None:
        self.wp_url = os.getenv("WP_URL", "https://coulisseheir.com").rstrip("/")
        self.wp_username = os.getenv("WP_USERNAME", "")
        self.wp_app_password = os.getenv("WP_APP_PASSWORD", "")
        self.pexels_api_key = os.getenv("PEXELS_API_KEY", "")
        self.api_url = f"{self.wp_url}/wp-json/wp/v2"

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.wp_username}:{self.wp_app_password}".encode()
        ).decode()
        return f"Basic {token}"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def publish(
        self,
        title: str,
        html: str,
        meta_description: str = "",
        target_keyword: str = "",
        status: str = "draft",
    ) -> dict:
        """Create a WordPress post with the supplied content.

        status: 'draft' (default, for weekly pipeline) or 'publish' (for approved posts).
        Returns a result dict with post ID, edit URL, and featured-image status.
        """
        if not self.wp_username or not self.wp_app_password:
            return {"skipped": True, "reason": "WP credentials not configured."}
        if not html:
            return {"skipped": True, "reason": "No HTML content provided."}

        # Duplicate guard — exact title match across all statuses
        existing = await self._find_duplicate(title)
        if existing:
            existing_title = existing.get("title", {}).get("rendered", "")
            return {
                "skipped": True,
                "reason": (
                    f"Duplicate post found: '{existing_title}' "
                    f"(ID: {existing['id']}, status: {existing.get('status')})"
                ),
                "existing_post": {
                    "id": existing["id"],
                    "title": existing_title,
                    "status": existing.get("status"),
                    "link": existing.get("link"),
                    "edit_url": f"{self.wp_url}/wp-admin/post.php?post={existing['id']}&action=edit",
                },
            }

        category_id = await self._get_or_create_category("Hair Tips & Advice")

        post_result = await self._post_to_wordpress(
            title=title,
            content=html,
            excerpt=meta_description,
            category_id=category_id,
            focus_keyword=target_keyword,
            meta_description=meta_description,
            status=status,
        )

        featured_image_ok = post_result.get("featured_image", {}).get("set", False)
        return {
            "skipped": False,
            "post_status": "draft",
            "title": title,
            "keyword": target_keyword,
            "word_count": len(html.split()),
            "featured_image_set": featured_image_ok,
            "wp_result": post_result,
        }

    async def publish_post(self, post_id: int) -> dict:
        """Flip a draft to 'publish' status (called after email approval)."""
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/posts/{post_id}",
                    headers=headers,
                    json={"status": "publish"},
                ) as resp:
                    result = await resp.json(content_type=None)
                    if resp.status == 200:
                        logger.info("Post %d published successfully", post_id)
                        return {
                            "success": True,
                            "post_id": post_id,
                            "post_url": result.get("link"),
                            "status": result.get("status"),
                        }
                    error_msg = result.get("message", "") or str(result)[:200]
                    logger.error("Failed to publish post %d: %s", post_id, error_msg)
                    return {"success": False, "post_id": post_id, "error": error_msg}
        except aiohttp.ClientError as exc:
            logger.error("Network error publishing post %d: %s", post_id, exc)
            return {"success": False, "post_id": post_id, "error": str(exc)}

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    async def _find_duplicate(self, title: str) -> dict | None:
        """Return the first existing post with an identical title, or None."""
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }
        all_posts: list[dict] = []
        try:
            async with aiohttp.ClientSession() as session:
                for status in ("publish", "draft", "pending", "private"):
                    async with session.get(
                        f"{self.api_url}/posts",
                        headers=headers,
                        params={"status": status, "per_page": 50},
                    ) as resp:
                        if resp.status == 200:
                            all_posts.extend(await resp.json(content_type=None))
        except aiohttp.ClientError as exc:
            logger.warning("Duplicate check failed (%s) — proceeding with publish", exc)
            return None

        new_title_lower = title.strip().lower()
        for post in all_posts:
            existing_title = post.get("title", {}).get("rendered", "").strip()
            if existing_title.lower() == new_title_lower:
                logger.warning(
                    "Duplicate title: '%s' (ID: %s, %s)",
                    existing_title,
                    post.get("id"),
                    post.get("status"),
                )
                return post
        return None

    # ------------------------------------------------------------------
    # Category helper
    # ------------------------------------------------------------------

    async def _get_or_create_category(self, name: str) -> int | None:
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/categories",
                    headers=headers,
                    params={"search": name, "per_page": 5},
                ) as resp:
                    if resp.status == 200:
                        for cat in await resp.json(content_type=None):
                            if cat.get("name", "").lower() == name.lower():
                                return cat["id"]
                async with session.post(
                    f"{self.api_url}/categories",
                    headers=headers,
                    json={"name": name, "slug": name.lower().replace(" ", "-")},
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json(content_type=None)
                        return data.get("id")
                    logger.warning("Failed to create category '%s': HTTP %d", name, resp.status)
        except aiohttp.ClientError as exc:
            logger.warning("Category lookup/create failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Core WP poster
    # ------------------------------------------------------------------

    async def _post_to_wordpress(
        self,
        title: str,
        content: str,
        excerpt: str,
        category_id: int | None,
        focus_keyword: str = "",
        meta_description: str = "",
        status: str = "draft",
    ) -> dict:
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }
        payload: dict = {
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": status,
            "format": "standard",
        }
        if category_id:
            payload["categories"] = [category_id]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/posts", headers=headers, json=payload
                ) as resp:
                    resp_text = await resp.text()
                    try:
                        result = json.loads(resp_text)
                    except json.JSONDecodeError:
                        logger.error("WP returned non-JSON (%d): %s", resp.status, resp_text[:200])
                        return {"success": False, "error": f"WP returned HTTP {resp.status} (non-JSON response, likely rate limit)"}
                    if resp.status not in (200, 201):
                        error_msg = result.get("message", "") or str(result)[:200]
                        logger.error("WP API error (%d): %s", resp.status, error_msg)
                        return {"success": False, "error": error_msg}

                    post_id = result.get("id")
                    logger.info("Draft created: '%s' (ID: %d)", title, post_id)

                    # Featured image from Pexels
                    media_id = None
                    image_error = None
                    try:
                        media_id = await self._fetch_and_upload_image(
                            session, headers, focus_keyword or title, post_id
                        )
                    except aiohttp.ClientError as exc:
                        image_error = str(exc)
                        logger.warning("Featured image failed: %s", exc)

                    if not media_id:
                        logger.warning(
                            "Post %d has no featured image — add one manually in WP", post_id
                        )

                    # Update SEO fields + featured image in one call
                    try:
                        update_payload: dict = {
                            "aioseo_meta_data": {
                                "title": title,
                                "description": meta_description,
                                "keyphrases": {
                                    "focus": {"keyphrase": focus_keyword},
                                },
                            },
                        }
                        if media_id:
                            update_payload["featured_media"] = media_id
                        async with session.post(
                            f"{self.api_url}/posts/{post_id}",
                            headers=headers,
                            json=update_payload,
                        ) as update_resp:
                            if update_resp.status == 200 and media_id:
                                logger.info("Featured image set (media ID: %d)", media_id)
                    except aiohttp.ClientError as exc:
                        logger.warning("SEO/image update failed for post %d: %s", post_id, exc)

                    return {
                        "success": True,
                        "post_id": post_id,
                        "post_url": result.get("link"),
                        "status": result.get("status"),
                        "edit_url": f"{self.wp_url}/wp-admin/post.php?post={post_id}&action=edit",
                        "featured_image": {
                            "set": media_id is not None,
                            "media_id": media_id,
                            "error": image_error,
                        },
                    }
        except aiohttp.ClientError as exc:
            logger.error("WP connection error: %s", exc)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Pexels featured image
    # ------------------------------------------------------------------

    async def _fetch_and_upload_image(
        self,
        session: aiohttp.ClientSession,
        wp_headers: dict,
        keyword: str,
        post_id: int,
    ) -> int | None:
        """Search Pexels for a relevant image, upload to WP media library."""
        if not self.pexels_api_key:
            logger.warning("PEXELS_API_KEY not set — skipping featured image")
            return None

        search_query = f"{keyword} hair salon"
        pexels_headers = {"Authorization": self.pexels_api_key}

        try:
            async with session.get(
                "https://api.pexels.com/v1/search",
                headers=pexels_headers,
                params={"query": search_query, "per_page": 5, "orientation": "landscape"},
            ) as resp:
                if resp.status != 200:
                    logger.warning("Pexels API error: HTTP %d", resp.status)
                    return None
                data = await resp.json(content_type=None)
                photos = data.get("photos", [])

            # Fallback to broader search
            if not photos:
                async with session.get(
                    "https://api.pexels.com/v1/search",
                    headers=pexels_headers,
                    params={
                        "query": "hair treatment salon",
                        "per_page": 5,
                        "orientation": "landscape",
                    },
                ) as fallback_resp:
                    if fallback_resp.status == 200:
                        fallback_data = await fallback_resp.json(content_type=None)
                        photos = fallback_data.get("photos", [])
        except aiohttp.ClientError as exc:
            logger.warning("Pexels search failed: %s", exc)
            return None

        if not photos:
            return None

        photo = photos[0]
        image_url = (
            photo.get("src", {}).get("large", "")
            or photo.get("src", {}).get("original", "")
        )
        photographer = photo.get("photographer", "Unknown")
        if not image_url:
            return None

        # Download the image
        try:
            async with session.get(image_url) as img_resp:
                if img_resp.status != 200:
                    return None
                image_data = await img_resp.read()
        except aiohttp.ClientError as exc:
            logger.warning("Image download failed: %s", exc)
            return None

        # Upload to WordPress media library
        slug = keyword.lower().replace(" ", "-")[:50]
        filename = f"{slug}-coulisseheir.jpg"
        alt_text = f"{keyword} at Coulisse Heir"
        caption = f"Photo by {photographer} on Pexels"

        upload_headers = {
            "Authorization": wp_headers["Authorization"],
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "image/jpeg",
        }
        try:
            async with session.post(
                f"{self.api_url}/media",
                headers=upload_headers,
                data=image_data,
            ) as upload_resp:
                if upload_resp.status not in (200, 201):
                    err = await upload_resp.text()
                    logger.warning("WP media upload failed (%d): %s", upload_resp.status, err[:200])
                    return None
                media = await upload_resp.json(content_type=None)
                media_id = media.get("id")
        except aiohttp.ClientError as exc:
            logger.warning("WP media upload error: %s", exc)
            return None

        # Set alt text and caption on the media item
        if media_id:
            try:
                async with session.post(
                    f"{self.api_url}/media/{media_id}",
                    headers=wp_headers,
                    json={
                        "alt_text": alt_text,
                        "caption": caption,
                        "post": post_id,
                    },
                ) as _:
                    pass
            except aiohttp.ClientError as exc:
                logger.warning("Failed to set alt text on media %d: %s", media_id, exc)

        return media_id
