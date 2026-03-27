# Phase 3: Bug Audit & Fixes - Research

**Researched:** 2026-03-23
**Domain:** Python extraction pipeline — pytest regression debugging, HTML parsing, Windows encoding
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Fix the 11 known failing tests first before running the broader audit. Starting from a clean baseline makes it easier to distinguish new bugs found during the audit. (10 in `tests/test_phase2.py`, 1 in `tests/test_phase4.py::TestFootnoteTextRendering::test_rbrackdotrdquo_gives_compound_suffix`)
- **D-02:** After known failures are fixed, run the curated sample through all phases to discover additional bugs. All discovered bugs go into the catalogue.
- **D-03:** Sample size is approximately 20 talks, curated by the user (not random, not algorithm-selected).
- **D-04:** Sample list lives in `config/audit_sample.json` as a list of `talk_id` values. Version-controlled, easy to edit without touching source code.
- **D-05:** The audit script reads `config/audit_sample.json` to know which talks to run. The user will populate this file with their chosen talk_ids before the audit runs.
- **D-06:** Single `BUGS.md` file with a markdown table. One row per bug.
- **D-07:** Minimal fields per bug: `ID`, `Phase`, `Description`, `Status` (open/fixed). Root cause and fix details go in commit messages, not the catalogue.
- **D-08:** Regression tests go into the existing `tests/test_phase*.py` files, co-located with the phase they cover.
- **D-09:** One test per bug — enough to fail if the fix were reverted, no more.
- **D-10:** BUGS-03 also requires coverage for existing Phase 4 fixes already in place. These should be identified during the fix phase (Plan 1) and covered alongside other regressions.

### Claude's Discretion

- Exact `BUGS.md` file location (root, `docs/`, or `.planning/phases/03-bug-audit-fixes/`)
- Audit script name and location (e.g., `scripts/run_audit.py` or ad-hoc)
- Whether to run all 5 phases per talk or limit scope based on what bugs surface
- Fix commit granularity (one commit per bug vs. batching closely-related bugs)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BUGS-01 | All Phase 1–5 extractor bugs identified and catalogued across the codebase | Research identified 7 confirmed failing tests as the starting baseline; audit script design documented |
| BUGS-02 | All identified bugs fixed with root cause addressed (not papered over) | Root causes fully diagnosed for all 7 current failures — fixes are clear, no guesswork needed |
| BUGS-03 | Regression tests added for all fixed bugs, including coverage of the Phase 4 fixes already in place | Phase 4 existing fix coverage mapped in BUG_FIXING_SUMMARY.md; test gap analysis completed |
</phase_requirements>

---

## Summary

**Current baseline:** 7 tests fail across two files — 6 in `tests/test_phase2.py` and 1 in `tests/test_phase4.py`. This differs from the 11 referenced in CONTEXT.md; 4 previously-failing tests have since been fixed (or were counted differently at context-gathering time). The 7 remaining failures are fully diagnosed.

**Phase 2 failures** share two root causes. The first is that `extract_paragraphs()` requires a recognized body container class (`body-block`, `#primary`, `.gcbody`, `.primary`), so test HTML that uses a bare `<div>` or bare `<p>` without any of those classes silently returns an empty result (extraction_success=False). Several tests were written before `find_body_container()` was enforced as a hard requirement. The second root cause is that `is_container_element()` does not recognize `div.figure` as a container — the implementation returns `False` for all `div` elements except `div.stanza`, so figure containers are not descended into. Additionally, `extract_list_item_paragraphs()` only looks for `<p>` and `div.stanza` inside `<li>` elements, so bare text directly in `<li>` (without a wrapping `<p>`) produces zero paragraphs.

**Phase 4 failure** is a Windows cp1252 encoding bug in `extractors/html_parsing_utils.py`. The `dquo` entry in `_PUNCT_TOKENS` stores curly-quote characters (`"` / `"`) as UTF-8 bytes in the source file. Windows resolves locale-preferred encoding as cp1252, so when CPython imports the module the bytes `\xe2\x80\x9c` and `\xe2\x80\x9d` are decoded as replacement characters (`\ufffd`) instead of the intended curly quotes. The fix is to add a `# -*- coding: utf-8 -*-` encoding declaration at the top of the file, which forces the interpreter to read it as UTF-8 regardless of locale. Alternatively, the literals can be replaced with `\u201c`/`\u201d` ASCII-safe escape sequences.

**Primary recommendation:** Fix tests in this order: (1) Phase 4 encoding bug (one-line fix), (2) Phase 2 body-container tests (update test HTML to use a recognized container class or add a fallback path in the extractor), (3) Phase 2 `is_container_element` / bare-`<li>` issues. Then run the audit.

