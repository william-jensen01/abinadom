# Phase 2: Paragraph Segmentation - Implementation Summary

## Overview

Phase 2 extracts and segments General Conference talk HTML into structured paragraphs with position tracking, producing data ready for ChromaDB insertion.

**Status**: ✅ Complete and tested

## Quick Start

### Run Example

```bash
# Extract paragraphs from sample talks
pipenv run python examples/phase2_example.py
```

### Extract Paragraphs from Single Talk

```python
from extractors.phase2_paragraph_extraction import process_talk_paragraphs
from db import content_db
from config.schemas import PARAGRAPH_CONFIG

# Process a talk
talk_paras, errors = process_talk_paragraphs(
    content_db,
    talk_id=1,
    config=PARAGRAPH_CONFIG
)

print(f"Extracted {talk_paras.total_paragraphs} paragraphs")
print(f"Total words: {talk_paras.total_words}")
```

### Extract for ChromaDB

```python
from extractors.phase2_paragraph_extraction import extract_paragraphs_for_chromadb

# Extract paragraphs from all talks and prepare for ChromaDB
documents, metadatas, ids = extract_paragraphs_for_chromadb(limit=None)

# Ready to insert into ChromaDB
# collection.add(documents=documents, metadatas=metadatas, ids=ids)
```

## Architecture

### Three-Layer Design

```
┌─────────────────────────────────────────────┐
│           Database Layer                     │
│  - fetch_talk_html()                        │
│  - fetch_talks_html_batch()                 │
│  - fetch_all_talk_ids()                     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│      Extraction/Transformation Layer        │
│  - parse_html()                             │
│  - extract_paragraph_elements()             │
│  - element_to_text()                        │
│  - count_words(), count_sentences()         │
│  - determine_paragraph_type()               │
│  - is_opening_paragraph()                   │
│  - is_closing_paragraph()                   │
│  - extract_paragraphs()                     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│           Validation Layer                   │
│  - validate_paragraph()                     │
│  - validate_talk_paragraphs()               │
│  - detect_extraction_anomalies()            │
└─────────────────────────────────────────────┘
```

## Data Structures

### ParagraphData

Represents a single paragraph with:
- **Identity**: `paragraph_id`, `talk_id`, `paragraph_number`
- **Content**: `text`, `text_raw` (original HTML)
- **Metrics**: `word_count`, `char_count`, `sentence_count`
- **Classification**: `paragraph_type`, `is_opening`, `is_closing`
- **Metadata**: `extraction_warnings`

### ParagraphType Enum

```python
class ParagraphType(Enum):
    BODY = "body"                        # Standard paragraph
    OPENING = "opening"                  # First substantive paragraph
    CLOSING = "closing"                  # Final paragraph (testimony)
    SCRIPTURE_BLOCK = "scripture_block"  # Extended scripture quotation
    POEM = "poem"                        # Hymn lyrics, poetry
    LIST_ITEM = "list_item"              # Bullet/numbered list
    HEADING = "heading"                  # Section headers
```

### TalkParagraphs

Container for all paragraphs from a talk:
- `talk_id`: Parent talk reference
- `paragraphs`: List of ParagraphData instances
- `total_paragraphs`, `total_words`, `total_chars`: Aggregate metrics
- `extraction_success`: Boolean flag
- `extraction_errors`: List of errors/warnings

## Configuration

Configuration is defined in `config/schemas.py`:

```python
PARAGRAPH_CONFIG = {
    # HTML parsing
    'html_parser': 'lxml',  # Fallback to 'html.parser'

    # Paragraph detection
    'paragraph_tags': ['p', 'div.paragraph', 'div.body-block'],

    # Special element types
    'special_tags': {
        'blockquote': ParagraphType.SCRIPTURE_BLOCK,
        'li': ParagraphType.LIST_ITEM,
        'h2': ParagraphType.HEADING,
        # ... more
    },

    # Elements to skip
    'skip_tags': ['script', 'style', 'nav', 'header', 'footer'],

    # Text cleaning
    'normalize_whitespace': True,
    'min_paragraph_length': 10,

    # Classification patterns
    'opening_patterns': [
        r'^(My )?[Dd]ear (brothers and sisters|friends)',
        r'^(President|Brothers and sisters)',
    ],
    'closing_patterns': [
        r'[Ii]n the name of Jesus Christ',
        r'[Aa]men\.?\s*$',
    ],
}
```

