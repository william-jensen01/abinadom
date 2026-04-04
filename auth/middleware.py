"""
Bearer token authentication middleware for the LDS MCP server.

Enforces bearer token auth on all routes except /health (D-04).
Logs every authenticated request to usage_log via KeyStore (AUTH-03).

Design decisions (from 14-CONTEXT.md):
  D-01: Middleware depends on KeyStore interface (not SqliteKeyStore directly).
  D-03: Auth enforced at Starlette/ASGI level before FastMCP tools are reached.
  D-04: /health is explicitly allowlisted — no token required.
  D-08/D-09: Every authenticated request logged via KeyStore.log_request().
  Pitfall 2: __init__ must accept store kwarg and pass only app to super().__init__().
  Pitfall 3: Body reads safe on starlette 1.0.0 (_CachedRequest caching).
"""
import json
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from auth.store import KeyStore


# Routes that bypass bearer token enforcement (D-04)
PUBLIC_PATHS = {"/health"}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces bearer token auth on all non-public routes.

    Usage:
        store = SqliteKeyStore(AUTH_DB_PATH)
        app = mcp.streamable_http_app()
        app.add_middleware(BearerAuthMiddleware, store=store)
    """

    def __init__(self, app, store: KeyStore) -> None:
        """Initialize middleware with the underlying app and a KeyStore instance.

        Args:
            app: The ASGI application to wrap.
            store: KeyStore implementation for token verification and logging.
        """
        super().__init__(app)
        self._store = store

    async def dispatch(self, request: Request, call_next) -> Response:
        """Intercept every request and enforce bearer token auth (D-03).

        Allows /health through without a token (D-04).
        Returns 401 JSON for missing or invalid tokens.
        Logs usage on successful auth (AUTH-03, D-08, D-09).
        """
        # Allow public paths through without auth (D-04)
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Check Authorization header
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

        # Log usage (AUTH-03, D-08, D-09)
        tool_name = await _extract_tool_name(request)
        timestamp = datetime.now(timezone.utc).isoformat()
        self._store.log_request(key_name, tool_name, timestamp)

        return await call_next(request)


async def _extract_tool_name(request: Request) -> str:
    """Parse MCP JSON-RPC body to extract tool or method name.

    For tools/call requests: returns params.name (the tool name, e.g. "search").
    For other MCP methods: returns the method name (e.g. "initialize", "tools/list").
    On any error (missing body, invalid JSON, missing keys): returns "unknown".

    Body reads are safe on starlette 1.0.0 — _CachedRequest caches the body
    so downstream handlers still receive it intact (Pitfall 3).

    Args:
        request: The Starlette request object.

    Returns:
        The extracted tool or method name, or "unknown" on any error.
    """
    try:
        body = await request.body()
        payload = json.loads(body)
        if payload.get("method") == "tools/call":
            return payload.get("params", {}).get("name", "unknown")
        return payload.get("method", "unknown")
    except Exception:
        return "unknown"
