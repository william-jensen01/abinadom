---
phase: 19
slug: create-an-alternative-mcp-server-using-fastmcp-and-scalekit
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-15
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none (pytest auto-discovers tests/) |
| **Quick run command** | `pipenv run py -m pytest tests/test_server.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_server.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 19-01-01 | 01 | 1 | FastMCP server boot | — | Server starts, /health returns 200 | integration | `pipenv run py -m pytest tests/test_server.py::test_health -x -q` | ❌ W0 | ⬜ pending |
| 19-01-02 | 01 | 1 | search tool | — | search returns ChromaDB results | unit | `pipenv run py -m pytest tests/test_server.py::test_search -x -q` | ❌ W0 | ⬜ pending |
| 19-01-03 | 01 | 1 | get_talk tool | — | get_talk returns full talk text | unit | `pipenv run py -m pytest tests/test_server.py::test_get_talk -x -q` | ❌ W0 | ⬜ pending |
| 19-02-01 | 02 | 2 | local mode (no auth) | — | All endpoints pass without token | integration | `pipenv run py -m pytest tests/test_server.py::test_local_mode -x -q` | ❌ W0 | ⬜ pending |
| 19-02-02 | 02 | 2 | remote mode (ScaleKit JWT) | T-19-01 | Invalid token rejected 401 | integration | `pipenv run py -m pytest tests/test_server.py::test_remote_auth -x -q` | ❌ W0 | ⬜ pending |
| 19-02-03 | 02 | 2 | ScaleKit JWT validation | T-19-01 | Valid JWT passes, expired JWT rejected | unit | `pipenv run py -m pytest tests/test_server.py::test_scalekit_verifier -x -q` | ❌ W0 | ⬜ pending |
| 19-03-01 | 03 | 3 | session management | — | MCP-Session-ID header tracked | integration | `pipenv run py -m pytest tests/test_server.py::test_session -x -q` | ❌ W0 | ⬜ pending |
| 19-03-02 | 03 | 3 | startup validation | — | ChromaDB + Ollama health checked on boot | integration | `pipenv run py -m pytest tests/test_server.py::test_startup -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_server.py` — rewrite/adapt for FastMCP (current tests assume FastAPI JSON-RPC dispatch)
- [ ] Stubs for all test IDs marked ❌ W0 above

*Wave 0 must be completed first in execution before any feature tasks.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ScaleKit token issuance → MCP call end-to-end | D-04 remote mode | Requires live ScaleKit environment + real token | Set SCALEKIT_* env vars, obtain JWT from ScaleKit, call POST /mcp with Bearer token and verify 200 |
| No BaseHTTPMiddleware in stack | D-03 | Runtime stack inspection | Start server, hit GET /health, confirm no anyio task group error in logs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
