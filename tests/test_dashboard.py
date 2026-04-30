"""Tests for the dashboard generator."""

import json
import pytest
from pathlib import Path

from dashboard_generator import DashboardGenerator


class TestDashboardGenerator:
    def test_generates_html_file(self, tmp_vault, tmp_path):
        gen = DashboardGenerator(brand="coulissehair")
        gen.vault_dir = tmp_vault
        gen.output_path = tmp_path / "docs" / "dashboard.html"
        gen.generate()
        assert gen.output_path.exists()
        html = gen.output_path.read_text()
        assert "Coulisse Heir SEO Dashboard" in html

    def test_shows_review_count(self, tmp_vault, tmp_path):
        gen = DashboardGenerator(brand="coulissehair")
        gen.vault_dir = tmp_vault
        gen.output_path = tmp_path / "docs" / "dashboard.html"
        gen.generate()
        html = gen.output_path.read_text()
        # 3 reviews in the fixture
        assert ">3<" in html

    def test_handles_empty_vault(self, tmp_path):
        vault = tmp_path / "vault" / "coulissehair"
        vault.mkdir(parents=True)
        gen = DashboardGenerator(brand="coulissehair")
        gen.vault_dir = vault
        gen.output_path = tmp_path / "docs" / "dashboard.html"
        gen.generate()
        html = gen.output_path.read_text()
        assert "No posts yet" in html

    def test_shows_cluster_bars(self, tmp_vault, tmp_path):
        gen = DashboardGenerator(brand="coulissehair")
        gen.vault_dir = tmp_vault
        gen.output_path = tmp_path / "docs" / "dashboard.html"
        gen.generate()
        html = gen.output_path.read_text()
        assert "Anti Frizz Results" in html
        assert "Pricing Value" in html

    def test_shows_stale_warning(self, tmp_path):
        vault = tmp_path / "vault" / "coulissehair"
        vault.mkdir(parents=True)
        # Create services.json but no other files
        (vault / "services.json").write_text("[]")
        gen = DashboardGenerator(brand="coulissehair")
        gen.vault_dir = vault
        gen.output_path = tmp_path / "docs" / "dashboard.html"
        gen.generate()
        html = gen.output_path.read_text()
        assert "missing" in html.lower()

    def test_shows_posts_table(self, tmp_vault, tmp_path):
        posts = [
            {"date": "2026-03-28T10:00:00", "title": "Test Post", "status": "draft", "word_count": 1200, "quality_passed": True}
        ]
        (tmp_vault / "posts_log.json").write_text(json.dumps(posts))
        gen = DashboardGenerator(brand="coulissehair")
        gen.vault_dir = tmp_vault
        gen.output_path = tmp_path / "docs" / "dashboard.html"
        gen.generate()
        html = gen.output_path.read_text()
        assert "Test Post" in html
