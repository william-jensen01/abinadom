---
phase: 01-db-enrichment
verified: 2026-03-19T00:00:00Z
status: gaps_found
score: 7/9 must-haves verified
re_verification: false
gaps:
  - truth: "Test stubs for DDL validation (TestTalkMetadataDDL) are implemented"
    status: failed
    reason: "TestTalkMetadataDDL remains @unittest.skip('Wave 0 stub -- filled by Plan 01-01') with self.fail() bodies. Plan 01-01 was supposed to un-skip and implement these tests but did not."
    artifacts:
      - path: "tests/test_phase1.py"
        issue: "Lines 428-442: TestTalkMetadataDDL class still has @unittest.skip decorator and self.fail() stubs for all 3 methods"
    missing:
      - "Remove @unittest.skip from TestTalkMetadataDDL and implement real assertions: check PRAGMA table_info(talk_metadata) returns 7 columns, check indexes exist via sqlite_master"
  - truth: "Test stubs for backfill target validation (TestBackfillTargets) are implemented"
    status: failed
    reason: "TestBackfillTargets remains @unittest.skip('Wave 0 stub -- filled by Plan 01-01') with self.fail() bodies. Plan 01-01 was supposed to implement these tests but did not."
    artifacts:
      - path: "tests/test_phase1.py"
        issue: "Lines 445-455: TestBackfillTargets class still has @unittest.skip decorator and self.fail() stubs for both methods"
    missing:
      - "Remove @unittest.skip from TestBackfillTargets and implement real assertions: grep each of the 5 backfill scripts for 'from create_talk_metadata_table import upsert_talk_metadata' and verify absence of 'UPDATE talk SET' (except Title)"
human_verification:
  - test: "Run api/fetch_talk_previews.py --dry-run and observe output"
    expected: "Should log conference count (~167) and URI count (~4230) without errors; requests_cache writes to http_cache.sqlite"
    why_human: "Requires live filesystem and requests_cache behavior to validate properly; automated dry-run was documented in summary but not re-verified here"
---

# Phase 01: DB Enrichment Verification Report

**Phase Goal:** Enrich the talk_metadata table with additional metadata fields (kicker, talk_preview, uri_l, uri_gc, data_aid, speaker_role_id) by running backfill scripts, and update the Phase 1 extractor to expose these enriched fields via LEFT JOIN on talk_metadata.
**Verified:** 2026-03-19
**Status:** gaps_found — 2 gaps (Wave 0 test stubs never implemented)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | talk_metadata table exists with 7 columns and 2 indexes | VERIFIED | `PRAGMA table_info` returns 7 rows (talk_id PK, speaker_role_id, uri_l, uri_gc, kicker, talk_preview, data_aid); `sqlite_master` shows idx_talk_metadata_data_aid and idx_talk_metadata_uri_gc |
| 2 | talk_metadata is populated with enrichment data (>0 rows, all columns have data) | VERIFIED | 5441 rows total; speaker_role_id=3994, kicker=2125, uri_l=5441, talk_preview=34, data_aid=4006 |
| 3 | All 5 backfill scripts write to talk_metadata via upsert, not directly to talks table | VERIFIED | All 5 scripts import `upsert_talk_metadata`; grep for `UPDATE talk SET` returns 0 in kicker/uri/role_extraction/preview scripts; backfill_talk_metadata.py has `UPDATE talk SET Title` only (allowed) |
| 4 | backfill_talk_preview writes to core.52.db talk_metadata.talk_preview (not content.52.db) | VERIFIED | File imports CORE_DB_PATH and calls `upsert_talk_metadata(db, talk_id, talk_preview=preview)` |
| 5 | Phase 1 SQL query includes LEFT JOIN talk_metadata with COALESCE fallbacks | VERIFIED | extractors/phase1_talk_metadata.py lines 70-75,113: `COALESCE(tm.uri_l, t.URI_L)`, `COALESCE(tm.uri_gc, t.URI_GC)`, `COALESCE(tm.data_aid, t.data_aid)`, `COALESCE(tm.speaker_role_id, t.speaker_role_id)`, `tm.kicker`, `tm.talk_preview`, `LEFT JOIN talk_metadata tm ON t.ID = tm.talk_id` |
| 6 | TalkMetadata dataclass has kicker and talk_preview fields; document summary includes them | VERIFIED | models/talk_metadata.py lines 77-78: `kicker: Optional[str] = None`, `talk_preview: Optional[str] = None`; lines 181-185: both included in `_create_document_summary()`; line 259-260: factory function maps both from db row |
| 7 | Church API fetcher script exists with two-level fetch pattern | VERIFIED | api/fetch_talk_previews.py: `def fetch_conference_talk_uris`, `def fetch_talk_preview`, `def get_uri_gc_lookup`, parses `toc_entries[1:]`, navigates `page-meta-social.pageMeta.description`, uses requests_cache |
| 8 | TestTalkMetadataDDL is implemented (not a stub) | FAILED | Lines 428-442: class still has `@unittest.skip("Wave 0 stub -- filled by Plan 01-01")` with `self.fail("Stub")` bodies. Plan 01-01 SUMMARY claims these were created but not implemented. |
| 9 | TestBackfillTargets is implemented (not a stub) | FAILED | Lines 445-455: class still has `@unittest.skip("Wave 0 stub -- filled by Plan 01-01")` with `self.fail("Stub")` bodies. Same issue. |

