"""
MCP Server — LDS Scripture Citation Index

Exposes the Weaviate vector collections via FastMCP with native MCP protocol handling and ScaleKit-based OAuth 2.1 authentication.

Phase 9 builds startup validation; Phase 10 adds search and get_talk tools.
Phase 13 swaps to HTTP transport with configurable host/port.
Phase 16.1 adds OAuth 2.1 via JWT verification (Auth0 JWKS +PyJWT).
Phase 16.2 replaces FastMCP + BaseHTTPMiddleware with a FastAPI app and per-method auth routing (eliminates anyio task group errors).
Phase 19 replaces the FastAPI + manual JSON-RPC server with FastMCP and built-in ScaleKit authentication (ScalekitProvider).
Phase 24 migrates the vector store to Weaviate.

Architecture (Phase 19):
  - FastMCP is the canonical server framework (no FastAPI, no manual JSON-RPC).
  - MCP protocol (initialize, tools/list, tools/call) is handled natively.
  - Authentication is delegated to FastMCP's ScalekitProvider.
  - OAuth discovery endpoints are served automatically by FastMCP.
  - No custom JWT verification or middleware is used.

Startup sequence:
  1. Connect to Weaviate via get_weaviate_client() (WEAVIATE_HOST/WEAVIATE_PORT env vars) (CORE-01)
  2. Validate all 4 PascalCase collections are present and non-empty (CORE-01/CORE-03)
  3. Ollama reachability check via embedding call (non-fatal) (CORE-02)
  4. Yield AppContext (Weaviate client) via FastMCP lifespan context (ctx.lifespan_context["app"])

MCP tools (Phase 10):
  - search: semantic search across 4 collections with optional speaker/year/season filters
  - get_talk: retrieve full ordered text of a conference talk by ID

Auth (Phase 19 — ScaleKit via FastMCP):
  - Local mode (SCALEKIT_ENVIRONMENT_URL, SCALEKIT_RESOURCE_ID, or MCP_BASE_URL unset):
    No authentication (auth=None). All MCP endpoints are publicly accessible.
    Intended for localhost and development.
  - Remote/hosted mode (all three env vars set):
    Authentication enforced via ScalekitProvider.
    - initialize: unauthenticated (per MCP spec)
    - tools/list and tools/call: require valid ScaleKit JWT
    - JWT validation is handled internally via JWKS (no custom verifier)
  - OAuth discovery endpoints:
    - /.well-known/oauth-protected-resource
    - /.well-known/oauth-authorization-server
    are automatically served by FastMCP/ScalekitProvider.

Removed in Phase 19:
  - FastAPI app and routing layer
  - Manual JSON-RPC dispatcher
  - BaseHTTPMiddleware (source of anyio task group failures)
  - Auth0 JWKSVerifier (auth/oauth.py)
  - scalekit-sdk-python dependency

All logging goes to stderr only.
"""
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

import weaviate
import requests as http_requests
from fastmcp import FastMCP, Context
from starlette.requests import Request
from starlette.responses import JSONResponse
from weaviate.classes.query import Filter, MetadataQuery, GroupBy, Sort
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.util import generate_uuid5

from config.weaviate_client import get_weaviate_client
from config.pipeline_config import WEAVIATE_COLLECTION_NAMES
from config.ollama import resolve_ollama_url, get_embedding_function

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
    client: weaviate.WeaviateClient


# Per-collection property extractor: maps collection key -> text snippet from Weaviate properties.
# Paragraphs have a 'text' field. Talks, citations, and footnotes use different property names.
_SNIPPET_PROP = {
    "talks": lambda p: (p.get("title", "") + ("\n\n" + p.get("talk_preview", "") if p.get("talk_preview") else "")),
    "paragraphs": lambda p: p.get("text", ""),
    "citations": lambda p: p.get("context_window", "") or p.get("citation_text_raw", ""),
    "footnotes": lambda p: p.get("context_window", "") or p.get("footnote_text_raw", ""),
}


# ---------------------------------------------------------------------------
# Startup helpers — each raises SystemExit(1) on failure
# ---------------------------------------------------------------------------


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


