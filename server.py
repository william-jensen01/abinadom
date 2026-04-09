"""
MCP Server — LDS Scripture Citation Index

Exposes the ChromaDB vector collections via FastAPI with a manual MCP JSON-RPC dispatcher.
Phase 9 builds startup validation; Phase 10 adds search and get_talk tools.
Phase 13 swaps to HTTP transport with configurable host/port.
Phase 14 adds bearer token authentication via SqliteKeyStore.
Phase 16.1 adds OAuth 2.1 via algorithm-agnostic JWT verification (Auth0 JWKS + PyJWT).
Phase 16.2 replaces FastMCP + BaseHTTPMiddleware with a FastAPI app and per-method
auth routing directly in the dispatcher (eliminates anyio task group errors).

Startup sequence:
  1. Resolve ChromaDB path to absolute (CORE-01)
  2. Validate path exists and all 4 collections are present and non-empty (CORE-01/CORE-03)
  3. Ollama health check via live embedding call (CORE-02)
  4. Load all 4 collections into AppContext (CORE-03)
  5. Yield AppContext via FastAPI lifespan, stored in app.state.ctx

MCP tools (Phase 10):
  - search: semantic search across 4 collections with optional speaker/year/season filters
  - get_talk: retrieve full ordered text of a conference talk by ID

Auth (Phase 14/16.1/16.2):
  - OAuth 2.1: When AUTH0_DOMAIN is set, JWKSVerifier handles JWT validation.
    Per-method auth is applied inline in the dispatcher — no middleware involved.
    RFC 9728 protected resource metadata and RFC 8414 authorization server metadata
    are served as discovery endpoints.
  - Static-only fallback: When AUTH0_DOMAIN is unset, SqliteKeyStore bearer check
    is used for tools/list and tools/call.
  - AUTH_DB_PATH env var configures auth.db location (default: project_root/auth.db)

All logging goes to stderr only.
"""
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import chromadb
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from config.pipeline_config import CHROMADB_COLLECTION_NAMES
from config.ollama import resolve_ollama_url, get_embedding_function
from auth.oauth import JWKSVerifier
from auth.store import SqliteKeyStore

# ---------------------------------------------------------------------------
# Logging — must be configured before anything else writes to stderr (INTG-01)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context dataclass — carries live resources for tool calls
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    client: chromadb.ClientAPI
    collections: dict  # str -> chromadb.Collection


# ---------------------------------------------------------------------------
# Startup helpers — each raises SystemExit(1) on failure
# ---------------------------------------------------------------------------


def _resolve_chromadb_path() -> str:
    """
    Return the absolute path to the ChromaDB directory.

    Default: <project_root>/data/chromadb (resolved from __file__, so it works
    regardless of the working directory Claude Desktop uses when spawning the
    server process).

    Override: Set CHROMADB_PATH env var to any path.
    """
    default = Path(__file__).parent.resolve() / "data" / "chromadb"
    raw = os.environ.get("CHROMADB_PATH", str(default))
    return str(Path(raw).resolve())


def _check_ollama() -> None:
    """
    Log Ollama reachability at startup — non-fatal.

    Ollama is a separate service accessed by URL; the server starts regardless
    of its availability. Search calls will fail gracefully if Ollama is down.
    The /health endpoint reports live Ollama status on demand.
    """
    try:
        ollama_url = resolve_ollama_url()
        ef = get_embedding_function(url=ollama_url)
        ef(["health check"])
        logger.info("Ollama reachable at startup (nomic-embed-text ready)")
    except Exception:
        logger.warning(
            "Ollama unreachable at startup — search will be unavailable until Ollama is running"
        )


