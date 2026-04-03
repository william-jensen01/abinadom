---
phase: 11
slug: claude-desktop-integration
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-02
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed via pipenv) |
| **Config file** | none — uses default discovery |
| **Quick run command** | `pipenv run py -m pytest tests/test_server.py -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_server.py -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 0 | INTG-02 | unit | `pipenv run py -m pytest tests/test_server.py -k ollama_url -x` | ✅ | ✅ green |
| 11-01-02 | 01 | 0 | INTG-02 | unit | `pipenv run py -m pytest tests/test_server.py -k embedding_function -x` | ✅ | ✅ green |
| 11-01-03 | 01 | 0 | INTG-03 | unit | `pipenv run py -m pytest tests/test_server.py -k instructions -x` | ✅ | ✅ green |
| 11-01-04 | 01 | 0 | INTG-03 | unit | `pipenv run py -m pytest tests/test_server.py -k docstring -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_server.py` — add `test_ollama_url_env_override`, `test_get_embedding_function_url_param`, `test_mcp_has_instructions`, `test_search_docstring_has_collection_hint`, `test_get_talk_docstring_has_workflow_hint`

*All new tests go into the existing `tests/test_server.py` — no new file needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `claude_desktop_config.json` template correctness | INTG-02 | Requires Claude Desktop UI to verify connection | Add config, restart Claude Desktop, confirm MCP server appears connected |
| End-to-end Claude converses about LDS content | INTG-03 | Requires live Claude Desktop + Ollama running | Ask Claude a question about General Conference, verify it uses search/get_talk tools and responds conversationally |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-04-02 (Phase 12 tech debt cleanup)
