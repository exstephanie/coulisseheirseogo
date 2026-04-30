"""Tests for review clustering: keyword classification and cluster management."""

import json
import pytest
from pathlib import Path

from agents.data_collector import DataCollector, REVIEW_TAXONOMY


class TestKeywordClassify:
    def setup_method(self):
        self.collector = DataCollector(brand="coulissehair")

    def test_frizz_keywords(self):
        assert self.collector._keyword_classify("Amazing frizz control treatment") == "anti-frizz-results"
        assert self.collector._keyword_classify("My frizzy hair is finally smooth") == "anti-frizz-results"

    def test_keratin_keywords(self):
        assert self.collector._keyword_classify("Got keratin treatment here") == "keratin-treatment"

    def test_pricing_keywords(self):
        assert self.collector._keyword_classify("Great value for the price") == "pricing-value"
        assert self.collector._keyword_classify("A bit expensive but worth it") == "pricing-value"

    def test_stylist_keywords(self):
        assert self.collector._keyword_classify("The stylist was very professional") == "stylist-skill"

    def test_first_visit(self):
        assert self.collector._keyword_classify("My first time visiting this salon") == "first-time-visit"

    def test_wedding_keywords(self):
        assert self.collector._keyword_classify("Got my hair done for my wedding") == "wedding-event-prep"

    def test_scalp_keywords(self):
        assert self.collector._keyword_classify("Helped with my dandruff problem") == "scalp-hair-loss"

    def test_colour_keywords(self):
        assert self.collector._keyword_classify("Beautiful balayage highlights") == "colour-highlights"

    def test_kids_keywords(self):
        assert self.collector._keyword_classify("Brought my daughter here") == "kids-family"

    def test_fallback_to_ambience(self):
        assert self.collector._keyword_classify("Nice place, good experience") == "salon-ambience-service"

    def test_empty_text(self):
        assert self.collector._keyword_classify("") == "salon-ambience-service"

    def test_humidity_keywords(self):
        assert self.collector._keyword_classify("Singapore weather ruins my hair") == "humidity-hair-problems"


class TestCSVImport:
    def test_imports_new_reviews(self, tmp_vault):
        csv_content = """review_id,reviewer,rating,text,date
r10,Test User,5,Great anti-frizz results!,2026-03-28
r11,Another User,4,Good service overall,2026-03-28"""
        (tmp_vault / "reviews_import.csv").write_text(csv_content)

        collector = DataCollector(brand="coulissehair")
        collector.vault_dir = tmp_vault
        new_reviews = collector._import_csv(
            tmp_vault / "reviews_import.csv",
            existing_ids={"r1", "r2", "r3"},  # Existing IDs from conftest
        )
        assert len(new_reviews) == 2
        assert new_reviews[0]["reviewer_name"] == "Test User"
        assert new_reviews[0]["rating"] == 5

    def test_skips_existing_ids(self, tmp_vault):
        csv_content = """review_id,reviewer,rating,text,date
r1,Existing User,5,Already imported,2026-03-28"""
        (tmp_vault / "reviews_import.csv").write_text(csv_content)

        collector = DataCollector(brand="coulissehair")
        collector.vault_dir = tmp_vault
        new_reviews = collector._import_csv(
            tmp_vault / "reviews_import.csv",
            existing_ids={"r1"},
        )
        assert len(new_reviews) == 0

    def test_skips_empty_text(self, tmp_vault):
        csv_content = """review_id,reviewer,rating,text,date
r20,Star Only,5,,2026-03-28"""
        (tmp_vault / "reviews_import.csv").write_text(csv_content)

        collector = DataCollector(brand="coulissehair")
        collector.vault_dir = tmp_vault
        new_reviews = collector._import_csv(
            tmp_vault / "reviews_import.csv",
            existing_ids=set(),
        )
        assert len(new_reviews) == 0  # Star-only reviews skipped

    def test_handles_alternative_column_names(self, tmp_vault):
        csv_content = """Review ID,Reviewer,Rating,Review Text,Date
r30,Alt Format,4,Good salon experience,2026-03-28"""
        (tmp_vault / "reviews_import.csv").write_text(csv_content)

        collector = DataCollector(brand="coulissehair")
        collector.vault_dir = tmp_vault
        new_reviews = collector._import_csv(
            tmp_vault / "reviews_import.csv",
            existing_ids=set(),
        )
        assert len(new_reviews) == 1
        assert new_reviews[0]["reviewer_name"] == "Alt Format"


class TestTaxonomy:
    def test_taxonomy_has_expected_categories(self):
        assert "anti-frizz-results" in REVIEW_TAXONOMY
        assert "keratin-treatment" in REVIEW_TAXONOMY
        assert "pricing-value" in REVIEW_TAXONOMY
        assert len(REVIEW_TAXONOMY) == 14
