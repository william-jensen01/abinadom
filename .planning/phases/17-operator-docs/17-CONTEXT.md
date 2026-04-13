# Phase 17: Operator Docs - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Produce three user-facing guides (connection, self-deploy, key management) plus a root README.md that lets any user or operator go end-to-end without author help. No new server code. No changes to infra/SETUP.md. Documentation artifacts only.

This phase does NOT include changes to auth, server, or infra code.

</domain>

<decisions>
## Implementation Decisions

### Document Structure

- **D-01:** Three guides live in `docs/`: `docs/CONNECTION.md`, `docs/DEPLOY.md`, `docs/KEY-MANAGEMENT.md`. Each guide owns its domain.
- **D-02:** A root `README.md` is created as the entry point — concise project description plus links to all three guides and `infra/SETUP.md`. First thing a GitHub visitor sees.
- **D-03:** `infra/SETUP.md` is unchanged — it is the canonical Caddy + Cloudflare Tunnel walkthrough and stays where it is.

### Self-Deploy Guide (`docs/DEPLOY.md`)

- **D-04:** Written for a Linux server operator — assumes Docker and Docker Compose are already installed, reader can run shell commands and edit files. Starts from "clone the repo". No hand-holding on OS or Docker prerequisites.
- **D-05:** For the Caddy + Cloudflare Tunnel step, `DEPLOY.md` links to `infra/SETUP.md` rather than inlining or duplicating the content. No divergence risk.

### Key Management Guide (`docs/KEY-MANAGEMENT.md`)

- **D-06:** Format is a **reference page** — flat list of all `manage_keys.py` (or `auth/manage_keys.py`) commands with flags and examples. Reader can scan to the command they need.
- **D-07:** Include a **usage log inspection** section showing how to query `auth.db` to see who used which key and when. The usage log is a Phase 14 deliverable and part of operator visibility.

### Connection Guide (`docs/CONNECTION.md`)

- **D-08:** Covers three clients: **Claude.ai (OAuth 2.0)**, **Claude Desktop (bearer token)**, and a **generic/other clients** section (curl, HTTP clients, ChatGPT, etc.).
- **D-09:** Written for a **technical user** — assumes reader knows HTTP APIs, can edit JSON configs, understands auth tokens. Minimal explanation, just the steps and commands.

### Claude's Discretion

- Section ordering within each guide
- Whether to use a table or prose for command flags in the reference page
- Exact formatting conventions (headers, code blocks, notes/warnings)
- Whether the root README includes a brief feature summary or just links

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Infrastructure & Auth

- `infra/SETUP.md` — Full Caddy + Cloudflare Tunnel walkthrough (8 steps + troubleshooting). Self-deploy guide links here for the proxy step.
- `infra/.env.example` — Operator-facing env vars for the infra stack (TUNNEL_TOKEN, DOMAIN)
- `infra/docker-compose.yml` — Infra Compose stack (Caddy + cloudflared)

### MCP Server & Auth

- `scripts/manage_keys.py` — Key management CLI (verified at scripts/, not auth/) — source of truth for all key management commands
- `auth/store.py` — SqliteKeyStore: token hashing, usage log schema
- `.env.example` (project root) — MCP server operator vars (OLLAMA_URL, MCP_HOST, MCP_PORT, CHROMADB_DATA_PATH, AUTH_DATA_PATH)
- `docker-compose.yml` (project root) — MCP Compose stack

### OAuth / Claude.ai Connection

- `auth/oauth.py` — JWKSVerifier, OAuth 2.0 implementation details for Claude.ai remote MCP flow

### Requirements

- `REQUIREMENTS.md` — DOCS-01, DOCS-02, DOCS-03 acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `infra/SETUP.md` — Can be linked directly from DEPLOY.md; fully covers the proxy/tunnel setup step already
- `auth/manage_keys.py` — All CLI commands documented here; KEY-MANAGEMENT.md is a prose wrapper around this file's `--help` output

### Established Patterns

- `infra/SETUP.md` tone: numbered steps, clear prerequisites section, troubleshooting section with numbered items, bash code blocks
- `.env.example` convention: every operator-facing variable has a comment explaining its purpose

### Integration Points

- DEPLOY.md Step N → links to `infra/SETUP.md` for Caddy/Tunnel setup
- README.md → links to docs/CONNECTION.md, docs/DEPLOY.md, docs/KEY-MANAGEMENT.md, infra/SETUP.md

</code_context>

<specifics>
## Specific Ideas

- Key management guide format: reference page (not walkthrough) — user wants to scan to the command they need
- Connection guide: technical user — minimal explanation, commands and config only
- Self-deploy: operator audience — starts at "clone the repo", no Docker prereqs
- Usage log section in KEY-MANAGEMENT.md: show the SQLite query to inspect auth.db

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 17-operator-docs*
*Context gathered: 2026-04-13*
