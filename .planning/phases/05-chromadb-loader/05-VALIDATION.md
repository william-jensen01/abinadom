---
phase: 5
slug: chromadb-loader
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pytest.ini or pyproject.toml (existing) |
| **Quick run command** | `pipenv run py -m pytest tests/test_phase5_loader.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_phase5_loader.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | LOAD-01 | unit | `pipenv run py -m pytest tests/test_phase5_loader.py::test_talks_transform -x -q` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | LOAD-02 | unit | `pipenv run py -m pytest tests/test_phase5_loader.py::test_annotation_exclusion -x -q` | ❌ W0 | ⬜ pending |
| 5-01-03 | 01 | 1 | LOAD-03 | unit | `pipenv run py -m pytest tests/test_phase5_loader.py::test_citations_from_annotations -x -q` | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 2 | LOAD-04 | unit | `pipenv run py -m pytest tests/test_phase5_loader.py::test_insertion_order -x -q` | ❌ W0 | ⬜ pending |
| 5-02-02 | 02 | 2 | LOAD-05 | unit | `pipenv run py -m pytest tests/test_phase5_loader.py::test_batch_chunking -x -q` | ❌ W0 | ⬜ pending |
| 5-03-01 | 03 | 3 | LOAD-06 | integration | `pipenv run py -m pytest tests/test_phase5_loader.py::test_verification_report -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase5_loader.py` — stubs for LOAD-01 through LOAD-06
- [ ] `tests/conftest.py` — shared fixtures (extend existing if present)
- [ ] `pipenv install chromadb` — new dependency required

*Wave 0 must install chromadb and create test stubs before any loader code is written.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ChromaDB persistent client connects to correct path | LOAD-04 | Requires live ChromaDB instance with real filesystem path | Run loader against test DB path, confirm collections appear in directory |
| Verification report human-readable output | LOAD-06 | Format/readability is subjective | Inspect printed report for all required sections: counts, sample queries, FK checks |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
