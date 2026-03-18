# Phase 4: Footnote Extraction Plan

## Context

Phase 4 extracts footnotes from General Conference talk HTML as "see also" markers. Phases 1-3 (metadata, paragraphs, citations) are complete. Phase 3 already captures scripture citations found within footnotes — phase 4 captures ALL footnotes (including scripture-only ones) with their full raw text for embedding. No type-specific parsing (no conference_talk/book/hymn classification). The full footnote text is the data to be embedded.

## HTML Structure (from real data)

```html
<!-- Standard pattern: noteMarker > anchor > footnote span -->
<sup class="noteMarker">
  <a href="#footnote1-03006_000_028">1</a>
  <span class="footnote">[John Ruskin, "Little Brass Nails."]</span>
</sup>

<!-- With emphasis inside footnote text -->
<sup class="noteMarker">
  <a href="#footnote3-03006_000_028">3</a>
  <span class="footnote">[Juvenal, <span class="emphasis">Satires, </span>xiii.]</span>
</sup>

<!-- Asterisk marker (older talks) -->
<sup class="noteMarker">
  <a href="#footnoteSTAR-03006_000_025">*</a>
  <span class="footnote">[Fast day was regularly observed...]</span>
</sup>

<!-- Multiple footnotes in one paragraph (DeMille + Marcus Aurelius) -->
<p>...DeMille said: "..."<sup class="noteMarker">
  <a href="#footnote4">4</a>
  <span class="footnote">[Cecil B. DeMille, BYU Address, 1957.]</span>
</sup> O let us think... Marcus Aurelius, "..."<sup class="noteMarker">
  <a href="#footnote5">5</a>
  <span class="footnote">[Marcus Aurelius, <span class="emphasis">Meditations</span>...]</span>
</sup></p>

<!-- Scripture citation in noteMarker (phase 3 also captures these) -->
<sup class="noteMarker">
  <span class="citation" id="7">Mosiah 2:17</span>
</sup>
```

## Files to Create

| File | Purpose |
|------|---------|
| `models/footnote_data.py` | FootnoteData + TalkFootnotes dataclasses |
| `extractors/phase4_footnote_extraction.py` | 3-layer extractor |
| `tests/test_phase4.py` | Unit + integration tests |
| `examples/phase4_example.py` | Runnable example against real DB |

## Files to Modify

| File | Change |
|------|--------|
| `config/schemas.py` | Add FOOTNOTE_CONFIG + FOOTNOTE_DATA_SCHEMA |

## Step 1: Config (`config/schemas.py`)

Add after CITATION_DATA_SCHEMA:

```python
FOOTNOTE_CONFIG = {
    "html_parser": "html.parser",
    "context_before_chars": 100,
    "context_after_chars": 100,
    "context_window_mode": "word",
    "max_footnotes_per_paragraph_warning": 20,
}
```

Add FOOTNOTE_DATA_SCHEMA with fields matching the dataclass (same pattern as CITATION_DATA_SCHEMA).

## Step 2: Data Model (`models/footnote_data.py`)

### FootnoteData

```
Identity:
  footnote_id: int       # talk_id * 100000 + paragraph_number * 100 + footnote_index (1-based)
  talk_id: int
  paragraph_id: int      # talk_id * 10000 + paragraph_number
  paragraph_number: int   # 1-indexed

Raw extraction:
  footnote_number: int    # Superscript number (sequential fallback for * markers)
  footnote_text_raw: str  # Full footnote text (THIS is what gets embedded)

Position:
  char_position: int      # Where marker appears in clean text (-1 if not found)

Context:
  context_before: str
  context_after: str
  context_window: str     # context_before + footnote_text_raw + context_after

Metadata:
  parse_success: bool = True
  extraction_warnings: List[str]
```

**Validation (`__post_init__`):** footnote_id > 0, paragraph_number >= 1, footnote_number >= 1, footnote_text_raw not empty.

**Methods:** `to_dict()`, `to_chromadb_format()` (document = context_window or footnote_text_raw), `__repr__`

### TalkFootnotes

Mirror TalkCitations: talk_id, footnotes list, total_footnotes, extraction_success, extraction_errors. Validate count match in `__post_init__`.

## Step 3: Extractor (`extractors/phase4_footnote_extraction.py`)

3-layer architecture. No Layer 1 (no DB access needed — footnotes are entirely in HTML).

> **Note:** Footnote type classification (conference_talk, book, hymn, etc.) is intentionally deferred. Phase 4 extracts raw footnote text only.

### Layer 2: Extraction

**2a. `extract_footnotes_from_paragraph(paragraph, config) -> List[Dict]`**

1. Parse `paragraph.text_raw` with BeautifulSoup
2. Find all `<sup class="noteMarker">` elements
3. For each noteMarker:
   - Extract footnote number from `<a>` tag text (handle `*` → assign sequential number, add warning)
   - Extract footnote text: prefer `<span class="footnote">` child's `get_text()`, fall back to `<span class="citation">` child's `get_text()`, then full sup `get_text()`
   - Return `{footnote_number, footnote_text_raw, element_index}`
4. Warn if count exceeds threshold

**2b. Position calculation**

