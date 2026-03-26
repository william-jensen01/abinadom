---
phase: 6
slug: pipeline-orchestrator
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pytest.ini / pyproject.toml (existing) |
| **Quick run command** | `pipenv run py -m pytest tests/test_phase6_orchestrator.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_phase6_orchestrator.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 6-01-01 | 01 | 1 | PIPE-01 | unit | `pipenv run py -m pytest tests/test_phase6_orchestrator.py::test_talk_query -xq` | ❌ W0 | ⬜ pending |
| 6-01-02 | 01 | 1 | PIPE-01 | unit | `pipenv run py -m pytest tests/test_phase6_orchestrator.py::test_pipeline_loop -xq` | ❌ W0 | ⬜ pending |
| 6-01-03 | 01 | 1 | PIPE-02 | unit | `pipenv run py -m pytest tests/test_phase6_orchestrator.py::test_resume -xq` | ❌ W0 | ⬜ pending |
| 6-02-01 | 02 | 2 | PIPE-03 | unit | `pipenv run py -m pytest tests/test_phase6_orchestrator.py::test_skip_mode -xq` | ❌ W0 | ⬜ pending |
| 6-02-02 | 02 | 2 | PIPE-03 | unit | `pipenv run py -m pytest tests/test_phase6_orchestrator.py::test_force_flag -xq` | ❌ W0 | ⬜ pending |
| 6-02-03 | 02 | 2 | PIPE-04 | unit | `pipenv run py -m pytest tests/test_phase6_orchestrator.py::test_buffer_size -xq` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase6_orchestrator.py` — stubs for PIPE-01, PIPE-02, PIPE-03, PIPE-04
- [ ] Shared fixtures in `tests/conftest.py` (extend existing) — mock DB connections, mock phase runners

*Existing test infrastructure (pytest) already installed. Wave 0 only needs new test file.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full pipeline run on real DB | PIPE-01 | Requires live SQLite + ChromaDB, ~hours to complete | Run `pipenv run py scripts/run_pipeline.py --limit 5` and verify 5 talks processed |
| Resume after interrupt | PIPE-02 | Requires mid-run kill signal | Run with `--limit 10`, Ctrl+C mid-way, re-run and verify no duplicate processing |
| --force reprocesses | PIPE-03 | Requires pre-populated DB state | Process 3 talks, run again with `--force`, verify all 3 re-processed |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
