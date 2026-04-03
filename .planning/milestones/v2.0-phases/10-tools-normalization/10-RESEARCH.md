# Phase 10: Tools & Normalization - Research

**Researched:** 2026-04-01
**Domain:** FastMCP tool registration, ChromaDB query/filter API, Python async tool patterns
**Confidence:** HIGH

## Summary

Phase 10 adds two MCP tools (`search` and `get_talk`) to the existing `server.py`. The foundation is solid: Phase 9 established `AppContext`, the lifespan pattern, and collection loading. Phase 9.1 (completed) enriched all 202,175 paragraph records with `speaker_name`, `title`, `conference_year`, `conference_month` — so the 6-field result shape (D-01) is achievable without secondary lookups.

The single most important finding is that **ChromaDB 1.5.5's `$contains` metadata operator silently returns 0 results** — it does not perform substring matching on string metadata fields. The CONTEXT.md design note about `{"speaker_name": {"$contains": "Holland"}}` assumes functionality that does not work in practice. Speaker substring filtering must be done in Python after fetching results, or via a `where_document` approach. This is a well-bounded problem with a clean solution (post-filter or fetch-more-then-filter), and the CONTEXT.md already grants discretion on this exact point.

The `get_talk` pattern is clean: one `collection.get()` call with a `{"talk_id": {"$eq": int_id}}` filter on the `paragraphs` collection, then Python sort by `paragraph_number`. Result metadata fields `text`, `text_raw`, and all pipeline-internal fields must be stripped before returning output.

**Primary recommendation:** Implement both tools as `async def` functions registered with `@mcp.tool()`. Extract pure-logic helpers (filter-building, result formatting) into testable module-level functions. Test those helpers directly with mocked ChromaDB return data — no need for `pytest-asyncio` or a live server in tests.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Every search result returns exactly 6 fields: `snippet` (matched text), `speaker_name`, `title`, `conference_year`, `conference_month`, `talk_id`.
**D-02:** Relevance/distance scores are omitted.
**D-03:** `talk_id` included in every result (enables search → get_talk flow). Not displayed to user.
**D-04:** No pipeline-internal fields exposed: no `paragraph_id`, `speaker_id`, `conference_id`, `word_count`, `source_type`, `text_raw`, `extraction_*`, `corpus`, `data_aid`, `uri_*`.

**D-05:** Speaker normalization offloaded to Claude. No server-side lookup table.
**D-06:** Server applies case-insensitive contains match on `speaker_name`. Input "Holland" matches "Jeffrey R. Holland".

**D-07:** Date normalization offloaded to Claude. Claude passes `year` (int) and `season` ("April" or "October"). Server applies exact filters on `conference_year` and `conference_month`.

**D-08:** Collection aliases ("talks", "paragraphs", "citations", "footnotes") map directly to `CHROMADB_COLLECTION_NAMES` keys. No resolution layer needed.

**D-09:** Single `search` tool with optional `collection` parameter. Not separate per-collection tools.
**D-10:** Default collection is `paragraphs`.
**D-11:** Parameters: `query` (required), `speaker` (optional str), `year` (optional int), `season` (optional: "April" | "October"), `collection` (optional, default "paragraphs"), `limit` (optional int, default 5, max 20).

**D-12:** `get_talk` accepts `talk_id` (string, e.g., "talk_8820").
**D-13:** Discovery/disambiguation via `search(collection="talks")`, not `get_talk`.
**D-14:** `get_talk` output format: structured header then ordered paragraph body (see CONTEXT.md for exact template).
**D-15:** Paragraphs sorted by `paragraph_number`. No pipeline fields in output.

### Claude's Discretion

- Exact ChromaDB `where` filter construction for contains-match on speaker_name (e.g., `$contains` or post-filter)
- How to handle `get_talk` when `talk_id` is not found (error message wording)
- Whether to truncate very long talks or return all paragraphs
- Internal batching of talk metadata enrichment lookup per search call

### Deferred Ideas (OUT OF SCOPE)

