"""
Field validation functions for data extraction.

Provides specific validators for common data types and formats.
"""

import re
from datetime import datetime
from typing import Any


def validate_year(year: int) -> bool:
    """
    Validate conference year.

    Args:
        year: Year value (YYYY)

    Returns:
        True if valid (1942-present)
    """
    if not isinstance(year, int):
        return False
    current_year = datetime.now().year
    return 1942 <= year <= current_year + 1  # Allow next year for upcoming conferences


def validate_month(month: str) -> bool:
    """
    Validate conference month.

    Args:
        month: Month name

    Returns:
        True if valid (April or October)
    """
    if not isinstance(month, str):
        return False
    return month in ["April", "October"]


def validate_date_iso(date_str: str) -> bool:
    """
    Validate ISO date format (YYYY-MM-DD).

    Args:
        date_str: Date string

    Returns:
        True if valid ISO date format
    """
    if not isinstance(date_str, str):
        return False
    try:
        datetime.fromisoformat(date_str)
        return True
    except (ValueError, TypeError):
        return False


def validate_conference_id_format(conf_id: str) -> bool:
    """
    Validate conference ID format.

    Args:
        conf_id: Conference ID string (e.g., "2023-04", "2023-10")

    Returns:
        True if format is YYYY-MM where MM is 04 or 10
    """
    if not isinstance(conf_id, str):
        return False
    pattern = r"^\d{4}-(04|10)$"
    return bool(re.match(pattern, conf_id))


def validate_url(url: str) -> bool:
    """
    Validate URL format.

    Args:
        url: URL string

    Returns:
        True if basic URL format is valid
    """
    if not isinstance(url, str):
        return False
    # Basic URL validation - starts with http:// or https:// or /
    return url.startswith(("http://", "https://", "/"))


def validate_speaker_name(name: str) -> bool:
    """
    Validate speaker name.

    Args:
        name: Speaker name

    Returns:
        True if non-empty string
    """
    if not isinstance(name, str):
        return False
    return len(name.strip()) > 0


def validate_corpus(corpus: str) -> bool:
    """
    Validate corpus identifier.

    Args:
        corpus: Corpus identifier (typically 'E' for English)

    Returns:
        True if valid corpus code
    """
    if not isinstance(corpus, str):
        return False
    # Common corpus codes: E (English), S (Spanish), P (Portuguese), etc.
    return len(corpus) == 1 and corpus.isalpha()


def validate_positive_int(value: int) -> bool:
    """
    Validate positive integer.

    Args:
        value: Integer value

    Returns:
        True if positive integer
    """
    return isinstance(value, int) and value > 0


def validate_non_negative_int(value: int) -> bool:
    """
    Validate non-negative integer.

    Args:
        value: Integer value

    Returns:
        True if non-negative integer (>= 0)
    """
    return isinstance(value, int) and value >= 0


def validate_iso_timestamp(timestamp: str) -> bool:
    """
    Validate ISO 8601 timestamp format.

    Args:
        timestamp: Timestamp string

    Returns:
        True if valid ISO 8601 format
    """
    if not isinstance(timestamp, str):
        return False
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        return False


def validate_version_string(version: str) -> bool:
    """
    Validate version string format.

    Args:
        version: Version string (e.g., "1.0.0", "v1.0", "phase1-v1")

    Returns:
        True if non-empty string
    """
    if not isinstance(version, str):
        return False
    return len(version.strip()) > 0


def coerce_to_int(value: Any) -> int:
    """
    Safely coerce value to integer.

    Args:
        value: Value to coerce

    Returns:
        Integer value

    Raises:
        ValueError: If coercion fails
    """
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"Cannot coerce {type(value).__name__} to int")


def coerce_to_str(value: Any) -> str:
    """
    Safely coerce value to string.

    Args:
        value: Value to coerce

    Returns:
        String value
    """
    if value is None:
        return None
    return str(value)


def sanitize_speaker_name(given_names: str, last_names: str) -> str:
    """
    Format speaker name from database fields.

    Args:
        given_names: Given names
        last_names: Last names

    Returns:
        Formatted full name (GivenNames LastNames)
    """
    given = (given_names or "").strip()
    last = (last_names or "").strip()

    if given and last:
        return f"{given} {last}"
    elif last:
        return last
    elif given:
        return given
    else:
        return "Unknown Speaker"


def determine_conference_month(annual: str) -> str:
    """
    Determine conference month from annual flag.

    Args:
        annual: Annual flag ('A' for April, 'S' for October/Semi-Annual)

    Returns:
        Month name ('April' or 'October')
    """
    if annual == "A":
        return "April"
    elif annual == "S":
        return "October"
    else:
        # Fallback: parse from date or default
        return "October"
