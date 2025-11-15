"""Unit tests for text processing utilities."""

import pytest

from src.utils.text_processing import (
    beautify_text,
    extract_urls,
    truncate_text,
    normalize_language_code,
    normalize_country_code
)


class TestBeautifyText:
    """Test text beautification function."""

    def test_normalize_line_breaks(self):
        """Test line break normalization."""
        text = "Line 1\r\nLine 2\rLine 3\n\n\n\nLine 4"
        result = beautify_text(text)
        assert "\r" not in result
        assert "\n\n\n" not in result
        assert "Line 1\nLine 2\nLine 3\n\nLine 4" == result

    def test_normalize_whitespace(self):
        """Test whitespace normalization."""
        text = "  Too    many     spaces   "
        result = beautify_text(text)
        assert result == "Too many spaces"

    def test_normalize_bullets(self):
        """Test bullet point normalization."""
        text = """
        - Item 1
        * Item 2
        • Item 3
        1. Item 4
        2) Item 5
        """
        result = beautify_text(text)
        assert "• Item 1" in result
        assert "• Item 2" in result
        assert "• Item 3" in result
        assert "• Item 4" in result
        assert "• Item 5" in result

    def test_remove_duplicate_urls(self):
        """Test duplicate URL removal."""
        text = """
        Check out https://example.com
        Also visit https://example.com
        And don't forget https://example.com
        But this is different: https://other.com
        """
        result = beautify_text(text)
        # Should keep first occurrence and remove duplicates
        assert result.count("https://example.com") == 1
        assert "https://other.com" in result

    def test_empty_text(self):
        """Test handling of empty text."""
        assert beautify_text("") == ""
        assert beautify_text(None) == ""
        assert beautify_text("   \n\n\n   ") == ""

    def test_preserve_paragraph_structure(self):
        """Test that paragraph structure is preserved."""
        text = """
        Paragraph 1
        Still paragraph 1

        Paragraph 2
        Still paragraph 2
        """
        result = beautify_text(text)
        paragraphs = result.split("\n\n")
        assert len(paragraphs) == 2


class TestExtractUrls:
    """Test URL extraction function."""

    def test_extract_multiple_urls(self):
        """Test extracting multiple URLs."""
        text = "Visit https://example.com and http://test.org for more info"
        urls = extract_urls(text)
        assert len(urls) == 2
        assert "https://example.com" in urls
        assert "http://test.org" in urls

    def test_extract_no_duplicates(self):
        """Test that duplicates are removed."""
        text = "https://example.com is great. Check https://example.com again!"
        urls = extract_urls(text)
        assert len(urls) == 1
        assert urls[0] == "https://example.com"

    def test_no_urls(self):
        """Test when no URLs are present."""
        text = "This text has no URLs"
        urls = extract_urls(text)
        assert len(urls) == 0

    def test_empty_text(self):
        """Test with empty text."""
        assert extract_urls("") == []
        assert extract_urls(None) == []

    def test_complex_urls(self):
        """Test extraction of complex URLs."""
        text = "Apply at https://example.com/apply?id=123&ref=abc#section"
        urls = extract_urls(text)
        assert len(urls) == 1
        assert "https://example.com/apply?id=123&ref=abc#section" in urls[0]


class TestTruncateText:
    """Test text truncation function."""

    def test_truncate_long_text(self):
        """Test truncation of long text."""
        text = "This is a very long text that needs to be truncated"
        result = truncate_text(text, 20)
        assert len(result) <= 20
        assert result.endswith("...")

    def test_no_truncation_needed(self):
        """Test when text is already short."""
        text = "Short text"
        result = truncate_text(text, 20)
        assert result == text

    def test_word_boundary_preservation(self):
        """Test that truncation happens at word boundaries."""
        text = "This is a sentence with many words"
        result = truncate_text(text, 15)
        assert not result.endswith("s...")  # Should not cut mid-word
        assert result == "This is a..."

    def test_custom_suffix(self):
        """Test custom suffix."""
        text = "Long text to truncate"
        result = truncate_text(text, 12, suffix=" [...]")
        assert result.endswith(" [...]")

    def test_empty_text(self):
        """Test with empty text."""
        assert truncate_text("", 10) == ""
        assert truncate_text(None, 10) == None


class TestNormalizeLanguageCode:
    """Test language code normalization."""

    def test_normalize_common_codes(self):
        """Test normalization of common language codes."""
        assert normalize_language_code("ukr") == "uk"
        assert normalize_language_code("ukrainian") == "uk"
        assert normalize_language_code("eng") == "en"
        assert normalize_language_code("english") == "en"
        assert normalize_language_code("pol") == "pl"
        assert normalize_language_code("polish") == "pl"

    def test_already_normalized(self):
        """Test already normalized codes."""
        assert normalize_language_code("uk") == "uk"
        assert normalize_language_code("en") == "en"
        assert normalize_language_code("pl") == "pl"

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert normalize_language_code("UK") == "uk"
        assert normalize_language_code("En") == "en"
        assert normalize_language_code("UKRAINIAN") == "uk"

    def test_default_to_ukrainian(self):
        """Test defaulting to Ukrainian for unknown codes."""
        assert normalize_language_code("") == "uk"
        assert normalize_language_code(None) == "uk"
        assert normalize_language_code("unknown") == "uk"

    def test_whitespace_handling(self):
        """Test handling of whitespace."""
        assert normalize_language_code("  uk  ") == "uk"
        assert normalize_language_code("\nen\n") == "en"


class TestNormalizeCountryCode:
    """Test country code normalization."""

    def test_normalize_common_codes(self):
        """Test normalization of common country codes."""
        assert normalize_country_code("UKR") == "UA"
        assert normalize_country_code("UKRAINE") == "UA"
        assert normalize_country_code("POL") == "PL"
        assert normalize_country_code("POLAND") == "PL"
        assert normalize_country_code("USA") == "US"
        assert normalize_country_code("GBR") == "GB"

    def test_already_normalized(self):
        """Test already normalized codes."""
        assert normalize_country_code("UA") == "UA"
        assert normalize_country_code("PL") == "PL"
        assert normalize_country_code("US") == "US"

    def test_case_handling(self):
        """Test case handling."""
        assert normalize_country_code("ua") == "UA"
        assert normalize_country_code("Pl") == "PL"
        assert normalize_country_code("ukraine") == "UA"

    def test_return_none_for_invalid(self):
        """Test returning None for invalid codes."""
        assert normalize_country_code("") is None
        assert normalize_country_code(None) is None
        assert normalize_country_code("INVALID") is None

    def test_whitespace_handling(self):
        """Test handling of whitespace."""
        assert normalize_country_code("  UA  ") == "UA"
        assert normalize_country_code("\nPL\n") == "PL"