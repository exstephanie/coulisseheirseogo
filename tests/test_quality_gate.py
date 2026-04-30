"""Tests for the content writer quality gate checklist."""

import pytest
from agents.content_writer import ContentWriter


class TestQualityGate:
    def setup_method(self):
        self.writer = ContentWriter(brand="coulissehair")
        self.plan = {
            "title": "Test Post",
            "target_keyword": "anti frizz treatment",
            "outline": [],
        }
        self.reviews = [
            {"text": "Great treatment", "reviewer": "Test", "rating": 5},
            {"text": "Loved it", "reviewer": "Test2", "rating": 4},
        ]

    def test_passes_valid_content(self):
        html = """<p>Looking for an anti frizz treatment in Singapore? Here's what our customers say about their experience.</p>
        <h2>Why Anti Frizz Treatment Works in Singapore's Climate</h2>
        <p>Singapore's humidity makes frizz a daily battle. However, professional treatments can help. For example, our anti frizz treatment uses keratin technology.</p>
        <p>Check out <a href="https://coulisseheir.com/services/">our full range of services</a> for more details.</p>
        <h2>Real Customer Reviews</h2>
        <blockquote>"Great treatment" — Sarah T</blockquote>
        <blockquote>"Loved the results" — Mike L</blockquote>
        <p>As a result, many customers return regularly. In addition, <a href="https://www.healthline.com/health/keratin-treatment">research shows keratin treatments</a> are safe for most hair types.</p>
        <h2>How Much Does It Cost?</h2>
        <p>Our anti frizz treatment starts from $188 SGD for short hair.</p>
        <p>Ready to say goodbye to frizz? Book your appointment today!</p>
        """ + ("<p>Meanwhile, Singapore's tropical climate means dealing with humidity every single day. Professional salon services use advanced formulas that create a protective barrier around each hair strand. This helps you manage your hair effectively for three to six months depending on your specific hair type and daily styling routine. Many of our loyal customers come back regularly because the lasting results speak for themselves clearly. </p>" * 15)
        result = self.writer._quality_check(html, self.plan, self.reviews)
        assert result.passed
        assert result.word_count >= 900

    def test_fails_too_short(self):
        html = "<p>Short article about anti frizz treatment.</p>"
        result = self.writer._quality_check(html, self.plan, self.reviews)
        assert not result.passed
        assert any("Too short" in f for f in result.failures)

    def test_fails_missing_keyword_in_first_paragraph(self):
        html = """<p>Welcome to our blog about hair care in Singapore.</p>
        <h2>Anti Frizz Treatment Details</h2>
        <h2>More About Anti Frizz Treatment</h2>
        <blockquote>Quote 1</blockquote><blockquote>Quote 2</blockquote>
        <p>From $188 SGD. Book now!</p>
        """ + ("<p>Content padding. </p>" * 80)
        result = self.writer._quality_check(html, self.plan, self.reviews)
        assert not result.passed
        assert any("first paragraph" in f for f in result.failures)

    def test_fails_missing_review_quotes(self):
        html = """<p>Anti frizz treatment is great in Singapore.</p>
        <h2>About Anti Frizz Treatment</h2>
        <h2>Anti Frizz Treatment Pricing</h2>
        <p>From $188 SGD. Book your appointment!</p>
        """ + ("<p>Content padding. </p>" * 80)
        result = self.writer._quality_check(html, self.plan, self.reviews)
        assert not result.passed
        assert any("review quotes" in f for f in result.failures)

    def test_fails_missing_pricing(self):
        html = """<p>Anti frizz treatment is great in Singapore.</p>
        <h2>About Anti Frizz Treatment</h2>
        <h2>Anti Frizz Treatment Reviews</h2>
        <blockquote>Quote 1</blockquote><blockquote>Quote 2</blockquote>
        <p>Book your appointment today!</p>
        """ + ("<p>Content padding. </p>" * 80)
        result = self.writer._quality_check(html, self.plan, self.reviews)
        assert not result.passed
        assert any("pricing" in f.lower() for f in result.failures)

    def test_fails_missing_cta(self):
        html = """<p>Anti frizz treatment is great in Singapore.</p>
        <h2>About Anti Frizz Treatment</h2>
        <h2>Anti Frizz Treatment Results</h2>
        <blockquote>Quote 1</blockquote><blockquote>Quote 2</blockquote>
        <p>Price starts from $188 SGD.</p>
        """ + ("<p>Content padding. </p>" * 80)
        result = self.writer._quality_check(html, self.plan, self.reviews)
        assert not result.passed
        assert any("call-to-action" in f for f in result.failures)

    def test_fails_keyword_not_in_any_h2(self):
        html = """<p>Anti frizz treatment is our specialty.</p>
        <h2>About Our Services</h2>
        <h2>Customer Reviews</h2>
        <blockquote>Quote 1</blockquote><blockquote>Quote 2</blockquote>
        <p>From $188 SGD. Book now!</p>
        <a href="https://coulisseheir.com/services/">services</a>
        <a href="https://www.example.com">external</a>
        """ + ("<p>Content padding with anti frizz treatment mention. </p>" * 80)
        result = self.writer._quality_check(html, self.plan, self.reviews)
        assert not result.passed
        assert any("H2" in f for f in result.failures)

    def test_passes_with_no_reviews_when_none_expected(self):
        html = """<p>Anti frizz treatment is our specialty in Singapore.</p>
        <h2>Anti Frizz Treatment Overview</h2>
        <h2>Anti Frizz Treatment Pricing</h2>
        <p>Starts from $188 SGD. Book your appointment today!</p>
        """ + ("<p>Content padding. </p>" * 80)
        result = self.writer._quality_check(html, self.plan, reviews=[])
        # No review quotes required when no reviews provided
        assert not any("review quotes" in f for f in result.failures)
