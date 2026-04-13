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

- [x] **Phase 13: HTTP Transport** — Swap stdio transport for Streamable HTTP; expose health endpoint (completed 2026-04-03)
- [x] **Phase 14: Auth Module** — Bearer token API key issuance, request validation, and per-request usage logging (completed 2026-04-04)
- [x] **Phase 15: Docker Compose & Config** — Containerize the full stack with env-var driven configuration (completed 2026-04-04)
- [x] **Phase 16: Caddy & Cloudflare Tunnel** — TLS termination and stable public URL via Caddy + cloudflared in Compose (completed 2026-04-04)
- [x] **Phase 16.1: OAuth 2.0 for Claude Desktop** — OAuth 2.0 auth flow so Claude Desktop can connect via its remote MCP OAuth handshake (completed 2026-04-13)
- [x] **Phase 16.2: FastAPI MCP Protocol Rewrite** — Replace FastMCP with FastAPI + manual JSON-RPC MCP protocol to enable per-method auth and spec-compliant initialize flow (completed 2026-04-09)
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
**Plans:** 2/2 plans complete
Plans:
- [x] 13-01-PLAN.md — Swap stdio to streamable-http transport, wire MCP_HOST/MCP_PORT env vars
- [x] 13-02-PLAN.md — Add GET /health endpoint with live Ollama and ChromaDB dependency checks

### Phase 14: Auth Module
**Goal**: Every request to the server is authenticated and logged by user identity
**Depends on**: Phase 13
**Requirements**: AUTH-01, AUTH-02, AUTH-03
**Success Criteria** (what must be TRUE):
  1. Operator can run a script or command to create a named API key and receive the bearer token
  2. A request without a bearer token, or with an invalid token, receives a 401 response and never reaches a tool
  3. A valid authenticated request is stored in the usage log with tool name, timestamp, and user identity
  4. Existing tool behavior (search, get_talk) is unchanged for authenticated requests
**Plans:** 3/3 plans complete
Plans:
- [x] 14-01-PLAN.md — KeyStore ABC and SqliteKeyStore implementation with full test coverage
- [x] 14-02-PLAN.md — BearerAuthMiddleware and server.py entry point wiring
- [x] 14-03-PLAN.md — manage_keys.py CLI script for key issuance, revocation, and listing
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
**Plans:** 2/2 plans complete
Plans:
- [x] 15-01-PLAN.md — Generate requirements.txt, update .gitignore, create Dockerfile and .dockerignore
- [x] 15-02-PLAN.md — Create docker-compose.yml with healthcheck/bind mounts and .env.example

### Phase 16: Caddy & Cloudflare Tunnel
**Goal**: The server is reachable at a stable public HTTPS URL without exposing the host IP
**Depends on**: Phase 15
**Requirements**: DEPLOY-03, DEPLOY-04
**Success Criteria** (what must be TRUE):
  1. HTTPS requests to the Cloudflare Tunnel URL reach the MCP server (TLS terminated by Caddy)
  2. The host machine's IP address is not revealed to clients; all traffic routes through Cloudflare
  3. Caddy and cloudflared run as services inside the Compose stack — no separate install steps on the host
  4. Restarting the Compose stack restores the public URL automatically (tunnel token persists via env var)
**Plans:** 2/2 plans complete
Plans:
- [x] 16-01-PLAN.md — Create infra/ Compose stack (Caddy + cloudflared) and wire MCP into proxy network
- [x] 16-02-PLAN.md — Setup walkthrough document and end-to-end HTTPS verification

### Phase 16.1: OAuth 2.0 for Claude Desktop
**Goal**: Claude Desktop can connect to the remote MCP server via its built-in OAuth flow
**Depends on**: Phase 16
**Requirements**: OAUTH-01, OAUTH-02, OAUTH-03
**Success Criteria** (what must be TRUE):
  1. Claude Desktop's "Add MCP Server" dialog completes the OAuth handshake against this server
  2. Server implements `/.well-known/oauth-protected-resource/mcp` (RFC 9728) and proxies `/.well-known/oauth-authorization-server` to Auth0
  3. Static bearer token auth is removed; Auth0 JWT is the sole auth path
**Plans:** 5/5 plans complete
Plans:
- [x] 16.1-01-PLAN.md — Auth0JWTVerifier and DualTokenVerifier with full test coverage (superseded)
- [x] 16.1-02-PLAN.md — Wire OAuth into FastMCP constructor, Auth0 discovery proxy, env config (superseded)
- [x] 16.1-03-PLAN.md — Auth0 tenant setup (operator) and end-to-end verification (completed 2026-04-13)
- [x] 16.1-04-PLAN.md — Corrective: replace custom auth with mcpauth resource-server mode (superseded)
- [x] 16.1-05-PLAN.md — Corrective: replace mcpauth with algorithm-agnostic JWT verifier, add RFC 9728 endpoint

### Phase 16.2: FastAPI MCP Protocol Rewrite
**Goal**: The MCP server runs on FastAPI with a manual JSON-RPC dispatcher, enabling per-method auth routing and spec-compliant `initialize` (no auth required)
**Depends on**: Phase 16.1
**Requirements**: OAUTH-01, OAUTH-02, OAUTH-03
**Success Criteria** (what must be TRUE):
  1. `initialize` succeeds without a token; `tools/list` and `tools/call` require a valid OAuth token
  2. HS256 tokens from DCR-registered clients (Claude Desktop, Cursor) validate via `/userinfo`; RS256 tokens validate via JWKS
  3. All existing tool behavior (`search`, `get_talk`) is unchanged for authenticated requests
  4. `BaseHTTPMiddleware` and FastMCP are fully removed; server starts cleanly under FastAPI
**Plans:** 2/2 plans complete
Plans:
- [x] 16.2-01-PLAN.md — Install FastAPI, kid-based token routing in oauth.py, Wave 0 test stubs
- [x] 16.2-02-PLAN.md — Full server.py rewrite to FastAPI + MCP JSON-RPC dispatcher, all tests passing

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
| 13. HTTP Transport | v3.0 | 2/2 | Complete    | 2026-04-03 |
| 14. Auth Module | v3.0 | 2/3 | Complete    | 2026-04-04 |
| 15. Docker Compose & Config | v3.0 | 2/2 | Complete    | 2026-04-04 |
| 16. Caddy & Cloudflare Tunnel | v3.0 | 2/2 | Complete    | 2026-04-05 |
| 16.1 OAuth 2.0 for Claude Desktop | v3.0 | 5/5 | Complete   | 2026-04-13 |
| 16.2 FastAPI MCP Protocol Rewrite | v3.0 | 2/2 | Complete   | 2026-04-09 |
| 17. Operator Docs | v3.0 | 0/? | Not started | - |
