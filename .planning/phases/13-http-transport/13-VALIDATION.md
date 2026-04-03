---
phase: 13
slug: http-transport
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-03
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` (or existing pytest config) |
| **Quick run command** | `pipenv run py -m pytest tests/test_server.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest -x -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_server.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | TRANS-01 | unit | `pipenv run py -m pytest tests/test_server.py -x -q` | ✅ | ⬜ pending |
| 13-01-02 | 01 | 1 | TRANS-01 | integration | `pipenv run py -m pytest tests/test_server.py -x -q` | ✅ | ⬜ pending |
| 13-02-01 | 02 | 1 | TRANS-02 | unit | `pipenv run py -m pytest tests/test_server.py -x -q` | ✅ | ⬜ pending |
| 13-02-02 | 02 | 2 | TRANS-02 | integration | `pipenv run py -m pytest tests/test_server.py -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_server.py` — add stubs for HTTP transport tests (TRANS-01) and /health endpoint tests (TRANS-02)

*Existing test infrastructure covers the suite runner; Wave 0 adds new test stubs only.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| MCP client connects over HTTP and tools return results | TRANS-01 | Requires live MCP client (e.g., Claude Desktop or mcptools CLI) | Point a client at `http://localhost:8000/mcp`; run `search` and `get_talk` tools; verify valid responses |
| /health returns 503 when Ollama is down | TRANS-02 | Requires stopping Ollama process | Stop Ollama, hit `GET /health`, confirm 503 with `ollama` field showing failure |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
