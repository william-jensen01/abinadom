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


def _format_search_result(
    document: str,
    meta: dict,
    *,
    relevance=None,
    score_type=None,
    distance=None,
) -> dict:
    """
    Build the public result dict from a document snippet + Weaviate properties.

    Base fields (always present): snippet, speaker_name, title, conference_year,
    conference_month, talk_id.
    Optional fields (present only when passed): relevance, score_type, distance.

    D-04: NO pipeline-internal fields (paragraph_id, word_count, text, text_raw,
    source_type, speaker_id, conference_id, etc.).
    """
    result = {
        "snippet": document,
        "speaker_name": meta.get("speaker_name", ""),
        "title": meta.get("title", ""),
        "conference_year": int(meta.get("conference_year", 0)),
        "conference_month": meta.get("conference_month", ""),
        "talk_id": f"talk_{int(meta.get('talk_id', 0))}",
    }
    if relevance is not None:
        result["relevance"] = relevance
    if score_type is not None:
        result["score_type"] = score_type
    if distance is not None:
        result["distance"] = distance
    return result


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
    alpha: float = 0.7,
    group_by_talk: bool = False,
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
        alpha: Blend of vector (1.0) and keyword/BM25 (0.0). Default 0.7 (hybrid).
        group_by_talk: If True (paragraphs only), cluster results by talk_id.
    """
    app: AppContext = ctx.lifespan_context["app"]

    col_name = WEAVIATE_COLLECTION_NAMES.get(collection)
    if col_name is None:
        return f"Unknown collection '{collection}'. Valid: talks, paragraphs, citations, footnotes."

    if group_by_talk and collection != "paragraphs":
        return "group_by_talk is only supported for the paragraphs collection."

    alpha = max(0.0, min(1.0, alpha))
    limit = max(1, min(limit, 20))
    weaviate_filter = _build_weaviate_filters(year, season, speaker)
    col = app.client.collections.use(col_name)
    snippet_fn = _SNIPPET_PROP.get(collection, lambda p: "")

    # Empty/whitespace query — browse or error
    if not query.strip():
        if weaviate_filter is None:
            return "Provide a query or at least one filter (speaker, year, or season)."
        result = col.query.fetch_objects(filters=weaviate_filter, limit=limit)
        if not result.objects:
            return "No results found."
        results = [
            _format_search_result(snippet_fn(obj.properties), obj.properties)
            for obj in result.objects
        ]
        return json.dumps(
            {"search_mode": "browse_filtered", "results": results},
            ensure_ascii=False,
            indent=2,
        )

    # Embedding — only needed when alpha > 0
    need_vector = alpha != 0.0
    query_vector = None
    ollama_failed = False

    if need_vector:
        try:
            ollama_url = resolve_ollama_url()
            ef = get_embedding_function(url=ollama_url)
            query_vector = ef([query])[0]
        except Exception as e:
            logger.warning("Ollama unavailable for search (falling back to bm25): %s", e)
            ollama_failed = True

    # Determine effective search path
    if ollama_failed:
        effective_alpha = 0.0
        search_mode = "keyword_only_ollama_unavailable"
    elif alpha == 0.0:
        effective_alpha = 0.0
        search_mode = "keyword"
    elif alpha == 1.0:
        effective_alpha = 1.0
        search_mode = "vector"
    else:
        effective_alpha = alpha
        search_mode = "hybrid"

    # GroupBy — only for ranked (vector/hybrid) paths
    group_by_arg = None
    if group_by_talk and effective_alpha != 0.0:
        group_by_arg = GroupBy(prop="talk_id", number_of_groups=limit, objects_per_group=3)

    # Execute the appropriate Weaviate query
    if effective_alpha == 1.0:
        kwargs: dict = dict(
            near_vector=query_vector,
            limit=limit,
            filters=weaviate_filter,
            target_vector="default",
            return_metadata=MetadataQuery(distance=True, certainty=True),
        )
        if group_by_arg is not None:
            kwargs["group_by"] = group_by_arg
        result = col.query.near_vector(**kwargs)
    elif effective_alpha == 0.0:
        result = col.query.bm25(
            query=query,
            limit=limit,
            filters=weaviate_filter,
            return_metadata=MetadataQuery(score=True),
        )
    else:
        kwargs = dict(
            query=query,
            vector=query_vector,
            alpha=effective_alpha,
            limit=limit,
            filters=weaviate_filter,
            target_vector="default",
            return_metadata=MetadataQuery(score=True),
        )
        if group_by_arg is not None:
            kwargs["group_by"] = group_by_arg
        result = col.query.hybrid(**kwargs)

    # Grouped output (near_vector or hybrid with group_by_talk)
    if group_by_arg is not None:
        groups_raw = getattr(result, "groups", None)
        if not groups_raw:
            return "No results found."
        groups_out = []
        for group in groups_raw:
            group_val = group.belongs_to_group
            try:
                talk_id_str = f"talk_{int(group_val)}"
            except (ValueError, TypeError):
                talk_id_str = str(group_val)
            paragraphs = []
            for obj in group.objects:
                props = obj.properties
                meta = obj.metadata
                if effective_alpha == 1.0:
                    relevance = getattr(meta, "certainty", None)
                    dist = getattr(meta, "distance", None)
                    row = _format_search_result(
                        snippet_fn(props), props,
                        relevance=relevance, score_type="vector_certainty", distance=dist,
                    )
                else:
                    relevance = getattr(meta, "score", None)
                    row = _format_search_result(
                        snippet_fn(props), props,
                        relevance=relevance, score_type="hybrid_fusion",
                    )
                paragraphs.append(row)
            groups_out.append({"talk_id": talk_id_str, "paragraphs": paragraphs})
        return json.dumps(
            {"search_mode": search_mode, "groups": groups_out},
            ensure_ascii=False,
            indent=2,
        )

    # Non-grouped output
    if not result.objects:
        return "No results found."

    results = []
    for obj in result.objects:
        props = obj.properties
        meta = obj.metadata
        if effective_alpha == 1.0:
            relevance = getattr(meta, "certainty", None)
            dist = getattr(meta, "distance", None)
            row = _format_search_result(
                snippet_fn(props), props,
                relevance=relevance, score_type="vector_certainty", distance=dist,
            )
        elif effective_alpha == 0.0:
            relevance = getattr(meta, "score", None)
            row = _format_search_result(
                snippet_fn(props), props,
                relevance=relevance, score_type="bm25",
            )
        else:
            relevance = getattr(meta, "score", None)
            row = _format_search_result(
                snippet_fn(props), props,
                relevance=relevance, score_type="hybrid_fusion",
            )
        results.append(row)

    return json.dumps(
        {"search_mode": search_mode, "results": results},
        ensure_ascii=False,
        indent=2,
    )


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


if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_http_async(
        host=FASTMCP_HOST,
        port=FASTMCP_PORT,
        transport="http"
    ))
