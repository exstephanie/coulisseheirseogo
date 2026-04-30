"""
Dashboard Generator — Creates a static HTML performance dashboard.

Reads vault data (reviews, clusters, GSC, post history) and generates
a self-contained HTML file at docs/dashboard.html.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("coulissehair.dashboard")


class DashboardGenerator:
    def __init__(self, brand: str = "coulissehair"):
        self.brand = brand
        self.vault_dir = Path(f"vault/{brand}")
        self.output_path = Path("docs/dashboard.html")

    def generate(self) -> None:
        """Generate the static HTML dashboard."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Load data
        clusters = self._load_json("review_clusters.json") or {}
        gsc_data = self._load_json("gsc_data.json") or {}
        posts_log = self._load_json("posts_log.json") or []
        reviews = self._load_json("reviews.json") or []

        # Build stats
        total_reviews = len(reviews)
        total_posts = len(posts_log)
        total_clusters = len(clusters.get("clusters", {}))
        gsc_summary = gsc_data.get("summary", {})
        cluster_counts = {
            k: len(v) for k, v in clusters.get("clusters", {}).items()
        }

        # Staleness check
        stale_files = []
        for fname in ["services.json", "stylists.json", "faqs.json"]:
            fpath = self.vault_dir / fname
            if fpath.exists():
                days = (datetime.now() - datetime.fromtimestamp(fpath.stat().st_mtime)).days
                if days > 90:
                    stale_files.append(f"{fname} ({days}d old)")
            else:
                stale_files.append(f"{fname} (missing)")

        # Recent posts
        recent_posts = sorted(posts_log, key=lambda p: p.get("date", ""), reverse=True)[:10]

        # Generate HTML
        html = self._render_html(
            total_reviews=total_reviews,
            total_posts=total_posts,
            total_clusters=total_clusters,
            gsc_summary=gsc_summary,
            cluster_counts=cluster_counts,
            recent_posts=recent_posts,
            stale_files=stale_files,
        )

        self.output_path.write_text(html, encoding="utf-8")
        logger.info(f"Dashboard generated: {self.output_path}")

    def _render_html(self, **data) -> str:
        now = datetime.now().strftime("%d %b %Y, %I:%M %p")

        cluster_bars = ""
        for cat, count in sorted(data["cluster_counts"].items(), key=lambda x: -x[1]):
            max_count = max(data["cluster_counts"].values()) if data["cluster_counts"] else 1
            width = int((count / max_count) * 100)
            label = cat.replace("-", " ").title()
            cluster_bars += f'<div class="bar-row"><span class="bar-label">{label}</span><div class="bar" style="width:{width}%">{count}</div></div>\n'

        posts_rows = ""
        for post in data["recent_posts"]:
            date = post.get("date", "")[:10]
            title = post.get("title", "Untitled")
            status = post.get("status", "draft")
            words = post.get("word_count", "?")
            quality = "pass" if post.get("quality_passed") else "fail"
            posts_rows += f"<tr><td>{date}</td><td>{title}</td><td>{status}</td><td>{words}</td><td>{quality}</td></tr>\n"

        vault_status = ""
        if data["stale_files"]:
            vault_status = '<div class="alert">' + "<br>".join(data["stale_files"]) + "</div>"
        else:
            vault_status = '<div class="ok">All vault files are fresh</div>'

        gsc = data["gsc_summary"]
        clicks = gsc.get("total_clicks", "—")
        impressions = gsc.get("total_impressions", "—")
        avg_pos = gsc.get("avg_position", "—")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coulisse Heir SEO Dashboard</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }}
.header {{ background: #1a1a2e; color: white; padding: 24px; text-align: center; }}
.header h1 {{ font-size: 1.5rem; font-weight: 600; }}
.header p {{ color: #888; font-size: 0.85rem; margin-top: 4px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; padding: 16px; max-width: 1200px; margin: 0 auto; }}
.card {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.card h2 {{ font-size: 1rem; color: #666; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500; }}
.stat {{ font-size: 2.5rem; font-weight: 700; color: #1a1a2e; }}
.stat-label {{ font-size: 0.85rem; color: #999; }}
.bar-row {{ display: flex; align-items: center; margin: 6px 0; }}
.bar-label {{ width: 140px; font-size: 0.8rem; color: #666; flex-shrink: 0; }}
.bar {{ background: #4361ee; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; min-width: 30px; text-align: center; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }}
th {{ color: #666; font-weight: 500; }}
.alert {{ background: #fff3cd; border: 1px solid #ffc107; padding: 12px; border-radius: 6px; font-size: 0.85rem; color: #856404; }}
.ok {{ background: #d4edda; border: 1px solid #28a745; padding: 12px; border-radius: 6px; font-size: 0.85rem; color: #155724; }}
.footer {{ text-align: center; padding: 24px; color: #999; font-size: 0.75rem; }}
</style>
</head>
<body>
<div class="header">
  <h1>Coulisse Heir SEO Dashboard</h1>
  <p>Review-Driven Content Engine v3</p>
</div>

<div class="grid">
  <div class="card">
    <h2>Reviews</h2>
    <div class="stat">{data['total_reviews']}</div>
    <div class="stat-label">Google reviews imported</div>
  </div>
  <div class="card">
    <h2>Posts</h2>
    <div class="stat">{data['total_posts']}</div>
    <div class="stat-label">Blog posts generated</div>
  </div>
  <div class="card">
    <h2>Clusters</h2>
    <div class="stat">{data['total_clusters']}</div>
    <div class="stat-label">Review topic clusters</div>
  </div>
  <div class="card">
    <h2>GSC (28 days)</h2>
    <div class="stat">{clicks}</div>
    <div class="stat-label">Clicks | {impressions} impressions | Pos {avg_pos}</div>
  </div>
</div>

<div class="grid">
  <div class="card" style="grid-column: span 2;">
    <h2>Review Clusters</h2>
    {cluster_bars or '<p style="color:#999">No clusters yet. Import reviews to get started.</p>'}
  </div>
  <div class="card">
    <h2>Vault Health</h2>
    {vault_status}
  </div>
</div>

<div class="grid">
  <div class="card" style="grid-column: 1 / -1;">
    <h2>Recent Posts</h2>
    <table>
      <thead><tr><th>Date</th><th>Title</th><th>Status</th><th>Words</th><th>Quality</th></tr></thead>
      <tbody>{posts_rows or '<tr><td colspan="5" style="color:#999;text-align:center">No posts yet</td></tr>'}</tbody>
    </table>
  </div>
</div>

<div class="footer">Generated {now} | Coulisse Heir SEO Agent v3</div>
</body>
</html>"""

    def _load_json(self, filename: str):
        path = self.vault_dir / filename
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return None