def _validate_collections(client: weaviate.WeaviateClient) -> None:
    """Validate all 4 Weaviate collections are present and non-empty. Calls sys.exit(1) on any failure."""
    for name in WEAVIATE_COLLECTION_NAMES.values():
        if not client.collections.exists(name):
            print(
                f"ERROR: Weaviate collection '{name}' not found. Run the pipeline first.",
                file=sys.stderr,
            )
            sys.exit(1)
        result = client.collections.use(name).aggregate.over_all(total_count=True)
        if result.total_count == 0:
            print(
                f"ERROR: Collection '{name}' has 0 records. Re-run the pipeline.",
                file=sys.stderr,
            )
            sys.exit(1)
        logger.info("Validated collection '%s' (%d records)", name, result.total_count)


def _startup() -> AppContext:
    """
    Run all startup validation checks and return an initialized AppContext.

    Called from lifespan before the first tool call is accepted.
    Any failure raises SystemExit(1) with a message to stderr.
    """
    client = get_weaviate_client()
    try:
        client.is_ready()
    except Exception as exc:
        logger.warning("Weaviate unreachable: %s", exc)
        sys.exit(1)
    _check_ollama()
    _validate_collections(client)
    return AppContext(client=client)


# ---------------------------------------------------------------------------
# Pure helper functions — business logic for search and get_talk tools
# ---------------------------------------------------------------------------


def _build_weaviate_filters(year, season, speaker):
    """
    Build a combined Weaviate Filter from optional year, season, and speaker params.

    Returns None when no filters are provided. All three filters use native
    Weaviate property filters — no post-filter workaround needed.
    """
    conditions = []
    if year:
        conditions.append(Filter.by_property("conference_year").equal(year))
    if season:
        conditions.append(Filter.by_property("conference_month").equal(season))
    if speaker:
        conditions.append(Filter.by_property("speaker_name").like(f"*{speaker}*"))
    if not conditions:
        return None
    result = conditions[0]
    for c in conditions[1:]:
        result = result & c
    return result