**Score:** 7/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db/one-off-migration/create_talk_metadata_table.py` | DDL script + reusable upsert helper | VERIFIED | Contains `CREATE TABLE IF NOT EXISTS talk_metadata`, `def upsert_talk_metadata(db, talk_id, **fields)`, `ON CONFLICT(talk_id) DO UPDATE SET`, both index DDL statements |
| `db/one-off-migration/backfill_talk_metadata.py` | Upserts speaker_role_id and data_aid to talk_metadata | VERIFIED | Imports `upsert_talk_metadata`; calls it with `speaker_role_id` and `data_aid`; Title stays on talks |
| `db/one-off-migration/backfill_talk_kicker.py` | Upserts kicker to talk_metadata | VERIFIED | 2 upsert_talk_metadata references, 0 `UPDATE talk SET` |
| `db/one-off-migration/backfill_talk_uri.py` | Upserts uri_l and uri_gc to talk_metadata | VERIFIED | 4 upsert_talk_metadata references, 0 `UPDATE talk SET` |
| `db/one-off-migration/backfill_talk_metadata_role_extraction.py` | Upserts speaker_role_id to talk_metadata | VERIFIED | 2 upsert_talk_metadata references, 0 `UPDATE talk SET` |
| `db/one-off-migration/backfill_talk_preview.py` | Upserts talk_preview to core.52.db talk_metadata | VERIFIED | Imports CORE_DB_PATH, 2 upsert_talk_metadata references, 0 `UPDATE talk SET` |
| `api/fetch_talk_previews.py` | Church API two-level preview fetcher | VERIFIED | All required functions present; correct API URL, toc parsing, page-meta-social navigation |
| `extractors/phase1_talk_metadata.py` | Phase 1 extractor with LEFT JOIN | VERIFIED | LEFT JOIN at line 113, COALESCE for all 4 overlapping fields at lines 70-74, tm.kicker/tm.talk_preview at lines 75-76 |
| `models/talk_metadata.py` | TalkMetadata with kicker and talk_preview | VERIFIED | Both fields at lines 77-78 with Optional[str] = None defaults |
| `tests/test_phase1.py` | TestEnrichedFields implemented | VERIFIED | 7 real test methods without skip decorator; all 39 tests pass (5 skipped are the two stub classes) |
| `tests/test_phase1.py` | TestTalkMetadataDDL implemented | FAILED | Still `@unittest.skip` with `self.fail()` stubs |
| `tests/test_phase1.py` | TestBackfillTargets implemented | FAILED | Still `@unittest.skip` with `self.fail()` stubs |
| `config/schemas.py` | kicker and talk_preview in TALK_METADATA_SCHEMA | VERIFIED | Lines 154-160: both fields present in schema |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `create_talk_metadata_table.py` | core.52.db | DDL execution | WIRED | Table confirmed in DB with 7 cols and 2 indexes |
| `backfill_talk_metadata.py` | talk_metadata table | UPSERT | WIRED | `INSERT INTO talk_metadata ... ON CONFLICT(talk_id) DO UPDATE SET` |
| `extractors/phase1_talk_metadata.py` | talk_metadata table | LEFT JOIN in SQL | WIRED | `LEFT JOIN talk_metadata tm ON t.ID = tm.talk_id` at line 113 |
| `extractors/phase1_talk_metadata.py` | models/talk_metadata.py | TalkMetadata fields kicker/talk_preview | WIRED | `create_talk_metadata_from_db_row` maps `kicker=row.get("kicker")` and `talk_preview=row.get("talk_preview")` |
| `backfill_talk_preview.py` | db/one-off-migration/talk_previews.json | JSON file read | WIRED | File references `talk_previews.json`; 34 rows populated |
| `api/fetch_talk_previews.py` | Church API (conference endpoint) | requests_cache | WIRED | `churchofjesuschrist.org/study/api/v3` present, `requests_cache.install_cache` present |
| `api/fetch_talk_previews.py` | Church API (individual talk endpoint) | requests_cache | WIRED | `fetch_talk_preview` function navigates `page-meta-social.pageMeta.description` |
| `api/fetch_talk_previews.py` | core.52.db | conference list query | WIRED | `get_uri_gc_lookup` queries `SELECT ID, URI_GC FROM talk` |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| ENRCH-01 | 01-00, 01-01 | `talk_metadata` table created with 6 enrichment columns | SATISFIED | Table confirmed in DB with correct 7-column schema and 2 indexes |
| ENRCH-02 | 01-00, 01-01 | All backfill scripts write to `talk_metadata` instead of `talks` | SATISFIED | All 5 scripts use upsert_talk_metadata; no direct UPDATE talk SET for enrichment fields |
| ENRCH-03 | 01-02 | Church API preview fetcher completed | SATISFIED | `api/fetch_talk_previews.py` implements two-level fetch; dry-run verified 167 conferences, 4230 URIs |
| ENRCH-04 | 01-00, 01-03 | All backfill scripts re-run to populate `talk_metadata` | SATISFIED | 5441 rows in talk_metadata with data in all columns |
| ENRCH-05 | 01-03 | Phase 1 extractor updated to JOIN talks + talk_metadata and expose enriched fields | SATISFIED | LEFT JOIN with COALESCE in extractor; kicker/talk_preview in TalkMetadata model and document summary |
| ENRCH-06 | 01-00, 01-01 | `talk_topic` and `conference_topic` tables remain unchanged | SATISFIED | conference_topic=333, talk_topic=16162 confirmed in DB; `backfill_topics.py` and `backfill_talk_texts.py` have 0 git diff lines across relevant commits |

**Note on ENRCH-01/ENRCH-02 test coverage:** REQUIREMENTS.md lists no orphaned requirements. All 6 ENRCH IDs appear in at least one plan. However, the test classes designated to verify ENRCH-01 and ENRCH-02 programmatically (`TestTalkMetadataDDL`, `TestBackfillTargets`) remain unimplemented stubs. The underlying code artifacts ARE correct; the test gap is coverage-only, not a functional failure. This is the source of the two gaps above.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_phase1.py` | 428-442 | `@unittest.skip` + `self.fail("Stub")` on TestTalkMetadataDDL | Warning | Tests that were supposed to be implemented post-Plan-01-01 are still inert stubs |
| `tests/test_phase1.py` | 445-455 | `@unittest.skip` + `self.fail("Stub")` on TestBackfillTargets | Warning | Same — tests are collected but never execute |

