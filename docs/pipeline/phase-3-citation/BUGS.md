# Bug Catalogue

All known bugs across Phases 1–5 of the extraction pipeline.

One row per bug. Root cause and fix details live in the relevant commit messages.

| ID | Phase | Description | Status |
|----|-------|-------------|--------|
| BUG-01 | 4 | cp1252 encoding of curly quotes in _PUNCT_TOKENS causes replacement chars on Windows | fixed |
| BUG-02 | 2 | test_extract_simple_talk: bare div lacks body-block container class | fixed |
| BUG-03 | 2 | test_extract_with_multiple_paragraphs: bare div lacks body-block container class | fixed |
| BUG-04 | 2 | test_very_long_paragraph: bare p not wrapped in body-block container | fixed |
| BUG-05 | 2 | is_container_element returns False for div.figure despite docstring saying it should be True | fixed |
| BUG-06 | 2 | extract_list_item_paragraphs silently drops bare li text without p wrapper | fixed |
| BUG-07 | 2 | Debug print() statements left in extract_semantic_paragraphs violating logging convention | fixed |
| BUG-08 | 2 | test_nested_tags_stripped: test HTML text below min_paragraph_length (9 < 10) | fixed |
| BUG-09 | 2 | test_skip_tags: first paragraph text below min_paragraph_length (9 < 10) | fixed |
| BUG-10 | 2 | test_paragraph_ids_generated: bare p without body-block container | fixed |
| BUG-11 | 2 | test_multiple_paragraphs (EdgeCases): bare div without body-block container | fixed |
| BUG-12 | 2 | test_extract_real_talk: no skip guard when database file absent in test environment | fixed |
| BUG-13 | 4 | Whitespace destroyed between inline elements — get_text(strip=True) drops inter-element spaces | fixed |
| BUG-14 | 4 | Extra leading spaces from sx() anchors containing non-breaking space before citation text | fixed |
| BUG-15 | 4 | Missing punctuation from CSS ccontainer pseudo-elements not present in HTML text content | fixed |

## Audit Log

| Date | Sample | Talks | New Bugs |
|------|--------|-------|----------|
| 2026-03-23 | config/audit_sample.json (52 unique talks, IDs curated by user) | 52 clean, 0 errors | 0 — audit complete, no additional bugs found |
