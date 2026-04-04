# Phase 14: Auth Module - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Add bearer token authentication to the FastMCP Streamable HTTP server. Every MCP request must include a valid `Authorization: Bearer <token>` header. Operator manages keys via a CLI script. Authenticated requests are stored in a usage log with tool name, timestamp, and user identity. The `/health` endpoint stays public (required for Docker Compose healthcheck in Phase 15).

This phase does NOT add rate limiting (deferred), usage admin endpoint (deferred), OAuth (deferred), or Docker containerization (Phase 15 scope).

</domain>

<decisions>
## Implementation Decisions

### Auth Architecture

- **D-01:** Auth is implemented as a **provider pattern** — the enforcement layer (Starlette middleware) depends on an abstract `KeyStore` interface, not directly on SQLite. This allows the storage backend to be swapped (e.g., to Supabase) without touching the middleware.
- **D-02:** Initial implementation uses local SQLite (`auth.db`) via a `SqliteKeyStore` implementation of the `KeyStore` interface.
- **D-03:** Auth middleware enforces bearer tokens at the Starlette/ASGI level — intercepts all requests before they reach FastMCP tools.
- **D-04:** `/health` endpoint explicitly bypasses auth — no token required. The middleware must allowlist this route.

### Key Storage

- **D-05:** Keys are stored in a new `auth.db` SQLite file (separate from the pipeline database). Contains at minimum: a `keys` table (name, token_hash, created_at) and a `usage_log` table.
- **D-06:** Tokens are stored as **SHA-256 hashes** — never plaintext. The raw token is shown to the operator once at creation time and is not retrievable afterward.
- **D-07:** `auth.db` path is configurable via `AUTH_DB_PATH` env var (12-factor). Default: `<project_root>/auth.db`.

### Usage Logging

- **D-08:** Every authenticated request is stored in a `usage_log` table in `auth.db` with: tool name, timestamp (ISO 8601 UTC), and user identity (key name). AUTH-03 satisfied.
- **D-09:** The `KeyStore` interface owns `log_request(key_name, tool_name, timestamp)` — usage logging is co-located with key management, not scattered across middleware.

### Token Security

- **D-10:** Tokens are generated as cryptographically random strings (e.g., `secrets.token_urlsafe(32)`) — sufficient entropy for personal use.
- **D-11:** Validation: hash the incoming token with SHA-256, compare to stored hash. Constant-time comparison (`hmac.compare_digest`) to prevent timing attacks.

### Key Management Interface

- **D-12:** `scripts/manage_keys.py` — dedicated CLI script following the existing `scripts/` pattern.
  - `create --name <name>` — generates token, stores hash, prints token once
  - `revoke --name <name>` — removes key from keys table
  - `list` — shows all key names and creation dates (never tokens)

### Claude's Discretion

- Module structure within the codebase (`auth/` package vs flat files in project root)
- Whether `KeyStore` is an ABC or a Protocol
- Exact `auth.db` schema details (column names, indexes)
- Whether middleware is added via Starlette `Middleware` class or via ASGI wrapping
- How `manage_keys.py` resolves `AUTH_DB_PATH` (same env var logic as server.py)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Server (auth integrates here)
- `server.py` — FastMCP server; auth middleware mounts on `streamable_http_app()` Starlette instance

### Requirements
- `.planning/REQUIREMENTS.md` §Auth — AUTH-01, AUTH-02, AUTH-03 (key issuance, 401 enforcement, usage logging)

### Roadmap
- `.planning/ROADMAP.md` §Phase 14 — Success criteria (4 items: key creation script, 401 on invalid token, usage log entry per request, existing tools unchanged)

### Prior Phase Context
- `.planning/phases/13-http-transport/13-CONTEXT.md` — Established that `/health` must remain public (Docker Compose healthcheck target); `streamable_http_app()` returns a Starlette app

No external auth specs — bearer token enforcement is standard HTTP (RFC 6750). No library beyond Python stdlib (`secrets`, `hashlib`, `hmac`, `sqlite3`) is required.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `os.environ.get("VAR", default)` pattern — used throughout `server.py` for `MCP_HOST`, `MCP_PORT`, `CHROMADB_PATH`; same pattern for `AUTH_DB_PATH`
- `@mcp.custom_route("/health", ...)` — established that FastMCP supports Starlette route additions; middleware follows the same `streamable_http_app()` integration point
- `scripts/` directory — `run_pipeline.py`, `process_all.py`, `manage_keys.py` fits naturally here

### Established Patterns
- All logging to `sys.stderr` — preserve in middleware; usage logging goes to SQLite, not stderr
- Env var resolution at module level (`MCP_HOST = os.environ.get(...)`) — same for `AUTH_DB_PATH`
- FastMCP 1.26.0: `streamable_http_app()` returns a `Starlette` instance — middleware added here

### Integration Points
- `mcp.streamable_http_app()` — where Starlette middleware is registered for auth enforcement
- `if __name__ == "__main__": mcp.run(transport="streamable-http")` — entry point unchanged
- `AppContext` dataclass — auth context is separate; `KeyStore` instance is NOT added to `AppContext` (tools don't need it)

</code_context>

<specifics>
## Specific Ideas

- Provider pattern was chosen explicitly to allow a future swap to Supabase or another managed auth service without touching the middleware layer. The swap is a one-file change (`sqlite_store.py` → `supabase_store.py`) plus an env var.
- Token shown once at creation, never retrievable — consistent with how services like GitHub, Supabase, and Railway issue API keys.

</specifics>

<deferred>
## Deferred Ideas

- **Supabase backend** — `SqliteKeyStore` is the initial implementation; a `SupabaseKeyStore` can be added later without touching middleware. Noted as the intended growth path.
- **Rate limiting** — AUTH-05 in REQUIREMENTS.md, deferred explicitly.
- **Usage admin endpoint** — AUTH-06 in REQUIREMENTS.md, deferred explicitly.
- **OAuth 2.1** — AUTH-04 in REQUIREMENTS.md, deferred explicitly.

</deferred>

---

*Phase: 14-auth-module*
*Context gathered: 2026-04-03*
