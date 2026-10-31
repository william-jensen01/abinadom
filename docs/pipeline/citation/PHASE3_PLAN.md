# Phase 3: Citation Extraction & Parsing — Implementation Plan

## Context

Phases 1 (metadata) and 2 (paragraph segmentation) are complete. Phase 3 detects scripture citations in talk HTML, resolves them via the `core.52.db` citation/book tables, and produces structured `CitationData` objects with context windows — ready for the `conference_talk_citations` ChromaDB collection.

**Key insight:** Every citation has a `<span class="citation" id="X">` HTML tag. That `id` maps directly to `citation.ID` in `core.52.db`, which already stores BookID, Chapter, Verses, MinVerse, MaxVerse. BookID maps to the `book` table (99 rows) with FullName, CiteAbbr, JSTTitle, etc. So the primary path is **HTML tag detection → DB lookup**, not regex parsing.

---

## Prerequisite: Update Phase 2 to Populate `text_raw`

Phase 2 currently sets `text_raw=None` (line 914 of `paragraphs.py`). Phase 3 needs the paragraph's raw HTML to scan for `<span class="citation">` tags.

**Fix:** In `extract_semantic_paragraphs()`, the BS4 `element` is already available at each point where paragraphs are appended. Store `str(element)` (the element's outer HTML) in the paragraph dict, then pass it through to `ParagraphData.text_raw`.

**Changes in `extractors/paragraphs.py`:**

1. In `extract_semantic_paragraphs()` — add `"text_raw": str(element)` to each paragraph dict:
    - Line ~670 (stanza): add `"text_raw": str(element)` to the dict
    - Line ~698 (standard `<p>`): add `"text_raw": str(element)` to the dict
    - Line ~689 (list): `extract_list()` returns dicts — add `text_raw` there too
    - Line ~740 (bare text / other): add `"text_raw": str(element)` to the dict

2. In `extract_paragraphs()` line 914: change `text_raw=None` to `text_raw=para_dict.get("text_raw")`

This is a small, backwards-compatible change — `text_raw` was already defined as `Optional[str]` with default `None`.

---

## Files to Create

| File                                       | Purpose                                      |
| ------------------------------------------ | -------------------------------------------- |
| `models/citation_data.py`                  | `CitationData` + `TalkCitations` dataclasses |
| `extractors/citations.py` | Main extractor (3-layer architecture)        |
| `tests/test_citations.py`                     | Unit + integration tests                     |

## Files to Modify

| File                                        | Change                                            |
| ------------------------------------------- | ------------------------------------------------- |
| `extractors/paragraphs.py` | Populate `text_raw` with paragraph HTML           |
| `config/schemas.py`                         | Append `CITATION_CONFIG` + `CITATION_DATA_SCHEMA` |

---

## Step 1: CitationData Dataclass

**File:** `models/citation_data.py`

Following `models/paragraph_data.py` pattern exactly.

```python
@dataclass
class CitationData:
    # Identity
    citation_id: int          # From core.52.db citation.ID (= HTML span id)
    talk_id: int
    paragraph_id: int         # talk_id * 10000 + paragraph_number
    paragraph_number: int     # 1-indexed

    # Raw extraction
    citation_text_raw: str    # Display text from HTML (e.g., "D&C 84:32-44")

    # Position in paragraph clean text
    char_position: int        # Start offset (-1 if not found)
    char_end_position: int    # End offset (-1 if not found)

    # Parsed fields (primary source: DB lookup)
    scripture_ref: str        # Normalized: "Doctrine and Covenants 84:32-44"
    book: str                 # FullName from book table
    book_abbr: str            # CiteAbbr from book table
    book_id: Optional[int]
    chapter: Optional[int]
    verses: str               # Raw from DB: "32-44", "3,5,7"
    verse_start: Optional[int]  # MinVerse
    verse_end: Optional[int]    # MaxVerse
    verse_list: List[int]       # Expanded: [32,33,...,44]

    # Classification
    is_jst: bool = False
    citation_location: str = "inline"  # "inline" or "footnote"

    # Parse metadata
    parse_success: bool = False
    parse_source: str = ""       # "db_lookup" or "regex_fallback"
    parse_pattern: str = ""
    parse_confidence: float = 0.0  # 1.0 for DB, 0.5-0.9 for regex

    # Context
    context_before: str = ""
    context_after: str = ""
    context_window: str = ""

    extraction_warnings: List[str] = field(default_factory=list)
```

Methods: `__post_init__()` validation, `to_dict()`, `to_chromadb_format()`, `__repr__()`.

```python
@dataclass
class TalkCitations:
    talk_id: int
    citations: List[CitationData]
    total_citations: int
    extraction_success: bool
    extraction_errors: List[str] = field(default_factory=list)
```

Reuse `ValidationResult` from `models/paragraph_data.py`.

---

## Step 2: Configuration Schema

**File:** `config/schemas.py` (append after line 351)

```python
CITATION_CONFIG = {
    "html_parser": "html.parser",
    "context_before_chars": 100,
    "context_after_chars": 100,
    "position_match_case_sensitive": False,
    "max_citations_per_paragraph_warning": 20,
    "batch_size": 100,
    "sqlite_max_params": 999,
    "max_verse_range": 200,
}
```

Plus `CITATION_DATA_SCHEMA` dict with field definitions matching the dataclass.

---

## Step 3: Extractor Module (3-Layer Architecture)

**File:** `extractors/citations.py`

### Layer 1: Database Access

| Function                                             | Purpose                                      |
| ---------------------------------------------------- | -------------------------------------------- |
| `fetch_all_books(db) -> Dict[int, Row]`              | Load all 99 books into cache (called once)   |
| `fetch_citations_for_talk(db, talk_id) -> List[Row]` | All citation rows for a talk from core.52.db |

Book cache is loaded once at startup since it's only 99 rows. Citation rows are fetched per-talk using `WHERE TalkID = ?` — this gives us both the lookup data and cross-validation baseline.

### Layer 2: Extraction

**2a. HTML Citation Detection (per paragraph)**

`extract_citations_from_paragraph(paragraph: ParagraphData, config) -> List[Dict]`

- Parse `paragraph.text_raw` (HTML) with BeautifulSoup
- Find all `<span class="citation" id="X">` elements within this paragraph
- For each: extract `id` (int), display text (from inner `<a onclick="gs(...)">` or direct text)
- Determine location: check if citation is inside a `<span class="footnote">` ancestor → "footnote", else "inline"
- No paragraph mapping needed — we already know which paragraph we're in

**2b. DB Resolution**

`resolve_citation_from_db(citation_id, citation_rows_cache, book_cache) -> Dict`

- Look up citation_id in pre-fetched citation rows for this talk
- Look up BookID in book cache for names
- Build normalized `scripture_ref` string
- Detect JST via `book.JSTTitle`
- Set `parse_success=True, parse_source="db_lookup", parse_confidence=1.0`

**2c. Verse Expansion**

`expand_verses(verses_str) -> List[int]`

- `"3"` → `[3]`
- `"3-10"` or `"3–10"` → `[3,4,...,10]` (handle en-dash)
- `"3,5,7"` → `[3,5,7]`
- `"3-5,8,10-12"` → `[3,4,5,8,10,11,12]`
- Non-numeric parts skipped with warning

**2d. Position Calculation**

`calculate_citation_position(clean_text, display_text) -> Tuple[int, int]`

- Use `find_all_occurrences()` from `tools/text_processing.py`
- Single match → return position
- Multiple matches → use context to disambiguate
- No match → return (-1, -1)

**2e. Context Windows**

`extract_context_window(clean_text, char_start, char_end, config) -> Tuple[str, str, str]`

- Extract 100 chars before and after citation in clean text
- Handle paragraph boundaries (clamp to 0 / len)
- Returns (context_before, context_after, context_window)

### Layer 3: Validation

| Function                                                 | Purpose                                                                 |
| -------------------------------------------------------- | ----------------------------------------------------------------------- |
| `validate_citation(citation, config)`                    | Single citation: valid ID, non-empty text, position bounds, verse range |
| `validate_talk_citations(talk_citations, config)`        | Talk level: duplicate IDs, parse success rate, stats                    |
| `cross_validate_with_db(talk_id, extracted_ids, db_ids)` | Compare HTML citations vs DB expected citations                         |

### Orchestration

`process_talk_citations(core_db, talk_id, paragraphs, book_cache, config) -> Tuple[TalkCitations, List[str]]`

Pipeline per talk:

1. Fetch all citation DB rows for this talk from core.52.db (batch)
2. For each ParagraphData: scan `text_raw` for `<span class="citation">` tags
3. For each citation found: resolve via DB lookup, calculate position in `text`, extract context
4. Build CitationData objects
5. Validate + cross-validate (extracted IDs vs DB expected IDs)
6. Update paragraph flags (`has_scripture_citation`, `citation_count`)

`process_all_citations(limit=None) -> List[TalkCitations]`

Batch processing with progress tracking. Requires Phase 2 to run first to get ParagraphData with `text_raw`.

`extract_citations_for_chromadb(limit=None) -> Tuple[List[str], List[Dict], List[str]]`

Final output in ChromaDB format (documents, metadatas, ids).

---

## Step 4: Paragraph Flag Updates

Phase 3 populates the downstream flags on ParagraphData:

```python
def update_paragraph_citation_flags(paragraphs, citations):
    # Group citations by paragraph_id
    # Set has_scripture_citation = True, citation_count = N
```

---

## Step 5: Tests

**File:** `tests/test_citations.py`

| Test Class                | Coverage                                                                                         |
| ------------------------- | ------------------------------------------------------------------------------------------------ |
| `TestCitationDetection`   | Find spans in paragraph HTML, location classification, display text extraction, entity decoding  |
| `TestVerseExpansion`      | Single, range, list, mixed, empty, en-dash                                                       |
| `TestDBLookup`            | Existing/missing citations, book resolution, JST detection                                       |
| `TestPositionCalculation` | Single match, no match, disambiguation                                                           |
| `TestContextWindow`       | Normal, paragraph start/end boundaries, invalid position                                         |
| `TestValidation`          | Valid/invalid citations, verse range, cross-validation                                           |
| `TestIntegration`         | Real DB: process talk 1059 (4 citations), talk with footnote citations, talk with zero citations |

---

## Edge Cases

- **Citation ID not in DB:** Regex fallback on display text, lower confidence
- **Duplicate citation IDs in same talk:** Each HTML occurrence = separate CitationData
- **`<span class="footnote long">`:** Has NO citation tags — ignored (Phase 4)
- **HTML entities:** `D&amp;C` → BeautifulSoup handles automatically
- **Multiple citations in one footnote span:** Each extracted individually
- **Talks with no HTML / no text_raw:** Return empty TalkCitations with `extraction_success=False`
- **Non-numeric verse parts:** ("3a", "title") → skip with warning in `expand_verses()`
- **Paragraphs with no citations:** Skip, no CitationData produced

---

## Reusable Existing Code

| What                                | Where                                       |
| ----------------------------------- | ------------------------------------------- |
| `parse_html()`                      | `extractors/paragraphs.py` |
| `find_all_occurrences()`            | `tools/text_processing.py:10`               |
| `Database`, `core_db`, `content_db` | `db/__init__.py`                            |
| `ValidationResult`                  | `models/paragraph_data.py:150`              |
| `PARAGRAPH_CONFIG` pattern          | `config/schemas.py:248`                     |

---

## Verification

1. **Phase 2 regression:** Run existing Phase 2 tests to confirm `text_raw` change doesn't break anything
2. **Unit tests:** `python -m pytest tests/test_citations.py -v`
3. **Single talk smoke test:** Process talk 1059 (4 known citations), verify all 4 detected with correct book/chapter/verse
4. **Footnote citation test:** Process a talk with `<span class="footnote">` citations (talk ~7200+), verify `citation_location="footnote"`
5. **Zero-citation talk:** Process talk 1 or 5000 (0 citations), verify empty TalkCitations
6. **Cross-validation:** Compare extracted citation count vs `SELECT COUNT(*) FROM citation WHERE TalkID = ?` for several talks
7. **Paragraph flag check:** After processing, verify `has_scripture_citation=True` and `citation_count > 0` on paragraphs that contain citations
8. **Batch test:** Process 50 talks, check parse_success rate > 95%
