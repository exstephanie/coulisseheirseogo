"""
Coulisse Heir SEO Agent v3 — Review-Driven Content Engine

Sequential pipeline orchestrator. Replaces the 15+ agent v2 system
with a focused 5-agent pipeline using real customer review data.

Pipeline: Data Collector → Content Planner → Content Writer → Publisher → GBP
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Structured logging setup ──────────────────────────────────────────────────

LOG_FORMAT = json.dumps({
    "time": "%(asctime)s",
    "agent": "%(name)s",
    "level": "%(levelname)s",
    "msg": "%(message)s",
})


def setup_logging():
    """Configure structured JSON logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        fmt='{"time":"%(asctime)s","agent":"%(name)s","level":"%(levelname)s","msg":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


logger = logging.getLogger("coulissehair.orchestrator")


# ── Configuration ─────────────────────────────────────────────────────────────

BRAND = os.getenv("BRAND", "coulissehair")
SITE_URL = os.getenv("SITE_URL", "https://coulisseheir.com/")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "")


# ── Pipeline steps ────────────────────────────────────────────────────────────

async def step_collect_data() -> dict:
    """Step 1: Collect reviews, cluster them, pull GSC data."""
    from agents.data_collector import DataCollector

    logger.info("Step 1/5: Collecting data (reviews + GSC)")
    collector = DataCollector(brand=BRAND, site_url=SITE_URL)
    result = await collector.run()

    # Log staleness warnings
    for warning in result.get("staleness", {}).get("warnings", []):
        logger.warning(f"Vault: {warning}")

    reviews_info = result.get("reviews", {})
    gsc_info = result.get("gsc", {})
    logger.info(
        f"Data collected: {reviews_info.get('total', 0)} reviews, "
        f"GSC clicks={gsc_info.get('summary', {}).get('total_clicks', '?')}"
    )

    # Cache GSC data to vault for dashboard
    vault_dir = Path(f"vault/{BRAND}")
    if "error" not in gsc_info:
        gsc_cache = vault_dir / "gsc_data.json"
        gsc_cache.parent.mkdir(parents=True, exist_ok=True)
        gsc_cache.write_text(json.dumps(gsc_info, indent=2), encoding="utf-8")

    return result


async def step_plan_content(gsc_data: dict) -> dict:
    """Step 2: Select this week's topic using review clusters + GSC data."""
    from agents.content_planner import ContentPlanner

    logger.info("Step 2/5: Planning content (topic selection)")
    planner = ContentPlanner(brand=BRAND, gsc_data=gsc_data)
    plan = await planner.plan()

    if plan.get("fallback"):
        logger.warning("Using fallback topic (no review data or GSC data available)")
    else:
        logger.info(f"Topic selected: '{plan.get('title', '?')}' | keyword: {plan.get('target_keyword', '?')}")

    return plan


async def step_write_content(plan: dict) -> dict:
    """Step 3: Write article using real reviews, pricing, and brand voice."""
    from agents.content_writer import ContentWriter

    logger.info("Step 3/5: Writing article")

    # Load brand voice
    brand_voice_path = Path(f"vault/{BRAND}/brand_voice.md")
    brand_voice = brand_voice_path.read_text(encoding="utf-8") if brand_voice_path.exists() else ""

    writer = ContentWriter(brand=BRAND)
    article = await writer.write(plan, brand_voice)

    if article.get("error"):
        logger.error(f"Content writing failed: {article['error']}")
        return article

    if article.get("needs_manual_review"):
        logger.warning(
            f"Quality gate failed after {article.get('attempts', '?')} attempts. "
            f"Failures: {', '.join(article.get('quality_failures', []))}"
        )
    else:
        logger.info(
            f"Article written: {article.get('word_count', '?')} words, "
            f"passed quality gate on attempt {article.get('attempts', '?')}"
        )

    return article


