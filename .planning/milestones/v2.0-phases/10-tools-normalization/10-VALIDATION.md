---
phase: 10
slug: tools-normalization
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-01
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | none — existing pytest config |
| **Quick run command** | `pipenv run py -m pytest tests/test_server.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_server.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | TOOL-01, TOOL-02 | unit | `pipenv run py -m pytest tests/test_server.py -x -q` | ✅ | ✅ green |
| 10-01-02 | 01 | 1 | TOOL-03, TOOL-04 | unit | `pipenv run py -m pytest tests/test_server.py -x -q` | ✅ | ✅ green |
| 10-01-03 | 01 | 1 | CORE-04, CORE-05 | unit | `pipenv run py -m pytest tests/test_server.py -x -q` | ✅ | ✅ green |
| 10-02-01 | 02 | 2 | TOOL-05, CORE-06 | unit | `pipenv run py -m pytest tests/test_server.py -x -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_server.py` — stubs/tests for TOOL-01 through TOOL-05, CORE-04, CORE-05, CORE-06
- [x] Existing `tests/test_server.py` — extend with new tool test cases

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Speaker fuzzy normalization returns correct speaker | TOOL-03 | Requires live ChromaDB with real data | Query with "Holland", verify results are from Jeffrey R. Holland |
| Date informal parsing filters correctly | TOOL-04 | Requires live ChromaDB with real data | Query with "April 2020", verify results are from conference_year=2020, conference_month=4 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-04-02 (Phase 12 tech debt cleanup)
