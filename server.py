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
  3. Embedding server reachability check via embedding call (non-fatal) (CORE-02)
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
from config.pipeline_config import WEAVIATE_COLLECTION_NAMES, WEAVIATE_SCRIPTURE_COLLECTION_NAMES
from config.embedding import resolve_embedding_url, get_embedding_function
from db.scripture import open_scripture_db
from tools.scripture_tools import (
    NOT_AVAILABLE as SCRIPTURE_NOT_AVAILABLE,
    ScriptureStore,
    build_scripture_filter,
    format_scripture_result,
    get_chapter_overview as scripture_chapter_overview,
    get_verse as scripture_verse,
)

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
    scripture: ScriptureStore | None = None   # None: scripture.db is not available (talk tools are unaffected)


# Per-collection property extractor: maps collection key -> text snippet from Weaviate properties.
# Paragraphs have a 'text' field. Talks, citations, and footnotes use different property names.
_SNIPPET_PROP = {
    "talks": lambda p: (p.get("title", "") + ("\n\n" + p.get("talk_preview", "") if p.get("talk_preview") else "")),
    "paragraphs": lambda p: p.get("text", ""),
    "citations": lambda p: p.get("context_window", "") or p.get("citation_text_raw", ""),
    "footnotes": lambda p: p.get("context_window", "") or p.get("footnote_text_raw", ""),
}

# Per-collection chronological sort property for the browse path (sort_by).
# talks carry a fine-grained ISO talk_date; paragraphs only carry conference_year
# (year granularity). citations and footnotes have no chronological field, so
# sort_by is unsupported there (search returns a clear message rather than erroring).
_SORT_PROP = {
    "talks": "talk_date",
    "paragraphs": "conference_year",
}


# ---------------------------------------------------------------------------
# Startup helpers — each raises SystemExit(1) on failure
# ---------------------------------------------------------------------------


