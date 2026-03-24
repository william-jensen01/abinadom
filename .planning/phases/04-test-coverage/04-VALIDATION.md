---
phase: 4
slug: test-coverage
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-23
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via Pipfile dev-packages) |
| **Config file** | None — default pytest discovery |
| **Quick run command** | `pipenv run py -m pytest tests/test_pipeline_integration.py tests/test_phase1.py tests/test_phase5.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -q` |
| **Estimated runtime** | ~5s unit only / ~30s full suite |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/ -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | QUAL-04 | integration | `pipenv run py -m pytest tests/test_pipeline_integration.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-01 | 02 | 1 | QUAL-05 | unit | `pipenv run py -m pytest tests/test_phase1.py -k "edge" -x -q` | ❌ W0 | ⬜ pending |
| 4-02-02 | 02 | 1 | QUAL-06 | unit+integration | `pipenv run py -m pytest tests/test_phase1.py -k "schema_validation" -x -q` | ❌ W0 | ⬜ pending |
| 4-03-01 | 03 | 1 | QUAL-10 | unit | `pipenv run py -m pytest tests/test_phase5.py -k "adversarial" -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pipeline_integration.py` — stub/skeleton file for QUAL-04 integration tests (file does not exist yet)
- [ ] Schema validation function in `db/__init__.py` — `validate_schema()` and `SchemaError` for QUAL-06
- [ ] Schema validation tests in `tests/test_phase1.py` — test stubs for QUAL-06
- [ ] Phase 1 edge case tests in `tests/test_phase1.py` — stubs for missing speaker, unusual session, no URL (QUAL-05)
- [ ] Adversarial test cases in `tests/test_phase5.py` — stubs for all four adversarial categories (QUAL-10)

*All Wave 0 items are new code/tests — no existing infrastructure covers them.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real DB files present on disk | QUAL-04 | DB files not committed to git | Confirm `db/core.52.db` and `db/content.52.db` exist before running integration tests |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
