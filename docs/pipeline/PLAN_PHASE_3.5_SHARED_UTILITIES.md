# Plan: Extract Shared Utilities from Phase 3 & Update Phase 4 Plan

## Context

Phase 3 (citation extraction) is complete and passing 63+ tests. Phase 4 (footnote extraction) has a plan but isn't implemented yet. Review revealed:

1. **Duplicated logic** — Phase 4 would reimplement Phase 3's context window, word boundary snapping, filtered paragraph building, and position anchor walking.
2. **Spec violation in Phase 4 plan** — `to_chromadb_format()` uses `footnote_text_raw` as the document; spec requires `context_window`.
3. **Paragraph flags** — Phase 3 already sets `has_scripture_citation`/`citation_count` during extraction. Phase 4 should follow the same pattern for `has_footnote`/`footnote_count` (set during extraction, validated in Phase 5).

This plan extracts shared utilities before Phase 4 implementation begins.

---

## Part A: Extract Shared Utilities

### Step 1: Create `extractors/html_parsing_utils.py`

New shared module with these exports:

```
ELEMENT_PLACEHOLDER = "\x00"

_find_position_anchor(element: Tag) -> Tag
    # Walks up parent chain to topmost Tag below paragraph root.
    # Exact move from phase3 (lines 315-332). Already generic.

_snap_to_word_boundaries(before, after, before_truncated, after_truncated) -> (str, str)
    # Trims partial words at context window edges.
    # Exact move from phase3 (lines 372-399). Already generic.

filter_paragraph_around_anchor(soup, anchor, placeholder) -> str
    # Replaces anchor with placeholder, decomposes remaining noteMarker sups,
    # returns soup.get_text(strip=True).
    # Extracted from _build_filtered_paragraph steps 4-6.

apply_context_window(filtered_text, placeholder_char, label, config) -> (str, str, str)
    # Finds placeholder in filtered_text, extracts before/after slices,
    # applies word boundary snapping per config, assembles context_window.
    # Returns ("", "", "") if placeholder not found.
    # Extracted from extract_context_window lines 443-458.
```

No dependencies on any phase module — only `bs4.Tag` and `BeautifulSoup`.

### Step 2: Refactor `extractors/phase3_citation_extraction.py`

**Imports to add:**

```python
from extractors.html_parsing_utils import (
    ELEMENT_PLACEHOLDER,
    _find_position_anchor,
    _snap_to_word_boundaries,
    filter_paragraph_around_anchor,
    apply_context_window,
)
```

**Remove local definitions of:**

- `_CITATION_PLACEHOLDER` (line 312)
- `_find_position_anchor` (lines 315-332)
- `_snap_to_word_boundaries` (lines 372-399)

**Update `_build_filtered_paragraph`** (stays in phase3 — citation-specific lookup):

```python
def _build_filtered_paragraph(text_raw, citation_id, parser="html.parser"):
    soup = BeautifulSoup(text_raw, parser)
    target_span = soup.find("span", class_="citation", id=str(citation_id))
    display_text = ""
    if target_span:
        display_text = target_span.get_text(strip=True)
        anchor = _find_position_anchor(target_span)
        filtered = filter_paragraph_around_anchor(soup, anchor, ELEMENT_PLACEHOLDER)
    else:
        for marker in soup.find_all("sup", class_="noteMarker"):
            marker.decompose()
        filtered = soup.get_text(strip=True)
    return filtered, display_text
```

**Update `calculate_citation_position`:** replace `_CITATION_PLACEHOLDER` → `ELEMENT_PLACEHOLDER`

**Update `extract_context_window`:** replace inline context calculation (lines 443-458) with:

```python
return apply_context_window(filtered, ELEMENT_PLACEHOLDER, citation_label, config)
```

Keep the fallback path (lines 460-476) for when `text_raw`/`citation_id` are not provided.

### Step 3: Update `tests/test_phase3.py`

**Import changes only:**

- Remove `_find_position_anchor` from phase3 imports
- Add: `from extractors.html_parsing_utils import _find_position_anchor, ELEMENT_PLACEHOLDER`
- Replace `"\x00"` literals with `ELEMENT_PLACEHOLDER` in assertions (clarity)

All 63+ existing tests should pass unchanged — behavior is identical.

### Step 4: Create `tests/test_html_parsing_utils.py`

Focused unit tests for the shared module:

