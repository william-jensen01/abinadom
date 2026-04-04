# Requirements: BYU Scripture Citation Index RAG System

**Defined:** 2026-04-03
**Core Value:** All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks and discourse, with full referential integrity between talks, paragraphs, citations, and footnotes.

## v3.0 Requirements

Requirements for the Remote MCP milestone. Each maps to roadmap phases.

### Transport

- [x] **TRANS-01**: User can connect any MCP client (Claude.ai, ChatGPT, etc.) via Streamable HTTP URL
- [x] **TRANS-02**: Operator can verify server health via GET /health endpoint

### Auth

- [x] **AUTH-01**: Operator can issue a named API key for a user
- [ ] **AUTH-02**: Server rejects requests without a valid bearer token with 401
- [x] **AUTH-03**: Server logs tool name, timestamp, and user for every authenticated request

### Deployment

- [x] **DEPLOY-01**: Operator can run full stack via `docker compose up` (mcp-server + ollama)
- [x] **DEPLOY-02**: All secrets and paths configurable via .env file — no hardcoded values
- [x] **DEPLOY-03**: Caddy reverse proxy handles TLS termination inside Compose stack
- [x] **DEPLOY-04**: cloudflared in Compose stack exposes stable public URL via Cloudflare Tunnel

### Docs

- [ ] **DOCS-01**: User can connect Claude.ai, ChatGPT, or any MCP client using the connection guide
- [ ] **DOCS-02**: Operator can deploy stack on a new machine following the self-deploy guide
- [ ] **DOCS-03**: Operator can issue, revoke, and rotate API keys following the key management guide

## Future Requirements

Deferred to future milestones. Tracked but not in current roadmap.

### Auth

- **AUTH-04**: OAuth 2.1 authorization flow (MCP spec compliant) — upgrade path from bearer tokens
- **AUTH-05**: Per-user rate limiting
- **AUTH-06**: Usage query / admin endpoint (view stats per user)

### Content

- **CONT-01**: Journal of Discourse content indexed and searchable — Milestone 4
- **CONT-02**: Standard LDS scriptures indexed and searchable — Milestone 5+

## Out of Scope

| Feature | Reason |
|---------|--------|
| OAuth 2.1 | Complexity not warranted at current scale; upgrade path preserved |
| stdio fallback | Desktop use case retired; HTTP transport replaces it |
| Usage admin endpoint | Nice-to-have; logs in SQLite are accessible directly |
| Rate limiting | Audience is trusted users; defer until abuse is observed |
| Remote/hosted ChromaDB | Local volume mount sufficient; VPS migration is a copy operation |
| Web UI for key management | CLI/script sufficient for operator |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TRANS-01 | Phase 13 | Complete |
| TRANS-02 | Phase 13 | Complete |
| AUTH-01 | Phase 14 | Complete |
| AUTH-02 | Phase 14 | Pending |
| AUTH-03 | Phase 14 | Complete |
| DEPLOY-01 | Phase 15 | Complete |
| DEPLOY-02 | Phase 15 | Complete |
| DEPLOY-03 | Phase 16 | Complete |
| DEPLOY-04 | Phase 16 | Complete |
| DOCS-01 | Phase 17 | Pending |
| DOCS-02 | Phase 17 | Pending |
| DOCS-03 | Phase 17 | Pending |

**Coverage:**
- v3.0 requirements: 12 total
- Mapped to phases: 12 (100%)
- Unmapped: 0

---
*Requirements defined: 2026-04-03*
*Last updated: 2026-04-03 — traceability filled after roadmap creation (Phases 13–17)*
