"""Shared fixtures for the Coulisse Heir SEO Agent v3 test suite."""

import json
import pytest
from pathlib import Path


@pytest.fixture
def tmp_vault(tmp_path):
    """Create a temporary vault directory with sample data."""
    vault = tmp_path / "vault" / "coulissehair"
    vault.mkdir(parents=True)

    # Sample reviews
    reviews = [
        {
            "review_id": "r1",
            "reviewer_name": "Sarah T",
            "rating": 5,
            "text": "Amazing anti-frizz treatment! My hair stayed smooth even in the humidity.",
            "date": "2026-03-15",
            "source": "test",
            "cluster": "anti-frizz-results",
        },
        {
            "review_id": "r2",
            "reviewer_name": "Mike L",
            "rating": 4,
            "text": "Good keratin treatment, price was reasonable at $288 for medium length.",
            "date": "2026-03-20",
            "source": "test",
            "cluster": "pricing-value",
        },
        {
            "review_id": "r3",
            "reviewer_name": "Anna K",
            "rating": 5,
            "text": "First time here for soft rebonding. The stylist was so skilled and patient.",
            "date": "2026-03-25",
            "source": "test",
            "cluster": None,  # Unclustered
        },
    ]
    (vault / "reviews.json").write_text(json.dumps(reviews), encoding="utf-8")

    # Sample clusters
    clusters = {
        "taxonomy": ["anti-frizz-results", "pricing-value", "stylist-skill"],
        "clusters": {
            "anti-frizz-results": [
                {"review_id": "r1", "text": "Amazing anti-frizz treatment!", "rating": 5, "reviewer": "Sarah T"}
            ],
            "pricing-value": [
                {"review_id": "r2", "text": "Good keratin treatment, price was reasonable", "rating": 4, "reviewer": "Mike L"}
            ],
        },
        "last_clustered": "2026-03-25T10:00:00",
        "total_reviews": 2,
    }
    (vault / "review_clusters.json").write_text(json.dumps(clusters), encoding="utf-8")

    # Sample services
    services = [
        {
            "name": "Anti-Frizz Treatment",
            "slug": "anti-frizz",
            "price_from": 188,
            "price_to": 388,
            "currency": "SGD",
            "duration_minutes": 120,
            "keywords": ["anti frizz treatment singapore"],
        },
    ]
    (vault / "services.json").write_text(json.dumps(services), encoding="utf-8")

    # Brand voice
    (vault / "brand_voice.md").write_text("# Coulisse Heir\nFriendly, Singapore-local tone.", encoding="utf-8")

    # Locations
    (vault / "locations.json").write_text(json.dumps([{"name": "Coulisse Heir Jurong Point", "outlet": "Jurong Point"}]), encoding="utf-8")

    # FAQs
    (vault / "faqs.json").write_text(json.dumps([{"question": "How long?", "answer": "3-6 months"}]), encoding="utf-8")

    return vault


@pytest.fixture
def sample_gsc_data():
    """Sample GSC data for testing."""
    return {
        "period": "test",
        "total_keywords": 10,
        "quick_wins": [
            {"keyword": "anti frizz treatment singapore", "clicks": 8, "impressions": 190, "ctr": 0.042, "position": 18.5},
        ],
        "summary": {"total_clicks": 100, "total_impressions": 3000, "avg_position": 12.0},
    }


@pytest.fixture
def sample_plan():
    """Sample content plan for testing."""
    return {
        "title": "Anti-Frizz Treatment in Singapore: What 200 Customers Actually Think",
        "target_keyword": "anti frizz treatment singapore",
        "cluster": "anti-frizz-results",
        "angle": "Real customer review data",
        "reviews_to_include": 2,
        "services_to_mention": ["Anti-Frizz Treatment"],
        "outline": ["What Is Anti-Frizz Treatment?", "Real Customer Reviews", "Pricing", "Book Now"],
        "meta_description": "Anti-frizz treatment at Coulisse Heir from $188. See what 200+ customers say.",
        "review_quotes": [
            {"text": "Amazing anti-frizz treatment!", "reviewer": "Sarah T", "rating": 5},
        ],
        "services_data": [{"name": "Anti-Frizz Treatment", "price_from": 188, "price_to": 388, "duration_minutes": 120}],
    }