No blocker anti-patterns found in implementation files. No TODO/FIXME/PLACEHOLDER patterns in modified source files.

---

### Human Verification Required

#### 1. Church API Dry-Run Verification

**Test:** Run `pipenv run py api/fetch_talk_previews.py --dry-run`
**Expected:** Logs approximately 167 conferences and 4230 talk URIs collected; completes without error; writes no output file
**Why human:** Requires live filesystem and requests_cache sqlite write; the dry-run was documented in Plan 01-02 SUMMARY as verified but is not re-verified programmatically in this check

#### 2. Phase 1 End-to-End Enriched Field Output

**Test:** Run `pipenv run py extractors/phase1_talk_metadata.py --limit 1 --stats` (or equivalent invocation)
**Expected:** Output shows a talk with kicker and/or talk_preview fields populated (for a talk that has them in talk_metadata); fields appear in document summary
**Why human:** Verifies the full data flow from DB through extractor to output format; requires checking a live talk with known enrichment data

---

### Gaps Summary

Two Wave 0 test stubs were never promoted to real implementations. Plan 01-01 (which was responsible for these two classes per the `@unittest.skip` label "filled by Plan 01-01") created the code artifacts the tests would verify, but did not circle back to implement the test assertions.

**Impact:** Low — the underlying code is correct and verified by other means (direct DB inspection, grep-based checks). The 39-test suite passes (39 passed, 5 skipped). The gap is test coverage only.

**Root cause:** Plan 01-01 SUMMARY documents test counts (30 passed, 14 skipped) as a passing check, which matched the Wave 0 state. The plan did not include a task to un-skip and implement TestTalkMetadataDDL and TestBackfillTargets even though the skip decorators named Plan 01-01 as responsible.

**Fix required:** A gap-closure plan should add one task to `tests/test_phase1.py`: remove `@unittest.skip` from both classes and implement real assertions using `sqlite3.connect` for DDL/index checks and `os.path` + `open` for backfill script content checks.

---

_Verified: 2026-03-19_
_Verifier: Claude (gsd-verifier)_