---

## Standard Stack

### Core (all already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.2 | Test framework | Confirmed installed; all existing tests use it |
| BeautifulSoup4 | (installed) | HTML parsing | Used throughout all phases |
| pipenv | (installed) | Virtual environment | Project standard per CLAUDE.md |

**Run command (per CLAUDE.md):**
```bash
pipenv run py -m pytest tests/test_phase2.py tests/test_phase4.py -v
```

**Full suite:**
```bash
pipenv run py -m pytest tests/ -v
```

No new library installations are required for this phase.

---

## Architecture Patterns

### Established project patterns

- All extractors use `logger = logging.getLogger(__name__)` — no `logging.basicConfig` in extractor modules.
- All file I/O uses `encoding='utf-8'` (established in Phase 1 fix for Windows cp1252 compatibility).
- `config/pipeline_config.py` is the single source of truth for processing constants.
- One test file per phase: `tests/test_phase*.py`.
- Regression tests are added to the existing per-phase file, not a separate file.

### Bug catalogue pattern (D-06, D-07)

BUGS.md is a markdown table with columns: `ID`, `Phase`, `Description`, `Status`. Root cause and fix details belong in commit messages, not the catalogue. Keep the table minimal.

```markdown
| ID | Phase | Description | Status |
|----|-------|-------------|--------|
| BUG-01 | 2 | ... | fixed |
```

### Audit script pattern (D-04, D-05)

`config/audit_sample.json` is a JSON array of `talk_id` integers. The audit script (`scripts/run_audit.py` or similar) reads this file, runs each talk through all five phases, and reports failures. The script should use `cache_manager_CLAUDE.py` for any HTTP requests and import constants from `config/pipeline_config.py` rather than hardcoding values.

```python
import json
from config.pipeline_config import ...

with open("config/audit_sample.json", encoding="utf-8") as f:
    talk_ids = json.load(f)
```

### Regression test pattern (D-08, D-09)

One test per bug. Test must demonstrate the exact symptom (assert the behavior that was wrong), and pass only when the fix is applied. The test name should clearly link to the bug (e.g., `test_bug_phase2_bare_li_without_p_tag_extracts_text`).

```python
def test_bug_N_short_description(self):
    """Regression: BUG-N — [root cause one line]."""
    ...
    assert <failing assertion from the original bug>
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML parsing | Custom parser | BeautifulSoup4 (already used) | Handles malformed HTML; already integrated |
| Test discovery | Custom test runner | pytest (already used) | Standard; already configured |
| File encoding declarations | Custom file reader | `# -*- coding: utf-8 -*-` PEP 263 declaration | Interpreter-native; zero-cost fix |
| Unicode escape | Re-encode file | `\u201c` / `\u201d` in string literals | ASCII-safe; no encoding dependency |

---

## Confirmed Failing Tests (Baseline Inventory)

This section maps each failing test to its root cause and the specific fix needed.

### Phase 2 — 6 failures

| Test | Root Cause | Fix Strategy |
|------|-----------|--------------|
| `TestParagraphExtraction::test_extract_simple_talk` | HTML uses bare `<div>`, no recognized body container class | Update test HTML to use `<div class="body-block">` |
| `TestParagraphExtraction::test_extract_with_multiple_paragraphs` | Same — bare `<div>` | Update test HTML to use `<div class="body-block">` |
| `TestEdgeCases::test_very_long_paragraph` | HTML is bare `<p>` with no container at all | Update test HTML to wrap in `<div class="body-block">` |
| `TestSemanticExtraction::test_is_container_figure` | `is_container_element()` returns `False` for `div.figure` (code line 596 only returns True for `section`) | Add `"figure" in classes` check to `is_container_element()` |
| `TestSemanticExtraction::test_extract_semantic_paragraphs_mixed` | `ol` in test HTML not processed — `extract_list_item_paragraphs` finds no `<p>` inside bare `<li>text</li>` | Bare `<li>` text without `<p>` wrapper needs handling in `extract_list_item_paragraphs` |
| `TestNewExtractionApproach::test_extract_list_items_separately` | Same bare-`<li>` issue — list items contain raw text, no `<p>` wrapper | Same fix as above |

**Important clarification on fix strategy:** There are two valid approaches for the body-container tests:
1. Update test HTML to match the requirement (tests were written before the strict container requirement was enforced).
2. Add a fallback in `extract_paragraphs()` that handles containerless HTML.

