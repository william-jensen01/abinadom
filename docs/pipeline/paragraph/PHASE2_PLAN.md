# Phase 2: Paragraph Segmentation — Implementation Plan

## Overview

**Goal:** Parse HTML content from the database and segment each talk into paragraphs with position tracking, producing structured data for the `conference_talk_paragraphs` ChromaDB collection.

**Input:** Talk HTML content from SQLite database (keyed by `talk_id`)
**Output:** List of `ParagraphData` dataclass instances per talk

---

## Data Structures

```python
from dataclasses import dataclass, asdict, field
from typing import Optional, List
from enum import Enum

class ParagraphType(Enum):
    """Classification of paragraph content type."""
    BODY = "body"
    SCRIPTURE_BLOCK = "scripture_block"  # Extended scripture quotation
    POEM = "poem"              # Hymn lyrics, poetry
    LIST_ITEM = "list_item"    # Bullet/numbered list content
    HEADING = "heading"        # Section headers within talk


@dataclass
class ParagraphData:
    """Represents a single paragraph extracted from a talk."""

    # Identity
    paragraph_id: int              # From database or generated: talk_id * 10000 + paragraph_number
    talk_id: int                   # Parent talk reference
    paragraph_number: int          # 1-indexed position in talk

    # Content
    text: str                      # Clean text (HTML stripped)
    text_raw: Optional[str]        # Original HTML (for debugging/reprocessing)

    # Metrics
    word_count: int
    char_count: int
    sentence_count: int

    # Classification
    paragraph_type: ParagraphType

    # Downstream flags (populated in later phases, default False)
    has_scripture_citation: bool = False
    has_footnote: bool = False
    citation_count: int = 0
    footnote_count: int = 0

    # Extraction metadata
    extraction_warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate required fields."""
        if not self.text or not self.text.strip():
            raise ValueError(f"Paragraph {self.paragraph_id} has empty text")
        if self.paragraph_number < 1:
            raise ValueError(f"Invalid paragraph_number: {self.paragraph_number}")
        if self.word_count < 0 or self.char_count < 0:
            raise ValueError("Counts cannot be negative")

    def to_dict(self) -> dict:
        """Convert to dictionary for ChromaDB metadata."""
        result = asdict(self)
        result['paragraph_type'] = self.paragraph_type.value
        return result


@dataclass
class TalkParagraphs:
    """Container for all paragraphs from a single talk."""
    talk_id: int
    paragraphs: List[ParagraphData]
    total_paragraphs: int
    total_words: int
    total_chars: int
    extraction_success: bool
    extraction_errors: List[str] = field(default_factory=list)
```

---

## Configuration Schema

```python
PARAGRAPH_CONFIG = {
    # HTML parsing
    'html_parser': 'lxml',  # or 'html.parser' as fallback

    # Elements that indicate paragraph boundaries
    'paragraph_tags': ['p', 'div.paragraph', 'div.body-block'],

    # Elements to extract but classify differently
    'special_tags': {
        'blockquote': ParagraphType.SCRIPTURE_BLOCK,
        'div.poem': ParagraphType.POEM,
        'li': ParagraphType.LIST_ITEM,
        'h2': ParagraphType.HEADING,
        'h3': ParagraphType.HEADING,
    },

    # Elements to skip entirely
    'skip_tags': ['script', 'style', 'nav', 'header', 'footer', 'aside'],

    # Minimum paragraph length (chars) to include
    'min_paragraph_length': 10,

    # Text cleaning
    'normalize_whitespace': True,
    'strip_footnote_markers': False,  # Keep for Phase 7
    'decode_entities': True,

    # Validation thresholds
    'max_paragraph_length': 10000,  # Flag unusually long paragraphs
    'expected_avg_paragraphs': 25,   # For anomaly detection
}
```

---

## Architecture: Three Layers

### Layer 1: Data Access

```python
def fetch_talk_html(db_connection, talk_id: int) -> Optional[str]:
    """Fetch raw HTML content for a single talk.

    Args:
        db_connection: SQLite connection
        talk_id: Talk identifier

    Returns:
        HTML string or None if not found
    """
    pass


def fetch_talks_html_batch(db_connection, talk_ids: List[int]) -> dict[int, str]:
    """Fetch HTML for multiple talks efficiently.

    Args:
        db_connection: SQLite connection
        talk_ids: List of talk identifiers

    Returns:
        Dict mapping talk_id -> HTML string
    """
    pass


def fetch_all_talk_ids(db_connection) -> List[int]:
    """Get all talk IDs that need processing."""
    pass
```

### Layer 2: Extraction/Transformation