## Key Functions

### Data Access

**`fetch_talk_html(db, talk_id)`**
- Fetches HTML content for a single talk from database
- Tries `TextRaw` first, falls back to `TextSimple`
- Returns HTML string or None

### Extraction

**`extract_paragraphs(talk_id, html, config)`**
- Main orchestration function
- Parses HTML → extracts elements → creates ParagraphData instances
- Returns TalkParagraphs container

**`parse_html(html, parser='lxml')`**
- Parses HTML using BeautifulSoup
- Falls back to 'html.parser' if lxml unavailable

**`element_to_text(element, config)`**
- Extracts clean text from HTML element
- Normalizes whitespace, decodes entities

### Classification

**`determine_paragraph_type(element, config)`**
- Classifies paragraph based on HTML tag
- Maps special tags to ParagraphType enum

**`is_opening_paragraph(text, position, config)`**
- Detects opening paragraphs using regex patterns
- Must be in first 3 paragraphs

**`is_closing_paragraph(text, position, total, config)`**
- Detects closing paragraphs using regex patterns
- Must be in last 3 paragraphs

### Validation

**`validate_paragraph(para, config)`**
- Validates single paragraph for:
  - Non-empty text
  - Accurate counts
  - Reasonable length

**`validate_talk_paragraphs(talk_paras, config)`**
- Validates entire talk:
  - Sequential numbering
  - No duplicate IDs
  - Totals match sums
  - Opening/closing detected

**`detect_extraction_anomalies(talk_paras, config)`**
- Flags unusual patterns:
  - Too few paragraphs (< 5)
  - Too many paragraphs (> 100)
  - Very short average length
  - Missing opening/closing

## Pipeline

### Single Talk Processing

```python
talk_paras, errors = process_talk_paragraphs(
    db=content_db,
    talk_id=123,
    config=PARAGRAPH_CONFIG,
    strict=False  # True = fail on validation errors
)
```

Returns:
- `talk_paras`: TalkParagraphs object or None
- `errors`: List of error/warning messages

### Batch Processing

```python
all_talk_paragraphs, stats = process_all_talks(
    db=content_db,
    config=PARAGRAPH_CONFIG,
    batch_size=100,  # Progress reporting interval
    strict=False
)
```

Returns:
- `all_talk_paragraphs`: List of TalkParagraphs
- `stats`: Dictionary with:
  - `total_talks`, `successful`, `errors`, `warnings`
  - `elapsed_seconds`
  - `total_paragraphs`, `total_words`, `total_chars`

### ChromaDB Preparation

```python
documents, metadatas, ids = paragraphs_to_chromadb_format(
    all_talk_paragraphs
)
```

Converts to ChromaDB insertion format:
- `documents`: Paragraph texts (for embedding)
- `metadatas`: Metadata dicts
- `ids`: Paragraph IDs as strings (`para_{paragraph_id}`)

## Command-Line Interface

```bash
# Extract single talk
pipenv run python extractors/phase2_paragraph_extraction.py --talk-id 1

# Extract limited number of talks
pipenv run python extractors/phase2_paragraph_extraction.py --limit 10

# Skip validation
pipenv run python extractors/phase2_paragraph_extraction.py --no-validate

# Show statistics only
pipenv run python extractors/phase2_paragraph_extraction.py --stats
```

## Testing

### Unit Tests

Located in `tests/test_phase2.py` (requires pytest):

```bash
# Run all tests
pipenv run pytest tests/test_phase2.py -v

# Run specific test class
pipenv run pytest tests/test_phase2.py::TestHTMLParsing -v
```

