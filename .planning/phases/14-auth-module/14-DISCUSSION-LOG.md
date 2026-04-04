# Phase 14: Auth Module - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-03
**Phase:** 14-auth-module
**Areas discussed:** Key storage, Usage log persistence, Token security model, Key management interface

---

## Key Storage

| Option | Description | Selected |
|--------|-------------|----------|
| New SQLite file (auth.db) | Separate auth.db with keys table. Queryable, extensible, Docker volume-friendly. | ✓ |
| JSON flat file (keys.json) | Simple dict, human-readable, no dependencies. Harder to query or extend. | |
| Environment variable | API_KEYS=name:token in .env. Pure 12-factor. Revoking requires server restart. | |

**User's choice:** Local `auth.db` — but with a **provider pattern** so the backend can be swapped to Supabase or another service later without touching the enforcement layer.

**Notes:** User wanted something "dynamic — works now but allows room for growth." Resolved as an abstract `KeyStore` interface with `SqliteKeyStore` as the initial implementation. Supabase path preserved as a future `SupabaseKeyStore`.

---

## Usage Log Persistence

| Option | Description | Selected |
|--------|-------------|----------|
| SQLite table in auth.db | usage_log table alongside keys. Queryable — "how many calls did user X make?" | ✓ |
| Append-only log file | JSON lines to logs/usage.log. Simple, grep-able, no schema. | |
| stderr logger only | Matches existing pattern but NOT persistent — lost on container restart. | |

**User's choice:** SQLite table in `auth.db`.

**Notes:** Co-located with keys table in the same `auth.db`. `KeyStore` interface owns `log_request()`.

---

## Token Security Model

| Option | Description | Selected |
|--------|-------------|----------|
| SHA-256 hashed | Store hash only. Token shown once at creation. Compromised DB doesn't expose tokens. | ✓ |
| Plaintext | Store raw token. Simpler, retrievable. Fine for personal use but leaks on DB compromise. | |

**User's choice:** SHA-256 hashed.

**Notes:** Validation uses `hmac.compare_digest` for constant-time comparison. Tokens generated with `secrets.token_urlsafe(32)`.

---

## Key Management Interface

| Option | Description | Selected |
|--------|-------------|----------|
| scripts/manage_keys.py | Dedicated CLI script: create, revoke, list subcommands. Fits existing scripts/ pattern. | ✓ |
| Management HTTP endpoint | POST/DELETE /admin/keys. Needs its own auth layer. More complex to secure. | |
| Direct DB edits | No tooling — operator uses sqlite3 CLI. Bypasses hashing logic, error-prone. | |

**User's choice:** `scripts/manage_keys.py` with `create --name`, `revoke --name`, `list` subcommands.

**Notes:** Consistent with `run_pipeline.py`, `process_all.py`, `process_topics.py` in `scripts/`.

---

## Claude's Discretion

- Module structure (`auth/` package vs flat files)
- Whether `KeyStore` is an ABC or Protocol
- Exact `auth.db` schema details
- Starlette middleware registration approach
- How `manage_keys.py` resolves `AUTH_DB_PATH`

## Deferred Ideas

- Supabase backend (`SupabaseKeyStore`) — growth path identified, implementation deferred
- Rate limiting (AUTH-05), usage admin endpoint (AUTH-06), OAuth 2.1 (AUTH-04) — all deferred per REQUIREMENTS.md
