# Key Management

Reference for managing API keys on the LDS MCP server.

## Overview

API keys are managed via `scripts/manage_keys.py`. Tokens are generated using `secrets.token_urlsafe(32)` and stored as SHA-256 hashes — the raw token is shown once at creation and cannot be retrieved later. The key database is a SQLite file at the path specified by `AUTH_DB_PATH` (defaults to `auth.db` in the project root).

## Commands

### `create` — Issue a New Key

```bash
pipenv run py scripts/manage_keys.py create --name alice
```

Output:

```
Key 'alice' created.
Token (save this — it will not be shown again):
<token string>
```

Flags:

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | Yes | Human-readable label for the key (must be unique) |

Notes:

- Save the token immediately — it is not stored and cannot be retrieved
- If the name already exists, the command exits with an error: `Error: A key named 'alice' already exists.`

### `revoke` — Remove a Key

```bash
pipenv run py scripts/manage_keys.py revoke --name alice
```

Output on success: `Key 'alice' revoked.`

Output if not found: `No key named 'alice' found.` (exits with code 1)

Flags:

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | Yes | Name of the key to revoke |

Notes:

- Revocation is immediate — any in-flight request using this token will fail on next auth check
- Usage log entries for the revoked key are preserved (not deleted)

### `list` — List All Keys

```bash
pipenv run py scripts/manage_keys.py list
```

Output:

```
Name                           Created
------------------------------------------------------------
alice                          2026-04-04T12:00:00+00:00
bob                            2026-04-05T09:30:00+00:00
```

No flags. If no keys exist, prints: `No keys found.`

## Docker Usage

When running inside Docker, exec into the container:

```bash
docker compose exec mcp-server python scripts/manage_keys.py create --name alice
docker compose exec mcp-server python scripts/manage_keys.py list
docker compose exec mcp-server python scripts/manage_keys.py revoke --name alice
```

Note: Inside the container, auth.db is at `/data/auth.db` (set by `AUTH_DB_PATH` in the Dockerfile). No `pipenv` prefix needed inside the container.

## Usage Log Inspection

The server logs every authenticated request to the `usage_log` table in auth.db. Schema:

```sql
CREATE TABLE usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
```

### View Recent Requests

```bash
sqlite3 /path/to/auth.db "SELECT key_name, tool_name, timestamp FROM usage_log ORDER BY id DESC LIMIT 20;"
```

### Count Requests per Key

```bash
sqlite3 /path/to/auth.db "SELECT key_name, COUNT(*) as requests FROM usage_log GROUP BY key_name ORDER BY requests DESC;"
```

### Filter by Key Name

```bash
sqlite3 /path/to/auth.db "SELECT tool_name, timestamp FROM usage_log WHERE key_name = 'alice' ORDER BY id DESC LIMIT 20;"
```

### Docker Access

```bash
docker compose exec mcp-server sqlite3 /data/auth.db "SELECT key_name, tool_name, timestamp FROM usage_log ORDER BY id DESC LIMIT 20;"
```

## Database Schema

Both tables for reference:

```sql
-- API keys (name is primary key, token_hash is SHA-256 of the raw token)
CREATE TABLE keys (
    name TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Usage log (indexed on key_name for fast lookups)
CREATE TABLE usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX idx_usage_key ON usage_log(key_name);
```

The `keys` table never stores raw tokens — only SHA-256 hashes. Lost tokens cannot be recovered; issue a new key instead.
