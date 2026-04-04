---
phase: 14
slug: auth-module
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-03
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pytest.ini` or `pyproject.toml` (existing) |
| **Quick run command** | `pipenv run py -m pytest tests/test_auth.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest -x -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_auth.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 0 | AUTH-01 | unit | `pipenv run py -m pytest tests/test_auth.py::test_keystore -x -q` | ❌ W0 | ⬜ pending |
| 14-01-02 | 01 | 0 | AUTH-01 | unit | `pipenv run py -m pytest tests/test_auth.py::test_create_key -x -q` | ❌ W0 | ⬜ pending |
| 14-02-01 | 02 | 1 | AUTH-02 | integration | `pipenv run py -m pytest tests/test_auth.py::test_middleware_401 -x -q` | ❌ W0 | ⬜ pending |
| 14-02-02 | 02 | 1 | AUTH-02 | integration | `pipenv run py -m pytest tests/test_auth.py::test_health_no_token -x -q` | ❌ W0 | ⬜ pending |
| 14-03-01 | 03 | 2 | AUTH-03 | unit | `pipenv run py -m pytest tests/test_auth.py::test_usage_log -x -q` | ❌ W0 | ⬜ pending |
| 14-04-01 | 04 | 3 | AUTH-01 | integration | `pipenv run py -m pytest tests/test_auth.py::test_manage_keys_cli -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_auth.py` — stubs for AUTH-01, AUTH-02, AUTH-03
- [ ] `tests/conftest.py` — add shared fixtures for auth (in-memory auth.db, test client with middleware)

*Existing pytest infrastructure is present; Wave 0 adds auth-specific test stubs only.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Raw token shown once at creation and not stored | AUTH-01 | Output is printed to stdout; no assertion possible without capturing CLI output in test | Run `pipenv run py scripts/manage_keys.py create --name test-key`, verify token is printed, then run again and verify a different token is printed |
| Existing tools unchanged for authenticated requests | AUTH-01/02 | End-to-end MCP protocol behavior | Connect MCP client with valid token, call `search` and `get_talk`, verify correct responses |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
