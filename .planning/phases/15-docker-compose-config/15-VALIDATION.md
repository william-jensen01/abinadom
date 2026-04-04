---
phase: 15
slug: docker-compose-config
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (project standard) |
| **Config file** | none — invoked directly |
| **Quick run command** | `pipenv run py -m pytest tests/test_server.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -x -q` |
| **Estimated runtime** | ~10 seconds (existing suite; no new test files) |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_server.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green + smoke check `docker compose up`
- **Max feedback latency:** ~10 seconds (unit); smoke checks are manual

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 0 | DEPLOY-02 | static | `grep "^\.env$" .gitignore` | ✅ existing | ⬜ pending |
| 15-01-02 | 01 | 0 | DEPLOY-02 | generated | `test -f requirements.txt && wc -l requirements.txt` | ❌ W0 | ⬜ pending |
| 15-02-01 | 02 | 1 | DEPLOY-01 | static | `grep "FROM python:3.12-slim" Dockerfile` | ❌ W0 | ⬜ pending |
| 15-02-02 | 02 | 1 | DEPLOY-01 | static | `grep "COPY requirements.txt" Dockerfile` | ❌ W0 | ⬜ pending |
| 15-03-01 | 03 | 1 | DEPLOY-01 | static | `grep "start_period: 60s" docker-compose.yml` | ❌ W0 | ⬜ pending |
| 15-03-02 | 03 | 1 | DEPLOY-02 | static | `grep "CHROMADB_DATA_PATH" docker-compose.yml` | ❌ W0 | ⬜ pending |
| 15-04-01 | 04 | 1 | DEPLOY-02 | static | `grep "OLLAMA_URL" .env.example` | ❌ W0 | ⬜ pending |
| 15-04-02 | 04 | 2 | DEPLOY-01/02 | smoke/manual | `docker compose up -d && sleep 15 && curl -f http://localhost:8000/health` | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Verify `.env` is in `.gitignore` — prerequisite before any files are committed
- [ ] Generate `requirements.txt` via `pipenv requirements > requirements.txt` — prerequisite for Dockerfile `COPY requirements.txt .`

*No new test stub files required — DEPLOY-01/DEPLOY-02 are verified by static checks and smoke testing against the live compose stack.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose up` starts mcp-server container | DEPLOY-01 | Requires Docker daemon + running Ollama + real filesystem paths | `docker compose up -d && sleep 15 && curl -f http://localhost:8000/health` |
| Container healthcheck shows `healthy` | DEPLOY-01 | Requires live compose stack and ChromaDB initialization | `docker compose ps` → verify `(healthy)` after startup window |
| Changing .env value takes effect on next `compose up` | DEPLOY-02 | Requires live stack and manual config change | Update `MCP_PORT`, `docker compose up -d`, verify new port responds |
| Operator can bring up stack on fresh VPS | DEPLOY-01/02 | End-to-end deployment test | Copy repo, fill `.env`, run `docker compose up`, verify health |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s (unit); manual smoke tests documented
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
