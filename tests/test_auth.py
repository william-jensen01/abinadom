"""
Unit tests for auth.store — SqliteKeyStore and KeyStore ABC.
Integration tests for auth.middleware — BearerAuthMiddleware.

Covers AUTH-01 (key issuance), AUTH-02 (bearer enforcement), and
AUTH-03 (usage logging) behaviors.
Each test uses tmp_path for an isolated auth.db — no shared state.
"""
import sqlite3

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from auth.store import KeyStore, SqliteKeyStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path):
    """Fresh SqliteKeyStore with an isolated db per test."""
    db_path = str(tmp_path / "auth.db")
    return SqliteKeyStore(db_path)


# ---------------------------------------------------------------------------
# test_init_creates_tables
# ---------------------------------------------------------------------------


def test_init_creates_tables(tmp_path):
    """A fresh SqliteKeyStore creates both 'keys' and 'usage_log' tables."""
    db_path = str(tmp_path / "auth.db")
    SqliteKeyStore(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "keys" in table_names, "Expected 'keys' table to be created"
    assert "usage_log" in table_names, "Expected 'usage_log' table to be created"


# ---------------------------------------------------------------------------
# test_create_key
# ---------------------------------------------------------------------------


def test_create_key(store):
    """create_key returns a non-empty string token."""
    token = store.create_key("alice")
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_key_duplicate_raises(store):
    """create_key raises sqlite3.IntegrityError when name already exists (name is PRIMARY KEY)."""
    store.create_key("alice")
    with pytest.raises(sqlite3.IntegrityError):
        store.create_key("alice")


# ---------------------------------------------------------------------------
# test_verify_token
# ---------------------------------------------------------------------------


def test_verify_token_valid(store):
    """verify_token returns the key name for a valid token."""
    token = store.create_key("bob")
    result = store.verify_token(token)
    assert result == "bob"


def test_verify_token_invalid(store):
    """verify_token returns None for an invalid/unknown token."""
    result = store.verify_token("garbage-token-that-does-not-exist")
    assert result is None


def test_verify_token_after_revoke(store):
    """verify_token returns None after the key has been revoked."""
    token = store.create_key("charlie")
    store.revoke_key("charlie")
    result = store.verify_token(token)
    assert result is None


# ---------------------------------------------------------------------------
# test_revoke_key
# ---------------------------------------------------------------------------


def test_revoke_key_existing(store):
    """revoke_key returns True when the key exists and is successfully removed."""
    store.create_key("alice")
    result = store.revoke_key("alice")
    assert result is True


def test_revoke_key_nonexistent(store):
    """revoke_key returns False when the key does not exist."""
    result = store.revoke_key("nonexistent-key-name")
    assert result is False


# ---------------------------------------------------------------------------
# test_list_keys
# ---------------------------------------------------------------------------


def test_list_keys(store):
    """list_keys returns dicts with 'name' and 'created_at' for each key, never token_hash."""
    store.create_key("alice")
    store.create_key("bob")

    keys = store.list_keys()

    assert len(keys) == 2
    names = {k["name"] for k in keys}
    assert names == {"alice", "bob"}

    for k in keys:
        assert "name" in k
        assert "created_at" in k
        assert "token_hash" not in k, "token_hash must never appear in list_keys output"


def test_list_keys_empty(store):
    """list_keys returns an empty list when no keys exist."""
    keys = store.list_keys()
    assert keys == []


# ---------------------------------------------------------------------------
# test_log_request
# ---------------------------------------------------------------------------


def test_log_request(tmp_path):
    """log_request inserts a row into usage_log with matching key_name, tool_name, timestamp."""
    db_path = str(tmp_path / "auth.db")
    s = SqliteKeyStore(db_path)

    timestamp = "2026-04-03T12:00:00+00:00"
    s.log_request("alice", "search", timestamp)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT key_name, tool_name, timestamp FROM usage_log"
    ).fetchall()
    conn.close()

    assert len(rows) == 1
    key_name, tool_name, ts = rows[0]
    assert key_name == "alice"
    assert tool_name == "search"
    assert ts == timestamp


# ---------------------------------------------------------------------------
# test_constant_time_comparison (acceptance criteria grep check)
# ---------------------------------------------------------------------------


