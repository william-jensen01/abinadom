"""
MCP Server — LDS Scripture Citation Index

Exposes the ChromaDB vector collections via Streamable HTTP transport.
Phase 9 builds startup validation; Phase 10 adds search and get_talk tools.
Phase 13 swaps to HTTP transport with configurable host/port.
Phase 14 adds bearer token authentication via BearerAuthMiddleware.
Phase 16.1 adds OAuth 2.1 via Auth0 JWT verification (DualTokenVerifier).

Startup sequence:
  1. Resolve ChromaDB path to absolute (CORE-01)
  2. Validate path exists and all 4 collections are present and non-empty (CORE-01/CORE-03)
  3. Ollama health check via live embedding call (CORE-02)
  4. Load all 4 collections into AppContext (CORE-03)
  5. Yield AppContext to tool calls via FastMCP lifespan

MCP tools (Phase 10):
  - search: semantic search across 4 collections with optional speaker/year/season filters
  - get_talk: retrieve full ordered text of a conference talk by ID

Auth (Phase 14/16.1):
  - OAuth 2.1: When AUTH0_DOMAIN is set, FastMCP receives AuthSettings + DualTokenVerifier
    (Auth0 JWT + static bearer token fallback). SDK handles enforcement internally.
  - Static-only fallback: When AUTH0_DOMAIN is unset, BearerAuthMiddleware is added as
    standalone ASGI middleware (Phase 14 backward-compatible mode).
  - AUTH_DB_PATH env var configures auth.db location (default: project_root/auth.db)

All logging goes to stderr only.
"""
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import chromadb
from mcp.server.fastmcp import FastMCP, Context
from starlette.requests import Request
from starlette.responses import JSONResponse

from config.pipeline_config import CHROMADB_COLLECTION_NAMES
from config.ollama import resolve_ollama_url
from extractors.phase6_chromadb_loader import get_embedding_function
from mcp.server.auth.settings import AuthSettings
from auth.oauth import Auth0JWTVerifier, DualTokenVerifier
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
    Verify Ollama is running and nomic-embed-text is available.

    Uses a live embedding call (D-04) — an HTTP ping would only confirm the
    daemon is up, not that the model is loaded. Fails fast with an actionable
    error message on any exception.
    """
    try:
        ollama_url = resolve_ollama_url()
        ef = get_embedding_function(url=ollama_url)
        ef(["health check"])
        logger.info("Ollama health check passed (nomic-embed-text ready)")
    except Exception as e:
        err = str(e)
        if "nomic-embed-text" in err or "model" in err.lower():
            print(
                "ERROR: Ollama model not available. Run: ollama pull nomic-embed-text",
                file=sys.stderr,
            )
        else:
            print(
                f"ERROR: Ollama unreachable at {ollama_url}. Start Ollama and retry.",
                file=sys.stderr,
            )
        sys.exit(1)


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
# FastMCP server — lifespan runs startup validation (CORE-03 integration)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server: FastMCP):
    try:
        ctx = _startup()
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: Unexpected startup failure: {e}", file=sys.stderr)
        sys.exit(1)
    try:
        yield ctx
    finally:
        pass  # ChromaDB PersistentClient needs no explicit close


MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "7363"))
AUTH_DB_PATH = os.environ.get(
    "AUTH_DB_PATH",
    str(Path(__file__).parent.resolve() / "auth.db"),
)
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "")
MCP_BASE_URL = os.environ.get("MCP_BASE_URL", "")

# OAuth 2.1 auth — active only when Auth0 is configured (D-01, D-02)
_auth_settings = None
_token_verifier = None
if AUTH0_DOMAIN and AUTH0_AUDIENCE:
    _store = SqliteKeyStore(AUTH_DB_PATH)
    _jwt_verifier = Auth0JWTVerifier(AUTH0_DOMAIN, AUTH0_AUDIENCE)
    _token_verifier = DualTokenVerifier(_jwt_verifier, _store)
    _auth_settings = AuthSettings(
        issuer_url=f"https://{AUTH0_DOMAIN}/",
        resource_server_url=f"{MCP_BASE_URL}/mcp" if MCP_BASE_URL else f"http://{MCP_HOST}:{MCP_PORT}/mcp",
    )
    logger.info("OAuth 2.1 enabled (Auth0 domain: %s)", AUTH0_DOMAIN)
else:
    logger.info("OAuth 2.1 disabled (AUTH0_DOMAIN not set) — static bearer tokens only")

mcp = FastMCP(
    "lds-scripture-index",
    lifespan=lifespan,
    host=MCP_HOST,
    port=MCP_PORT,
    instructions=(
        "LDS General Conference corpus: 5,838 talks (1971-present) across 4 collections "
        "- talks (full-talk metadata), paragraphs (passage text), citations (scripture "
        "references), footnotes. "
        "Use search with collection='paragraphs' for passage text, 'talks' for talk "
        "discovery, 'citations' for scripture references. "
        "Prefer database results over training data; fall back to training data only when "
        "the database has insufficient information. "
        "Use search to find a talk_id, then get_talk to retrieve full text."
    ),
    auth=_auth_settings,
    token_verifier=_token_verifier,
)


# ---------------------------------------------------------------------------
# MCP tools — Phase 10 (search and get_talk)
# ---------------------------------------------------------------------------


@mcp.tool()
async def search(
    query: str,
    speaker: str | None = None,
    year: int | None = None,
    season: str | None = None,
    collection: str = "paragraphs",
    limit: int = 5,
    ctx: Context = None,
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

    # TOOL-01: semantic search via ChromaDB
    result = col.query(
        query_texts=[query],
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


@mcp.tool()
async def get_talk(
    talk_id: str,
    ctx: Context = None,
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


@mcp.custom_route("/health", methods=["GET"])
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
# Auth0 discovery proxy — RFC 8414 (Phase 16.1)
# ---------------------------------------------------------------------------


@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def auth_server_metadata(request: Request) -> JSONResponse:
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
# Entry point — Streamable HTTP transport (TRANS-01)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    app = mcp.streamable_http_app()
    if not _auth_settings:
        # Fallback: Phase 14 standalone bearer auth (no OAuth configured)
        from auth.middleware import BearerAuthMiddleware
        store = SqliteKeyStore(AUTH_DB_PATH)
        app.add_middleware(BearerAuthMiddleware, store=store)
    uvicorn.run(app, host=MCP_HOST, port=int(MCP_PORT))