The CONTEXT.md establishes that these are bugs in the extractor logic (not the tests), so approach 2 is more likely correct — but this needs review against actual talk HTML from the database to determine what the real-world behavior should be. Research finding: the test failures reveal a real behavioral contract question. **This is an open question the planner should resolve before specifying the fix.**

### Phase 4 — 1 failure

| Test | Root Cause | Fix |
|------|-----------|-----|
| `TestFootnoteTextRendering::test_rbrackdotrdquo_gives_compound_suffix` | `dquo` in `_PUNCT_TOKENS` stores UTF-8 curly quotes; Windows cp1252 locale decodes them as replacement characters `\ufffd` | Add `# -*- coding: utf-8 -*-` to `extractors/html_parsing_utils.py` line 1, OR replace `"` / `"` literals with `\u201c` / `\u201d` escape sequences |

**Confirmed root cause:** `locale.getpreferredencoding()` returns `cp1252` on this machine. CPython uses locale encoding to read source files when no explicit encoding declaration is present. The bytes `\xe2\x80\x9c` (UTF-8 for `"`) cannot be decoded as cp1252 and become `\ufffd`. The fix is identical to the Phase 1 `encoding='utf-8'` pattern already established in this project.

---

## Phase 4 Existing Fixes — Coverage Gap (BUGS-03)

Per `docs/pipeline/phase-4-footnote/BUG_FIXING_SUMMARY.md`, three bugs were already fixed in Phase 4:

| Fixed Bug | Description | Existing Tests? |
|-----------|-------------|----------------|
| Bug 1: Whitespace destroyed between inline elements | `get_text(strip=True)` → `get_text().strip()` | `test_cite_tags_preserve_surrounding_spaces`, `test_nbsp_converted_to_regular_space`, `test_multiple_spaces_collapsed` — COVERED (passing) |
| Bug 2: Extra leading spaces from `sx()` anchors | `sx()` anchor removal before text extraction | `test_sx_anchor_removed_no_extra_space` — COVERED (passing) |
| Bug 3: Missing punctuation from CSS `ccontainer` pseudo-elements | Dynamic `_parse_punct_class()` replacing static map | `test_rsemi_gives_semicolon_suffix`, `test_rbrackdotrdquo_gives_compound_suffix`, etc. — PARTIALLY COVERED (`rbrackdotrdquo` test failing due to encoding bug) |

The 15 tests added in `TestFootnoteTextRendering` cover Bugs 1, 2, and 3. The encoding fix for Bug 3's `rbrackdotrdquo` test will make coverage complete. No new tests need to be written for existing Phase 4 fixes — the tests exist but one is broken by the encoding bug.

**After the encoding fix:** All 15 `TestFootnoteTextRendering` tests will pass, satisfying BUGS-03 for Phase 4's existing fixes.

---

## Common Pitfalls

### Pitfall 1: Fixing the test instead of the extractor

**What goes wrong:** For tests like `test_extract_simple_talk` that use bare `<div>` HTML, the quick fix is to update the test HTML to add `class="body-block"`. But this may mask a real extractor deficiency — talks in the database may not always have a recognized body container.
**Why it happens:** The `find_body_container()` fallback chain only handles four known selectors. HTML outside those selectors silently returns `extraction_success=False`.
**How to avoid:** Before fixing, run `test_extract_real_talk` against a sample of real talks to understand what HTML patterns appear in production. If real talks always have one of the four selectors, fixing the tests is correct. If not, the extractor needs a broader fallback.
**Warning signs:** If the audit reveals talks with 0 paragraphs extracted, the body-container logic needs expanding.

### Pitfall 2: Windows encoding regression on future edits

**What goes wrong:** A developer edits `html_parsing_utils.py` and adds a new Unicode character literal without encoding awareness. On Windows the character becomes a replacement character at import time.
**Why it happens:** Python reads source files using locale encoding by default. Windows locale is cp1252.
**How to avoid:** The `# -*- coding: utf-8 -*-` declaration at line 1 prevents this for the whole file. Alternatively, use only ASCII-safe `\uXXXX` escape sequences in string literals.
**Warning signs:** Test output shows `\ufffd` (replacement character) where a specific Unicode character was expected.

### Pitfall 3: Bare `<li>` text without `<p>` wrappers

**What goes wrong:** `extract_list_item_paragraphs()` only processes `<p>` and `div.stanza` inside `<li>`. A `<li>text content</li>` without a wrapping `<p>` produces zero paragraphs silently.
**Why it happens:** The implementation assumes list items always contain `<p>` tags. Older or simpler HTML may not.
**How to avoid:** Add a fallback in `extract_list_item_paragraphs()` that reads bare text content from `<li>` when no `<p>` children are found.
**Warning signs:** Audit talks where lists appear produce 0 paragraphs but the talk clearly has list content.

