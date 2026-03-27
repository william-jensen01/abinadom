---
plan: 07-01
phase: 07-full-run-verification
status: complete
completed: 2026-03-27
---

## Summary

Built `scripts/verify_pipeline.py` (702 lines) — a reusable, standalone verification orchestrator for all four VER checks against live ChromaDB collections.

## What Was Built

**`scripts/verify_pipeline.py`** — post-pipeline verification script with:

- **VER-01 `check_counts()`**: Derives expected GC talk count at runtime via `SELECT COUNT(*) ... INNER JOIN conference_talk` (not hardcoded). Checks all 4 ChromaDB collection counts. Flags `data/failed_talks.json` if present.
- **VER-02 `check_semantic_search()`**: Runs 5 semantic queries (3 topical + 2 scriptural) against `conference_talk_paragraphs` with `embedding_function`. Prints top-5 results per query with talk metadata. Skips gracefully if Ollama is unavailable.
- **VER-03 `check_metadata_filters()`**: 4 filter tests on `conference_talks` (speaker/year/session/compound) plus two-step paragraph filter via `$in` operator.
- **VER-04 `check_fk_integrity()`**: Paged FK scan (`batch_size=5000`) across paragraphs→talks, citations→paragraphs (informational), and footnotes→talks. Uses tqdm progress.

Writes structured JSON report to `data/verification_report.json`. Prints per-check `PASS/FAIL` to stdout with overall summary.

## Key Files

- **created**: `scripts/verify_pipeline.py`
- **modified**: `CLAUDE.md` (project structure index updated)

## Decisions

- VER-02 is excluded from `overall_passed` (requires manual review)
- Citation→paragraph FK failures are informational only (annotation-sourced citations by design)
- `--output PATH` argparse flag for custom report location (default `data/verification_report.json`)

## Self-Check: PASSED

All 18 acceptance criteria verified:
- All 4 VER check functions present
- Proper imports from `db`, `extractors.phase6_chromadb_loader`, `config.pipeline_config`
- No hardcoded talk count — derives from SQLite at runtime
- `batch_size = 5000` for paged FK retrieval
- No forbidden anti-patterns (`generate_verification_report`, `include=["ids"]`)
- Syntax parses cleanly (`ast.parse` exits 0)
- 702 lines (min 200 required)