- Gap Phase 9.5 (paragraph metadata enrichment) — already completed as Phase 9.1
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-04 | User can pass informal speaker names ("Holland", "Elder Holland") and server resolves | Post-filter approach on `speaker_name` after ChromaDB query (see Pitfall 1) |
| CORE-05 | User can pass informal year/season values and server normalizes to metadata filters | Exact `$eq` filters on `conference_year` (int) and `conference_month` (str) — verified working |
| CORE-06 | User can pass collection aliases that resolve to ChromaDB collection names | Direct map via `CHROMADB_COLLECTION_NAMES` dict — no resolution layer |
| TOOL-01 | User can perform semantic search across any of the 4 collections | `collection.query(query_texts=[...], n_results=..., where={...})` |
| TOOL-02 | User can filter search results by speaker, year, conference season, and/or collection | `where` dict with `$and` combining `conference_year`/`conference_month` exact filters; speaker via post-filter |
| TOOL-03 | Search returns readable snippet text (no internal pipeline fields), default 5, max 20 | Strip fields; document text is the snippet |
| TOOL-04 | User can retrieve full ordered text of a talk by talk ID | `paras.get(where={"talk_id": {"$eq": int_id}})` + Python sort |
| TOOL-05 | `get_talk` returns paragraphs sorted by narrative position | Sort by `paragraph_number` in Python |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp` (FastMCP) | 1.26.0 | Tool registration, Context injection, lifespan | Already in use — Phase 9 established the pattern |
| `chromadb` | 1.5.5 | Semantic search (`query()`), direct retrieval (`get()`) | Already in use — 4 collections loaded at startup |

### No New Dependencies

Phase 10 adds zero new packages. All required capabilities are already installed.

**Verified installed versions:**
```
chromadb: 1.5.5   (pipenv run py -c "import chromadb; print(chromadb.__version__)")
mcp:      1.26.0  (importlib.metadata.version('mcp'))
```

## Architecture Patterns

### Recommended Project Structure

No new files required. All code goes in `server.py`:

```
server.py
├── AppContext (dataclass)     — unchanged from Phase 9
├── lifespan()                 — unchanged from Phase 9
├── _build_where_filter()      — NEW: pure helper, builds ChromaDB where dict
├── _format_search_results()   — NEW: pure helper, strips pipeline fields, returns 6-field dicts
├── search()                   — NEW: @mcp.tool() registered async function
└── get_talk()                 — NEW: @mcp.tool() registered async function
```

### Pattern 1: Tool Registration with Context

```python
# Source: FastMCP Context documentation (mcp 1.26.0)
from mcp.server.fastmcp import FastMCP, Context

@mcp.tool()
async def search(
    query: str,
    speaker: str | None = None,
    year: int | None = None,
    season: str | None = None,   # "April" or "October"
    collection: str = "paragraphs",
    limit: int = 5,
    ctx: Context = None,         # injected by FastMCP
) -> str:
    app: AppContext = ctx.request_context.lifespan_context
    col = app.collections[collection]
    ...
```

**Note:** `ctx` is injected by FastMCP when parameter is annotated with `Context` type. The `lifespan_context` field on `RequestContext` holds the `AppContext` yielded from the lifespan function.

### Pattern 2: ChromaDB Semantic Query

```python
# Source: verified against chromadb 1.5.5
result = col.query(
    query_texts=[query],
    n_results=n,
    where=where_dict,          # None if no filters
    include=["documents", "metadatas"],
)
# result["ids"][0]        — list of IDs
# result["documents"][0]  — list of document texts (the snippet)
# result["metadatas"][0]  — list of metadata dicts
```

### Pattern 3: ChromaDB Direct Retrieval (get_talk)

```python
# Source: verified against chromadb 1.5.5
result = col.get(
    where={"talk_id": {"$eq": int(talk_id_num)}},
    include=["documents", "metadatas"],
)
# result["ids"]       — flat list (not nested like query())
# result["documents"] — flat list
# result["metadatas"] — flat list
```

**Critical difference:** `collection.get()` returns flat lists; `collection.query()` returns nested lists (`result["ids"][0]`).

### Pattern 4: Speaker Contains-Match (Post-Filter)

Because `$contains` in ChromaDB `where` metadata filters silently returns 0 results (verified against chromadb 1.5.5), speaker substring matching must be done in Python:

```python
# Fetch more results to compensate for post-filter reduction
# Then filter in Python with case-insensitive substring match
def _speaker_matches(stored_name: str, input_name: str) -> bool:
    return input_name.lower() in stored_name.lower()
```

**Recommended approach:** When `speaker` is provided, fetch `limit * 4` results (capped at a reasonable ceiling), post-filter to those whose `speaker_name` contains the input (case-insensitive), then truncate to `limit`. This is the approach granted by Claude's Discretion in D-06.

### Pattern 5: Where Filter Construction

```python
# Source: verified against chromadb 1.5.5 — $eq, $and, $in confirmed working
def _build_where_filter(year: int | None, season: str | None) -> dict | None:
    filters = []
    if year is not None:
        filters.append({"conference_year": {"$eq": year}})
    if season is not None:
        filters.append({"conference_month": {"$eq": season}})
    if len(filters) == 0:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}