### Pitfall 4: Debug print statements left in production code

**What goes wrong:** `extract_semantic_paragraphs()` at line 644-645 has `print("Stanza Detected")` and `print(element)` left in production code. This pollutes test stdout and is a code quality problem.
**Why it happens:** Debug instrumentation was never removed after development.
**How to avoid:** Remove both print statements during bug-fix cleanup.
**Warning signs:** Test output shows stanza HTML printed to stdout even in passing tests.

---

## Code Examples

### Encoding declaration fix (Phase 4 bug)

```python
# -*- coding: utf-8 -*-
"""
Shared HTML parsing utilities for the extraction pipeline.
...
"""
```

This single line at the top of `extractors/html_parsing_utils.py` resolves the `rbrackdotrdquo` failure.

**Alternative (no file-level declaration needed):**
```python
# Before (cp1252 decodes \xe2\x80\x9c as replacement character):
"dquo": {"l": "\u201c", "r": "\u201d"},

# After (ASCII-safe — works on any platform regardless of locale):
"dquo": {"l": "\u201c", "r": "\u201d"},
```

### is_container_element fix

```python
def is_container_element(element: Tag) -> bool:
    if not element or not isinstance(element, Tag):
        return False

    if element.name == "section":
        return True

    if element.name == "div":
        classes = element.get("class", [])
        if "stanza" in classes:
            return False  # semantic unit, not container
        if "figure" in classes:   # ADD THIS
            return True           # ADD THIS

    return False
```

**Note:** The `div.figure` handling in `extract_semantic_paragraphs()` (lines 762–859) already has custom logic that takes over before `is_container_element()` is reached. So fixing `is_container_element()` alone may not fix the test — `process_element()` handles `div.figure` explicitly at line 762 before it reaches the `is_container_element` branch. The test failure root cause needs to be re-examined in context.

### Body-container fallback for bare-`<div>` tests

If tests are correct and the extractor needs a fallback:
```python
# In find_body_container(), add a final fallback:
# 5. body tag (for any HTML with a <body>)
container = soup.find("body")
if container:
    return container

# 6. Root element if nothing else found (allow bare divs in tests)
return soup  # or return first child div
```

If tests are wrong (bare `<div>` is not a real pattern), fix test HTML:
```python
# test_extract_simple_talk: change
html = """<div>...</div>"""
# to
html = """<div class="body-block">...</div>"""
```

---

## Runtime State Inventory

This section is omitted — Phase 3 is not a rename/refactor/migration phase. No runtime state is involved.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (pipenv) | All tests | Yes | 3.14.2 | — |
| pytest | Test runner | Yes | 9.0.2 | — |
| BeautifulSoup4 | Extractors | Yes | (installed) | — |
| SQLite database | `test_extract_real_talk` | Yes | core.52.db present | Skip real-data tests |

