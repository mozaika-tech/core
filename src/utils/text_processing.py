"""Text processing utilities."""

import re
from typing import List


def beautify_text(text: str) -> str:
    """
    Beautify raw text by normalizing whitespace, bullets, and URLs.

    Args:
        text: Raw text to beautify

    Returns:
        Beautified text
    """
    if not text:
        return ""

    # Normalize line breaks (preserve paragraph structure)
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\r', '\n', text)

    # Normalize multiple line breaks to maximum 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Normalize whitespace within lines
    lines = text.split('\n')
    normalized_lines = []

    for line in lines:
        # Trim leading/trailing whitespace
        line = line.strip()

        # Skip empty lines (they'll be handled by line break normalization)
        if not line:
            normalized_lines.append('')
            continue

        # Normalize multiple spaces to single space
        line = re.sub(r'\s+', ' ', line)

        # Normalize bullet points
        # Convert various bullet symbols to standard bullet
        bullet_patterns = [
            r'^[-–—]\s+',  # Dashes
            r'^[*]\s+',    # Asterisk
            r'^[•·∙◦▪▫]\s+',  # Various bullet symbols
            r'^[\d]+\.\s+',  # Numbered lists
            r'^[\d]+\)\s+',  # Numbered with parenthesis
        ]

        for pattern in bullet_patterns:
            if re.match(pattern, line):
                # Replace with standard bullet
                line = re.sub(pattern, '• ', line)
                break

        normalized_lines.append(line)

    text = '\n'.join(normalized_lines)

    # Remove duplicate URLs (keep first occurrence)
    url_pattern = r'https?://[^\s\n]+'
    urls = re.findall(url_pattern, text)
    seen_urls = set()
    for url in urls:
        if url in seen_urls:
            # Remove duplicate URL
            text = text.replace(url, '', 1)
        else:
            seen_urls.add(url)

    # Clean up any resulting multiple spaces from URL removal
    text = re.sub(r'\s+', ' ', text)

    # Final trim
    text = text.strip()

    return text


def extract_urls(text: str) -> List[str]:
    """
    Extract all URLs from text.

    Args:
        text: Text to extract URLs from

    Returns:
        List of unique URLs
    """
    if not text:
        return []

    url_pattern = r'https?://[^\s\n]+'
    urls = re.findall(url_pattern, text)

    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return unique_urls


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to maximum length, preserving word boundaries.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text

    # Account for suffix length
    max_length = max_length - len(suffix)

    # Find last space before max_length
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')

    if last_space > 0:
        truncated = truncated[:last_space]

    return truncated + suffix


def normalize_language_code(code: str) -> str:
    """
    Normalize language code to ISO-639-1.

    Args:
        code: Language code to normalize

    Returns:
        Normalized 2-letter language code
    """
    if not code:
        return "uk"  # Default to Ukrainian

    code = code.lower().strip()

    # Common mappings
    mappings = {
        "ukr": "uk",
        "ukrainian": "uk",
        "eng": "en",
        "english": "en",
        "pol": "pl",
        "polish": "pl",
        "rus": "ru",
        "russian": "ru"
    }

    if code in mappings:
        return mappings[code]

    # If already 2-letter code, return as is
    if len(code) == 2:
        return code

    # Default to Ukrainian for unknown codes
    return "uk"


def normalize_country_code(code: str) -> str:
    """
    Normalize country code to ISO-3166-1 alpha-2.

    Args:
        code: Country code to normalize

    Returns:
        Normalized 2-letter country code
    """
    if not code:
        return None

    code = code.upper().strip()

    # Common mappings
    mappings = {
        "UKR": "UA",
        "UKRAINE": "UA",
        "POL": "PL",
        "POLAND": "PL",
        "USA": "US",
        "UNITED STATES": "US",
        "GBR": "GB",
        "UK": "GB",
        "UNITED KINGDOM": "GB"
    }

    if code in mappings:
        return mappings[code]

    # If already 2-letter code, return as is
    if len(code) == 2:
        return code

    return None