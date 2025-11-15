"""Simple tests to verify the test framework works."""

import pytest
from unittest.mock import MagicMock, AsyncMock

# Test text processing utilities without dependencies
def test_text_beautification():
    """Test basic text beautification."""
    from src.utils.text_processing import beautify_text

    # Test whitespace normalization
    text = "  Too    many     spaces   "
    result = beautify_text(text)
    assert result == "Too many spaces"

    # Test line break normalization
    text = "Line 1\r\nLine 2\rLine 3"
    result = beautify_text(text)
    assert "\r" not in result


def test_url_extraction():
    """Test URL extraction."""
    from src.utils.text_processing import extract_urls

    text = "Visit https://example.com and http://test.org"
    urls = extract_urls(text)
    assert len(urls) == 2
    assert "https://example.com" in urls
    assert "http://test.org" in urls


def test_language_normalization():
    """Test language code normalization."""
    from src.utils.text_processing import normalize_language_code

    assert normalize_language_code("ukr") == "uk"
    assert normalize_language_code("eng") == "en"
    assert normalize_language_code("polish") == "pl"
    assert normalize_language_code("UK") == "uk"  # Case insensitive
    assert normalize_language_code("") == "uk"  # Default to Ukrainian


def test_country_normalization():
    """Test country code normalization."""
    from src.utils.text_processing import normalize_country_code

    assert normalize_country_code("UKR") == "UA"
    assert normalize_country_code("POLAND") == "PL"
    assert normalize_country_code("ua") == "UA"  # Case handling
    assert normalize_country_code("") is None
    assert normalize_country_code(None) is None


# Test database fingerprint generation without full DB setup
def test_fingerprint_generation():
    """Test deduplication fingerprint generation."""
    import hashlib

    # Simplified version of fingerprint generation
    def generate_fingerprint(source_url: str, title: str, raw_text: str) -> str:
        text_prefix = raw_text[:200] if len(raw_text) > 200 else raw_text
        fingerprint_str = f"{source_url.lower()}|{title.lower()}|{text_prefix.lower()}"
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()

    fp1 = generate_fingerprint("https://example.com", "Test Event", "This is content")
    fp2 = generate_fingerprint("https://example.com", "Test Event", "This is content")
    fp3 = generate_fingerprint("https://other.com", "Test Event", "This is content")

    assert fp1 == fp2  # Same input -> same fingerprint
    assert fp1 != fp3  # Different URL -> different fingerprint
    assert len(fp1) == 64  # SHA-256 hex length


# Test basic model validation
def test_event_extraction_model():
    """Test EventExtraction model validation."""
    from src.models.event import EventExtraction
    from datetime import datetime

    # Valid extraction
    extraction = EventExtraction(
        title="Test Event",
        language="uk",
        city="Київ",
        country="UA",
        is_remote=False,
        organizer="Test Org",
        apply_url="https://example.com",
        occurs_from=datetime(2025, 12, 1, 10, 0),
        occurs_to=datetime(2025, 12, 1, 18, 0),
        deadline_at=datetime(2025, 11, 25),
        status="active",
        categories_slugs=["workshop", "meetup"]
    )

    assert extraction.title == "Test Event"
    assert extraction.language == "uk"
    assert extraction.city == "Київ"
    assert extraction.country == "UA"
    assert len(extraction.categories_slugs) == 2

    # Test language validation
    with pytest.raises(ValueError):
        EventExtraction(
            title="Test",
            language="invalid_long_code",  # Should be 2-letter code
            status="active",
            categories_slugs=[]
        )


def test_search_request_model():
    """Test SearchRequest model."""
    from src.models.event import SearchRequest
    from datetime import datetime

    request = SearchRequest(
        q="workshop",
        city="Київ",
        language="uk",
        is_remote=False,
        category=["workshop", "meetup"],
        page=2,
        size=50,
        sort_by="posted_at",
        order="desc"
    )

    assert request.q == "workshop"
    assert request.city == "Київ"
    assert len(request.category) == 2
    assert request.page == 2
    assert request.size == 50

    # Test defaults
    request2 = SearchRequest()
    assert request2.page == 1
    assert request2.size == 20
    assert request2.sort_by == "posted_at"
    assert request2.order == "desc"


@pytest.mark.asyncio
async def test_database_pool_singleton():
    """Test database pool singleton pattern."""
    from src.database.connection import DatabasePool

    pool1 = DatabasePool()
    pool2 = DatabasePool()

    # Should be the same instance (singleton)
    assert pool1 is pool2


def test_config_validation():
    """Test configuration validation."""
    from src.config import Settings

    # Valid settings with minimal required fields
    settings = Settings(
        database_url="postgresql://test:test@localhost/test",
        sqs_queue_url="https://sqs.test.com/queue",
        llm_provider="anthropic",
        anthropic_api_key="test-key"
    )

    assert settings.database_url == "postgresql://test:test@localhost/test"
    assert settings.llm_provider == "anthropic"
    assert settings.api_port == 8000  # Default value

    # Invalid LLM provider
    with pytest.raises(ValueError):
        Settings(
            database_url="postgresql://test:test@localhost/test",
            sqs_queue_url="https://sqs.test.com/queue",
            llm_provider="invalid_provider"
        )


def test_api_match_score_calculation():
    """Test match score calculation logic."""
    from src.models.event import EventSearchResult
    from uuid import uuid4
    from datetime import datetime

    # Create a test event
    event = EventSearchResult(
        id=uuid4(),
        title="Test Event",
        city="Київ",
        country="UA",
        language="uk",
        is_remote=False,
        source_url="https://test.com",
        posted_at=datetime.now(),
        occurs_from=None,  # Optional fields
        occurs_to=None,
        deadline_at=None,
        status="active",
        categories_slugs=["workshop"],
        score=0.85
    )

    # Test profile matching logic
    profile = {
        "city": "Київ",
        "languages": ["uk"],
        "preferred_categories": ["workshop"],
        "remote_preference": "onsite"
    }

    # Simple match score calculation
    match_score = 0.0
    factors = 0

    # City match
    if profile.get("city") == event.city:
        match_score += 0.3
    factors += 0.3

    # Language match
    if event.language in profile.get("languages", []):
        match_score += 0.2
    factors += 0.2

    # Category match
    if set(event.categories_slugs) & set(profile.get("preferred_categories", [])):
        match_score += 0.3
    factors += 0.3

    # Remote preference
    if profile.get("remote_preference") == "onsite" and not event.is_remote:
        match_score += 0.2
    factors += 0.2

    final_score = match_score / factors if factors > 0 else 0

    # All criteria match, should have high score
    assert final_score > 0.9


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])