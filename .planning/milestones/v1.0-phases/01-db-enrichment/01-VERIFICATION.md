---
phase: 01-db-enrichment
verified: 2026-03-20T09:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 7/9
  gaps_closed:
    - "TestTalkMetadataDDL runs without skip and all 3 tests pass"
    - "TestBackfillTargets runs without skip and both tests pass"
  gaps_remaining: []
  regressions: []
---

# Phase 01: DB Enrichment Verification Report

**Phase Goal:** Restructure metadata storage so Phase 1 reads enriched fields from a dedicated `talk_metadata` table instead of scattered `talks` columns.
**Verified:** 2026-03-20
**Status:** passed — all 9 must-haves verified, 44/44 tests pass, 0 skipped
**Re-verification:** Yes — after gap closure via Plan 01-04

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `talk_metadata` table exists with 7 columns and 2 indexes | VERIFIED | `PRAGMA table_info` returns 7 rows (talk_id PK, speaker_role_id, uri_l, uri_gc, kicker, talk_preview, data_aid); `sqlite_master` shows idx_talk_metadata_data_aid and idx_talk_metadata_uri_gc. Confirmed live by TestTalkMetadataDDL (3 tests pass). |
| 2 | `talk_metadata` is populated with enrichment data (>0 rows, all columns have data) | VERIFIED | 5441 rows total; speaker_role_id=3994, kicker=2125, uri_l=5441, talk_preview=4006 (expanded), data_aid=4006 confirmed in prior verification. |
| 3 | All 5 backfill scripts write to `talk_metadata` via upsert, not directly to `talks` table | VERIFIED | TestBackfillTargets::test_backfill_scripts_use_upsert_helper and test_no_direct_writes_to_talks_table both pass. All 5 scripts confirmed to import `upsert_talk_metadata`; no direct `UPDATE talk SET` except the allowed Title update in backfill_talk_metadata.py. |
| 4 | `backfill_talk_preview` writes to core.52.db `talk_metadata.talk_preview` (not content.52.db) | VERIFIED | Script imports CORE_DB_PATH and calls `upsert_talk_metadata(db, talk_id, talk_preview=preview)`. Confirmed by TestBackfillTargets. |
| 5 | Phase 1 SQL query includes LEFT JOIN `talk_metadata` with COALESCE fallbacks | VERIFIED | extractors/phase1_talk_metadata.py: `COALESCE(tm.uri_l, t.URI_L)`, `COALESCE(tm.uri_gc, t.URI_GC)`, `COALESCE(tm.data_aid, t.data_aid)`, `COALESCE(tm.speaker_role_id, t.speaker_role_id)`, `tm.kicker`, `tm.talk_preview`, `LEFT JOIN talk_metadata tm ON t.ID = tm.talk_id`. Confirmed by TestEnrichedFields::test_query_has_left_join. |
| 6 | `TalkMetadata` dataclass has `kicker` and `talk_preview` fields; document summary includes them | VERIFIED | models/talk_metadata.py: `kicker: Optional[str] = None`, `talk_preview: Optional[str] = None`; both in `_create_document_summary()` and mapped by factory. Confirmed by TestEnrichedFields (7 tests pass). |
| 7 | Church API fetcher script exists with two-level fetch pattern | VERIFIED | api/fetch_talk_previews.py: `fetch_conference_talk_uris`, `fetch_talk_preview`, `get_uri_gc_lookup`, toc_entries parsing, page-meta-social.pageMeta.description navigation, requests_cache present. |
| 8 | TestTalkMetadataDDL runs without skip and all 3 tests pass | VERIFIED | CLOSED by Plan 01-04 (commit a87e2f6). No `@unittest.skip` on class; grep for skip/self.fail stubs returns 0 matches. `pytest tests/test_phase1.py::TestTalkMetadataDDL -v` shows 3 passed. |
| 9 | TestBackfillTargets runs without skip and both tests pass | VERIFIED | CLOSED by Plan 01-04 (commit b3bca6c). No `@unittest.skip` on class; grep for skip/self.fail stubs returns 0 matches. `pytest tests/test_phase1.py::TestBackfillTargets -v` shows 2 passed. |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db/one-off-migration/create_talk_metadata_table.py` | DDL script + reusable upsert helper | VERIFIED | `CREATE TABLE IF NOT EXISTS talk_metadata`, `def upsert_talk_metadata(db, talk_id, **fields)`, `ON CONFLICT(talk_id) DO UPDATE SET`, both index DDL statements present |
| `db/one-off-migration/backfill_talk_metadata.py` | Upserts speaker_role_id and data_aid to talk_metadata | VERIFIED | Imports `upsert_talk_metadata`; calls it with `speaker_role_id` and `data_aid`; Title stays on talks |
| `db/one-off-migration/backfill_talk_kicker.py` | Upserts kicker to talk_metadata | VERIFIED | 2 upsert_talk_metadata references, 0 `UPDATE talk SET` |
| `db/one-off-migration/backfill_talk_uri.py` | Upserts uri_l and uri_gc to talk_metadata | VERIFIED | 4 upsert_talk_metadata references, 0 `UPDATE talk SET` |
| `db/one-off-migration/backfill_talk_metadata_role_extraction.py` | Upserts speaker_role_id to talk_metadata | VERIFIED | 2 upsert_talk_metadata references, 0 `UPDATE talk SET` |
| `db/one-off-migration/backfill_talk_preview.py` | Upserts talk_preview to core.52.db talk_metadata | VERIFIED | Imports CORE_DB_PATH, 2 upsert_talk_metadata references, 0 `UPDATE talk SET` |
| `api/fetch_talk_previews.py` | Church API two-level preview fetcher | VERIFIED | All required functions present; correct API URL, toc parsing, page-meta-social navigation |
| `extractors/phase1_talk_metadata.py` | Phase 1 extractor with LEFT JOIN | VERIFIED | LEFT JOIN at line 113, COALESCE for all 4 overlapping fields at lines 70-74, tm.kicker/tm.talk_preview at lines 75-76 |
| `models/talk_metadata.py` | TalkMetadata with kicker and talk_preview | VERIFIED | Both fields with `Optional[str] = None` defaults |
| `tests/test_phase1.py` | TestEnrichedFields implemented | VERIFIED | 7 real test methods; all pass |
| `tests/test_phase1.py` | TestTalkMetadataDDL implemented | VERIFIED | CLOSED — 3 methods with real sqlite3 assertions; `PRAGMA table_info(talk_metadata)` and index checks confirmed present and passing |
| `tests/test_phase1.py` | TestBackfillTargets implemented | VERIFIED | CLOSED — 2 methods with real file-content assertions; `upsert_talk_metadata` presence and `UPDATE talk SET` absence verified for all 5 scripts |
| `config/schemas.py` | kicker and talk_preview in TALK_METADATA_SCHEMA | VERIFIED | Both fields present in schema |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `create_talk_metadata_table.py` | core.52.db | DDL execution | WIRED | Table confirmed in DB with 7 cols and 2 indexes; live-verified by TestTalkMetadataDDL |
| `backfill_talk_metadata.py` | talk_metadata table | UPSERT | WIRED | `INSERT INTO talk_metadata ... ON CONFLICT(talk_id) DO UPDATE SET`; confirmed by TestBackfillTargets |
| `extractors/phase1_talk_metadata.py` | talk_metadata table | LEFT JOIN in SQL | WIRED | `LEFT JOIN talk_metadata tm ON t.ID = tm.talk_id` at line 113; confirmed by TestEnrichedFields::test_query_has_left_join |
| `extractors/phase1_talk_metadata.py` | models/talk_metadata.py | TalkMetadata fields kicker/talk_preview | WIRED | `create_talk_metadata_from_db_row` maps both fields; confirmed by TestEnrichedFields |
| `tests/test_phase1.py::TestTalkMetadataDDL` | db/core.52.db | sqlite3.connect + PRAGMA table_info | WIRED | Pattern `PRAGMA table_info(talk_metadata)` at line 460; 3 tests pass live against DB |
| `tests/test_phase1.py::TestBackfillTargets` | db/one-off-migration/backfill_*.py | open() + file content search | WIRED | Pattern `upsert_talk_metadata` in assertions at line 504; `UPDATE talk SET` negative check at line 517; 2 tests pass |
| `backfill_talk_preview.py` | db/one-off-migration/talk_previews.json | JSON file read | WIRED | File references talk_previews.json; cache expanded to 4006 entries |
| `api/fetch_talk_previews.py` | Church API (conference endpoint) | requests_cache | WIRED | `churchofjesuschrist.org/study/api/v3` present, `requests_cache.install_cache` present |
| `api/fetch_talk_previews.py` | core.52.db | conference list query | WIRED | `get_uri_gc_lookup` queries `SELECT ID, URI_GC FROM talk` |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| ENRCH-01 | 01-00, 01-01, 01-04 | `talk_metadata` table created with 6 enrichment columns | SATISFIED | Table confirmed in DB with correct 7-column schema and 2 indexes; automated test coverage now live via TestTalkMetadataDDL (3 passing tests) |
| ENRCH-02 | 01-00, 01-01, 01-04 | All backfill scripts write to `talk_metadata` instead of `talks` | SATISFIED | All 5 scripts use upsert_talk_metadata; no direct UPDATE talk SET for enrichment fields; automated test coverage now live via TestBackfillTargets (2 passing tests) |
| ENRCH-03 | 01-02 | Church API preview fetcher completed | SATISFIED | `api/fetch_talk_previews.py` implements two-level fetch; talk_previews.json expanded to 4006 entries |
| ENRCH-04 | 01-00, 01-03 | All backfill scripts re-run to populate `talk_metadata` | SATISFIED | 5441 rows in talk_metadata with data in all columns |
| ENRCH-05 | 01-03 | Phase 1 extractor updated to JOIN talks + talk_metadata and expose enriched fields | SATISFIED | LEFT JOIN with COALESCE in extractor; kicker/talk_preview in TalkMetadata model and document summary |
| ENRCH-06 | 01-00, 01-01 | `talk_topic` and `conference_topic` tables remain unchanged | SATISFIED | conference_topic=333, talk_topic=16162 confirmed in DB; TestTopicTablesUnchanged passes |

No orphaned requirements. All 6 ENRCH IDs appear in at least one plan and are now fully satisfied with automated test coverage.

---

### Anti-Patterns Found

None. No `@unittest.skip`, `self.fail("Stub")`, TODO, FIXME, PLACEHOLDER, or empty implementation patterns remain in any modified file.

The two Warning-level anti-patterns from the initial verification (TestTalkMetadataDDL and TestBackfillTargets skip stubs) are resolved.

---

### Human Verification Required

#### 1. Church API Dry-Run Verification

**Test:** Run `pipenv run py api/fetch_talk_previews.py --dry-run`
**Expected:** Logs approximately 167 conferences and 4230 talk URIs collected; completes without error; writes no output file
**Why human:** Requires live network and requests_cache sqlite write behavior; the script fetches from `churchofjesuschrist.org/study/api/v3` which cannot be asserted against in automated tests without mocking

#### 2. Phase 1 End-to-End Enriched Field Output

**Test:** Run `pipenv run py extractors/phase1_talk_metadata.py --limit 1 --stats` (or equivalent invocation)
**Expected:** Output shows a talk with kicker and/or talk_preview fields populated (for a talk with known enrichment data in talk_metadata); fields appear in document summary
**Why human:** Verifies the full live data flow from DB through extractor to output format; requires a talk with known enrichment data

---

### Re-verification Summary

**Previous status:** gaps_found (7/9 — 2026-03-19)
**Current status:** passed (9/9 — 2026-03-20)

**Gaps closed (2/2):**

1. **TestTalkMetadataDDL** — Plan 01-04 (commit a87e2f6) removed `@unittest.skip`, implemented 3 test methods using `sqlite3.connect` with `PRAGMA table_info(talk_metadata)` and `sqlite_master` index queries. All 3 pass against live core.52.db.

2. **TestBackfillTargets** — Plan 01-04 (commit b3bca6c) removed `@unittest.skip`, implemented 2 test methods using `Path.read_text(encoding="utf-8")` to assert `upsert_talk_metadata` presence and `UPDATE talk SET` absence across all 5 backfill scripts. Both pass.

**Full test suite result:** 44 passed, 0 skipped, 0 failed (0.11s)

**Regressions:** None. All 39 previously passing tests continue to pass. TestTopicTablesUnchanged (previously DB-conditional skips) now passes as well, confirming the live DB is available and unchanged.

---

_Verified: 2026-03-20_
_Verifier: Claude (gsd-verifier)_
