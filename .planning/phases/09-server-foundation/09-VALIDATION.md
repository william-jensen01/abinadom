---
phase: 9
slug: server-foundation
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-30
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none — implicit discovery |
| **Quick run command** | `pipenv run py -m pytest tests/test_server.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -x -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_server.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 9-01-01 | 01 | 0 | CORE-01,02,03 | setup | `pipenv install mcp` exits 0 | ✅ | ✅ green |
| 9-01-02 | 01 | 0 | CORE-01,02,03 | setup | `tests/test_server.py` file exists | ✅ | ✅ green |
| 9-01-03 | 01 | 1 | CORE-01 | unit | `pipenv run py -m pytest tests/test_server.py::test_chromadb_path_absolute -x` | ✅ | ✅ green |
| 9-01-04 | 01 | 1 | CORE-01 | unit | `pipenv run py -m pytest tests/test_server.py::test_chromadb_missing_collection_exits -x` | ✅ | ✅ green |
| 9-01-05 | 01 | 1 | CORE-02 | unit | `pipenv run py -m pytest tests/test_server.py::test_ollama_failure_exits -x` | ✅ | ✅ green |
| 9-01-06 | 01 | 1 | CORE-03 | unit | `pipenv run py -m pytest tests/test_server.py::test_all_collections_warmed -x` | ✅ | ✅ green |
| 9-01-07 | 01 | 2 | INTG-01 | manual | See manual verification below | manual-only | ✅ green — verified in 09-VERIFICATION.md Truth #4 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_server.py` — stubs for CORE-01, CORE-02, CORE-03 (does not exist yet)
- [x] `pipenv install mcp` — mcp package not yet in Pipfile/Pipfile.lock

*Existing 395-test suite covers Phases 1–6; no server tests exist yet.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| No stdout output during server startup | INTG-01 | Requires full server process capture; not feasible in unit tests | Run `pipenv run py server.py 2>/dev/null` and verify stdout is empty (Ctrl+C to stop) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-04-02 (Phase 12 tech debt cleanup)