```python
from extractors.html_parsing_utils import (
    ELEMENT_PLACEHOLDER,
    filter_paragraph_around_anchor,
    apply_context_window,
)

def _build_filtered_paragraph_for_footnote(text_raw, footnote_index, parser="html.parser"):
    soup = BeautifulSoup(text_raw, parser)
    markers = soup.find_all("sup", class_="noteMarker")
    if footnote_index < 0 or footnote_index >= len(markers):
        for m in markers:
            m.decompose()
        return soup.get_text(strip=True), ""
    target = markers[footnote_index]
    fn_span = target.find("span", class_=lambda c: c and "footnote" in c)
    footnote_text = fn_span.get_text(strip=True) if fn_span else ""
    if not footnote_text:
        cit_span = target.find("span", class_="citation")
        if cit_span:
            footnote_text = cit_span.get_text(strip=True)
    # noteMarker IS the anchor — no _find_position_anchor needed
    filtered = filter_paragraph_around_anchor(soup, target, ELEMENT_PLACEHOLDER)
    return filtered, footnote_text
```

Footnote-specific version: locates by index among `<sup class="noteMarker">` elements (no unique IDs on footnotes). Uses `filter_paragraph_around_anchor` from shared utilities.

```python
def calculate_footnote_position(text_raw, footnote_index, config) -> int:
```

Single `char_position` (not start/end pair — markers are point insertions, not text spans).

**2c. `extract_footnote_context_window(text_raw, footnote_index, footnote_text_raw, config) -> (before, after, window)`**

```python
def extract_footnote_context_window(text_raw, footnote_index, footnote_text_raw, config):
    parser = config.get("html_parser", "html.parser")
    filtered, _ = _build_filtered_paragraph_for_footnote(text_raw, footnote_index, parser)
    return apply_context_window(filtered, ELEMENT_PLACEHOLDER, footnote_text_raw, config)
```

Uses `apply_context_window` from shared utilities — no duplicated logic.

### Layer 3: Validation

**`validate_footnote(footnote, config) -> List[str]`**
- Warn if footnote_text_raw < 3 chars
- Warn if char_position == -1
- Warn if context_window empty when position valid

**`validate_talk_footnotes(talk_footnotes, config) -> ValidationResult`**
- Check sequential footnote_number (warn on gaps)
- Per-footnote validation
- Stats: total, position_found_rate

### Orchestration

**`process_talk_footnotes(talk_id, paragraphs, config) -> (TalkFootnotes, List[str])`**

1. For each paragraph with text_raw:
   - Detect footnotes → calculate positions → extract context windows → build FootnoteData
   - **Set paragraph flags during extraction** (same pattern as Phase 3): `has_footnote = True`, `footnote_count = N`
   - Phase 5 validates these flags, not re-calculates them
2. Build TalkFootnotes container
3. Return with warnings

## Reuse from Shared Utilities

| What | Source | Notes |
|------|--------|-------|
| `ELEMENT_PLACEHOLDER` | `extractors.html_parsing_utils` | Null-byte placeholder constant |
| `_find_position_anchor` | `extractors.html_parsing_utils` | NOT needed for footnotes — noteMarker is already the anchor |
| `_snap_to_word_boundaries` | `extractors.html_parsing_utils` | Used internally by `apply_context_window` |
| `filter_paragraph_around_anchor` | `extractors.html_parsing_utils` | Replace anchor + decompose other noteMarkers |
| `apply_context_window` | `extractors.html_parsing_utils` | Full context window extraction from filtered text |
| `ValidationResult` | `models.paragraph_data` | Import for validation return type |

## Step 4: Tests (`tests/test_phase4.py`)

### Test Classes

**TestFootnoteDetection:**
- Single noteMarker with footnote span (standard pattern)
- noteMarker with citation span (scripture-in-footnote)
- Multiple footnotes in one paragraph
- No footnotes returns empty list
- Asterisk marker → sequential number + warning
- Footnote text with `<span class="emphasis">` inside
- No text_raw → empty list

**TestFootnotePosition:**
- Single marker position in clean text
- First of multiple markers selected by index
- Index out of range → -1
- Filtered paragraph removes other markers

**TestContextWindow:**
- Basic before/after extraction
- Word boundary snapping
- Marker near paragraph start/end
- Window = context_before + footnote_text_raw + context_after

**TestFootnoteData:**
- Valid creation
- Empty text raises ValueError
- Invalid paragraph_number raises ValueError
- to_dict round-trip
- to_chromadb_format: document = context_window or footnote_text_raw

**TestTalkFootnotes:**
- Valid container
- Count mismatch raises ValueError

**TestValidation:**
- Happy path (no issues)
- Short text warning
- Sequential numbering (no warnings)
- Gap in numbering (warning)

**TestOrchestration (integration):**
- Full pipeline with crafted paragraphs
- Paragraph flags updated (has_footnote, footnote_count)
- Talk with no footnotes → empty TalkFootnotes

## Verification

1. Run `pipenv run py -m pytest tests/test_phase4.py -v` — all tests pass
2. Run `pipenv run py examples/phase4_example.py` against real DB to inspect output on known talks
3. Verify paragraph flags (has_footnote, footnote_count) are set correctly
4. Spot-check context windows on talks with known footnotes (e.g., the Ruskin "Little Brass Nails" talk)
5. Verify asterisk-marker talks produce valid output with warnings