async def step_save_and_notify(article: dict) -> dict:
    """Step 4: Save article locally and send email for approval.

    WordPress is NOT called here. The article is saved to vault/
    as a pending post. Email is sent with a full preview. WordPress
    only gets hit when the publish workflow runs (after approval).
    """
    from agents.email_notifier import format_approval_email, send_notification

    logger.info("Step 4/5: Saving article + sending approval email")

    # Save pending post to vault
    pending_path = Path(f"vault/{BRAND}/pending_post.json")
    pending_data = {
        "title": article.get("title", ""),
        "html": article.get("html", ""),
        "meta_description": article.get("meta_description", ""),
        "target_keyword": article.get("target_keyword", ""),
        "word_count": article.get("word_count", 0),
        "quality_passed": article.get("quality_passed", False),
        "attempts": article.get("attempts", 0),
        "saved_at": datetime.now().isoformat(),
        "status": "pending_approval",
    }
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(json.dumps(pending_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Article saved to {pending_path}")

    # Send email with full article preview
    if NOTIFICATION_EMAIL:
        email_data = format_approval_email(
            title=article.get("title", ""),
            excerpt=article.get("meta_description", ""),
            edit_url="",
            word_count=article.get("word_count", 0),
            target_keyword=article.get("target_keyword", ""),
            article_html=article.get("html", ""),
        )
        result = send_notification(email_data, NOTIFICATION_EMAIL)
        if result.get("sent"):
            logger.info("Approval email sent")
        else:
            logger.warning(f"Email send failed: {result.get('error', 'unknown')}")
    else:
        logger.warning("No NOTIFICATION_EMAIL set — article saved but no notification sent")

    # Log to post history for dashboard
    _log_post(article, {"post_id": None, "post_url": None, "status": "pending_approval"})

    return {"success": True, "pending_path": str(pending_path)}


async def step_publish_pending() -> dict:
    """Publish a pending post to WordPress. Called separately after approval."""
    from agents.wordpress_agent import Publisher

    pending_path = Path(f"vault/{BRAND}/pending_post.json")
    if not pending_path.exists():
        logger.info("No pending post to publish")
        return {"skipped": True, "reason": "No pending post"}

    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    if pending.get("status") != "pending_approval":
        logger.info(f"Pending post status is '{pending.get('status')}', not publishing")
        return {"skipped": True, "reason": f"Status: {pending.get('status')}"}

    logger.info(f"Publishing pending post: '{pending.get('title')}'")

    publisher = Publisher()
    result = await publisher.publish(
        title=pending.get("title", ""),
        html=pending.get("html", ""),
        meta_description=pending.get("meta_description", ""),
        target_keyword=pending.get("target_keyword", ""),
        status="publish",  # Approved posts go live directly
    )

    wp_result = result.get("wp_result", {})
    if wp_result.get("success"):
        # Mark as published
        pending["status"] = "published"
        pending["post_id"] = wp_result.get("post_id")
        pending["post_url"] = wp_result.get("post_url")
        pending["published_at"] = datetime.now().isoformat()
        pending_path.write_text(json.dumps(pending, indent=2), encoding="utf-8")
        logger.info(f"Published: post_id={wp_result.get('post_id')}")
    else:
        logger.error(f"Publish failed: {wp_result.get('error', 'unknown')}")

    return result


async def step_gbp_posts() -> dict:
    """Step 5: Post to Google Business Profile (Tuesday/Friday only)."""
    today = datetime.now().strftime("%a").lower()
    if today not in ("tue", "fri"):
        logger.info(f"Step 5/5: GBP posts skipped (today is {datetime.now().strftime('%A')}, runs Tue/Fri)")
        return {"skipped": True}

    try:
        from agents.gbp_agent import GBPAgent
        logger.info("Step 5/5: Posting to Google Business Profile (3 outlets)")
        # GBP agent carries forward from v2 with minimal changes
        # TODO: Feed vault data into GBP posts for localization
        return {"skipped": True, "reason": "GBP agent integration pending vault data feed"}
    except ImportError:
        logger.warning("GBP agent not available")
        return {"skipped": True, "reason": "GBP agent not imported"}


async def step_dashboard() -> None:
    """Generate the performance dashboard."""
    try:
        from dashboard_generator import DashboardGenerator
        logger.info("Generating dashboard...")
        gen = DashboardGenerator(brand=BRAND)
        gen.generate()
        logger.info("Dashboard updated: docs/dashboard.html")
    except ImportError:
        logger.info("Dashboard generator not available — skipping")
    except Exception as e:
        logger.warning(f"Dashboard generation failed: {e}")


def _log_post(article: dict, wp_result: dict) -> None:
    """Append to post history for dashboard tracking."""
    log_path = Path(f"vault/{BRAND}/posts_log.json")
    posts = []
    if log_path.exists():
        try:
            posts = json.loads(log_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            posts = []

    posts.append({
        "date": datetime.now().isoformat(),
        "title": article.get("title", ""),
        "keyword": article.get("target_keyword", ""),
        "word_count": article.get("word_count", 0),
        "quality_passed": article.get("quality_passed", False),
        "attempts": article.get("attempts", 0),
        "post_id": wp_result.get("post_id"),
        "post_url": wp_result.get("post_url"),
        "status": "draft",
    })

    log_path.write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_weekly():
    """Full weekly pipeline: collect → plan → write → publish → GBP."""
    logger.info("=" * 60)
    logger.info(f"Coulisse Heir SEO Agent v3 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"Mode: WEEKLY | Brand: {BRAND}")
    logger.info("=" * 60)

    results = {}

    # Step 1: Collect data
    try:
        data = await step_collect_data()
        results["data"] = data
    except Exception as e:
        logger.error(f"Data collection failed: {e}")
        results["data"] = {"error": str(e)}
        # Can't continue without data
        return results

    gsc_data = data.get("gsc", {})

    # Step 2: Plan content
    try:
        plan = await step_plan_content(gsc_data)
        results["plan"] = plan
    except Exception as e:
        logger.error(f"Content planning failed: {e}")
        results["plan"] = {"error": str(e)}
        return results

    # Step 3: Write content
    try:
        article = await step_write_content(plan)
        results["article"] = article
        if article.get("error"):
            return results
    except Exception as e:
        logger.error(f"Content writing failed: {e}")
        results["article"] = {"error": str(e)}
        return results

    # Step 4: Save article + send approval email (NO WordPress call)
    try:
        save_result = await step_save_and_notify(article)
        results["save"] = save_result
    except Exception as e:
        logger.error(f"Save/notify failed: {e}")
        results["save"] = {"error": str(e)}

    # Step 5: GBP
    try:
        gbp_result = await step_gbp_posts()
        results["gbp"] = gbp_result
    except Exception as e:
        logger.warning(f"GBP posting failed: {e}")
        results["gbp"] = {"error": str(e)}

    # Dashboard
    await step_dashboard()

    logger.info("=" * 60)
    logger.info("Pipeline complete")
    logger.info("=" * 60)

    return results


async def run_daily():
    """Lightweight daily run: check data freshness, update dashboard."""
    logger.info(f"Coulisse Heir SEO Agent v3 | Daily check | {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Check vault staleness
    from agents.data_collector import DataCollector
    collector = DataCollector(brand=BRAND, site_url=SITE_URL)
    staleness = collector._check_staleness()
    for warning in staleness.get("warnings", []):
        logger.warning(f"Vault: {warning}")

    # Update dashboard
    await step_dashboard()

    logger.info("Daily check complete")


async def run_publish():
    """Publish a pending post to WordPress. Run after email approval."""
    logger.info(f"Coulisse Heir SEO Agent v3 | Publish mode | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    result = await step_publish_pending()
    if result.get("skipped"):
        logger.info(f"Nothing to publish: {result.get('reason')}")
    logger.info("Publish complete")


def main():
    setup_logging()

    mode = "weekly"
    if "--daily" in sys.argv:
        mode = "daily"
    elif "--weekly" in sys.argv:
        mode = "weekly"
    elif "--publish" in sys.argv:
        mode = "publish"
    else:
        # Auto-detect: Monday/Tuesday = weekly, other days = daily
        if datetime.now().weekday() in (0, 1):
            mode = "weekly"
        else:
            mode = "daily"

    if mode == "weekly":
        asyncio.run(run_weekly())
    elif mode == "publish":
        asyncio.run(run_publish())
    else:
        asyncio.run(run_daily())


if __name__ == "__main__":
    main()