```

**Note:** `speaker` is NOT included in the `where` dict — it is applied as a post-filter in Python (see Pattern 4).

### Pattern 6: get_talk Output Formatting

```python
# From D-14 (10-CONTEXT.md)
ALLOWED_TALK_META_FIELDS = {"speaker_name", "title", "conference_month", "conference_year", "session_description"}
ALLOWED_PARA_META_FIELDS = {"paragraph_number"}  # only used for sort

# Build header from talks collection metadata
# Build body from paragraphs collection, sorted by paragraph_number
```

The talks collection (metadata field `session_description`) has the session description. Verify via `talks.get(ids=[f"talk_{num}"])` to retrieve the header fields.

### Anti-Patterns to Avoid

- **Using `$contains` in `where` metadata filter:** Returns 0 results in chromadb 1.5.5. Use post-filter in Python instead.
- **Using `get_or_create_collection()` in tools:** Phase 9 established the pattern of `get_collection()` at startup and storing results in `AppContext`. Tools use `app.collections[key]` — no new collection calls in tool code.
- **Exposing raw ChromaDB document text as `text` or `text_raw`:** The paragraph metadata contains `text` and `text_raw` keys that ARE pipeline-internal fields (D-04). The snippet should come from `result["documents"][0][i]` (the ChromaDB document field, which is the same as `text` but retrieved via the documents include, not metadata).
- **Nesting query result access like `get()` access:** `query()` returns `result["ids"][0]`; `get()` returns `result["ids"]`. Mixing these causes IndexError.
- **Passing `collection` param directly as ChromaDB collection name:** The tool param ("paragraphs") is a logical key; `CHROMADB_COLLECTION_NAMES["paragraphs"]` is the actual name. Access via `app.collections[collection]` which already maps the key to a live Collection object.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Semantic similarity ranking | Custom vector math | `chromadb.Collection.query()` | ChromaDB uses Ollama embeddings + HNSW index; already integrated |
| Paragraph ordering | DB re-query with ORDER BY | Python `sorted()` on `paragraph_number` | ChromaDB has no ORDER BY; metadata sort in Python is trivial |
| Speaker name lookup table | Dict of name variants | Post-filter substring match | Context.md D-05 explicitly prohibits this; substring match covers the use case |

**Key insight:** The entire Phase 10 implementation is wiring — calling existing APIs (ChromaDB, FastMCP) with the correct parameters. There is no novel logic to build.

## Common Pitfalls

### Pitfall 1: `$contains` Metadata Filter Returns Empty (CRITICAL)
**What goes wrong:** Using `{"speaker_name": {"$contains": "Holland"}}` in the ChromaDB `where` dict returns 0 results even when matching records exist.
**Why it happens:** ChromaDB 1.5.5's `$contains` operator is defined in the `WhereDocument` type, not the `Where` (metadata) type. When used in `where=`, it is silently rejected or matched against nothing. `$contains` works in `where_document=` (full-text document matching), not metadata fields.
**How to avoid:** Do NOT put `speaker_name` in the `where` dict at all. Apply speaker filtering in Python after receiving ChromaDB results: `input.lower() in stored_name.lower()`.
**Warning signs:** Zero results when speaker filter is applied, non-zero results when removed.

### Pitfall 2: Query vs Get Return Shape Mismatch
**What goes wrong:** `collection.query()` returns nested lists (`result["ids"][0]`). `collection.get()` returns flat lists (`result["ids"]`). Treating them the same causes IndexError or wrong data.
**Why it happens:** ChromaDB supports multiple query_texts simultaneously, so `query()` returns one list per query. `get()` is a single retrieval, so the result is flat.
**How to avoid:** Always use `result["ids"][0]` with `query()` and `result["ids"]` with `get()`.

### Pitfall 3: `text` and `text_raw` in Paragraph Metadata
**What goes wrong:** Paragraph ChromaDB records have `text` and `text_raw` as metadata fields (confirmed in Phase 9.1 — they're stored via `_flatten_metadata(asdict(para))`). Passing the full metadata dict to the tool output exposes pipeline-internal fields.
**Why it happens:** `ParagraphData.to_chromadb_format()` puts `text` in `document` AND `text` leaks into metadata via `asdict()`.
**How to avoid:** Never return raw metadata dicts. Build the 6-field output dict explicitly: `{"snippet": doc_text, "speaker_name": meta["speaker_name"], "title": meta["title"], "conference_year": meta["conference_year"], "conference_month": meta["conference_month"], "talk_id": meta["talk_id"]}`. Use `result["documents"][0][i]` as the snippet, not `meta["text"]`.

### Pitfall 4: `talk_id` Type Mismatch in `get_talk`
**What goes wrong:** `talk_id` values in paragraph metadata are stored as integers (e.g., `8820`). If the filter uses a string, `{"talk_id": {"$eq": "8820"}}`, no results are returned.
**Why it happens:** ChromaDB metadata stores int fields as ints; `$eq` is type-strict.
**How to avoid:** Parse the `talk_id` parameter string ("talk_8820") to extract the integer: `int(talk_id.replace("talk_", ""))`. Apply filter as `{"talk_id": {"$eq": int_val}}`.

### Pitfall 5: `conference_year` Type in Metadata
**What goes wrong:** `conference_year` in paragraph metadata is stored as int. Type-strict `$eq` requires int for int fields. Also relevant for result formatting: `str(meta["conference_year"])` to avoid "2020.0" if somehow stored as float.
**Why it happens:** VER-06 already includes an int coercion guard — same vigilance applies in tool output.
**How to avoid:** Always cast with `int(meta["conference_year"])` when using in filters or output.

### Pitfall 6: Empty `where` Dict Passed to ChromaDB
**What goes wrong:** Passing `where={}` (empty dict) to ChromaDB raises a validation error. When no filters are provided, `where` must be `None`, not `{}`.
**Why it happens:** ChromaDB validates that every `where` clause has at least one condition.
**How to avoid:** The `_build_where_filter()` helper returns `None` when no filters apply. Pass `where=None` (which ChromaDB accepts by omitting the filter entirely).

## Code Examples

### Tool Registration Pattern

```python
# Source: mcp 1.26.0 FastMCP documentation + Phase 9 established pattern
from mcp.server.fastmcp import Context

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
    app: AppContext = ctx.request_context.lifespan_context
    col = app.collections.get(collection)
    if col is None:
        return f"Unknown collection '{collection}'. Valid: talks, paragraphs, citations, footnotes."
    ...