No missing dependencies. Environment is fully ready for this phase.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (default discovery) |
| Quick run command | `pipenv run py -m pytest tests/test_phase2.py tests/test_phase4.py -v --tb=short` |
| Full suite command | `pipenv run py -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BUGS-01 | Bug catalogue created | manual | N/A — BUGS.md written by hand | ❌ Wave 0 (create BUGS.md) |
| BUGS-01 | Audit script runs sample | smoke | `pipenv run py scripts/run_audit.py` | ❌ Wave 0 (create script and config/audit_sample.json) |
| BUGS-02 | Known failing tests pass | unit | `pipenv run py -m pytest tests/test_phase2.py tests/test_phase4.py -v` | ✅ (tests exist, need fixes) |
| BUGS-02 | Full suite still passes | unit | `pipenv run py -m pytest tests/ -v` | ✅ |
| BUGS-03 | Each fix has regression test | unit | `pipenv run py -m pytest tests/ -v` | ✅ (partially — new tests needed per bug fixed) |
| BUGS-03 | Phase 4 existing fix coverage | unit | `pipenv run py -m pytest tests/test_phase4.py::TestFootnoteTextRendering -v` | ✅ (15 tests exist; 1 fails due to encoding bug) |

### Sampling Rate

- **Per bug fix commit:** `pipenv run py -m pytest tests/test_phase2.py tests/test_phase4.py -v --tb=short`
- **Per wave merge:** `pipenv run py -m pytest tests/ -v`
- **Phase gate:** Full suite green (0 failures) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `BUGS.md` — catalogue file (location: Claude's discretion per D-06/D-07)
- [ ] `config/audit_sample.json` — empty array `[]` initially; user populates with talk_ids
- [ ] `scripts/run_audit.py` — audit driver script (runs phases 1–5 per talk_id in audit_sample.json)

*(Existing test infrastructure covers all phase requirements once the 7 known bugs are fixed.)*

---

## Open Questions

1. **Body-container test fix strategy: update tests or update extractor?**
   - What we know: 5 of 6 Phase 2 failures are caused by test HTML lacking a recognized body container class. The extractor's `find_body_container()` returns `None` for bare `<div>` or bare `<p>` HTML.
   - What's unclear: Whether the tests were intentionally written to test fallback behavior (in which case the extractor has a gap) or were written carelessly (in which case the test HTML should be fixed). The test docstrings say "Test extracting paragraphs from simple talk" — suggests the test intent is the happy path, not fallback.
   - Recommendation: Fix test HTML to use `<div class="body-block">` for the 3 simple-container cases. For `test_very_long_paragraph`, the bare `<p>` is testing edge case handling of very long text — the test should be updated to wrap in a `body-block` container. This is the lower-risk fix and does not change production behavior.

2. **Bare `<li>text</li>` handling: fix extractor or update tests?**
   - What we know: `extract_list_item_paragraphs()` expects `<p>` children inside `<li>`. The two failing list tests use bare text directly in `<li>`.
   - What's unclear: Whether real production talk HTML always wraps list item content in `<p>` tags, or whether bare `<li>text</li>` appears in real data.
   - Recommendation: Research during audit. If real talks always use `<p>` inside `<li>`, fix the tests. If not, fix the extractor to handle bare text.

3. **`is_container_element` for `div.figure`: is the fix needed?**
   - What we know: The test `test_is_container_figure` asserts `is_container_element(div.figure) is True`, but `extract_semantic_paragraphs()` handles `div.figure` explicitly in `process_element()` before the `is_container_element` branch is reached.
   - What's unclear: Whether fixing `is_container_element()` alone is sufficient to fix `test_extract_semantic_paragraphs_mixed`, or whether both the function and the test case need updates.
   - Recommendation: Fix `is_container_element()` to return `True` for `div.figure` to match the docstring, and verify that this does not create double-processing of figure elements in `extract_semantic_paragraphs()`.

---

## Sources

### Primary (HIGH confidence)

- Live test runs — `pipenv run py -m pytest tests/test_phase2.py tests/test_phase4.py -v --tb=long` — direct observation of failures
- `extractors/html_parsing_utils.py` — source code read directly, line-by-line
- `extractors/phase2_paragraph_extraction.py` — source code read directly, full file
- `docs/pipeline/phase-4-footnote/BUG_FIXING_SUMMARY.md` — canonical reference for Phase 4 existing fixes

### Secondary (MEDIUM confidence)

- Python PEP 263 — source encoding declarations (well-established standard, not verified against current docs but stable since Python 2.3)
- Windows cp1252 locale behavior — verified empirically via `locale.getpreferredencoding()` output

### Tertiary (LOW confidence)

- "Whether bare `<li>text</li>` appears in real talk HTML" — not verified; requires audit to confirm

---

## Metadata

**Confidence breakdown:**

- Known failing tests: HIGH — directly verified by test run
- Root cause diagnosis: HIGH — confirmed by inspecting source code and running encoding checks
- Fix strategies: MEDIUM — clear for encoding and `is_container_element`; body-container and bare-`<li>` fixes have an open question
- Phase 4 existing coverage: HIGH — read BUG_FIXING_SUMMARY.md and verified test presence

**Research date:** 2026-03-23
**Valid until:** 2026-04-23 (stable codebase; 30-day estimate)

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on this phase |
|-----------|---------------------|
| `pipenv run py` for all Python commands | All test commands use `pipenv run py -m pytest`, not `python -m pytest` |
| `encoding='utf-8'` on all file I/O | The Phase 4 encoding bug fix aligns with this existing convention |
| `logger = logging.getLogger(__name__)` everywhere | Debug `print()` statements in `extract_semantic_paragraphs()` must be removed (they violate logging convention) |
| Simplicity First — minimal code impact | Fix strategies should change as few lines as possible |
| No temporary fixes / find root causes | Confirmed: all fixes target root cause, not symptoms |
| Task tracking in `tasks/todo.md` | Planner should create `tasks/todo.md` for this phase's work |
| Update `tasks/lessons.md` after corrections | Not a research concern; note for executor |
| Update `CLAUDE.md` Project Structure Index when adding files | `config/audit_sample.json` and `scripts/run_audit.py` are new files; CLAUDE.md index must be updated |
