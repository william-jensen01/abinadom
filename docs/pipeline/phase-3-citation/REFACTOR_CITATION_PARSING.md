stateless-tumbling-charm.md

# Plan: Re-evaluate Citation Parsing in Phase 3

## Context

The current position calculation in `phase3_citation_extraction.py` uses text search
(`display_text` in `clean_text`) to locate citations in paragraphs. This is unreliable
when the same scripture reference appears multiple times in a paragraph, and it doesn't
account for the varied HTML structures citations can appear in. The user requires:

- Position must be found via citation `id` attribute (not text matching)
- Position anchor must be the topmost parent element whose parent is the paragraph root
  (e.g., `<sup class="noteMarker">` for footnote citations, `<span class="ccontainer">` for
  nested citations, or the `<span class="citation">` itself for direct citations)

## HTML Structure Summary

Seven citation patterns are present in the HTML:

1. Direct: `<span class="citation" id="X">` → anchor = citation span itself
2. `<span class="ccontainer rdot"><span class="citation" id="X"></span></span>` → anchor = ccontainer
3. `<span class="ccontainer rsemi"><span class="citation" id="X"></span></span>` → anchor = ccontainer
4. `<span class="ccontainer rbrackdotrdquo"><span class="citation" id="X"></span></span>` → anchor = ccontainer
5. `<span class="ccontainer lparen rparencomma"><span class="citation" id="X"></span></span>` → anchor = ccontainer
6. Footnote long: `<sup class="noteMarker">...<span class="footnote long">...<span class="citation" id="X"></span>...</span></sup>` → anchor = sup
7. Footnote short: `<sup class="noteMarker">...<span class="footnote">...<span class="citation" id="X"></span>...</span></sup>` → anchor = sup

## Critical File

`extractors/phase3_citation_extraction.py`

## Current Bugs

1. `calculate_citation_position` searches for `display_text` in `clean_text` — wrong approach
2. `_build_filtered_context_text` replaces the citation `<span>` (not the anchor), causing footnote
   citations' placeholder to be removed when noteMarker sups are decomposed — position becomes -1

## Implementation Plan

### Step 1 — Add `_find_position_anchor(citation_span)` helper (~line 315)

Walk up the parent chain of a citation span to find the topmost Tag element
whose parent is the paragraph root (either BeautifulSoup document root or `<p>` tag).

```python
def _find_position_anchor(citation_span: Tag) -> Tag:
    """
    Walk up from citation_span to find the topmost Tag element that is a
    direct child of the paragraph root (BeautifulSoup document or <p>).
    This gives us the correct position anchor for all citation structures.
    """
    anchor = citation_span
    for parent in citation_span.parents:
        if not isinstance(parent, Tag):
            break  # reached BeautifulSoup document root
        if parent.name == "p":
            break  # reached paragraph wrapper element
        anchor = parent
    return anchor
```

### Step 2 — Refactor `_build_filtered_context_text` → `_build_filtered_paragraph`

Replace citation span with `_find_position_anchor()` target, then decompose remaining
noteMarkers. This fixes the footnote bug where placeholder was removed along with the noteMarker.

Key change: `anchor.replace_with(_CITATION_PLACEHOLDER)` instead of `target_span.replace_with(...)`.
After replacement, `soup.find_all("sup", class_="noteMarker")` only finds OTHER noteMarkers
(since the anchor noteMarker is already replaced), so decomposing them is safe.

```python
def _build_filtered_paragraph(
    text_raw: str,
    citation_id: int,
    parser: str = "html.parser",
) -> Tuple[str, str]:
    soup = BeautifulSoup(text_raw, parser)
    target_span = soup.find("span", class_="citation", id=str(citation_id))
    display_text = ""
    if target_span:
        display_text = target_span.get_text(strip=True)
        anchor = _find_position_anchor(target_span)
        anchor.replace_with(_CITATION_PLACEHOLDER)
    for marker in soup.find_all("sup", class_="noteMarker"):
        marker.decompose()
    return soup.get_text(strip=True), display_text
```

### Step 3 — Replace `calculate_citation_position` signature and implementation

Old: `(clean_text, display_text, config) → (int, int)`
New: `(text_raw, citation_id, display_text, config) → (int, int)`

Use `_build_filtered_paragraph` to get filtered text with placeholder, then find
placeholder's position. `char_end = char_start + len(display_text)`.

```python
def calculate_citation_position(
    text_raw: str,
    citation_id: int,
    display_text: str,
    config: Dict[str, Any],
) -> Tuple[int, int]:
    if not text_raw:
        return -1, -1
    parser = config.get("html_parser", "html.parser")
    filtered, extracted_display = _build_filtered_paragraph(text_raw, citation_id, parser)
    pos = filtered.find(_CITATION_PLACEHOLDER)
    if pos == -1:
        return -1, -1
    label = display_text or extracted_display
    return pos, pos + len(label)
```

### Step 4 — Update `extract_context_window` to use `_build_filtered_paragraph`

Replace the internal call to `_build_filtered_context_text` with `_build_filtered_paragraph`.
Remove the now-deleted old function name. Signature and return values unchanged.

### Step 5 — Update `process_talk_citations` call site (~line 599)

Change:

```python
char_start, char_end = calculate_citation_position(
    paragraph.text, display_text, config
)
```

To:

```python
char_start, char_end = calculate_citation_position(
    paragraph.text_raw, citation_id, display_text, config
)
```

### Step 6 — Remove unused `find_all_occurrences` import

The old text-search based position calculation used `find_all_occurrences` from
`tools/text_processing`. After removing that approach, check if it's still needed
elsewhere in the file. If not, remove the import.

## Verification

1. Run the phase 3 pipeline on a talk with:
    - Direct citations (case 1)
    - ccontainer-wrapped citations (cases 2–5)
    - Footnote citations (cases 6–7)
    - Same scripture referenced multiple times in one paragraph
2. Confirm `char_position` values are non-negative and correspond to correct positions
3. Confirm footnote citations now get valid (non -1) positions
4. Confirm context_before/context_after no longer include footnote number text
5. No regressions in DB lookup, verse expansion, or validation logic
