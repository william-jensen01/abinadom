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
| **Framework** | pytest 9.0.2 |
| **Config file** | None (default discovery) |
| **Quick run command** | `pipenv run py -m pytest tests/test_phase6.py -x` |
| **Full suite command** | `pipenv run py -m pytest tests/ -x` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_phase6.py -x`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | LOAD-01 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_prepare_talk_record -x` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | LOAD-01 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_prepare_paragraph_record -x` | ❌ W0 | ⬜ pending |
| 5-01-03 | 01 | 1 | LOAD-01 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_prepare_citation_record -x` | ❌ W0 | ⬜ pending |
| 5-01-04 | 01 | 1 | LOAD-01 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_prepare_footnote_record -x` | ❌ W0 | ⬜ pending |
| 5-01-05 | 01 | 1 | LOAD-02 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_annotation_exclusion -x` | ❌ W0 | ⬜ pending |
| 5-01-06 | 01 | 1 | LOAD-02 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_annotation_folding -x` | ❌ W0 | ⬜ pending |
| 5-01-07 | 01 | 1 | LOAD-03 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_annotation_citation_included -x` | ❌ W0 | ⬜ pending |
| 5-01-08 | 01 | 1 | D-05/D-06 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_flatten_metadata -x` | ❌ W0 | ⬜ pending |
| 5-01-09 | 01 | 1 | D-10 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_invalid_talk_skipped -x` | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 2 | LOAD-04 | integration | `pipenv run py -m pytest tests/test_phase6.py::test_insertion_order -x` | ❌ W0 | ⬜ pending |
| 5-02-02 | 02 | 2 | LOAD-04 | integration | `pipenv run py -m pytest tests/test_phase6.py::test_batch_chunking -x` | ❌ W0 | ⬜ pending |
| 5-02-03 | 02 | 2 | LOAD-05 | unit | `pipenv run py -m pytest tests/test_phase6.py::test_batch_logging -x` | ❌ W0 | ⬜ pending |
| 5-03-01 | 03 | 3 | LOAD-06 | integration | `pipenv run py -m pytest tests/test_phase6.py::test_verification_counts -x` | ❌ W0 | ⬜ pending |
| 5-03-02 | 03 | 3 | LOAD-06 | integration | `pipenv run py -m pytest tests/test_phase6.py::test_verification_retrievals -x` | ❌ W0 | ⬜ pending |
| 5-03-03 | 03 | 3 | LOAD-06 | integration | `pipenv run py -m pytest tests/test_phase6.py::test_verification_fk_checks -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase6.py` — stubs for all tests above (new file, all tests above)
- [ ] `models/paragraph_data.py` — add `source_type: str = "p"` field (prerequisite for LOAD-02 tests)
- [ ] `pipenv install chromadb` — new dependency required

*Wave 0 must add source_type to ParagraphData and create test stubs before any loader code is written.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ChromaDB persistent client connects to correct path | LOAD-04 | Requires live ChromaDB instance with real filesystem path | Run loader against test DB path, confirm collections appear in directory |
| Verification report human-readable output | LOAD-06 | Format/readability is subjective | Inspect printed report for all required sections: counts, sample retrievals, FK checks |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
