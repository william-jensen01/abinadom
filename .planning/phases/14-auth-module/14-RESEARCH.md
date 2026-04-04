# Phase 14: Auth Module - Research

**Researched:** 2026-04-03
**Domain:** Bearer token authentication, Starlette middleware, SQLite key storage, Python stdlib security
**Confidence:** HIGH

## Summary

Phase 14 adds bearer token authentication to the FastMCP Streamable HTTP server. All architectural decisions are locked in CONTEXT.md — the research task is to verify the technical approach is sound, confirm the integration points behave as expected, and surface any pitfalls before planning.

All major claims were verified by live code inspection and test execution against the actual installed packages (mcp 1.26.0, starlette 1.0.0, pytest 9.0.2). No third-party libraries beyond Python stdlib are required — `secrets`, `hashlib`, `hmac`, and `sqlite3` are sufficient for every locked decision.

The key integration finding: `mcp.streamable_http_app()` returns a `Starlette` instance and `Starlette.add_middleware()` is available on it. A `BaseHTTPMiddleware` subclass with a `/health` allowlist is confirmed to produce the correct behavior — 200 for `/health` without a token, 401 for unauthenticated MCP requests, pass-through for valid tokens. This was verified with live tests against the installed packages.

**Primary recommendation:** Implement auth as a `BaseHTTPMiddleware` subclass added via `app.add_middleware()` on the `Starlette` instance returned by `mcp.streamable_http_app()`. No OAuth, no external libraries, no changes to existing tools.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Auth is implemented as a **provider pattern** — the enforcement layer (Starlette middleware) depends on an abstract `KeyStore` interface, not directly on SQLite.
- **D-02:** Initial implementation uses local SQLite (`auth.db`) via a `SqliteKeyStore` implementation of the `KeyStore` interface.
- **D-03:** Auth middleware enforces bearer tokens at the Starlette/ASGI level — intercepts all requests before they reach FastMCP tools.
- **D-04:** `/health` endpoint explicitly bypasses auth — no token required. The middleware must allowlist this route.
- **D-05:** Keys are stored in a new `auth.db` SQLite file (separate from the pipeline database). Contains at minimum: a `keys` table (name, token_hash, created_at) and a `usage_log` table.
- **D-06:** Tokens are stored as **SHA-256 hashes** — never plaintext. The raw token is shown to the operator once at creation time and is not retrievable afterward.
- **D-07:** `auth.db` path is configurable via `AUTH_DB_PATH` env var (12-factor). Default: `<project_root>/auth.db`.
- **D-08:** Every authenticated request is stored in a `usage_log` table in `auth.db` with: tool name, timestamp (ISO 8601 UTC), and user identity (key name).
- **D-09:** The `KeyStore` interface owns `log_request(key_name, tool_name, timestamp)`.
- **D-10:** Tokens are generated as cryptographically random strings (`secrets.token_urlsafe(32)`).
- **D-11:** Validation: hash the incoming token with SHA-256, compare with `hmac.compare_digest` (constant-time).
- **D-12:** `scripts/manage_keys.py` CLI with `create --name`, `revoke --name`, `list` subcommands.

### Claude's Discretion

- Module structure within the codebase (`auth/` package vs flat files in project root)
- Whether `KeyStore` is an ABC or a Protocol
- Exact `auth.db` schema details (column names, indexes)
- Whether middleware is added via Starlette `Middleware` class or via ASGI wrapping
- How `manage_keys.py` resolves `AUTH_DB_PATH` (same env var logic as server.py)

### Deferred Ideas (OUT OF SCOPE)