def _check_embedding() -> None:
    """
    Log embedding server (llama-server) reachability at startup — non-fatal.

    The embedding server is a separate service accessed by URL; the server starts regardless
    of its availability. Search calls will fail gracefully if it is down.
    The /health endpoint reports live embedding server status on demand.
    """
    try:
        embedding_url = resolve_embedding_url()
        ef = get_embedding_function(url=embedding_url, task="query")
        ef(["health check"])
        logger.info("Embedding server reachable at startup (nomic-embed-text ready)")
    except Exception:
        logger.warning(
            "Embedding server unreachable at startup — search will be unavailable until it is running"
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
    _check_embedding()
    _validate_collections(client)
    return AppContext(client=client, scripture=_open_scripture())


def _open_scripture() -> ScriptureStore | None:
    """Open scripture.db read-only from SCRIPTURE_DB_PATH (read now, at startup). None when it is unusable."""
    try:
        database = open_scripture_db()
        return ScriptureStore.open(database) if database is not None else None
    except Exception as exc:  # noqa: BLE001 — scripture is optional; never block the talk tools
        logger.warning("scripture.db unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pure helper functions — business logic for search and get_talk tools
# ---------------------------------------------------------------------------


def _build_weaviate_filters(year, season, speaker, *, session=None, cites_scripture=None, year_from=None, year_to=None):
    """
    Build a combined Weaviate Filter from optional year, season, speaker, session,
    cites_scripture, year_from, and year_to params.

    Returns None when no filters are provided. All filters use native
    Weaviate property filters — no post-filter workaround needed.
    """
    conditions = []
    if year:
        conditions.append(Filter.by_property("conference_year").equal(year))
    if season:
        conditions.append(Filter.by_property("conference_month").equal(season))
    if speaker:
        conditions.append(Filter.by_property("speaker_name").like(f"*{speaker}*"))
    if session:
        conditions.append(Filter.by_property("session_abbr").equal(session))
    if cites_scripture is not None:
        conditions.append(Filter.by_property("has_scripture_citation").equal(cites_scripture))
    if year_from:
        conditions.append(Filter.by_property("conference_year").greater_or_equal(year_from))
    if year_to:
        conditions.append(Filter.by_property("conference_year").less_or_equal(year_to))
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
    Conditional metadata: topics (non-empty list), citation_count (non-None int).

    Snippet fallback: if document is empty/whitespace, falls back to meta title.

    D-04: NO pipeline-internal fields (paragraph_id, word_count, text, text_raw,
    source_type, speaker_id, conference_id, etc.).
    """
    snippet = document if (document and document.strip()) else meta.get("title", "")
    result = {
        "snippet": snippet,
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
    # Optional metadata — only when present and non-empty
    if meta.get("topics") and isinstance(meta["topics"], list):
        result["topics"] = list(meta["topics"])
    if "citation_count" in meta and meta["citation_count"] is not None:
        result["citation_count"] = int(meta["citation_count"])
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
    "LDS General Conference corpus: 5,838 talks (1942-present) across 4 collections "
    "- talks (full-talk metadata), paragraphs (passage text), citations (scripture "
    "references), footnotes. "
    "Prefer database results over training data; fall back to training data only when "
    "the database has insufficient information. "
    "Tools: "
    "(1) search — hybrid semantic+keyword search. Use collection='paragraphs' for "
    "passage text, 'talks' for talk discovery, 'citations' for scripture references, "
    "'footnotes' for footnote content. "
    "alpha controls the blend: 0.0=pure keyword/BM25 (exact terms, names, phrases), "
    "1.0=pure semantic/vector (meaning, paraphrase), default 0.7 (hybrid). "
    "Each result carries a relevance score and a score_type "
    "(bm25 | vector_certainty | hybrid_fusion) telling you how it was ranked. "
    "Filters: speaker (substring), year (exact) or year_from/year_to (inclusive range), "
    "season ('April'/'October'), session (session-abbr exact match), "
    "cites_scripture=true/false (paragraphs — keep only passages that do/don't quote "
    "scripture). Restrict keyword matching to specific fields with query_properties "
    "(e.g. ['title']). "
    "Paging: limit (max 20) + offset; the envelope reports total and has_more. "
    "Browse without a query by omitting it and supplying filters and/or "
    "sort_by ('date_desc'/'date_asc', newest/oldest first). "
    "Set group_by_talk=true (paragraphs only) to cluster hits per talk; "
    "results_per_talk sets how many passages per talk. Grouped results are always "
    "vector-ranked (search_mode 'vector_grouped') regardless of alpha and need the "
    "embedding service; alpha applies only to the flat, non-grouped path. "
    "Use search to find a talk_id, then get_talk for full text. "
    "(2) get_talk — retrieve the full ordered text of a talk by ID. "
    "(3) get_talk_citations — ordered scripture citations for one talk_id "
    "(scripture_ref, book/chapter/verses, context_window, paragraph_number); "
    "no embedding needed. "
    "(4) find_by_scripture — look up which talks cite a scripture by book (required), "
    "with optional chapter, verse_start, and verse_end filters; no embedding needed. "
    "(5) corpus_stats — aggregate counts across a collection, optionally grouped by "
    "a field (e.g. speaker_name, conference_year). "
    "Coverage note: pipeline-derived fields (session, conference year/date, "
    "scripture-citation flags) are complete for the whole corpus, but "
    "API-enrichment fields (topics, talk_preview, speaker_role) are absent before "
    "~1971 — filter on them only for modern talks; treat them as metadata/boosts, "
    "not hard filters, when searching the full range."
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
    """Return server health with live embedding server and Weaviate reachability checks."""
    status = {"embedding": "reachable", "weaviate": "reachable"}
    http_status = 200

    # Embedding server check: live embedding call (per D-09 — same approach as _check_embedding but without sys.exit on failure)
    try:
        embedding_url = resolve_embedding_url()
        ef = get_embedding_function(url=embedding_url, task="query")
        ef(["health"])
    except Exception:
        status["embedding"] = "unreachable"
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
    alpha: float | None = None,
    group_by_talk: bool = False,
    session: str | None = None,
    cites_scripture: bool | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    query_properties: list[str] | None = None,
    offset: int = 0,
    sort_by: str | None = None,
    results_per_talk: int = 3,
    book: str | None = None,
    volume: str | None = None,
    chapter: int | None = None,
    variant: str | None = None,
    ctx: Context = None,
) -> str:
    """Search LDS General Conference content by meaning.

    Use collection='paragraphs' for passage text, 'talks' for talk discovery,
    'citations' for scripture references, 'footnotes' for footnote content.
    Use collection='scripture_verses' to search the scripture text itself (KJV wording
    matters, so alpha=0.0 gives exact-phrase keyword search) and 'scripture_chapters'
    to find which chapter is about a topic.

    Args:
        query: Natural language search query.
        speaker: Optional speaker name filter (substring match, e.g. "Holland").
        year: Optional conference year filter (e.g. 2020).
        season: Optional conference season filter ("April" or "October").
        collection: Collection to search - "talks", "paragraphs" (default), "citations", or "footnotes".
        limit: Number of results to return (default 5, max 20).
        alpha: Blend of vector (1.0) and keyword/BM25 (0.0). Default 0.7 (hybrid); 0.4 for
            scripture_verses, where people remember KJV wording and keyword matches should weigh more.
        group_by_talk: If True (paragraphs only), cluster results by talk_id.
            Grouped results are always vector-ranked (search_mode "vector_grouped")
            regardless of alpha, and require the embedding service; alpha applies
            only to the flat, non-grouped path.
        session: Optional session abbreviation filter (exact match, e.g. "Sun AM").
        cites_scripture: Optional bool; True/False keeps only passages that do/don't cite scripture.
        year_from: Optional inclusive lower bound on conference_year.
        year_to: Optional inclusive upper bound on conference_year.
        query_properties: Optional list of property names to restrict BM25/hybrid keyword matching.
        offset: Number of results to skip for pagination (default 0).
        sort_by: Sort order for browse path only — 'date_desc' (newest first) or 'date_asc' (oldest first).
        results_per_talk: Max passages per talk when group_by_talk=True (default 3, max 10).
        book: Scripture collections only. Book name or abbreviation ("Alma", "1 Ne.", "D&C").
        volume: Scripture collections only. Volume title or short name ("Book of Mormon", "bofm").
        chapter: Scripture collections only. Chapter or section number.
        variant: scripture_verses only. "standard" (default), "jst" or "both".
    """
    app: AppContext = ctx.lifespan_context["app"]

    scripture_key = None
    if collection in ("scripture_verses", "scripture_chapters"):
        scripture_key = collection.split("_", 1)[1]
        col_name = WEAVIATE_SCRIPTURE_COLLECTION_NAMES[scripture_key]
    else:
        col_name = WEAVIATE_COLLECTION_NAMES.get(collection)
    if col_name is None:
        return f"Unknown collection '{collection}'. Valid: talks, paragraphs, citations, footnotes."
    if scripture_key is None and any(x is not None for x in (book, volume, chapter, variant)):
        return "book, volume, chapter and variant apply only to the scripture_verses and scripture_chapters collections."
    if scripture_key is not None and any(
        x is not None for x in (speaker, year, season, session, cites_scripture, year_from, year_to)
    ):
        return "speaker, year, season, session, cites_scripture and year_from/to apply only to talk collections."
    if scripture_key == "chapters" and variant is not None:
        return "variant applies only to the scripture_verses collection."

    if group_by_talk and collection != "paragraphs":
        return "group_by_talk is only supported for the paragraphs collection."

    if alpha is None:
        alpha = 0.4 if scripture_key == "verses" else 0.7
    alpha = max(0.0, min(1.0, alpha))
    limit = max(1, min(limit, 20))
    offset = max(0, offset)
    results_per_talk = max(1, min(results_per_talk, 10))
    if scripture_key is not None:
        weaviate_filter = build_scripture_filter(
            app.scripture, scripture_key, book=book, volume=volume, chapter=chapter, variant=variant,
        )
        if isinstance(weaviate_filter, str):
            return weaviate_filter
    else:
        weaviate_filter = _build_weaviate_filters(
            year, season, speaker,
            session=session,
            cites_scripture=cites_scripture,
            year_from=year_from,
            year_to=year_to,
        )
    col = app.client.collections.use(col_name)
    snippet_fn = _SNIPPET_PROP.get(collection, lambda p: "")
    fmt = _format_search_result
    if scripture_key is not None:
        # scripture rows carry `reference`, not talk fields
        fmt = lambda document, meta, **kw: format_scripture_result(scripture_key, meta, **kw)  # noqa: E731

    # Compute total count for pagination envelope (best-effort; None on failure)
    total = None
    try:
        tc = col.aggregate.over_all(filters=weaviate_filter, total_count=True).total_count
        if tc is not None:
            total = int(tc)
    except Exception:
        pass

    # Validate sort_by — only recognised values are honoured; treat others as None
    if sort_by not in ("date_desc", "date_asc"):
        sort_by = None

    # Empty/whitespace query — browse or error
    if not query.strip():
        # sort_by is honoured per-collection: talks sort by ISO talk_date,
        # paragraphs by conference_year (year granularity). citations/footnotes
        # have no chronological field, so a sort request there is rejected clearly.
        sort_prop = _SORT_PROP.get(collection) if sort_by is not None else None
        if sort_by is not None and sort_prop is None:
            return f"sort_by is not supported for the '{collection}' collection (no chronological field). Use 'talks' or 'paragraphs'."
        if weaviate_filter is None and sort_prop is None:
            return "Provide a query, at least one filter (speaker, year, year_from/to, season, session, cites_scripture), or sort_by."
        sort_arg = None
        if sort_prop is not None:
            sort_arg = Sort.by_property(sort_prop, ascending=(sort_by == "date_asc"))
        fetch_kwargs: dict = dict(filters=weaviate_filter, limit=limit, offset=offset)
        if sort_arg is not None:
            fetch_kwargs["sort"] = sort_arg
        result = col.query.fetch_objects(**fetch_kwargs)
        if not result.objects:
            return "No results found."
        results = [
            fmt(snippet_fn(obj.properties), obj.properties)
            for obj in result.objects
        ]
        has_more = bool(total is not None and (offset + len(results)) < total)
        return json.dumps(
            {"search_mode": "browse_filtered", "results": results, "total": total, "has_more": has_more},
            ensure_ascii=False,
            indent=2,
        )

    # Embedding — needed when alpha > 0, and always when grouping (group_by_talk
    # is routed through near_vector, which requires a query vector).
    need_vector = alpha != 0.0 or group_by_talk
    query_vector = None
    embedding_failed = False

    if need_vector:
        try:
            embedding_url = resolve_embedding_url()
            ef = get_embedding_function(url=embedding_url, task="query")
            query_vector = ef([query])[0]
        except Exception as e:
            logger.warning("Embedding server unavailable for search (falling back to bm25): %s", e)
            embedding_failed = True

    # Determine effective search path
    if embedding_failed:
        effective_alpha = 0.0
        search_mode = "keyword_only_embedding_unavailable"
    elif alpha == 0.0:
        effective_alpha = 0.0
        search_mode = "keyword"
    elif alpha == 1.0:
        effective_alpha = 1.0
        search_mode = "vector"
    else:
        effective_alpha = alpha
        search_mode = "hybrid"

    # Grouped path — routed through near_vector regardless of alpha. On this
    # Weaviate version hybrid+group_by returns zero groups, so grouping only works
    # via the vector path; it requires a query vector. When none is available
    # (embedding server down), grouping cannot run — say so plainly instead of returning empty.
    if group_by_talk:
        if query_vector is None:
            return (
                "group_by_talk requires semantic search (a query embedding), which is "
                "currently unavailable. Retry without group_by_talk, or once the "
                "embedding service is reachable."
            )
        group_by_arg = GroupBy(prop="talk_id", number_of_groups=limit, objects_per_group=results_per_talk)
        result = col.query.near_vector(
            near_vector=query_vector,
            limit=limit,
            offset=offset,
            filters=weaviate_filter,
            target_vector="default",
            group_by=group_by_arg,
            return_metadata=MetadataQuery(distance=True, certainty=True),
        )
        # weaviate-client returns groups as a dict {group_value: GroupObject};
        # iterate its values and read the group value from .name.
        groups_raw = getattr(result, "groups", None)
        if not groups_raw:
            return "No results found."
        groups_out = []
        for group in groups_raw.values():
            group_val = getattr(group, "name", None)
            try:
                talk_id_str = f"talk_{int(group_val)}"
            except (ValueError, TypeError):
                talk_id_str = str(group_val)
            paragraphs = []
            for obj in group.objects:
                props = obj.properties
                meta = obj.metadata
                relevance = getattr(meta, "certainty", None)
                dist = getattr(meta, "distance", None)
                paragraphs.append(fmt(
                    snippet_fn(props), props,
                    relevance=relevance, score_type="vector_certainty", distance=dist,
                ))
            groups_out.append({"talk_id": talk_id_str, "paragraphs": paragraphs})
        has_more = bool(total is not None and (offset + len(groups_out)) < total)
        return json.dumps(
            {"search_mode": "vector_grouped", "groups": groups_out, "total": total, "has_more": has_more},
            ensure_ascii=False,
            indent=2,
        )

    # Execute the appropriate Weaviate query (non-grouped)
    if effective_alpha == 1.0:
        result = col.query.near_vector(
            near_vector=query_vector,
            limit=limit,
            offset=offset,
            filters=weaviate_filter,
            target_vector="default",
            return_metadata=MetadataQuery(distance=True, certainty=True),
        )
    elif effective_alpha == 0.0:
        bm25_kwargs: dict = dict(
            query=query,
            limit=limit,
            offset=offset,
            filters=weaviate_filter,
            return_metadata=MetadataQuery(score=True),
        )
        if query_properties:
            bm25_kwargs["query_properties"] = query_properties
        result = col.query.bm25(**bm25_kwargs)
    else:
        kwargs: dict = dict(
            query=query,
            vector=query_vector,
            alpha=effective_alpha,
            limit=limit,
            offset=offset,
            filters=weaviate_filter,
            target_vector="default",
            return_metadata=MetadataQuery(score=True),
        )
        if query_properties:
            kwargs["query_properties"] = query_properties
        result = col.query.hybrid(**kwargs)

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
            row = fmt(
                snippet_fn(props), props,
                relevance=relevance, score_type="vector_certainty", distance=dist,
            )
        elif effective_alpha == 0.0:
            relevance = getattr(meta, "score", None)
            row = fmt(
                snippet_fn(props), props,
                relevance=relevance, score_type="bm25",
            )
        else:
            relevance = getattr(meta, "score", None)
            row = fmt(
                snippet_fn(props), props,
                relevance=relevance, score_type="hybrid_fusion",
            )
        results.append(row)

    has_more = bool(total is not None and (offset + len(results)) < total)
    return json.dumps(
        {"search_mode": search_mode, "results": results, "total": total, "has_more": has_more},
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
        sort=Sort.by_property("paragraph_number", ascending=True),
    )

    if not para_result.objects:
        return f"No paragraphs found for talk_id '{talk_id}'."

    body = "\n\n".join(obj.properties.get("text", "") for obj in para_result.objects)
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
    filter — no embedding or embedding server required, so this works even when the
    embedding server is unavailable or down.

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

    # Pure filter query — no vector / no embedding call
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


@mcp.tool()
async def corpus_stats(
    collection: str = "talks",
    group_by: str | None = None,
    limit: int = 20,
    ctx: Context = None,
) -> str:
    """Returns aggregate counts across a collection, optionally grouped by a field (e.g. speaker_name, conference_year, conference_month); no embedding needed.

    Args:
        collection: Collection to aggregate - "talks" (default), "paragraphs", "citations", or "footnotes".
        group_by: Optional property name to group by (e.g. "speaker_name", "conference_year", "conference_month").
        limit: Maximum number of groups to return when group_by is set (default 20).
    """
    app: AppContext = ctx.lifespan_context["app"]

    if collection not in WEAVIATE_COLLECTION_NAMES:
        return f"Unknown collection '{collection}'. Valid: talks, paragraphs, citations, footnotes."

    col = app.client.collections.use(WEAVIATE_COLLECTION_NAMES[collection])

    if group_by is None:
        res = col.aggregate.over_all(total_count=True)
        return json.dumps({"collection": collection, "total": res.total_count})

    res = col.aggregate.over_all(group_by=GroupByAggregate(prop=group_by), total_count=True)
    groups = [
        {"value": group.grouped_by.value, "count": group.total_count}
        for group in res.groups
    ]
    groups.sort(key=lambda g: g["count"], reverse=True)
    groups = groups[:limit]
    return json.dumps({"collection": collection, "group_by": group_by, "groups": groups}, ensure_ascii=False)


@mcp.tool()
async def get_talk_citations(
    talk_id: str,
    limit: int = 100,
    ctx: Context = None,
) -> str:
    """Return the ordered scripture citations for a single talk. No embedding needed.

    Args:
        talk_id: Talk identifier (e.g. "talk_8820" or "8820").
        limit: Maximum number of citations to return (default 100, capped at 500).
    """
    app: AppContext = ctx.lifespan_context["app"]

    talk_num = _parse_talk_id(talk_id)
    if talk_num is None:
        return f"Invalid talk_id format '{talk_id}'. Expected format: 'talk_8820' or '8820'."

    limit = max(1, min(limit, 500))

    citations_col = app.client.collections.use(WEAVIATE_COLLECTION_NAMES["citations"])
    result = citations_col.query.fetch_objects(
        filters=Filter.by_property("talk_id").equal(talk_num),
        limit=limit,
        sort=Sort.by_property("paragraph_number", ascending=True),
    )

    if not result.objects:
        return f"No citations found for talk_id '{talk_id}'."

    # Secondary sort by char_position within each paragraph for stable ordering.
    # Weaviate's single-key sort handles paragraph_number; Python handles char_position.
    sorted_objects = sorted(
        result.objects,
        key=lambda o: (
            o.properties.get("paragraph_number") or 0,
            o.properties.get("char_position") or 0,
        ),
    )

    results = []
    for o in sorted_objects:
        props = o.properties
        results.append({
            "scripture_ref": props.get("scripture_ref", ""),
            "book": props.get("book", ""),
            "chapter": props.get("chapter"),
            "verses": props.get("verses", ""),
            "verse_start": props.get("verse_start"),
            "verse_end": props.get("verse_end"),
            "context_window": props.get("context_window", ""),
            "paragraph_number": props.get("paragraph_number"),
        })

    return json.dumps(results, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Scripture tools — read scripture.db directly (no embedding, no Weaviate)
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_verse(
    book: str,
    chapter: int,
    verse_start: int | None = None,
    verse_end: int | None = None,
    include_footnotes: bool = True,
    include_jst: bool = False,
    numbering: str = "standard",
    ctx: Context = None,
) -> str:
    """Return scripture verses with their chapter summary, footnotes and optionally the JST. No embedding needed.

    Args:
        book: Book name or abbreviation ("Alma", "1 Nephi", "1 Ne.", "First Nephi", "D&C", "Psalms").
            "JST Genesis" reads the Joseph Smith Translation in its own chapter and verse numbering.
        chapter: Chapter (or D&C section) number. For a one-chapter book ("Jude", 3) means Jude 1:3.
        verse_start: First verse; omit for the whole chapter.
        verse_end: Last verse of a range (default: verse_start).
        include_footnotes: Attach each verse's footnotes with their references (default true).
        include_jst: Attach the JST verses the Church links to each verse (its JST footnotes and appendix).
        numbering: "standard" (default) or "jst" (same as a "JST ..." book).

    Returns JSON {reference, chapter_summary, verses: [{reference, verse, text, jst?, footnotes?}]}.
    """
    app: AppContext = ctx.lifespan_context["app"]
    if app.scripture is None:
        return SCRIPTURE_NOT_AVAILABLE
    result = scripture_verse(app.scripture, book, chapter, verse_start, verse_end,
                             include_footnotes=include_footnotes, include_jst=include_jst, numbering=numbering)
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_chapter_overview(
    book: str,
    chapter: int,
    ctx: Context = None,
) -> str:
    """Orient on a chapter before reading it: title, intro, summary, verse count and its most-referenced
    cross-reference targets. No embedding needed.

    Args:
        book: Book name or abbreviation ("Alma", "1 Ne.", "D&C").
        chapter: Chapter (or D&C section) number.
    """
    app: AppContext = ctx.lifespan_context["app"]
    if app.scripture is None:
        return SCRIPTURE_NOT_AVAILABLE
    result = scripture_chapter_overview(app.scripture, book, chapter)
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_http_async(
        host=FASTMCP_HOST,
        port=FASTMCP_PORT,
        transport="http"
    ))