def _load_collections(client: chromadb.ClientAPI) -> dict:
    """
    Load all 4 ChromaDB collections using get_collection() (not get_or_create_collection).

    Fails fast with SystemExit(1) if any collection is missing or empty.
    Returns a dict mapping logical key -> chromadb.Collection.
    """
    collections = {}
    for key, name in CHROMADB_COLLECTION_NAMES.items():
        try:
            col = client.get_collection(name=name)
        except Exception:
            print(
                f"ERROR: ChromaDB collection '{name}' not found. "
                "Run the pipeline (scripts/run_pipeline.py) first.",
                file=sys.stderr,
            )
            sys.exit(1)
        count = col.count()
        if count == 0:
            print(
                f"ERROR: Collection '{name}' exists but has 0 records. "
                "Re-run the pipeline to populate it.",
                file=sys.stderr,
            )
            sys.exit(1)
        logger.info("Loaded collection '%s' (%d records)", name, count)
        collections[key] = col
    return collections


def _startup() -> AppContext:
    """
    Run all startup validation checks and return an initialized AppContext.

    Called from lifespan before the first tool call is accepted.
    Any failure raises SystemExit(1) with a message to stderr.
    """
    path = _resolve_chromadb_path()
    logger.info("ChromaDB path: %s", path)

    if not Path(path).exists():
        print(
            f"ERROR: ChromaDB directory not found at {path}. "
            "Run the pipeline (scripts/run_pipeline.py) first.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = chromadb.PersistentClient(path=path)
    _check_ollama()
    collections = _load_collections(client)
    return AppContext(client=client, collections=collections)


# ---------------------------------------------------------------------------
# Pure helper functions — business logic for search and get_talk tools
# ---------------------------------------------------------------------------


def _build_where_filter(year: int | None, season: str | None) -> dict | None:
    """
    Build a ChromaDB `where` filter dict from optional year and season params.

    Returns None (not {}) when no filters are provided — ChromaDB rejects empty
    where dicts (Pitfall 6). Speaker filtering is NOT included here; it is
    applied as a Python post-filter after the query (Pitfall 1 / D-06).
    """
    filters = []
    if year is not None:
        filters.append({"conference_year": {"$eq": year}})
    if season is not None:
        filters.append({"conference_month": {"$eq": season}})
    if not filters:
        return None
    return filters[0] if len(filters) == 1 else {"$and": filters}


def _matches_speaker(stored: str, query: str) -> bool:
    """
    Case-insensitive substring match on speaker name (D-06 / CORE-04).

    Input "Holland" matches stored "Jeffrey R. Holland". Whitespace is stripped
    from the query before comparison.
    """
    return query.strip().lower() in stored.lower()


def _format_search_result(document: str, meta: dict) -> dict:
    """
    Build the 6-field public result dict from a ChromaDB document + metadata.

    D-01: exactly 6 fields — snippet, speaker_name, title, conference_year,
    conference_month, talk_id.
    D-04: NO pipeline-internal fields (paragraph_id, word_count, text, text_raw,
    source_type, speaker_id, conference_id, etc.).
    Snippet comes from the document param (ChromaDB document text), NOT from
    meta["text"] (Pitfall 3).
    """
    return {
        "snippet": document,
        "speaker_name": meta.get("speaker_name", ""),
        "title": meta.get("title", ""),
        "conference_year": int(meta.get("conference_year", 0)),
        "conference_month": meta.get("conference_month", ""),
        "talk_id": f"talk_{int(meta.get('talk_id', 0))}",
    }


def _parse_talk_id(talk_id: str) -> int | None:
    """
    Parse a talk_id string to an integer, accepting both "talk_8820" and "8820".

    Returns None for strings that cannot be parsed (D-12 / TOOL-04).
    Defensive: strips whitespace and lowercases before parsing.
    """
    normalized = talk_id.strip().lower().replace("talk_", "")
    try:
        return int(normalized)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# MCP tool functions — Phase 10 (search and get_talk)
# ---------------------------------------------------------------------------


async def search(
    query: str,
    speaker: str | None = None,
    year: int | None = None,
    season: str | None = None,
    collection: str = "paragraphs",
    limit: int = 5,
    ctx=None,
) -> str:
    """Search LDS General Conference content by meaning.

    Use collection='paragraphs' for passage text, 'talks' for talk discovery,
    'citations' for scripture references, 'footnotes' for footnote content.

    Args:
        query: Natural language search query.
        speaker: Optional speaker name filter (substring match, e.g. "Holland").
        year: Optional conference year filter (e.g. 2020).
        season: Optional conference season filter ("April" or "October").
        collection: Collection to search - "talks", "paragraphs" (default), "citations", or "footnotes".
        limit: Number of results to return (default 5, max 20).
    """
    app: AppContext = ctx.request_context.lifespan_context

    # CORE-06: validate collection alias
    col = app.collections.get(collection)
    if col is None:
        return f"Unknown collection '{collection}'. Valid: talks, paragraphs, citations, footnotes."

    # Clamp limit per TOOL-03
    limit = max(1, min(limit, 20))

    # CORE-05: build where filter (year/season only; speaker is post-filtered)
    where = _build_where_filter(year=year, season=season)

    # CORE-04: fetch extra results when speaker filter active to compensate for post-filter reduction
    fetch_n = min(limit * 4, 80) if speaker else limit

    # TOOL-01: embed query via Ollama (separate service — fails gracefully if unreachable)
    try:
        ef = get_embedding_function()
        query_vector = ef([query])
    except Exception as e:
        return f"Search unavailable: Ollama is unreachable ({e})."

    # TOOL-01: semantic search via ChromaDB
    result = col.query(
        query_embeddings=query_vector,
        n_results=fetch_n,
        where=where,
        include=["documents", "metadatas"],
    )

    # Zip documents and metadatas (query returns nested lists — [0] for first query)
    docs = result["documents"][0] if result["documents"] else []
    metas = result["metadatas"][0] if result["metadatas"] else []
    items = list(zip(docs, metas))

    # CORE-04: post-filter by speaker (case-insensitive substring match, per D-06)
    if speaker:
        items = [(d, m) for d, m in items if _matches_speaker(m.get("speaker_name", ""), speaker)]

    # Truncate to requested limit
    items = items[:limit]

    if not items:
        return "No results found."

    # TOOL-03: format results — exactly 6 fields per D-01, no pipeline fields per D-04
    results = [_format_search_result(d, m) for d, m in items]
    return json.dumps(results, ensure_ascii=False, indent=2)


async def get_talk(
    talk_id: str,
    ctx=None,
) -> str:
    """Retrieve the full text of a General Conference talk by ID.

    Use search to find a talk_id first, then call this to retrieve full text.

    Args:
        talk_id: Talk identifier (e.g. "talk_8820" or "8820").
    """
    app: AppContext = ctx.request_context.lifespan_context

    # TOOL-04: parse talk_id to integer
    talk_num = _parse_talk_id(talk_id)
    if talk_num is None:
        return f"Invalid talk_id format '{talk_id}'. Expected format: 'talk_8820' or '8820'."

    # Get talk metadata for header (speaker, title, conference, session)
    talks_col = app.collections["talks"]
    talk_result = talks_col.get(ids=[f"talk_{talk_num}"], include=["metadatas"])

    if not talk_result["metadatas"]:
        return f"No talk found with ID '{talk_id}'."

    tm = talk_result["metadatas"][0]
    header = (
        f"Speaker: {tm.get('speaker_name', '')}\n"
        f"Title: {tm.get('title', '')}\n"
        f"Conference: {tm.get('conference_month', '')} {tm.get('conference_year', '')}\n"
        f"Session: {tm.get('session_description', '')}"
    )

    # TOOL-05: get all paragraphs for this talk, sorted by paragraph_number
    paras_col = app.collections["paragraphs"]
    para_result = paras_col.get(
        where={"talk_id": {"$eq": talk_num}},
        include=["documents", "metadatas"],
    )

    if not para_result["ids"]:
        return f"No paragraphs found for talk_id '{talk_id}'."

    # Sort by paragraph_number (narrative order per D-15/TOOL-05)
    sorted_rows = sorted(
        zip(para_result["documents"], para_result["metadatas"]),
        key=lambda x: int(x[1].get("paragraph_number", 0)),
    )

    # Build output: header + blank line + paragraphs separated by blank lines (per D-14)
    body = "\n\n".join(doc for doc, _meta in sorted_rows)
    return f"{header}\n\n{body}"


# ---------------------------------------------------------------------------
# Health endpoint — live dependency checks (TRANS-02)
# ---------------------------------------------------------------------------


async def health_check(request: Request) -> JSONResponse:
    """Return server health with live Ollama and ChromaDB reachability checks."""
    status = {"ollama": "reachable", "chromadb": "reachable"}
    http_status = 200

    # Ollama check: live embedding call (per D-09 — same approach as _check_ollama
    # but without sys.exit on failure)
    try:
        ollama_url = resolve_ollama_url()
        ef = get_embedding_function(url=ollama_url)
        ef(["health"])
    except Exception:
        status["ollama"] = "unreachable"
        http_status = 503

    # ChromaDB check: connect and verify collections exist (per D-09 — reuses
    # startup guard logic pattern without full count validation)
    try:
        path = _resolve_chromadb_path()
        client = chromadb.PersistentClient(path=path)
        for name in CHROMADB_COLLECTION_NAMES.values():
            client.get_collection(name=name)
    except Exception:
        status["chromadb"] = "unreachable"
        http_status = 503

    payload = {"status": "ok" if http_status == 200 else "degraded", **status}
    return JSONResponse(payload, status_code=http_status)


# ---------------------------------------------------------------------------
# RFC 9728 — OAuth 2.0 Protected Resource Metadata (Phase 16.1)
# ---------------------------------------------------------------------------


async def _protected_resource_metadata(request: Request) -> JSONResponse:
    """Serve OAuth 2.0 Protected Resource Metadata (RFC 9728).

    Tells MCP clients which authorization server handles tokens for this resource.
    Required by MCP spec for OAuth discovery.
    Paths: /.well-known/oauth-protected-resource
           /.well-known/oauth-protected-resource/mcp
    """
    if not AUTH0_DOMAIN or not MCP_BASE_URL:
        return JSONResponse({"error": "OAuth not configured"}, status_code=404)

    doc = {
        "resource": MCP_BASE_URL,
        "authorization_servers": [f"https://{AUTH0_DOMAIN}"],
        "bearer_methods_supported": ["header"],
    }
    response = JSONResponse(doc)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return response


# ---------------------------------------------------------------------------
# Auth0 discovery proxy — RFC 8414 (Phase 16.1)
# ---------------------------------------------------------------------------


async def _auth_server_metadata(request: Request) -> JSONResponse:
    """Proxy Auth0's OAuth authorization server metadata (RFC 8414).

    Claude clients may request this from the MCP server domain directly
    rather than following the authorization_servers array in the protected
    resource metadata. This proxy ensures compatibility.
    """
    if not AUTH0_DOMAIN:
        return JSONResponse(
            {"error": "OAuth not configured"},
            status_code=404,
        )
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://{AUTH0_DOMAIN}/.well-known/openid-configuration"
        )
        return JSONResponse(resp.json(), status_code=resp.status_code)