- **Supabase backend** — `SqliteKeyStore` is the initial implementation; a `SupabaseKeyStore` can be added later.
- **Rate limiting** — AUTH-05, deferred explicitly.
- **Usage admin endpoint** — AUTH-06, deferred explicitly.
- **OAuth 2.1** — AUTH-04, deferred explicitly.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | Operator can issue a named API key for a user | `scripts/manage_keys.py create --name <name>` writes to `keys` table; token printed once |
| AUTH-02 | Server rejects requests without a valid bearer token with 401 | `BaseHTTPMiddleware` on `streamable_http_app()` returns 401; confirmed by live test |
| AUTH-03 | Server logs tool name, timestamp, and user for every authenticated request | `usage_log` table in `auth.db`; `KeyStore.log_request()` called from middleware after successful auth |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `secrets` (stdlib) | Python 3.6+ | Cryptographically secure token generation | Built-in, no install required |
| `hashlib` (stdlib) | Python 3.x | SHA-256 hashing of tokens | Built-in, no install required |
| `hmac` (stdlib) | Python 3.x | Constant-time comparison to prevent timing attacks | Built-in, RFC-recommended approach |
| `sqlite3` (stdlib) | Python 3.x | Persistent key and usage log storage | Built-in; no separate service needed |
| `starlette.middleware.base.BaseHTTPMiddleware` | starlette 1.0.0 (installed) | ASGI middleware for request interception | Already a project dependency via mcp |
| `argparse` (stdlib) | Python 3.x | CLI argument parsing for `manage_keys.py` | Matches pattern in all other project scripts |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `abc.ABC` or `typing.Protocol` | stdlib | Define `KeyStore` interface | Module structure decision (Claude's Discretion) |
| `datetime` (stdlib) | Python 3.x | ISO 8601 UTC timestamps | For `usage_log` timestamp column |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `sqlite3` stdlib | `aiosqlite` | Async writes; unnecessary at current scale — sqlite writes are <1ms |
| `BaseHTTPMiddleware` | Pure ASGI middleware | More complex; `BaseHTTPMiddleware` is sufficient and simpler |
| `ABC` | `Protocol` | Protocol is more Pythonic for structural typing; either works, both stdlib |

**Installation:** No new dependencies. Everything is Python stdlib or already installed.

**Version verification (confirmed live):**
- `mcp`: 1.26.0 (installed)
- `starlette`: 1.0.0 (installed)
- `pytest`: 9.0.2 (installed)
- Python stdlib modules: confirmed functional by live test execution

---

## Architecture Patterns

### Recommended Project Structure

```
auth/
├── __init__.py          # exports KeyStore, SqliteKeyStore
├── store.py             # KeyStore ABC/Protocol + SqliteKeyStore implementation
└── middleware.py        # BearerAuthMiddleware (BaseHTTPMiddleware subclass)

scripts/
└── manage_keys.py       # CLI: create / revoke / list
```

Rationale: An `auth/` package is the natural home — it mirrors `config/` and `models/` patterns. The middleware file stays separate from the store for clean dependency direction: middleware imports `KeyStore`, not `SqliteKeyStore` directly (satisfying D-01).

### Pattern 1: KeyStore Interface + SqliteKeyStore

**What:** Abstract interface (`ABC` or `Protocol`) with `verify_token(raw_token) -> str | None` and `log_request(key_name, tool_name, timestamp)` methods. `SqliteKeyStore` implements both.

**When to use:** Any access to token validation or usage logging goes through `KeyStore`. Middleware holds a `KeyStore` instance — never a direct `sqlite3.Connection`.

**Example:**
```python
# auth/store.py
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
import sqlite3
from pathlib import Path

class KeyStore(ABC):
    @abstractmethod
    def verify_token(self, raw_token: str) -> str | None:
        """Return key name if valid, None if invalid."""
        ...

    @abstractmethod
    def log_request(self, key_name: str, tool_name: str, timestamp: str) -> None:
        ...

class SqliteKeyStore(KeyStore):
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS keys (
                    name TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_name TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)

    def create_key(self, name: str) -> str:
        """Generate token, store hash, return raw token (shown once)."""
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO keys (name, token_hash, created_at) VALUES (?, ?, ?)",
                (name, token_hash, timestamp),
            )
        return token

    def verify_token(self, raw_token: str) -> str | None:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, token_hash FROM keys WHERE token_hash = ?",
                (token_hash,),  # Lookup by hash, not by name — avoids full table scan timing leak
            ).fetchone()
        if row is None:
            return None
        # Constant-time comparison as final defense
        if hmac.compare_digest(row["token_hash"], token_hash):
            return row["name"]
        return None

    def log_request(self, key_name: str, tool_name: str, timestamp: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO usage_log (key_name, tool_name, timestamp) VALUES (?, ?, ?)",
                (key_name, tool_name, timestamp),
            )

    def revoke_key(self, name: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM keys WHERE name = ?", (name,))
        return cur.rowcount > 0

    def list_keys(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, created_at FROM keys ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]
```

### Pattern 2: BearerAuthMiddleware

**What:** `BaseHTTPMiddleware` subclass mounted on the `Starlette` app returned by `mcp.streamable_http_app()`. Intercepts all HTTP requests, allows `/health` through without a token, returns 401 for missing or invalid tokens, extracts tool name from MCP JSON-RPC body and logs the request.

**When to use:** Single class in `auth/middleware.py`. Imported and mounted in `server.py` after `streamable_http_app()` is called.

**Example:**
```python
# auth/middleware.py
import json
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from auth.store import KeyStore

PUBLIC_PATHS = {"/health"}

class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, store: KeyStore) -> None:
        super().__init__(app)
        self._store = store

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return Response(
                '{"error": "Missing bearer token"}',
                status_code=401,
                media_type="application/json",
            )

        raw_token = auth_header[len("Bearer "):]
        key_name = self._store.verify_token(raw_token)
        if key_name is None:
            return Response(
                '{"error": "Invalid token"}',
                status_code=401,
                media_type="application/json",
            )

        # Extract tool name from MCP JSON-RPC body for usage logging
        tool_name = await _extract_tool_name(request)
        timestamp = datetime.now(timezone.utc).isoformat()
        self._store.log_request(key_name, tool_name, timestamp)

        return await call_next(request)


async def _extract_tool_name(request: Request) -> str:
    """Parse MCP JSON-RPC body to extract tool name, return 'unknown' on any error."""
    try:
        body = await request.body()
        payload = json.loads(body)
        if payload.get("method") == "tools/call":
            return payload.get("params", {}).get("name", "unknown")
        return payload.get("method", "unknown")
    except Exception:
        return "unknown"
```

**Integration in server.py:**
```python
# server.py additions (after existing imports)
import os
from auth.store import SqliteKeyStore
from auth.middleware import BearerAuthMiddleware

AUTH_DB_PATH = os.environ.get(
    "AUTH_DB_PATH",
    str(Path(__file__).parent.resolve() / "auth.db")
)

# In the entry point section (not at module level — needs streamable_http_app())
if __name__ == "__main__":
    store = SqliteKeyStore(AUTH_DB_PATH)
    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware, store=store)
    import uvicorn
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
```

**CRITICAL NOTE on entry point:** `mcp.run(transport="streamable-http")` does NOT expose the Starlette app for middleware injection. The entry point must switch to calling `mcp.streamable_http_app()` directly and running via uvicorn. This is the only change to the existing entry point.

### Pattern 3: manage_keys.py CLI

**What:** Standalone script following the exact pattern of `scripts/run_pipeline.py` — `sys.path.insert`, `argparse`, `logging`, main guard.

**Example:**
```python
# scripts/manage_keys.py
"""Key management CLI for the LDS MCP server auth module.

Usage:
    pipenv run py scripts/manage_keys.py create --name alice
    pipenv run py scripts/manage_keys.py revoke --name alice
    pipenv run py scripts/manage_keys.py list
"""
import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.store import SqliteKeyStore

logger = logging.getLogger(__name__)

AUTH_DB_PATH = os.environ.get(
    "AUTH_DB_PATH",
    str(Path(__file__).parent.parent / "auth.db"),
)

def main() -> None:
    parser = argparse.ArgumentParser(description="Manage API keys for the MCP server")
    sub = parser.add_subparsers(dest="command", required=True)

    create_p = sub.add_parser("create", help="Issue a new API key")
    create_p.add_argument("--name", required=True, help="Name for the key (e.g. 'alice')")

    revoke_p = sub.add_parser("revoke", help="Revoke a key by name")
    revoke_p.add_argument("--name", required=True, help="Name of the key to revoke")

    sub.add_parser("list", help="List all key names and creation dates")

    args = parser.parse_args()
    store = SqliteKeyStore(AUTH_DB_PATH)

    if args.command == "create":
        token = store.create_key(args.name)
        print(f"Key '{args.name}' created.")
        print(f"Token (save this — it will not be shown again):\n{token}")

    elif args.command == "revoke":
        removed = store.revoke_key(args.name)
        if removed:
            print(f"Key '{args.name}' revoked.")
        else:
            print(f"No key named '{args.name}' found.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        keys = store.list_keys()
        if not keys:
            print("No keys found.")
        else:
            print(f"{'Name':<30} {'Created'}")
            print("-" * 60)
            for k in keys:
                print(f"{k['name']:<30} {k['created_at']}")

if __name__ == "__main__":
    main()
```

### Anti-Patterns to Avoid

- **Reading request body outside `BaseHTTPMiddleware`:** Raw ASGI middleware requires manual body buffering. `BaseHTTPMiddleware` uses `_CachedRequest` internally — body reads in `dispatch()` are safe and do not consume the stream for downstream handlers.
- **Storing raw tokens:** Never store the plaintext token in `auth.db`. Only the SHA-256 hex digest.
- **Using `==` for hash comparison:** Always use `hmac.compare_digest()` to prevent timing attacks, even though SQLite lookup by hash already narrows the timing surface.
- **Mounting middleware before `streamable_http_app()` is called:** `mcp.streamable_http_app()` creates the session manager lazily and adds `_custom_starlette_routes`. Call it first, then `add_middleware()`.
- **Adding KeyStore to AppContext:** Tools (`search`, `get_talk`) must NOT have access to `KeyStore`. Auth context is separate (D-01, confirmed in CONTEXT.md `code_context` section).
- **Using `mcp.run()` with middleware:** `mcp.run(transport="streamable-http")` starts uvicorn internally with no hook to inject middleware. The entry point must use `mcp.streamable_http_app()` + `uvicorn.run()` directly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cryptographic token generation | Custom random string | `secrets.token_urlsafe(32)` | Uses OS CSPRNG; custom implementations have entropy pitfalls |
| Timing-safe comparison | `token_a == token_b` | `hmac.compare_digest(a, b)` | Prevents timing oracle attacks; stdlib, no effort |
| ASGI request interception | Custom ASGI app wrapper | `BaseHTTPMiddleware` | Handles streaming, body buffering, error propagation correctly |
| Token hashing | Custom hash scheme | `hashlib.sha256(token.encode()).hexdigest()` | SHA-256 is standard, fast, and sufficient for personal-use API keys |

**Key insight:** The stdlib provides everything needed. The complexity in API key systems is in the operational details (token shown once, constant-time comparison, separate db file), not in the libraries.

---

## Common Pitfalls

### Pitfall 1: `mcp.run()` Does Not Accept Middleware

**What goes wrong:** Calling `mcp.run(transport="streamable-http")` and trying to inject middleware before or after — there is no hook. The middleware never executes.

**Why it happens:** `mcp.run()` creates and starts uvicorn internally with the Starlette app it builds, bypassing any external app wrapper.

**How to avoid:** Switch entry point to `mcp.streamable_http_app()` + `app.add_middleware(BearerAuthMiddleware, store=store)` + `uvicorn.run(app, ...)`. Uvicorn is already installed as a transitive dependency of mcp.

**Warning signs:** Server starts, `/health` works, but auth is never enforced — every request passes through.

### Pitfall 2: BaseHTTPMiddleware `__init__` Signature

**What goes wrong:** Passing constructor arguments to `BaseHTTPMiddleware` subclass without overriding `__init__` correctly. `app.add_middleware(BearerAuthMiddleware, store=store)` passes `store` as a kwarg to `__init__`.

**Why it happens:** Starlette's `add_middleware` passes extra kwargs to the class constructor. The subclass must accept them explicitly.

**How to avoid:** Always define `def __init__(self, app, store: KeyStore) -> None: super().__init__(app); self._store = store`.

**Warning signs:** `TypeError: __init__() got unexpected keyword argument 'store'` at startup.

### Pitfall 3: Request Body Consumed Before Downstream Handler

**What goes wrong:** Calling `await request.body()` in middleware appears to consume the body, causing empty body errors in FastMCP's MCP handler downstream.

**Why it happens:** In older Starlette versions, body reads in middleware were destructive. In Starlette 1.0.0 with `BaseHTTPMiddleware`, `_CachedRequest` caches the body — this is NOT a problem.

**How to avoid:** Confirmed safe on starlette 1.0.0. Rely on `BaseHTTPMiddleware`'s built-in caching. No manual body replay needed.

**Warning signs:** MCP tool calls return parse errors or empty responses even with a valid token.

### Pitfall 4: SQLite Thread Safety with Async Middleware

**What goes wrong:** Creating a single `sqlite3.Connection` at `SqliteKeyStore.__init__` time and sharing it across async requests causes `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that thread`.

**Why it happens:** `sqlite3.Connection` is not thread-safe. FastMCP/uvicorn runs multiple async coroutines.

**How to avoid:** Open a new connection per operation (`self._connect()` as shown in Pattern 1). SQLite connections are cheap; connection-per-operation is the correct pattern for stdlib sqlite3 in async contexts.

**Warning signs:** `ProgrammingError: SQLite objects created in a thread...` errors under concurrent requests.

### Pitfall 5: AUTH_DB_PATH Default Resolution

**What goes wrong:** Using `os.getcwd()` as the base for the default `auth.db` path. The working directory when the server starts depends on how the caller invokes it (especially under Docker or Claude Desktop).

**Why it happens:** Same issue solved for `CHROMADB_PATH` in Phase 13 — `cwd` is unreliable.

**How to avoid:** Use `Path(__file__).parent.resolve()` as the base, matching the `_resolve_chromadb_path()` pattern already in `server.py`.

**Warning signs:** `auth.db` created in an unexpected directory; keys not found on restart.

### Pitfall 6: Forgetting to Log Non-Tool MCP Methods

**What goes wrong:** Logging `tool_name = "unknown"` for MCP initialize, ping, and list-tools requests creates noise in `usage_log` that looks like auth failures.

**Why it happens:** MCP JSON-RPC sends `initialize`, `tools/list`, and `ping` methods before any `tools/call`.

**How to avoid:** Log all authenticated requests (the requirement says "every authenticated request"), but use `payload.get("method", "unknown")` to capture the method name for non-tool-call methods. This satisfies AUTH-03 faithfully.

---

## Code Examples

### Verified: Middleware on streamable_http_app() with /health bypass

```python
# Source: live test against mcp 1.26.0 / starlette 1.0.0
# Result: health=200, mcp_no_auth=401, mcp_with_token passes to app
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

mcp = FastMCP("test")
app = mcp.streamable_http_app()   # Returns Starlette instance

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in {"/health"}:
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return Response('{"error":"Unauthorized"}', status_code=401, media_type="application/json")
        return await call_next(request)

app.add_middleware(BearerAuthMiddleware)
# Verified: /health → 200, /mcp no token → 401, /mcp with token → passes through
```

### Verified: SHA-256 token hashing and constant-time comparison

```python
# Source: live Python 3.x test (stdlib only)
import secrets, hashlib, hmac

token = secrets.token_urlsafe(32)           # 43-char URL-safe string
token_hash = hashlib.sha256(token.encode()).hexdigest()  # 64-char hex
is_valid = hmac.compare_digest(token_hash, token_hash)  # True — constant-time
```

### Verified: SQLite schema and per-operation connection pattern

```python
# Source: live test — confirmed schema creates and inserts correctly
import sqlite3, tempfile, os
conn = sqlite3.connect("auth.db")
conn.execute("""
    CREATE TABLE IF NOT EXISTS keys (
        name TEXT PRIMARY KEY,
        token_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS usage_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_name TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )
""")
conn.commit()
```

### Verified: MCP JSON-RPC tool name extraction

```python
# Source: MCP JSON-RPC 2.0 wire format — tools/call method
import json
body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search","arguments":{}}}'
payload = json.loads(body)
tool_name = payload.get("params", {}).get("name") if payload.get("method") == "tools/call" else payload.get("method", "unknown")
# Result: "search"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `mcp.run(transport="streamable-http")` only entry point | `mcp.streamable_http_app()` + `uvicorn.run()` for middleware | Phase 14 | Entry point must change; uvicorn already installed |
| No auth | Bearer token + SHA-256 hash + SQLite | Phase 14 | New `auth/` package + `auth.db` |

---

## Open Questions

1. **Should `usage_log` log non-`tools/call` MCP methods (initialize, ping, etc.)?**
   - What we know: AUTH-03 says "every authenticated request". Initialize and ping are authenticated.
   - What's unclear: Logging these creates noise but satisfies the requirement literally.
   - Recommendation: Log all authenticated requests; the method name column distinguishes them. Cheap to filter out in a future admin view.

2. **Index on `usage_log(key_name)` vs no index?**
   - What we know: No performance requirement at current scale. Auth-06 (usage admin endpoint) is deferred.
   - What's unclear: Whether Phase 15/17 needs fast lookup by key_name.
   - Recommendation: Add `CREATE INDEX IF NOT EXISTS idx_usage_key ON usage_log(key_name)` — zero cost at current scale, avoids migration later.

3. **`uvicorn` as explicit dependency?**
   - What we know: Uvicorn is a transitive dependency of mcp 1.26.0; it is installed. But it is not in Pipfile directly.
   - Recommendation: No Pipfile change needed — `mcp` already pulls uvicorn. Import `uvicorn` in `server.py` entry point without adding to Pipfile.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `mcp` | FastMCP server | Yes | 1.26.0 | — |
| `starlette` | Middleware | Yes | 1.0.0 (transitive via mcp) | — |
| `uvicorn` | Entry point runner | Yes | (transitive via mcp) | — |
| `sqlite3` | Key storage | Yes | stdlib | — |
| `secrets`, `hashlib`, `hmac` | Token generation/validation | Yes | stdlib | — |
| `pytest` | Test framework | Yes | 9.0.2 | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (pytest auto-discovers `tests/`) |
| Quick run command | `pipenv run py -m pytest tests/test_auth.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | `create --name alice` writes key, prints token once | unit | `pipenv run py -m pytest tests/test_auth.py::TestSqliteKeyStore::test_create_key -x` | Wave 0 |
| AUTH-01 | `revoke --name alice` removes key, returns False for missing | unit | `pipenv run py -m pytest tests/test_auth.py::TestSqliteKeyStore::test_revoke_key -x` | Wave 0 |
| AUTH-01 | `list` returns names and dates, never token | unit | `pipenv run py -m pytest tests/test_auth.py::TestSqliteKeyStore::test_list_keys -x` | Wave 0 |
| AUTH-02 | Request without token → 401 | integration | `pipenv run py -m pytest tests/test_auth.py::TestBearerAuthMiddleware::test_no_token_returns_401 -x` | Wave 0 |
| AUTH-02 | Request with invalid token → 401 | integration | `pipenv run py -m pytest tests/test_auth.py::TestBearerAuthMiddleware::test_invalid_token_returns_401 -x` | Wave 0 |
| AUTH-02 | Request with valid token → pass-through | integration | `pipenv run py -m pytest tests/test_auth.py::TestBearerAuthMiddleware::test_valid_token_passes_through -x` | Wave 0 |
| AUTH-02 | `/health` without token → 200 (not 401) | integration | `pipenv run py -m pytest tests/test_auth.py::TestBearerAuthMiddleware::test_health_bypass -x` | Wave 0 |
| AUTH-03 | Valid request writes row to `usage_log` | unit | `pipenv run py -m pytest tests/test_auth.py::TestSqliteKeyStore::test_log_request -x` | Wave 0 |
| AUTH-03 | `tool_name` extracted from `tools/call` body | unit | `pipenv run py -m pytest tests/test_auth.py::test_extract_tool_name -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/test_auth.py -x -q`
- **Per wave merge:** `pipenv run py -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_auth.py` — covers all AUTH-01/AUTH-02/AUTH-03 tests listed above (none exist yet)

*(Existing `tests/test_server.py` covers TRANS-01/TRANS-02 and existing tools — no changes needed there)*

---

## Sources

### Primary (HIGH confidence)
- Live code inspection: `mcp.server.fastmcp.FastMCP.streamable_http_app` source — confirmed `Starlette` return type and `add_middleware` availability
- Live test execution: `BaseHTTPMiddleware` with `/health` bypass — confirmed 200/401 behavior against installed packages
- Live test execution: `secrets`, `hashlib`, `hmac`, `sqlite3` stdlib — confirmed token generation, hashing, comparison, and schema creation
- Live test execution: MCP JSON-RPC body extraction — confirmed `tools/call` method and `params.name` path

### Secondary (MEDIUM confidence)
- starlette 1.0.0 `BaseHTTPMiddleware` source inspection — confirmed `_CachedRequest` body caching; body reads in `dispatch()` are safe

### Tertiary (LOW confidence)
- None — all claims verified directly against installed packages

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries stdlib or already installed; versions confirmed
- Architecture: HIGH — integration approach tested live; middleware pattern confirmed functional
- Pitfalls: HIGH — all critical pitfalls (mcp.run limitation, thread safety, body caching) verified against source code
- Test map: HIGH — test file names and method names match the implementation plan

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable stdlib + pinned mcp version)
