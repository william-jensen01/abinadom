"""
Schema definitions for data extraction phases.

Configuration-driven schema validation to ensure data quality and consistency.
"""

from typing import Any, Dict, Optional, Callable


# Field schema structure:
# - required: Whether the field must be present
# - type: Expected Python type
# - validator: Optional callable for custom validation
# - default: Default value if field is missing (for optional fields)
# - description: Human-readable description

TALK_METADATA_SCHEMA: Dict[str, Dict[str, Any]] = {
    # Primary identifiers
    "talk_id": {
        "required": True,
        "type": int,
        "description": "Unique talk identifier from database",
    },
    # Core metadata
    "title": {"required": True, "type": str, "description": "Talk title"},
    "speaker_name": {
        "required": True,
        "type": str,
        "description": "Full speaker name (GivenNames LastNames)",
    },
    "speaker_id": {"required": True, "type": int, "description": "Speaker identifier"},
    # Conference information
    "conference_id": {
        "required": True,
        "type": int,
        "description": "Conference identifier",
    },
    "conference_year": {
        "required": True,
        "type": int,
        "description": "Year of conference (YYYY)",
    },
    "conference_month": {
        "required": True,
        "type": str,
        "description": "Month of conference (April or October)",
    },
    "conference_description": {
        "required": True,
        "type": str,
        "description": "Full conference description",
    },
    # Session information (optional - not all talks have session data)
    "session_id": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Session identifier",
    },
    "session_description": {
        "required": False,
        "type": str,
        "default": None,
        "description": 'Session description (e.g., "Saturday Morning Session")',
    },
    "session_abbr": {
        "required": False,
        "type": str,
        "default": None,
        "description": 'Session abbreviation (e.g., "Saturday Morning")',
    },
    "session_date": {
        "required": False,
        "type": str,
        "default": None,
        "description": "Session date (YYYY-MM-DD)",
    },
    "session_sequence": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Sequence number within conference",
    },
    "talk_sequence": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Sequence number within session",
    },
    # URLs and identifiers
    "url": {"required": False, "type": str, "default": None, "description": "Talk URL"},
    "uri_l": {
        "required": False,
        "type": str,
        "default": None,
        "description": "URI literal variant",
    },
    "uri_gc": {
        "required": False,
        "type": str,
        "default": None,
        "description": "URI General Conference normalized variant",
    },
    "data_aid": {
        "required": False,
        "type": str,
        "default": None,
        "description": "Content identifier (data-aid attribute)",
    },
    # Media URLs (optional)
    "audio_url": {
        "required": False,
        "type": str,
        "default": None,
        "description": "Audio URL",
    },
    "video_low_url": {
        "required": False,
        "type": str,
        "default": None,
        "description": "Low quality video URL",
    },
    "video_med_url": {
        "required": False,
        "type": str,
        "default": None,
        "description": "Medium quality video URL",
    },
    "video_high_url": {
        "required": False,
        "type": str,
        "default": None,
        "description": "High quality video URL",
    },
    # Additional metadata
    "talk_date": {
        "required": True,
        "type": str,
        "description": "Talk date (YYYY-MM-DD)",
    },
    "corpus": {
        "required": False,
        "type": str,
        "default": "E",  # E for English
        "description": "Corpus identifier",
    },
    "speaker_role_id": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Speaker role identifier",
    },
    # Page numbers (for print editions)
    "start_page_num": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Starting page number in print edition",
    },
    "end_page_num": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Ending page number in print edition",
    },
    # Extraction metadata
    "extraction_timestamp": {
        "required": True,
        "type": str,
        "description": "ISO format timestamp of extraction",
    },
    "extraction_version": {
        "required": True,
        "type": str,
        "description": "Version of extraction pipeline",
    },
}