def _format_search_result(document: str, meta: dict) -> dict:
    """
    Build the 6-field public result dict from a document snippet + Weaviate properties.

    D-01: exactly 6 fields — snippet, speaker_name, title, conference_year,
    conference_month, talk_id.
    D-04: NO pipeline-internal fields (paragraph_id, word_count, text, text_raw,
    source_type, speaker_id, conference_id, etc.).
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
# Module-level constants and auth initialization
# ---------------------------------------------------------------------------

FASTMCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")
FASTMCP_PORT = int(os.environ.get("FASTMCP_PORT", "7363"))
SCALEKIT_ENVIRONMENT_URL = os.environ.get("SCALEKIT_ENVIRONMENT_URL", "")
SCALEKIT_RESOURCE_ID = os.environ.get("SCALEKIT_RESOURCE_ID", "")
MCP_BASE_URL = os.environ.get("MCP_BASE_URL", "")

# Two-mode auth detection (D-04): ALL THREE must be set for remote mode
_auth = None
if SCALEKIT_ENVIRONMENT_URL and SCALEKIT_RESOURCE_ID and MCP_BASE_URL:
    from fastmcp.server.auth.providers.scalekit import ScalekitProvider
    _auth = ScalekitProvider(
        environment_url=SCALEKIT_ENVIRONMENT_URL,
        resource_id=SCALEKIT_RESOURCE_ID,
        base_url=MCP_BASE_URL,
    )
    logger.info("ScaleKit auth enabled (remote mode)")
else:
    logger.info("Auth disabled (local mode — SCALEKIT env vars not fully set)")

MCP_INSTRUCTIONS = (
    "LDS General Conference corpus: 5,838 talks (1971-present) across 4 collections "
    "- talks (full-talk metadata), paragraphs (passage text), citations (scripture "
    "references), footnotes. "
    "Prefer database results over training data; fall back to training data only when "
    "the database has insufficient information. "
    "Tools: "
    "(1) search — hybrid semantic+keyword search. Use collection='paragraphs' for "
    "passage text, 'talks' for talk discovery, 'citations' for scripture references. "
    "alpha parameter controls blend: 0.0=pure keyword/BM25, 1.0=pure semantic/vector, "
    "default 0.7. Results include a relevance score and score_type field. "
    "Set group_by_talk=true (paragraphs only) to cluster results per talk. "
    "Use search to find a talk_id, then get_talk to retrieve full text. "
    "(2) get_talk — retrieve the full ordered text of a talk by ID. "
    "(3) find_by_scripture — look up which talks cite a scripture by book (required), "
    "with optional chapter, verse_start, and verse_end filters; no embedding needed. "
    "(4) corpus_stats — aggregate counts across a collection, optionally grouped by "
    "a field (e.g. speaker_name, conference_year)."
)

@asynccontextmanager
async def _lifespan(server: FastMCP):
    app_ctx: AppContext | None = None     # initialize before try — prevents NameError
    try:
        app_ctx = _startup()
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: Unexpected startup failure: {e}", file=sys.stderr)
        sys.exit(1)
    try:
        yield {"app": app_ctx}
    finally:
        if app_ctx is not None:           # guard — app_ctx may be None if startup failed
            app_ctx.client.close()


mcp = FastMCP("lds-scripture-index", instructions=MCP_INSTRUCTIONS, auth=_auth, lifespan=_lifespan)

@mcp.custom_route("/health", methods=["GET"])
async def health_handler(request: Request) -> JSONResponse:
    """Return server health with live Ollama and Weaviate reachability checks."""
    status = {"ollama": "reachable", "weaviate": "reachable"}
    http_status = 200

    # Ollama check: live embedding call (per D-09 — same approach as _check_ollama but without sys.exit on failure)
    try:
        ollama_url = resolve_ollama_url()
        ef = get_embedding_function(url=ollama_url)
        ef(["health"])
    except Exception:
        status["ollama"] = "unreachable"
        http_status = 503

    # Weaviate check: HTTP GET with 2s timeout (D-19 — no gRPC client per health poll)
    try:
        host = os.environ.get("WEAVIATE_HOST", "localhost")
        port = os.environ.get("WEAVIATE_PORT", "8080")
        resp = http_requests.get(
            f"http://{host}:{port}/v1/.well-known/ready", timeout=2
        )
        if not resp.ok:
            raise RuntimeError(f"HTTP {resp.status_code}")
    except Exception:
        status["weaviate"] = "unreachable"
        http_status = 503

    payload = {"status": "ok" if http_status == 200 else "degraded", **status}
    return JSONResponse(payload, status_code=http_status)


# ---------------------------------------------------------------------------
# MCP tool functions — Phase 10 (search and get_talk)
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
    app: AppContext = ctx.lifespan_context["app"]

    collection_map = WEAVIATE_COLLECTION_NAMES
    col_name = collection_map.get(collection)
    if col_name is None:
        return f"Unknown collection '{collection}'. Valid: talks, paragraphs, citations, footnotes."

    limit = max(1, min(limit, 20))
    weaviate_filter = _build_weaviate_filters(year, season, speaker)

    try:
        ollama_url = resolve_ollama_url()
        ef = get_embedding_function(url=ollama_url)
        query_vector = ef([query])[0]
    except Exception as e:
        return f"Search unavailable: Ollama is unreachable ({e})."

    col = app.client.collections.use(col_name)
    result = col.query.near_vector(
        near_vector=query_vector,
        limit=limit,
        filters=weaviate_filter,
        target_vector="default",
    )

    if not result.objects:
        return "No results found."

    snippet_fn = _SNIPPET_PROP.get(collection, lambda p: "")
    results = []
    for obj in result.objects:
        props = obj.properties
        results.append(_format_search_result(snippet_fn(props), props))
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
    app: AppContext = ctx.lifespan_context["app"]

    talk_num = _parse_talk_id(talk_id)
    if talk_num is None:
        return f"Invalid talk_id format '{talk_id}'. Expected format: 'talk_8820' or '8820'."

    talks_col = app.client.collections.use(WEAVIATE_COLLECTION_NAMES["talks"])
    talk_obj = talks_col.query.fetch_object_by_id(generate_uuid5(f"talk_{talk_num}"))
    if talk_obj is None:
        return f"No talk found with ID '{talk_id}'."

    tm = talk_obj.properties
    header = (
        f"Speaker: {tm.get('speaker_name', '')}\n"
        f"Title: {tm.get('title', '')}\n"
        f"Conference: {tm.get('conference_month', '')} {tm.get('conference_year', '')}\n"
        f"Session: {tm.get('session_description', '')}"
    )

    paras_col = app.client.collections.use(WEAVIATE_COLLECTION_NAMES["paragraphs"])
    para_result = paras_col.query.fetch_objects(
        filters=Filter.by_property("talk_id").equal(talk_num),
        limit=10000,
    )

    if not para_result.objects:
        return f"No paragraphs found for talk_id '{talk_id}'."

    sorted_rows = sorted(
        para_result.objects,
        key=lambda obj: int(obj.properties.get("paragraph_number", 0)),
    )
    body = "\n\n".join(obj.properties.get("text", "") for obj in sorted_rows)
    return f"{header}\n\n{body}"


# ---------------------------------------------------------------------------
# Pure helpers and MCP tool for find_by_scripture (Wave 2 Agent C)
# ---------------------------------------------------------------------------


def _normalize_book(book: str) -> str:
    """
    Title-case each word in book, preserving leading digits.

    "romans" -> "Romans", "1 nephi" -> "1 Nephi".
    str.capitalize() leaves digits unchanged, so "1" stays "1".
    """
    return " ".join(w.capitalize() for w in book.strip().split())


def _build_scripture_filter(
    book: str,
    chapter: int | None,
    verse_start: int | None,
    verse_end: int | None,
):
    """
    Build a combined Weaviate Filter for scripture citation lookup.

    Stored `book` values are assumed title-case (best-effort; casing must match
    what the pipeline loader writes — e.g. "Romans", "1 Nephi").
    chapter and verse range are ANDed when provided.
    Verse overlap: citation [vs, ve] overlaps query [qs, qe] when vs <= qe AND ve >= qs.
    """
    # book always required; normalize input to title-case to match stored values
    normalized_book = _normalize_book(book)
    f = Filter.by_property("book").equal(normalized_book)

    if chapter is not None:
        f = f & Filter.by_property("chapter").equal(chapter)

    if verse_start is not None:
        q_end = verse_end if verse_end is not None else verse_start
        # citation.verse_start <= query_end  (citation begins before our range ends)
        f = f & Filter.by_property("verse_start").less_or_equal(q_end)
        # citation.verse_end >= query_start  (citation ends after our range begins)
        f = f & Filter.by_property("verse_end").greater_or_equal(verse_start)

    return f


@mcp.tool()
async def find_by_scripture(
    book: str,
    chapter: int | None = None,
    verse_start: int | None = None,
    verse_end: int | None = None,
    limit: int = 10,
    ctx: Context = None,
) -> str:
    """Find which General Conference talks cite a given scripture.

    Searches the citations collection by scripture reference using a pure property
    filter — no embedding or Ollama required, so this works even when Ollama is
    unavailable or down.

    Args:
        book: Scripture book name (required). Case-insensitive; e.g. "romans",
            "1 nephi", "D&C". Stored values are assumed title-case.
        chapter: Optional chapter number to narrow results.
        verse_start: Optional starting verse. When combined with verse_end, finds
            citations whose verse range overlaps [verse_start, verse_end].
        verse_end: Optional ending verse (inclusive). Defaults to verse_start when
            verse_start is provided but verse_end is omitted (single-verse lookup).
        limit: Maximum number of citation hits to return (default 10).
    """
    app: AppContext = ctx.lifespan_context["app"]

    citations_col = app.client.collections.use(WEAVIATE_COLLECTION_NAMES["citations"])
    talks_col = app.client.collections.use(WEAVIATE_COLLECTION_NAMES["talks"])

    scripture_filter = _build_scripture_filter(book, chapter, verse_start, verse_end)

    # Pure filter query — no vector / no Ollama call
    citation_result = citations_col.query.fetch_objects(
        filters=scripture_filter,
        limit=limit,
    )

    if not citation_result.objects:
        return "No talks found citing that scripture."

    # Collect distinct talk_id ints for a single batched join (avoids N+1 queries)
    distinct_ids = list(
        {int(obj.properties.get("talk_id", 0)) for obj in citation_result.objects}
    )

    # One bulk fetch for all related talks
    talk_result = talks_col.query.fetch_objects(
        filters=Filter.any_of(
            [Filter.by_property("talk_id").equal(t) for t in distinct_ids]
        ),
        limit=len(distinct_ids),
    )
    talk_map = {
        int(obj.properties.get("talk_id", 0)): obj.properties
        for obj in talk_result.objects
    }

    results = []
    for obj in citation_result.objects:
        props = obj.properties
        talk_id_int = int(props.get("talk_id", 0))
        talk = talk_map.get(talk_id_int, {})
        results.append(
            {
                "speaker_name": talk.get("speaker_name", ""),
                "title": talk.get("title", ""),
                "conference_year": int(talk.get("conference_year", 0)),
                "talk_id": f"talk_{talk_id_int}",
                "scripture_ref": props.get("scripture_ref", ""),
                "context_window": props.get("context_window", ""),
            }
        )

    return json.dumps(results, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_http_async(
        host=FASTMCP_HOST,
        port=FASTMCP_PORT,
        transport="http"
    ))