```

### Where Filter Builder

```python
# Verified: $eq works on int (conference_year) and str (conference_month)
# $and combines multiple filters
# Returns None when no filters — DO NOT pass {} to ChromaDB
def _build_where_filter(year: int | None, season: str | None) -> dict | None:
    filters = []
    if year is not None:
        filters.append({"conference_year": {"$eq": year}})
    if season is not None:
        filters.append({"conference_month": {"$eq": season}})
    if not filters:
        return None
    return filters[0] if len(filters) == 1 else {"$and": filters}
```

### Search Result Formatter

```python
# Document text is result["documents"][0][i] (the embedded text = paragraph text)
# snippet from document, not from meta["text"] (which would expose internal field)
SEARCH_OUTPUT_FIELDS = {"speaker_name", "title", "conference_year", "conference_month", "talk_id"}

def _format_search_result(document: str, meta: dict) -> dict:
    return {
        "snippet": document,
        "speaker_name": meta.get("speaker_name", ""),
        "title": meta.get("title", ""),
        "conference_year": int(meta.get("conference_year", 0)),
        "conference_month": meta.get("conference_month", ""),
        "talk_id": f"talk_{int(meta.get('talk_id', 0))}",
    }
```

### Speaker Post-Filter Pattern

```python
# Fetch extra results, post-filter by speaker substring (case-insensitive)
# Addresses CORE-04; workaround for $contains not working in metadata where filters
def _matches_speaker(stored: str, query: str) -> bool:
    return query.strip().lower() in stored.lower()

# In search tool:
fetch_n = min(limit * 4, 80) if speaker else limit
result = col.query(query_texts=[query], n_results=fetch_n, where=where_dict, include=["documents", "metadatas"])
items = list(zip(result["documents"][0], result["metadatas"][0]))
if speaker:
    items = [(d, m) for d, m in items if _matches_speaker(m.get("speaker_name", ""), speaker)]