# ---------------------------------------------------------------------------
# Module-level constants and auth initialization
# ---------------------------------------------------------------------------

MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "7363"))
AUTH_DB_PATH = os.environ.get(
    "AUTH_DB_PATH",
    str(Path(__file__).parent.resolve() / "auth.db"),
)
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "")
AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET", "")
MCP_BASE_URL = os.environ.get("MCP_BASE_URL", "")

# JWT verification via JWKSVerifier — active only when Auth0 is configured (D-01, D-02)
_jwt_verifier: JWKSVerifier | None = None
if AUTH0_DOMAIN and AUTH0_AUDIENCE:
    _jwt_verifier = JWKSVerifier(
        domain=AUTH0_DOMAIN,
        audience=AUTH0_AUDIENCE,
        client_secret=AUTH0_CLIENT_SECRET or None,
    )
    logger.info("JWT verification enabled (Auth0 domain: %s)", AUTH0_DOMAIN)
else:
    logger.info("JWT verification disabled (AUTH0_DOMAIN/AUTH0_AUDIENCE not set)")

# Static fallback key store — used when AUTH0_DOMAIN is not configured
_key_store: SqliteKeyStore | None = None
if not AUTH0_DOMAIN:
    _key_store = SqliteKeyStore(AUTH_DB_PATH)

