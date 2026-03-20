---
plan: 01-01
phase: 01-db-enrichment
status: complete
completed: 2026-03-19
commit: 97fed0e
---

# Plan 01-01: talk_metadata Table + Backfill Migration — Summary

## What Was Built

**Task 1: DDL + shared helper (`db/one-off-migration/create_talk_metadata_table.py`)**
- `create_table(db)` — CREATE TABLE IF NOT EXISTS talk_metadata (7 cols: talk_id PK, speaker_role_id, uri_l, uri_gc, kicker, talk_preview, data_aid) + 2 indexes
- `upsert_talk_metadata(db, talk_id, **fields)` — shared UPSERT helper using `ON CONFLICT(talk_id) DO UPDATE SET excluded.*`
- `verify_table(db)` — PRAGMA table_info check
- `main()` — CLI with `--db` flag; ran against `db/core.52.db` and confirmed 7 columns

**Task 2: Migrate 5 backfill scripts**
- `backfill_talk_metadata.py` — Title stays on `talks`, `speaker_role_id` + `data_aid` moved to `talk_metadata` via upsert
- `backfill_talk_kicker.py` — kicker write changed from `UPDATE talk SET Kicker` to `upsert_talk_metadata(core_db, talk_id, kicker=...)`
- `backfill_talk_uri.py` — uri_l/uri_gc writes changed from `UPDATE talk SET URI_L, URI_GC` to `upsert_talk_metadata`; corrections also updated
- `backfill_talk_metadata_role_extraction.py` — `UPDATE talk SET speaker_role_id` replaced with `upsert_talk_metadata`
- `backfill_talk_preview.py` — fully redirected from `content.52.db talkbody.TextPreview` to `core.52.db talk_metadata.talk_preview`; `--db` default changed to CORE_DB_PATH

## Verification

- `CREATE TABLE IF NOT EXISTS talk_metadata` ✓ in DDL script
- `def upsert_talk_metadata(db, talk_id, **fields)` ✓
- `ON CONFLICT(talk_id) DO UPDATE SET` ✓
- `UPDATE talk SET` → 0 matches in kicker/uri/role_extraction/preview scripts ✓
- All 5 scripts contain `from create_talk_metadata_table import upsert_talk_metadata` ✓
- `backfill_talk_preview.py` uses CORE_DB_PATH ✓
- `backfill_topics.py` and `backfill_talk_texts.py` — 0 git diff lines ✓
- `pytest tests/test_phase1.py`: 30 passed, 14 skipped ✓

## Key Files

### key-files.created
- db/one-off-migration/create_talk_metadata_table.py (new)
- db/one-off-migration/backfill_talk_metadata.py (modified)
- db/one-off-migration/backfill_talk_kicker.py (modified)
- db/one-off-migration/backfill_talk_uri.py (modified)
- db/one-off-migration/backfill_talk_metadata_role_extraction.py (modified)
- db/one-off-migration/backfill_talk_preview.py (modified)

## Deviations

None.

## Self-Check: PASSED