items = items[:limit]
```

### get_talk Pattern

```python
# Fetch all paragraphs for a talk by integer talk_id, sort by paragraph_number
def _parse_talk_id(talk_id: str) -> int | None:
    """Extract integer from "talk_8820" or "8820"."""
    normalized = talk_id.strip().lower().replace("talk_", "")
    try:
        return int(normalized)
    except ValueError:
        return None

# In get_talk tool:
talk_num = _parse_talk_id(talk_id)
if talk_num is None:
    return f"Invalid talk_id format '{talk_id}'. Expected format: 'talk_8820' or '8820'."

paras_col = app.collections["paragraphs"]
result = paras_col.get(
    where={"talk_id": {"$eq": talk_num}},
    include=["documents", "metadatas"],
)
if not result["ids"]:
    return f"No paragraphs found for talk_id '{talk_id}'."

# Sort by paragraph_number, build output
sorted_rows = sorted(
    zip(result["documents"], result["metadatas"]),
    key=lambda x: int(x[1].get("paragraph_number", 0)),
)
```

### get_talk Header Retrieval

```python
# Get talk metadata for the header (speaker, title, conference, session)
talks_col = app.collections["talks"]
talk_result = talks_col.get(ids=[f"talk_{talk_num}"], include=["metadatas"])
if talk_result["metadatas"]:
    tm = talk_result["metadatas"][0]
    header = (
        f"Speaker: {tm.get('speaker_name', '')}\n"
        f"Title: {tm.get('title', '')}\n"
        f"Conference: {tm.get('conference_month', '')} {tm.get('conference_year', '')}\n"
        f"Session: {tm.get('session_description', '')}\n"
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 10 search via secondary lookup for speaker/title on paragraph results | Paragraph records enriched at load time (Phase 9.1) | 2026-04-01 | No secondary lookup needed in search tool |
| `$contains` metadata filter (assumed in CONTEXT.md) | Post-filter in Python (actual working pattern) | Research finding | Speaker filter logic is in tool code, not in ChromaDB where clause |

**Deprecated/outdated:**
- `$contains` in `where=` dict: Defined in type signature but returns 0 results in practice (chromadb 1.5.5). Use Python substring match instead.

## Open Questions

1. **Truncation for very long talks**
   - What we know: `get_talk` must return paragraphs sorted by `paragraph_number`. Talk 8820 has 15 paragraphs.
   - What's unclear: No data on maximum paragraph count per talk. A very long talk could produce a very large string.
   - Recommendation: Return all paragraphs (no truncation) — this is within Claude's Discretion. Add a stderr log with paragraph count. If needed, truncation can be added later.

2. **`get_talk` when only numeric ID passed**
   - What we know: D-12 says `talk_id` is a string like "talk_8820".
   - What's unclear: Whether Claude will sometimes pass just "8820".
   - Recommendation: Accept both formats — strip "talk_" prefix if present, parse int. This is defensive and costs nothing.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| ChromaDB | All tools | ✓ | 1.5.5 | — |
| Ollama (nomic-embed-text) | `search` (semantic query embeds the query text) | ✓ (checked at startup) | — | — |
| FastMCP / mcp | Tool registration | ✓ | 1.26.0 | — |
| `pytest-asyncio` | Testing async tools | ✗ | — | Test pure helper functions directly (sync); no async test runner needed |

**Missing dependencies with no fallback:** None — all required dependencies are available.

**Missing dependencies with fallback:**
- `pytest-asyncio`: Not installed. Async tool tests not needed — extract business logic into pure sync helper functions and test those. The `@mcp.tool()` decorator is just registration and does not need to be tested.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed) |
| Config file | none (default discovery) |
| Quick run command | `pipenv run py -m pytest tests/test_server.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORE-04 | `_matches_speaker("Jeffrey R. Holland", "Holland")` returns True | unit | `pipenv run py -m pytest tests/test_server.py::test_matches_speaker -x -q` | ❌ Wave 0 |
| CORE-04 | `_matches_speaker` is case-insensitive | unit | `pipenv run py -m pytest tests/test_server.py::test_matches_speaker_case_insensitive -x -q` | ❌ Wave 0 |
| CORE-05 | `_build_where_filter(year=2020, season=None)` returns `{"conference_year": {"$eq": 2020}}` | unit | `pipenv run py -m pytest tests/test_server.py::test_build_where_filter_year_only -x -q` | ❌ Wave 0 |
| CORE-05 | `_build_where_filter(year=2020, season="April")` returns `{"$and": [...]}` | unit | `pipenv run py -m pytest tests/test_server.py::test_build_where_filter_year_and_season -x -q` | ❌ Wave 0 |
| CORE-05 | `_build_where_filter(year=None, season=None)` returns `None` | unit | `pipenv run py -m pytest tests/test_server.py::test_build_where_filter_no_filters -x -q` | ❌ Wave 0 |
| CORE-06 | `search` tool rejects unknown collection name | unit | `pipenv run py -m pytest tests/test_server.py::test_search_invalid_collection -x -q` | ❌ Wave 0 |
| TOOL-01 | `search` calls `col.query()` with correct args | unit (mock) | `pipenv run py -m pytest tests/test_server.py::test_search_calls_query -x -q` | ❌ Wave 0 |
| TOOL-02 | `search` applies speaker post-filter correctly | unit | `pipenv run py -m pytest tests/test_server.py::test_search_speaker_filter -x -q` | ❌ Wave 0 |
| TOOL-03 | `_format_search_result` returns exactly 6 fields | unit | `pipenv run py -m pytest tests/test_server.py::test_format_search_result_fields -x -q` | ❌ Wave 0 |
| TOOL-03 | `_format_search_result` excludes pipeline fields | unit | `pipenv run py -m pytest tests/test_server.py::test_format_search_result_no_pipeline_fields -x -q` | ❌ Wave 0 |
| TOOL-04 | `_parse_talk_id("talk_8820")` returns 8820 | unit | `pipenv run py -m pytest tests/test_server.py::test_parse_talk_id -x -q` | ❌ Wave 0 |
| TOOL-04 | `_parse_talk_id("8820")` returns 8820 (bare int format) | unit | `pipenv run py -m pytest tests/test_server.py::test_parse_talk_id_bare -x -q` | ❌ Wave 0 |
| TOOL-04 | `get_talk` not-found returns readable error message | unit (mock) | `pipenv run py -m pytest tests/test_server.py::test_get_talk_not_found -x -q` | ❌ Wave 0 |
| TOOL-05 | Paragraph sort by `paragraph_number` is ascending | unit | `pipenv run py -m pytest tests/test_server.py::test_paragraph_sort_order -x -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/test_server.py -x -q`
- **Per wave merge:** `pipenv run py -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