```python
# --- HTML Parsing (Pure Functions) ---

def parse_html(html: str, parser: str = 'lxml') -> BeautifulSoup:
    """Parse HTML string into BeautifulSoup object."""
    pass


def extract_paragraph_elements(soup: BeautifulSoup, config: dict) -> List[Tag]:
    """Extract all paragraph-level elements from parsed HTML.

    Respects config for paragraph_tags, special_tags, skip_tags.
    Returns elements in document order.
    """
    pass


def element_to_text(element: Tag, config: dict) -> str:
    """Extract clean text from a single HTML element.

    Handles:
    - Whitespace normalization
    - Entity decoding
    - Nested tag handling
    """
    pass


def classify_paragraph_type(
    text: str,
    element: Tag,
    position: int,
    total: int,
    config: dict
) -> ParagraphType:
    """Determine paragraph type based on content and position.

    Uses element tag, text patterns, and position heuristics.
    """
    pass


# --- Metrics Calculation (Pure Functions) ---

def count_words(text: str) -> int:
    """Count words in text (handles hyphenation, contractions)."""
    pass


def count_sentences(text: str) -> int:
    """Count sentences (handles abbreviations, decimal points)."""
    pass


# --- Main Extraction Orchestration ---

def extract_paragraphs(
    talk_id: int,
    html: str,
    config: dict
) -> TalkParagraphs:
    """Extract all paragraphs from a talk's HTML.

    Main orchestration function that:
    1. Parses HTML
    2. Extracts paragraph elements
    3. Converts each to ParagraphData
    4. Classifies and annotates
    5. Returns TalkParagraphs container

    Args:
        talk_id: Talk identifier
        html: Raw HTML content
        config: Extraction configuration

    Returns:
        TalkParagraphs with all extracted paragraphs
    """
    pass
```

### Layer 3: Validation

```python
@dataclass
class ValidationResult:
    """Result of paragraph validation."""
    is_valid: bool
    errors: List[str]      # Critical issues
    warnings: List[str]    # Non-critical issues
    stats: dict            # Extraction statistics


def validate_paragraph(para: ParagraphData, config: dict) -> ValidationResult:
    """Validate a single paragraph.

    Checks:
    - Text not empty
    - Counts match actual content
    - Length within bounds
    - No encoding issues
    """
    pass


def validate_talk_paragraphs(talk_paras: TalkParagraphs, config: dict) -> ValidationResult:
    """Validate all paragraphs from a talk.

    Checks:
    - Paragraph numbers sequential (1, 2, 3...)
    - No duplicate paragraph_ids
    - Total counts match sum of individual
    - Paragraph count within expected range
    """
    pass


def detect_extraction_anomalies(talk_paras: TalkParagraphs, config: dict) -> List[str]:
    """Flag unusual patterns that might indicate extraction issues.

    Examples:
    - Very few paragraphs (< 5)
    - Very many paragraphs (> 100)
    - Extremely short average paragraph length
    """
    pass
```

---

## Processing Pipeline

```python
def process_talk_paragraphs(
    db_connection,
    talk_id: int,
    config: dict,
    strict: bool = False
) -> Tuple[Optional[TalkParagraphs], List[str]]:
    """Full pipeline for single talk.

    Args:
        db_connection: Database connection
        talk_id: Talk to process
        config: Extraction configuration
        strict: If True, fail on any validation error

    Returns:
        (TalkParagraphs or None, list of errors/warnings)
    """
    errors = []

    # Layer 1: Fetch
    html = fetch_talk_html(db_connection, talk_id)
    if not html:
        return None, [f"No HTML found for talk {talk_id}"]

    # Layer 2: Extract
    try:
        talk_paras = extract_paragraphs(talk_id, html, config)
    except Exception as e:
        return None, [f"Extraction failed: {e}"]

    # Layer 3: Validate
    validation = validate_talk_paragraphs(talk_paras, config)

    if validation.errors:
        if strict:
            return None, validation.errors
        errors.extend(validation.errors)

    if validation.warnings:
        errors.extend([f"WARNING: {w}" for w in validation.warnings])

    return talk_paras, errors


def process_all_talks(
    db_connection,
    config: dict,
    batch_size: int = 100,
    strict: bool = False
) -> Tuple[List[TalkParagraphs], dict]:
    """Process all talks with progress tracking.

    Returns:
        (list of TalkParagraphs, statistics dict)
    """
    pass
```

---

## Edge Cases & Error Handling

| Scenario                   | Handling                                 | Level   |
| -------------------------- | ---------------------------------------- | ------- |
| Missing HTML content       | Return None, log error                   | ERROR   |
| Malformed HTML             | Try fallback parser, log warning         | WARNING |
| Zero paragraphs extracted  | Return empty list, log error             | ERROR   |
| Empty paragraph text       | Skip paragraph, log warning              | WARNING |
| Extremely long paragraph   | Include but flag, log warning            | WARNING |
| Encoding issues (mojibake) | Attempt decode, flag if fails            | WARNING |
| Nested blockquotes         | Flatten, preserve text                   | INFO    |
| Tables in content          | Extract cell text as separate paragraphs | INFO    |

---

## Testing Strategy

### Unit Tests

