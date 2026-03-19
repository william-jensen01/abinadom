---
phase: 1
slug: db-enrichment
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-19
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | none — existing setup |
| **Quick run command** | `pipenv run py -m pytest tests/test_phase1.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_phase1.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-00-01 | 00 | 0 | ENRCH-01..06 | unit | `pipenv run py -m pytest tests/test_phase1.py -x -q` | yes (stubs) | ⬜ pending |
| 1-01-01 | 01 | 1 | ENRCH-01 | unit | `pipenv run py db/one-off-migration/create_talk_metadata_table.py --db db/core.52.db 2>&1 \| head -20` | yes | ⬜ pending |
| 1-01-02 | 01 | 1 | ENRCH-02 | unit | `cd "C:/Users/wbjen/OneDrive/Documents/LDS MCP" && grep -l "UPDATE talk SET" db/one-off-migration/backfill_talk_metadata.py db/one-off-migration/backfill_talk_kicker.py db/one-off-migration/backfill_talk_uri.py db/one-off-migration/backfill_talk_metadata_role_extraction.py db/one-off-migration/backfill_talk_preview.py 2>/dev/null \| wc -l` | yes | ⬜ pending |
| 1-02-01 | 02 | 1 | ENRCH-03 | integration | `pipenv run py api/fetch_talk_previews.py --dry-run 2>&1 \| tail -20` | yes | ⬜ pending |
| 1-03-01 | 03 | 2 | ENRCH-04 | integration | `pipenv run py -c "from db import Database, CORE_DB_PATH; db = Database(CORE_DB_PATH); total = db.scalar('SELECT COUNT(*) FROM talk_metadata'); print(f'talk_metadata rows: {total}'); assert total > 0, 'talk_metadata is empty'"` | yes | ⬜ pending |
| 1-03-02 | 03 | 2 | ENRCH-05 | unit | `pipenv run py -m pytest tests/test_phase1.py -x -v 2>&1 \| tail -30` | yes (Wave 0) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_phase1.py` — add stubs for ENRCH-01 through ENRCH-06 (talk_metadata DDL, backfill behavior, no-direct-writes-to-talks, enriched field output) — Plan 01-00

*Existing test_phase1.py exists — Wave 0 adds new test stubs for enrichment behavior via Plan 01-00.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `talk_previews.json` contains previews from Church API | ENRCH-03 | Requires live Church API access; coverage varies by era | Run preview fetcher, inspect JSON for sample of recent and old talks |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** signed off (Wave 0 plan 01-00 in place, all automated commands recorded)
