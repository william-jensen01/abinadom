# Roadmap — BYU Scripture Citation Index RAG System

## Milestones

- ✅ **v1.0 General Conference Pipeline** — Phases 1–8 (shipped 2026-03-27)
- ✅ **v2.0 MCP Server** — Phases 9–12 (shipped 2026-04-03)
- 🚧 **v3.0 Remote MCP** — Phases 13–17 (in progress)

## Phases

<details>
<summary>✅ v1.0 General Conference Pipeline (Phases 1–8) — SHIPPED 2026-03-27</summary>

- [x] Phase 1: DB Enrichment (5/5 plans) — completed 2026-03-20
- [x] Phase 2: Code Quality (2/2 plans) — completed 2026-03-21
- [x] Phase 3: Bug Audit & Fixes (3/3 plans) — completed 2026-03-22
- [x] Phase 4: Test Coverage (3/3 plans) — completed 2026-03-24
- [x] Phase 5: ChromaDB Loader (3/3 plans) — completed 2026-03-25
- [x] Phase 6: Pipeline Orchestrator (2/2 plans) — completed 2026-03-26
- [x] Phase 7: Full Run & Verification (2/2 plans) — completed 2026-03-27
- [x] Phase 8: Topic Metadata (1/1 plan) — completed 2026-03-27

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v2.0 MCP Server (Phases 9–12) — SHIPPED 2026-04-03</summary>

- [x] Phase 9: Server Foundation (1/1 plans) — completed 2026-04-02
- [x] Phase 9.1: Paragraph Metadata Enrichment (1/1 plans) — completed 2026-04-02
- [x] Phase 10: Tools & Normalization (2/2 plans) — completed 2026-04-02
- [x] Phase 11: Claude Desktop Integration (2/2 plans) — completed 2026-04-03
- [x] Phase 12: Tech Debt & Validation Cleanup (1/1 plans) — completed 2026-04-03

Full details: `.planning/milestones/v2.0-ROADMAP.md`

</details>

### 🚧 v3.0 Remote MCP (In Progress)

**Milestone Goal:** Move from stdio/local to a cloud-portable HTTP MCP server accessible from any frontier LLM client, with bearer token auth and a Docker Compose deployment stack.

- [ ] **Phase 13: HTTP Transport** — Swap stdio transport for Streamable HTTP; expose health endpoint
- [ ] **Phase 14: Auth Module** — Bearer token API key issuance, request validation, and per-request usage logging
- [ ] **Phase 15: Docker Compose & Config** — Containerize the full stack with env-var driven configuration
- [ ] **Phase 16: Caddy & Cloudflare Tunnel** — TLS termination and stable public URL via Caddy + cloudflared in Compose
- [ ] **Phase 17: Operator Docs** — Connection guide, self-deploy guide, and key management guide

## Phase Details

### Phase 13: HTTP Transport
**Goal**: Any MCP client can connect to the server over a stable HTTP URL
**Depends on**: Phase 12 (v2.0 complete)
**Requirements**: TRANS-01, TRANS-02
**Success Criteria** (what must be TRUE):
  1. An MCP client pointed at the server's HTTP URL receives valid MCP responses (search and get_talk tools work)
  2. A GET request to /health returns 200 with a machine-readable status payload
  3. The stdio transport path is removed; the server starts cleanly with no stdio references
**Plans:** 1/2 plans executed
Plans:
- [x] 13-01-PLAN.md — Swap stdio to streamable-http transport, wire MCP_HOST/MCP_PORT env vars
- [ ] 13-02-PLAN.md — Add GET /health endpoint with live Ollama and ChromaDB dependency checks

