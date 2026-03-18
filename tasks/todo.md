## Unified Pipeline Plan

### Root Problems Identified

1. **Critical Bug**: Phase 2 calls `marker.decompose()` on the global soup *before* `str(element)` is captured into `text_raw` — so Phase 4 can never find `noteMarker` elements because Phase 2 already destroyed them.
2. **Isolation**: Phase 2 owns `parse_html()` and `find_body_container()` privately instead of sharing them via `html_parsing_utils.py`.
3. **Redundant parsing**: Each paragraph's HTML is parsed 3× total (Phase 2 once, Phase 3 once per para, Phase 4 once per para).
4. **Dead fields**: `ParagraphData.has_scripture_citation`, `citation_count`, `has_footnote`, `footnote_count` are never populated.

---

### Phase A — Fix the Critical Bug (Phase 2)

**`phase2_paragraph_extraction.py`**

- Remove the global `soup.find_all(class_="noteMarker") → decompose()` block from `extract_paragraphs()`.
- Add `_element_clean_text(element)` helper that deepcopies the element, strips noteMarkers from the copy, and returns clean text — leaving the original element (and thus `text_raw`) intact.
- Replace all `element.get_text(...)` calls that produce the `"text"` key with `_element_clean_text(element)`.

**Result**: `text_raw` now preserves `<sup class="noteMarker">` for Phase 4. `text` is still clean.

---

### Phase B — Promote Shared Utilities

**`html_parsing_utils.py`** (additions):
- Move `parse_html()` and `find_body_container()` here from Phase 2.
- Add `ParagraphHTMLContext` class:
  - Wraps a paragraph's `text_raw`, lazily parses it once, caches the soup.
  - `soup` property → read-only cached parse for discovery (`find_all`)
  - `fresh_soup()` method → new parse for mutating operations (`decompose`, `replace_with`)
  - `find_citation_spans()` and `find_note_markers()` convenience methods

**`phase2_paragraph_extraction.py`**: import `parse_html` and `find_body_container` from `html_parsing_utils`, remove local definitions.

---

### Phase C — Refactor Phases 3 & 4 to Accept Shared Context

**`phase3_citation_extraction.py`** and **`phase4_footnote_extraction.py`**:
- Add optional `ctx: Optional[ParagraphHTMLContext] = None` to the per-paragraph extraction functions.
- Add optional `contexts: Optional[Dict[int, ParagraphHTMLContext]] = None` to the talk-level orchestrators.
- When `ctx` is provided, use `ctx.soup` for element discovery (skips redundant re-parse).
- Mutating operations (position calculation via `filter_paragraph_around_anchor`) continue using `ctx.fresh_soup()` — isolation is preserved.
- `ctx=None` default means all existing callers work unchanged.

---

### Phase D — New Unified Orchestrator

**`extractors/pipeline.py`** (new file):

```
process_talk_pipeline(content_db, core_db, talk_id, book_cache, configs...)
  → Phase 2: extract paragraphs
  → build Dict[paragraph_id → ParagraphHTMLContext]
  → Phase 3: citations (with shared contexts)
  → Phase 4: footnotes (with shared contexts)
  → return TalkPipelineResult(paragraphs, citations, footnotes, warnings, errors)
```

`TalkPipelineResult` holds all three phase outputs plus merged diagnostics. The back-fill of `ParagraphData` fields (citation/footnote counts) happens automatically because Phase 3 & 4 already mutate the objects in-place.

---

### Key Risks

| Risk | Mitigation |
|---|---|
| `deepcopy` on every paragraph may be slow | Benchmark; fallback to `BeautifulSoup(str(element))` if needed |
| Phase 3/4 accidentally mutating `ctx.soup` | Discovery uses `ctx.soup`; mutations use `ctx.fresh_soup()` — enforced by convention |
| Stanza lines still call `get_text()` on sub-elements | `_element_clean_text()` should be applied at the stanza level, not per-line |
| Logger namespace changes when moving `find_body_container` | Minor, cosmetic only |

---

### Implementation Order

```
Phase A  →  Phase B  →  Phase C  →  Phase D
(bug fix)   (shared)   (optional   (pipeline
             utils)      ctx arg)    module)
```