def validate_schema(
    data: Dict[str, Any], schema: Dict[str, Dict[str, Any]]
) -> tuple[bool, list[str]]:
    """
    Validate data against schema definition.

    Args:
        data: Dictionary to validate
        schema: Schema definition

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    for field_name, field_schema in schema.items():
        value = data.get(field_name)

        # Check required fields
        if field_schema["required"] and value is None:
            errors.append(f"Required field '{field_name}' is missing or None")
            continue

        # Skip validation if optional and not provided
        if not field_schema["required"] and value is None:
            continue

        # Check type
        expected_type = field_schema["type"]
        if not isinstance(value, expected_type):
            errors.append(
                f"Field '{field_name}' has type {type(value).__name__}, "
                f"expected {expected_type.__name__}"
            )

        # Custom validator if provided
        if "validator" in field_schema and value is not None:
            validator = field_schema["validator"]
            try:
                if not validator(value):
                    errors.append(f"Field '{field_name}' failed custom validation")
            except Exception as e:
                errors.append(f"Field '{field_name}' validation error: {e}")

    return len(errors) == 0, errors


def get_required_fields(schema: Dict[str, Dict[str, Any]]) -> list[str]:
    """Get list of required field names from schema."""
    return [name for name, spec in schema.items() if spec["required"]]


def get_optional_fields(schema: Dict[str, Dict[str, Any]]) -> list[str]:
    """Get list of optional field names from schema."""
    return [name for name, spec in schema.items() if not spec["required"]]


def get_default_value(schema: Dict[str, Dict[str, Any]], field_name: str) -> Any:
    """Get default value for an optional field."""
    if field_name in schema and "default" in schema[field_name]:
        return schema[field_name]["default"]
    return None


# =============================================================================
# PHASE 2: Paragraph Extraction Configuration
# =============================================================================

PARAGRAPH_CONFIG = {
    # HTML parsing
    "html_parser": "html5lib",  # Standards-compliant parser
    # Minimum paragraph length (chars) to include
    "min_paragraph_length": 10,
    # Text cleaning
    "normalize_whitespace": True,
    "strip_footnote_markers": False,  # Keep for Phase 7
    "decode_entities": True,
    # Validation thresholds (from plan)
    "min_paragraphs_warning": 3,  # Warn if fewer than 3 paragraphs
    "max_paragraphs_warning": 150,  # Warn if more than 150 paragraphs
    "min_word_count_info": 5,  # Info log if paragraph < 5 words
    "max_word_count_warning": 400,  # Warning if paragraph > 400 words
    "max_word_count_critical": 800,  # Critical if paragraph > 800 words
}


# Paragraph data schema for validation
PARAGRAPH_DATA_SCHEMA: Dict[str, Dict[str, Any]] = {
    # Identity fields
    "paragraph_id": {
        "required": True,
        "type": int,
        "description": "Unique paragraph identifier",
    },
    "talk_id": {
        "required": True,
        "type": int,
        "description": "Parent talk reference",
    },
    "paragraph_number": {
        "required": True,
        "type": int,
        "description": "1-indexed position in talk",
    },
    # Content fields
    "text": {
        "required": True,
        "type": str,
        "description": "Clean text (HTML stripped)",
    },
    "text_raw": {
        "required": False,
        "type": str,
        "default": None,
        "description": "Original HTML (for debugging/reprocessing)",
    },
    # Metrics fields
    "word_count": {
        "required": True,
        "type": int,
        "description": "Number of words in paragraph",
    },
    # List context (optional)
    "list_header": {
        "required": False,
        "type": str,
        "description": "List header text (if applicable)",
    },
    "list_item_index": {
        "required": False,
        "type": int,
        "description": "Index of item within list",
    },
    "position_in_item": {
        "required": False,
        "type": int,
        "description": "Index of paragraph within list item",
    },
    # Downstream flags (optional for now)
    "has_scripture_citation": {
        "required": False,
        "type": bool,
        "default": False,
        "description": "Whether paragraph contains scripture citations",
    },
    "has_footnote": {
        "required": False,
        "type": bool,
        "default": False,
        "description": "Whether paragraph contains footnotes",
    },
    "citation_count": {
        "required": False,
        "type": int,
        "default": 0,
        "description": "Number of citations in paragraph",
    },
    "footnote_count": {
        "required": False,
        "type": int,
        "default": 0,
        "description": "Number of footnotes in paragraph",
    },
    # Extraction metadata
    "extraction_warnings": {
        "required": False,
        "type": list,
        "default": [],
        "description": "List of warnings during extraction",
    },
}


# =============================================================================
# PHASE 3: Citation Extraction Configuration
# =============================================================================

CITATION_CONFIG = {
    "html_parser": "html.parser",
    "context_before_chars": 100,
    "context_after_chars": 100,
    "context_window_mode": "word",  # "char" or "word" (word snaps to nearest whole word within limit)
    "position_match_case_sensitive": False,
    "max_citations_per_paragraph_warning": 20,
    "batch_size": 100,
    "sqlite_max_params": 999,
    "max_verse_range": 200,
}


CITATION_DATA_SCHEMA: Dict[str, Dict[str, Any]] = {
    # Identity fields
    "citation_id": {
        "required": True,
        "type": int,
        "description": "Unique citation identifier from core.52.db",
    },
    "talk_id": {
        "required": True,
        "type": int,
        "description": "Parent talk reference",
    },
    "paragraph_id": {
        "required": True,
        "type": int,
        "description": "Parent paragraph reference",
    },
    "paragraph_number": {
        "required": True,
        "type": int,
        "description": "1-indexed position of paragraph in talk",
    },
    # Raw extraction
    "citation_text_raw": {
        "required": True,
        "type": str,
        "description": "Display text from HTML",
    },
    # Position
    "char_position": {
        "required": True,
        "type": int,
        "description": "Start char offset in clean paragraph text (-1 if not found)",
    },
    "char_end_position": {
        "required": True,
        "type": int,
        "description": "End char offset in clean paragraph text (-1 if not found)",
    },
    # Parsed fields
    "scripture_ref": {
        "required": True,
        "type": str,
        "description": "Normalized scripture reference string",
    },
    "book": {
        "required": True,
        "type": str,
        "description": "Full book name from book table",
    },
    "book_abbr": {
        "required": True,
        "type": str,
        "description": "Book citation abbreviation",
    },
    "book_id": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Book identifier from book table",
    },
    "chapter": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Chapter number",
    },
    "verses": {
        "required": False,
        "type": str,
        "default": "",
        "description": "Raw verse string from DB",
    },
    "verse_start": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Minimum verse (MinVerse from DB)",
    },
    "verse_end": {
        "required": False,
        "type": int,
        "default": None,
        "description": "Maximum verse (MaxVerse from DB)",
    },
    "verse_list": {
        "required": False,
        "type": list,
        "default": [],
        "description": "Expanded list of verse numbers",
    },
    # Classification
    "is_jst": {
        "required": False,
        "type": bool,
        "default": False,
        "description": "Whether citation is Joseph Smith Translation",
    },
    "citation_location": {
        "required": False,
        "type": str,
        "default": "inline",
        "description": "Location of citation: inline or footnote",
    },
    # Parse metadata
    "parse_success": {
        "required": False,
        "type": bool,
        "default": False,
        "description": "Whether parsing succeeded",
    },
    "parse_source": {
        "required": False,
        "type": str,
        "default": "",
        "description": "Source of parse: db_lookup or regex_fallback",
    },
    "parse_pattern": {
        "required": False,
        "type": str,
        "default": "",
        "description": "Pattern used for regex fallback",
    },
    "parse_confidence": {
        "required": False,
        "type": float,
        "default": 0.0,
        "description": "Confidence score: 1.0 for DB, 0.5-0.9 for regex",
    },
    # Context
    "context_before": {
        "required": False,
        "type": str,
        "default": "",
        "description": "Text before citation in paragraph",
    },
    "context_after": {
        "required": False,
        "type": str,
        "default": "",
        "description": "Text after citation in paragraph",
    },
    "context_window": {
        "required": False,
        "type": str,
        "default": "",
        "description": "Combined context window around citation",
    },
    # Extraction metadata
    "extraction_warnings": {
        "required": False,
        "type": list,
        "default": [],
        "description": "List of warnings during extraction",
    },
}


# =============================================================================
# PHASE 4: Footnote Extraction Configuration
# =============================================================================

FOOTNOTE_CONFIG = {
    "html_parser": "html.parser",
    "context_before_chars": 100,
    "context_after_chars": 100,
    "context_window_mode": "word",  # "char" or "word" (word snaps to nearest whole word within limit)
    "max_footnotes_per_paragraph_warning": 20,
}


FOOTNOTE_DATA_SCHEMA: Dict[str, Dict[str, Any]] = {
    # Identity fields
    "footnote_id": {
        "required": True,
        "type": int,
        "description": "talk_id * 100000 + paragraph_number * 100 + footnote_index (1-based)",
    },
    "talk_id": {
        "required": True,
        "type": int,
        "description": "Parent talk reference",
    },
    "paragraph_id": {
        "required": True,
        "type": int,
        "description": "Parent paragraph reference (talk_id * 10000 + paragraph_number)",
    },
    "paragraph_number": {
        "required": True,
        "type": int,
        "description": "1-indexed position of paragraph in talk",
    },
    # Raw extraction
    "footnote_number": {
        "required": True,
        "type": int,
        "description": "Superscript number from HTML (sequential fallback for * markers)",
    },
    "footnote_text_raw": {
        "required": True,
        "type": str,
        "description": "Full footnote text — this is what gets embedded",
    },
    # Position
    "char_position": {
        "required": True,
        "type": int,
        "description": "Char offset of marker in clean paragraph text (-1 if not found)",
    },
    # Context
    "context_before": {
        "required": False,
        "type": str,
        "default": "",
        "description": "Text before footnote marker in paragraph",
    },
    "context_after": {
        "required": False,
        "type": str,
        "default": "",
        "description": "Text after footnote marker in paragraph",
    },
    "context_window": {
        "required": False,
        "type": str,
        "default": "",
        "description": "context_before + footnote_text_raw + context_after",
    },
    # Metadata
    "parse_success": {
        "required": False,
        "type": bool,
        "default": True,
        "description": "Whether extraction succeeded",
    },
    "extraction_warnings": {
        "required": False,
        "type": list,
        "default": [],
        "description": "List of warnings during extraction",
    },
}