| Test Class                        | What it covers                                                         |
| --------------------------------- | ---------------------------------------------------------------------- |
| `TestFindPositionAnchor`          | Direct child, ccontainer-wrapped, noteMarker-wrapped, deeply nested    |
| `TestSnapToWordBoundaries`        | Before truncated, after truncated, both, neither, no spaces in slice   |
| `TestFilterParagraphAroundAnchor` | Anchor replaced + other noteMarkers decomposed, anchor IS a noteMarker |
| `TestApplyContextWindow`          | Normal, placeholder at start/end, not found, word mode, char mode      |

### Step 5: Run full Phase 3 test suite — all 63+ tests must pass

---

## Part B: Update Phase 4 Plan (`bright-greeting-pike.md`)

### Fix 1: `to_chromadb_format()` document field

Change from `document = footnote_text_raw` to:

```python
document = self.context_window or self.footnote_text_raw
```

Matches `CitationData.to_chromadb_format()` pattern (line 85 of `models/citation_data.py`) and the pipeline spec (Phase 6: `documents = context_window text for embedding`).

### Fix 2: Type classification — document as intentional

Add explicit note: "Footnote type classification (conference_talk, book, hymn, etc.) is intentionally deferred. Phase 4 extracts raw footnote text only."

### Fix 3: Update "Reuse from Phase 3" table

Replace with imports from `extractors/html_parsing_utils`:

| What                             | Source                                                                                        |
| -------------------------------- | --------------------------------------------------------------------------------------------- |
| `ELEMENT_PLACEHOLDER`            | `extractors.html_parsing_utils`                                                               |
| `_find_position_anchor`          | `extractors.html_parsing_utils` (NOT needed for footnotes — noteMarker is already the anchor) |
| `_snap_to_word_boundaries`       | `extractors.html_parsing_utils` (used internally by `apply_context_window`)                   |
| `filter_paragraph_around_anchor` | `extractors.html_parsing_utils`                                                               |
| `apply_context_window`           | `extractors.html_parsing_utils`                                                               |
| `ValidationResult`               | `models.paragraph_data`                                                                       |

### Fix 4: Simplify `_build_filtered_paragraph_for_footnote`

With shared utilities, Phase 4's version becomes:

```python
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

### Fix 5: Simplify `extract_footnote_context_window`

```python
def extract_footnote_context_window(text_raw, footnote_index, footnote_text_raw, config):
    parser = config.get("html_parser", "html.parser")
    filtered, _ = _build_filtered_paragraph_for_footnote(text_raw, footnote_index, parser)
    return apply_context_window(filtered, ELEMENT_PLACEHOLDER, footnote_text_raw, config)
```

### Fix 6: Paragraph flags set during extraction

Phase 4's `process_talk_footnotes` sets `has_footnote = True` and `footnote_count = N` on paragraphs during extraction — same pattern as Phase 3. Phase 5 validates these, not re-calculates them.

---

## Implementation Order

1. Create `extractors/html_parsing_utils.py`
2. Create `tests/test_html_parsing_utils.py`
3. Refactor `extractors/phase3_citation_extraction.py` — imports + delegation
4. Update `tests/test_phase3.py` — import adjustments
5. Run `pytest tests/test_html_parsing_utils.py tests/test_phase3.py -v` — all green
6. Update `.claude/plans/bright-greeting-pike.md` — apply fixes 1-6

---

## Verification

1. `pytest tests/test_html_parsing_utils.py -v` — new shared utility tests pass
2. `pytest tests/test_phase3.py -v` — all 63+ existing tests pass (no regressions)
3. Manual: run `examples/phase3_example.py` against real DB — output unchanged
4. Review updated Phase 4 plan for consistency with pipeline spec

## Critical Files

| File                                       | Action                                                  |
| ------------------------------------------ | ------------------------------------------------------- |
| `extractors/html_parsing_utils.py`         | **Create** — shared utilities                           |
| `tests/test_html_parsing_utils.py`         | **Create** — tests for shared utilities                 |
| `extractors/phase3_citation_extraction.py` | **Modify** — remove local defs, import shared           |
| `tests/test_phase3.py`                     | **Modify** — update imports                             |
| `.claude/plans/bright-greeting-pike.md`    | **Modify** — apply 6 fixes                              |
| `config/schemas.py`                        | **Modify** — add FOOTNOTE_CONFIG + FOOTNOTE_DATA_SCHEMA |