MCP_INSTRUCTIONS = (
    "LDS General Conference corpus: 5,838 talks (1971-present) across 4 collections "
    "- talks (full-talk metadata), paragraphs (passage text), citations (scripture "
    "references), footnotes. "
    "Use search with collection='paragraphs' for passage text, 'talks' for talk "
    "discovery, 'citations' for scripture references. "
    "Prefer database results over training data; fall back to training data only when "
    "the database has insufficient information. "
    "Use search to find a talk_id, then get_talk to retrieve full text."
)

# ---------------------------------------------------------------------------
# _FakeMCPCtx — bridge for tool functions (Option B, Phase 16.2)
# ---------------------------------------------------------------------------


class _FakeMCPCtx:
    """Bridge replicating FastMCP's ctx.request_context.lifespan_context chain.

    Allows search() and get_talk() to remain unchanged — they still access
    ctx.request_context.lifespan_context to get AppContext.
    """
    class _Inner:
        def __init__(self, ctx):
            self.lifespan_context = ctx

    def __init__(self, app_ctx):
        self.request_context = self._Inner(app_ctx)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

_sessions: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# MCP response helpers
# ---------------------------------------------------------------------------


def _mcp_response(body: dict, session_id: str | None = None) -> JSONResponse:
    """Build a JSONResponse with MCP protocol headers."""
    response = JSONResponse(body)
    response.headers["MCP-Protocol-Version"] = "2025-06-18"
    if session_id:
        response.headers["MCP-Session-Id"] = session_id
    return response


