---
phase: 1
slug: db-enrichment
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| 1-01-01 | 01 | 1 | ENRCH-01 | unit | `pipenv run py -m pytest tests/test_phase1.py -k "talk_metadata" -q` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | ENRCH-02 | unit | `pipenv run py -m pytest tests/test_phase1.py -k "backfill" -q` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | ENRCH-06 | unit | `pipenv run py -m pytest tests/test_phase1.py -k "no_writes_to_talks" -q` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | ENRCH-03 | manual | N/A — Church API | N/A | ⬜ pending |
| 1-03-01 | 03 | 2 | ENRCH-04 | unit | `pipenv run py -m pytest tests/test_phase1.py -k "enriched_fields" -q` | ❌ W0 | ⬜ pending |
| 1-03-02 | 03 | 2 | ENRCH-05 | unit | `pipenv run py -m pytest tests/test_phase1.py -k "join_output" -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase1.py` — add stubs for ENRCH-01 through ENRCH-06 (talk_metadata DDL, backfill behavior, no-direct-writes-to-talks, enriched field output)

*Existing test_phase1.py exists — Wave 0 adds new test stubs for enrichment behavior.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `talk_previews.json` contains previews from Church API | ENRCH-03 | Requires live Church API access; coverage varies by era | Run preview fetcher, inspect JSON for sample of recent and old talks |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