```python
class TestTextExtraction:
    def test_simple_paragraph(self):
        """Basic p tag extraction."""
        html = "<p>Hello world.</p>"
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)
        assert len(result.paragraphs) == 1
        assert result.paragraphs[0].text == "Hello world."

    def test_multiple_paragraphs(self):
        """Multiple p tags with position tracking."""
        pass

    def test_nested_tags_stripped(self):
        """<p><strong>Bold</strong> text</p> -> 'Bold text'"""
        pass

    def test_whitespace_normalization(self):
        """Multiple spaces/newlines collapsed."""
        pass

    def test_entity_decoding(self):
        """&amp; -> &, &ldquo; -> ", etc."""
        pass


class TestParagraphClassification:
    def test_scripture_block(self):
        """Blockquote classified as SCRIPTURE_BLOCK."""
        pass

    def test_heading_classification(self):
        """h2/h3 tags classified as HEADING."""
        pass


class TestMetrics:
    def test_word_count_simple(self):
        assert count_words("Hello world") == 2

    def test_word_count_hyphenated(self):
        assert count_words("well-known fact") == 2  # or 3?

    def test_word_count_contractions(self):
        assert count_words("don't won't") == 2

    def test_sentence_count(self):
        assert count_sentences("Hello. World!") == 2

    def test_sentence_count_abbreviations(self):
        assert count_sentences("Dr. Smith went home.") == 1


class TestValidation:
    def test_sequential_numbering(self):
        """Paragraph numbers must be 1, 2, 3..."""
        pass

    def test_duplicate_id_detection(self):
        """Duplicate paragraph_ids flagged."""
        pass

    def test_anomaly_detection_few_paragraphs(self):
        """< 5 paragraphs flagged as anomaly."""
        pass


class TestEdgeCases:
    def test_empty_html(self):
        pass

    def test_malformed_html(self):
        pass

    def test_no_paragraph_tags(self):
        """Plain text without <p> tags."""
        pass

    def test_unicode_content(self):
        """Non-ASCII characters handled correctly."""
        pass
```

### Integration Tests

```python
class TestPhase2Integration:
    def test_real_talk_extraction(self, db_connection):
        """Extract paragraphs from actual database talk."""
        pass

    def test_batch_processing(self, db_connection):
        """Process multiple talks efficiently."""
        pass

    def test_phase1_compatibility(self):
        """Output talk_id matches Phase 1 TalkMetadata."""
        pass
```

---

## Integration with Phase 1

```python
# Phase 1 outputs TalkMetadata with talk_id
# Phase 2 uses same talk_id, adds paragraph data

def enrich_talk_metadata_with_paragraph_stats(
    talk_metadata: TalkMetadata,  # From Phase 1
    talk_paragraphs: TalkParagraphs  # From Phase 2
) -> TalkMetadata:
    """Update talk metadata with paragraph statistics.

    Adds:
    - total_paragraphs
    - total_words (sum of paragraph words)
    - total_chars
    """
    talk_metadata.total_paragraphs = talk_paragraphs.total_paragraphs
    talk_metadata.total_words = talk_paragraphs.total_words
    talk_metadata.total_chars = talk_paragraphs.total_chars
    return talk_metadata
```

---

## Output Format (for Phase 13 ChromaDB Prep)

```python
def paragraphs_to_chromadb_format(
    all_talk_paragraphs: List[TalkParagraphs]
) -> Tuple[List[str], List[dict], List[str]]:
    """Convert extracted paragraphs to ChromaDB insertion format.

    Returns:
        documents: List of paragraph texts (for embedding)
        metadatas: List of metadata dicts
        ids: List of paragraph IDs as strings
    """
    documents = []
    metadatas = []
    ids = []

    for talk_paras in all_talk_paragraphs:
        for para in talk_paras.paragraphs:
            documents.append(para.text)
            metadatas.append(para.to_dict())
            ids.append(f"para_{para.paragraph_id}")

    return documents, metadatas, ids
```

---

## Implementation Order

1. **Data structures** — Define `ParagraphData`, `TalkParagraphs` dataclasses
2. **Configuration** — Set up `PARAGRAPH_CONFIG` with HTML parsing rules
3. **Pure functions** — Implement text extraction, metrics, classification
4. **Data access** — Implement database fetch functions
5. **Validation** — Implement validation and anomaly detection
6. **Pipeline** — Wire together into `process_talk_paragraphs`
7. **Tests** — Unit tests for each function, integration tests
8. **Batch processing** — Add progress tracking, batch efficiency

---

## Estimated Complexity

| Component      | Effort        | Notes                            |
| -------------- | ------------- | -------------------------------- |
| Dataclasses    | Low           | Straightforward                  |
| HTML parsing   | Medium        | BeautifulSoup, handle edge cases |
| Text cleaning  | Medium        | Whitespace, entities, encoding   |
| Classification | Medium        | Pattern matching, heuristics     |
| Validation     | Low           | Straightforward checks           |
| Testing        | Medium        | Many edge cases to cover         |
| **Total**      | **~2-3 days** |                                  |

---

Want me to start implementing any specific component?