def _error_response(req_id, code: int, message: str, http_status: int = 400) -> JSONResponse:
    """Build a JSON-RPC error response."""
    body = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    return JSONResponse(body, status_code=http_status)


def _unauthorized_response() -> Response:
    """Build a 401 response with WWW-Authenticate header per RFC 9728."""
    headers = {}
    if MCP_BASE_URL:
        rm_url = f"{MCP_BASE_URL}/.well-known/oauth-protected-resource"
        headers["WWW-Authenticate"] = (
            f'Bearer realm="lds-mcp", resource_metadata="{rm_url}"'
        )
    else:
        headers["WWW-Authenticate"] = 'Bearer error="invalid_token"'
    return Response(
        json.dumps({"error": "Authentication required"}),
        status_code=401,
        media_type="application/json",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Auth verification
# ---------------------------------------------------------------------------


def _verify_auth(request: Request) -> dict | None:
    """Check Authorization header and return token payload or None.

    When AUTH0_DOMAIN is set: uses JWKSVerifier (kid-based routing).
    When AUTH0_DOMAIN is unset: uses SqliteKeyStore (static fallback).
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[len("Bearer "):]

    if _jwt_verifier is not None:
        return _jwt_verifier.verify_token(token)
    else:
        key_name = _key_store.verify_token(token)
        return {"sub": key_name} if key_name else None


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


async def _handle_initialize(body: dict) -> JSONResponse:
    """Handle MCP initialize request — no auth required."""
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"initialized": True}
    result = {
        "jsonrpc": "2.0",
        "id": body.get("id"),
        "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "lds-scripture-index", "version": "1.0.0"},
            "instructions": MCP_INSTRUCTIONS,
        },
    }
    return _mcp_response(result, session_id=session_id)


async def _handle_tools_list(body: dict, session_id: str) -> JSONResponse:
    """Handle MCP tools/list request — returns tool schemas."""
    tools = [
        {
            "name": "search",
            "description": search.__doc__,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query."},
                    "speaker": {"type": "string", "description": "Optional speaker name filter (substring match)."},
                    "year": {"type": "integer", "description": "Optional conference year filter."},
                    "season": {"type": "string", "description": "Optional conference season filter (April or October)."},
                    "collection": {"type": "string", "default": "paragraphs", "description": "Collection to search."},
                    "limit": {"type": "integer", "default": 5, "description": "Number of results (max 20)."},
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_talk",
            "description": get_talk.__doc__,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "talk_id": {"type": "string", "description": "Talk identifier (e.g. 'talk_8820' or '8820')."},
                },
                "required": ["talk_id"],
            },
        },
    ]
    result = {"jsonrpc": "2.0", "id": body.get("id"), "result": {"tools": tools}}
    return _mcp_response(result, session_id=session_id)


async def _handle_tools_call(body: dict, request: Request, session_id: str) -> JSONResponse:
    """Handle MCP tools/call request — dispatches to search or get_talk."""
    params = body.get("params", {})
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    app_ctx = request.app.state.ctx
    fake_ctx = _FakeMCPCtx(app_ctx)

    if tool_name == "search":
        result_text = await search(**arguments, ctx=fake_ctx)
    elif tool_name == "get_talk":
        result_text = await get_talk(**arguments, ctx=fake_ctx)
    else:
        return _error_response(body.get("id"), -32602, f"Unknown tool: {tool_name}", 404)

    # Log usage (AUTH-03)
    auth_payload = _verify_auth(request)
    if auth_payload and _key_store:
        from datetime import datetime, timezone
        _key_store.log_request(
            auth_payload.get("sub", "unknown"),
            tool_name,
            datetime.now(timezone.utc).isoformat(),
        )

    result = {
        "jsonrpc": "2.0",
        "id": body.get("id"),
        "result": {
            "content": [{"type": "text", "text": result_text}],
            "isError": False,
        },
    }
    return _mcp_response(result, session_id=session_id)


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ctx = _startup()
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: Unexpected startup failure: {e}", file=sys.stderr)
        sys.exit(1)
    app.state.ctx = ctx
    yield


# ---------------------------------------------------------------------------
# App factory — builds full FastAPI app with MCP dispatcher and all routes
# ---------------------------------------------------------------------------


def build_app() -> FastAPI:
    """Build and return the FastAPI application with MCP dispatcher."""
    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health(request: Request) -> JSONResponse:
        return await health_check(request)

    @app.get("/.well-known/oauth-protected-resource")
    @app.get("/.well-known/oauth-protected-resource/mcp")
    async def protected_resource(request: Request) -> JSONResponse:
        return await _protected_resource_metadata(request)

    @app.get("/.well-known/oauth-authorization-server")
    async def auth_server(request: Request) -> JSONResponse:
        return await _auth_server_metadata(request)

    @app.head("/")
    @app.head("/mcp")
    async def mcp_head() -> Response:
        return Response(status_code=200, headers={"MCP-Protocol-Version": "2025-06-18"})

    @app.get("/")
    @app.get("/mcp")
    async def mcp_get() -> Response:
        return Response(status_code=405, headers={"Allow": "POST, HEAD, DELETE"})

    @app.post("/")
    @app.post("/mcp")
    async def mcp_dispatcher(request: Request) -> Response:
        body = await request.json()
        method = body.get("method")
        req_id = body.get("id")

        # initialize — no auth required
        if method == "initialize":
            return await _handle_initialize(body)

        # All other methods require a valid session
        session_id = request.headers.get("MCP-Session-Id", "")
        if not session_id or session_id not in _sessions:
            return _error_response(req_id, -32600, "Invalid or missing session", 400)

        # notifications/initialized — session only, no auth
        if method == "notifications/initialized":
            return Response(status_code=202)

        # tools/list and tools/call — require OAuth or static token
        token_payload = _verify_auth(request)
        if token_payload is None:
            return _unauthorized_response()

        if method == "tools/list":
            return await _handle_tools_list(body, session_id)
        elif method == "tools/call":
            return await _handle_tools_call(body, request, session_id)
        else:
            return _error_response(req_id, -32601, f"Method not found: {method}", 404)

    @app.delete("/")
    @app.delete("/mcp")
    async def mcp_delete(request: Request) -> Response:
        session_id = request.headers.get("MCP-Session-Id", "")
        _sessions.pop(session_id, None)
        return Response(status_code=200)

    return app


# ---------------------------------------------------------------------------
# Entry point — FastAPI with uvicorn (TRANS-01)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    app = build_app()
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