### Phase 14: Auth Module
**Goal**: Every request to the server is authenticated and logged by user identity
**Depends on**: Phase 13
**Requirements**: AUTH-01, AUTH-02, AUTH-03
**Success Criteria** (what must be TRUE):
  1. Operator can run a script or command to create a named API key and receive the bearer token
  2. A request without a bearer token, or with an invalid token, receives a 401 response and never reaches a tool
  3. A valid authenticated request is stored in the usage log with tool name, timestamp, and user identity
  4. Existing tool behavior (search, get_talk) is unchanged for authenticated requests
**Plans**: TBD
**UI hint**: no

### Phase 15: Docker Compose & Config
**Goal**: The full stack runs on any machine with a single command and zero hardcoded values
**Depends on**: Phase 14
**Requirements**: DEPLOY-01, DEPLOY-02
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts mcp-server and ollama containers with no manual steps beyond filling in .env
  2. A .env.example file documents every configurable value; changing a value in .env takes effect on next compose up
  3. No secrets or absolute paths appear in any tracked file (Dockerfile, compose.yml, server.py)
  4. An operator on a fresh VPS can bring up the stack by copying the repo and editing .env
**Plans**: TBD

### Phase 16: Caddy & Cloudflare Tunnel
**Goal**: The server is reachable at a stable public HTTPS URL without exposing the host IP
**Depends on**: Phase 15
**Requirements**: DEPLOY-03, DEPLOY-04
**Success Criteria** (what must be TRUE):
  1. HTTPS requests to the Cloudflare Tunnel URL reach the MCP server (TLS terminated by Caddy)
  2. The host machine's IP address is not revealed to clients; all traffic routes through Cloudflare
  3. Caddy and cloudflared run as services inside the Compose stack — no separate install steps on the host
  4. Restarting the Compose stack restores the public URL automatically (tunnel token persists via env var)
**Plans**: TBD

### Phase 17: Operator Docs
**Goal**: Any user or operator can onboard, deploy, or manage keys without asking the author
**Depends on**: Phase 16
**Requirements**: DOCS-01, DOCS-02, DOCS-03
**Success Criteria** (what must be TRUE):
  1. A user follows the connection guide and successfully connects Claude.ai or another MCP client to the live server
  2. An operator follows the self-deploy guide and has a running stack on a new machine without prior knowledge of the project
  3. An operator follows the key management guide to issue a new key, verify it works, revoke it, and confirm it no longer authenticates
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. DB Enrichment | v1.0 | 5/5 | Complete | 2026-03-20 |
| 2. Code Quality | v1.0 | 2/2 | Complete | 2026-03-21 |
| 3. Bug Audit & Fixes | v1.0 | 3/3 | Complete | 2026-03-22 |
| 4. Test Coverage | v1.0 | 3/3 | Complete | 2026-03-24 |
| 5. ChromaDB Loader | v1.0 | 3/3 | Complete | 2026-03-25 |
| 6. Pipeline Orchestrator | v1.0 | 2/2 | Complete | 2026-03-26 |
| 7. Full Run & Verification | v1.0 | 2/2 | Complete | 2026-03-27 |
| 8. Topic Metadata | v1.0 | 1/1 | Complete | 2026-03-27 |
| 9. Server Foundation | v2.0 | 1/1 | Complete | 2026-04-02 |
| 9.1 Paragraph Metadata Enrichment | v2.0 | 1/1 | Complete | 2026-04-02 |
| 10. Tools & Normalization | v2.0 | 2/2 | Complete | 2026-04-02 |
| 11. Claude Desktop Integration | v2.0 | 2/2 | Complete | 2026-04-03 |
| 12. Tech Debt & Validation Cleanup | v2.0 | 1/1 | Complete | 2026-04-03 |
| 13. HTTP Transport | v3.0 | 1/2 | In Progress|  |
| 14. Auth Module | v3.0 | 0/? | Not started | - |
| 15. Docker Compose & Config | v3.0 | 0/? | Not started | - |
| 16. Caddy & Cloudflare Tunnel | v3.0 | 0/? | Not started | - |
| 17. Operator Docs | v3.0 | 0/? | Not started | - |