All Phase 10 tests need to be added to `tests/test_server.py`. The existing 5 tests cover Phase 9 startup only. New tests follow the same pattern: import helper functions from `server`, call with inline data or mocked ChromaDB objects, assert outputs.

- [ ] `tests/test_server.py` — add test class `TestBuildWhereFilter` (CORE-05)
- [ ] `tests/test_server.py` — add test class `TestMatchesSpeaker` (CORE-04)
- [ ] `tests/test_server.py` — add test class `TestFormatSearchResult` (TOOL-03)
- [ ] `tests/test_server.py` — add test class `TestParseTalkId` (TOOL-04)
- [ ] `tests/test_server.py` — add test class `TestSearchTool` with mocked collections (TOOL-01, TOOL-02, CORE-06)
- [ ] `tests/test_server.py` — add test class `TestGetTalkTool` with mocked collections (TOOL-04, TOOL-05)

*(No new test files or frameworks needed — pytest is already installed and `tests/test_server.py` is the right home for server-level tests.)*

## Sources

### Primary (HIGH confidence)
- Verified live against `chromadb 1.5.5` — `$contains` metadata operator behavior, `$eq`, `$and`, `$in` operators, `query()` vs `get()` return shapes
- Verified live against `mcp 1.26.0` / FastMCP — `Context` class, `request_context.lifespan_context` field, `@mcp.tool()` decorator signature
- `server.py` (project codebase) — `AppContext`, `lifespan`, `CHROMADB_COLLECTION_NAMES`, established patterns
- `extractors/phase6_chromadb_loader.py` — paragraph metadata field list (confirmed `text` and `text_raw` are in metadata)
- Live ChromaDB database — confirmed paragraph count (202,175), enrichment fields present (`speaker_name` etc.), talk_id as int

### Secondary (MEDIUM confidence)
- ChromaDB `Where` type annotation (`chromadb.api.types.Where`) — shows `$contains` and `$not_contains` in the type signature, but live verification showed it returns 0 results for metadata fields

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified installed versions, no new dependencies
- Architecture: HIGH — all patterns verified against live ChromaDB and FastMCP instances
- Pitfalls: HIGH — `$contains` finding verified live; other pitfalls verified from code inspection of existing data shapes

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (chromadb and mcp are stable; `$contains` behavior unlikely to change without a major version bump)