def test_constant_time_comparison_used():
    """Verify auth/store.py uses hmac.compare_digest (constant-time) in verify_token.

    This is a grep-style acceptance check — reads the source file to confirm
    the pattern is present, rather than testing behavior indirectly.
    """
    import inspect
    import auth.store as store_module

    source = inspect.getsource(store_module)
    assert "hmac.compare_digest(" in source, (
        "auth/store.py must use hmac.compare_digest() for constant-time comparison "
        "to prevent timing attacks"
    )


# ---------------------------------------------------------------------------
# test_keystore_is_abc
# ---------------------------------------------------------------------------


def test_keystore_is_abc():
    """KeyStore is an abstract base class — cannot be instantiated directly."""
    import inspect
    from abc import ABC

    assert issubclass(KeyStore, ABC), "KeyStore must be an ABC subclass"

    # Attempting to instantiate should raise TypeError
    with pytest.raises(TypeError):
        KeyStore()


# ---------------------------------------------------------------------------
# BearerAuthMiddleware integration tests (AUTH-02, AUTH-03)
# ---------------------------------------------------------------------------


def _make_test_app(store):
    """Create a minimal Starlette test app with BearerAuthMiddleware mounted."""
    from auth.middleware import BearerAuthMiddleware

    async def homepage(request):
        return PlainTextResponse("OK")

    async def health(request):
        return PlainTextResponse("healthy")

    app = Starlette(routes=[
        Route("/mcp", homepage, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
    ])
    app.add_middleware(BearerAuthMiddleware, store=store)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def test_app(tmp_path):
    """Provide a test app + store pair with a fresh auth.db per test."""
    db_path = str(tmp_path / "auth.db")
    store = SqliteKeyStore(db_path)
    client = _make_test_app(store)
    return client, store


def test_health_bypass(test_app):
    """GET /health with no Authorization header returns 200 (not 401)."""
    client, _ = test_app
    response = client.get("/health")
    assert response.status_code == 200


def test_no_token_returns_401(test_app):
    """POST /mcp with no Authorization header returns 401 with 'Missing bearer token'."""
    client, _ = test_app
    response = client.post("/mcp", json={"method": "tools/list"})
    assert response.status_code == 401
    assert "Missing bearer token" in response.text


def test_invalid_token_returns_401(test_app):
    """POST /mcp with invalid Bearer token returns 401 with 'Invalid token'."""
    client, _ = test_app
    response = client.post(
        "/mcp",
        json={"method": "tools/list"},
        headers={"Authorization": "Bearer bad-token"},
    )
    assert response.status_code == 401
    assert "Invalid token" in response.text


def test_valid_token_passes_through(test_app):
    """POST /mcp with a valid bearer token returns status != 401 (passes to app)."""
    client, store = test_app
    token = store.create_key("testuser")
    response = client.post(
        "/mcp",
        json={"method": "tools/list"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 401


def test_usage_logged_on_valid_request(tmp_path):
    """After a valid authenticated request, usage_log has 1 row with correct key_name."""
    import sqlite3 as _sqlite3

    db_path = str(tmp_path / "auth.db")
    store = SqliteKeyStore(db_path)
    token = store.create_key("alice")
    client = _make_test_app(store)
    client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "search", "arguments": {}}},
        headers={"Authorization": f"Bearer {token}"},
    )
    conn = _sqlite3.connect(db_path)
    rows = conn.execute("SELECT key_name, tool_name FROM usage_log").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "alice"
    assert rows[0][1] == "search"


# ---------------------------------------------------------------------------
# _extract_tool_name unit tests (AUTH-03)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_extract_tool_name_tools_call():
    """_extract_tool_name with tools/call body returns the tool name 'search'."""
    from auth.middleware import _extract_tool_name
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
    }
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search","arguments":{}}}'

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(scope, receive)
    result = await _extract_tool_name(request)
    assert result == "search"


@pytest.mark.anyio
async def test_extract_tool_name_other_method():
    """_extract_tool_name with initialize body returns 'initialize'."""
    from auth.middleware import _extract_tool_name
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
    }
    body = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(scope, receive)
    result = await _extract_tool_name(request)
    assert result == "initialize"


@pytest.mark.anyio
async def test_extract_tool_name_bad_body():
    """_extract_tool_name with invalid JSON returns 'unknown'."""
    from auth.middleware import _extract_tool_name
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "query_string": b"",
        "headers": [],
    }
    body = b"not-json-at-all"

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(scope, receive)
    result = await _extract_tool_name(request)
    assert result == "unknown"