Test coverage:
- ✅ HTML parsing (simple, empty, malformed)
- ✅ Text extraction (nested tags, whitespace)
- ✅ Paragraph classification (opening, closing, types)
- ✅ Metrics calculation (words, sentences)
- ✅ Validation (individual paragraphs, entire talks)
- ✅ Edge cases (Unicode, very long paragraphs)

### Example Script

```bash
pipenv run python examples/phase2_example.py
```

Demonstrates:
1. Single talk extraction
2. Multiple talk processing (limit=10)
3. Paragraph type distribution

## Example Output

```
=== Talk 1 ===
Total paragraphs: 120
Total words: 5485
Total characters: 28155
Extraction success: True

First paragraph:
  ID: 10001
  Type: body
  Word count: 6
  Text: Personal Testimony of the Lord's Providence...

Last paragraph:
  ID: 10120
  Type: closing
  Text: God bless us by His Spirit always...
```

## Integration with Other Phases

### Phase 1 (Talk Metadata)

Phase 2 uses `talk_id` from Phase 1 to link paragraphs to talks:

```python
from extractors.phase1_talk_metadata import extract_all_talk_metadata
from extractors.phase2_paragraph_extraction import process_talk_paragraphs

# Get talk metadata from Phase 1
talks = extract_all_talk_metadata(core_db)

# Extract paragraphs for each talk
for talk in talks:
    paragraphs, errors = process_talk_paragraphs(
        content_db,
        talk.talk_id,
        PARAGRAPH_CONFIG
    )
```

### Phase 13 (ChromaDB Insertion)

Phase 2 output format matches ChromaDB requirements:

```python
# Phase 2: Extract and format
documents, metadatas, ids = extract_paragraphs_for_chromadb()

# Phase 13: Insert into ChromaDB
collection.add(
    documents=documents,
    metadatas=metadatas,
    ids=ids
)
```

## Performance

Based on testing with real database data:

- **Single talk**: ~0.02s per talk
- **10 talks**: ~0.24s total (373 paragraphs)
- **All talks (7659)**: Estimated ~3-5 minutes

Bottleneck: HTML parsing (BeautifulSoup)

## Extracted Statistics (Sample: 10 talks)

- **Total paragraphs**: 373
- **Paragraph types**:
  - Body: 97.1%
  - Closing: 2.4%
  - Opening: 0.5%

## Known Issues & Limitations

1. **lxml parser**: Not installed by default, falls back to html.parser
   - Install: `pipenv install lxml` (optional, faster)

2. **TextRaw availability**: Some talks may not have HTML in TextRaw field
   - Fallback: Uses TextSimple wrapped in `<div>` tags

3. **Opening/Closing detection**: Regex-based, may miss variations
   - Future: Could use ML-based classification

4. **Paragraph count anomalies**: Some talks have 100+ paragraphs
   - Cause: Fine-grained HTML structure or list items
   - Not an error, just flagged as anomaly

## Files Created

```
models/
  └── paragraph_data.py        # Data structures

config/
  └── schemas.py               # Updated with PARAGRAPH_CONFIG

extractors/
  └── phase2_paragraph_extraction.py   # Main extraction module

tests/
  └── test_phase2.py           # Unit tests

examples/
  └── phase2_example.py        # Usage examples

PHASE2_README.md               # This file
```

## Next Steps (Phase 3+)

1. **Phase 3**: Citation Detection - Identify which paragraphs contain scripture citations
2. **Phase 4**: Raw Citation Extraction - Extract citation strings
3. **Phase 5**: Citation Parsing - Parse citations into structured fields
4. **Phase 6**: Citation Context Extraction - Extract surrounding text

## Dependencies

- `beautifulsoup4>=4.12.0` (required)
- `lxml` (optional, for faster parsing)

Install: `pipenv install`

## Credits

Implemented following the design philosophy and patterns established in Phase 1, with emphasis on:
- Layered architecture
- Pure functions
- Type safety with dataclasses
- Configuration-driven design
- Defensive programming
- Comprehensive testing
