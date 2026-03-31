# Phase 10: Tools & Normalization - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Working `search` and `get_talk` MCP tools added to `server.py`. `search` performs semantic query against ChromaDB with optional metadata filters (speaker, year, season, collection). `get_talk` retrieves full ordered talk content by ID. Both tools return clean, readable output — no internal pipeline fields. Speaker name resolution is offloaded to Claude; server handles contains-match filtering. No new infrastructure — tools are added to the existing FastMCP server from Phase 9.

**Note:** A gap phase (paragraph metadata enrichment) must be inserted before this phase executes. See Deferred Ideas.

</domain>

<decisions>
## Implementation Decisions

### Search Result Shape (TOOL-03)
- **D-01:** Every search result returns exactly 6 fields: `snippet` (the matched text), `speaker_name`, `title`, `conference_year`, `conference_month`, `talk_id`.
- **D-02:** Relevance/distance scores are omitted — they are internal ChromaDB implementation details with no conversational value.
- **D-03:** `talk_id` is included in every result to enable the search → disambiguate → `get_talk` flow. Claude uses it to call `get_talk` after the user selects a candidate talk. It is not displayed to the user.
- **D-04:** No pipeline-internal fields are exposed: no `paragraph_id`, `speaker_id`, `conference_id`, `word_count`, `source_type`, `text_raw`, `extraction_*`, `corpus`, `data_aid`, `uri_*`.

### Speaker Normalization (CORE-04)
- **D-05:** Speaker normalization is offloaded to Claude. Claude is expected to pass a canonical or close-to-canonical speaker name (e.g., "Jeffrey R. Holland", "Holland"). No server-side lookup table or startup query is built.
- **D-06:** The server applies a **case-insensitive contains match** on `speaker_name` metadata. Input "Holland" matches stored value "Jeffrey R. Holland". This handles natural variation in Claude's output without normalization code.

### Date/Season Normalization (CORE-05)
- **D-07:** Date normalization is also offloaded to Claude. Claude passes `year` (int) and `season` ("April" or "October") as structured parameters after interpreting natural language input ("2020", "April 2020", "last spring conference"). Server applies exact filters on `conference_year` and `conference_month`.

### Collection Alias Resolution (CORE-06)
- **D-08:** The `search` tool exposes user-facing aliases ("talks", "paragraphs", "citations", "footnotes") that map directly to `CHROMADB_COLLECTION_NAMES` keys. No separate resolution layer needed — the aliases ARE the keys.

### `search` Tool Interface (TOOL-01, TOOL-02)
- **D-09:** Single `search` tool with optional `collection` parameter — not separate per-collection tools. Keeps tool description tokens minimal (explicit project requirement).
- **D-10:** Default collection is `paragraphs` (202,175 records; returns actual passage text for conversational queries). Claude passes `collection="talks"` for talk discovery, `collection="citations"` for scripture reference queries.
- **D-11:** Parameters: `query` (required), `speaker` (optional), `year` (optional int), `season` (optional: "April" | "October"), `collection` (optional, default "paragraphs"), `limit` (optional int, default 5, max 20).

### `get_talk` Tool Interface (TOOL-04, TOOL-05)
- **D-12:** `get_talk` accepts `talk_id` (string, e.g., "talk_8820"). Primary — deterministic retrieval, no ambiguity.
- **D-13:** Discovery and disambiguation are handled by `search` on the `talks` collection, not by `get_talk`. If a user asks for "Elder Holland's talk from April 2013" without a title, Claude calls `search` first to get candidates with `talk_id`s, presents options, then calls `get_talk` with the selected ID.

### `get_talk` Return Format (TOOL-04, TOOL-05)
- **D-14:** Output is a structured header followed by ordered paragraph body:
  ```
  Speaker: [speaker_name]
  Title: [title]
  Conference: [conference_month] [conference_year]
  Session: [session_description]

  [paragraph 1 text]

  [paragraph 2 text]
  ...
  ```
- **D-15:** Paragraphs are sorted by `paragraph_number` (narrative sequence, TOOL-05). No pipeline fields (paragraph_id, source_type, etc.) in output.

### Claude's Discretion
- Exact ChromaDB `where` filter construction for contains-match on speaker_name (e.g., using `$contains` operator or post-filter)
- How to handle `get_talk` when `talk_id` is not found (error message wording)
- Whether to truncate very long talks or return all paragraphs
- Internal batching of talk metadata enrichment lookup per search call

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Requirements
- `.planning/REQUIREMENTS.md` — CORE-04, CORE-05, CORE-06, TOOL-01 through TOOL-05 are the seven requirements for this phase

### Existing Server Foundation
- `server.py` — FastMCP server with `AppContext` (client + collections dict), lifespan startup, `@mcp.tool()` decorator pattern. Tools are added here.

### Config
- `config/pipeline_config.py` — `CHROMADB_COLLECTION_NAMES` dict (keys: "talks", "paragraphs", "citations", "footnotes") — these are the valid `collection` parameter values for `search`

### Data Models (for field reference)
- `models/talk_metadata.py` — `TalkMetadata` fields: what's stored in the talks collection
- `models/paragraph_data.py` — `ParagraphData` fields: what's stored in the paragraphs collection (note: does NOT include speaker_name, title, conference_year, conference_month — see gap phase in Deferred Ideas)

### Phase 9 Context
- `.planning/phases/09-server-foundation/09-CONTEXT.md` — established patterns: FastMCP lifespan, AppContext, collection loading, stderr logging

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `server.py:AppContext` — `collections` dict already maps logical keys to live `chromadb.Collection` objects. Tools access collections via `mcp.get_context().request_context.lifespan_context`.
- `config/pipeline_config.py:CHROMADB_COLLECTION_NAMES` — the 4 collection name strings; use as the canonical mapping for the `collection` parameter.

### Established Patterns
- Tool registration: `@mcp.tool()` decorator on async functions, return value is the tool output string
- All logging to `sys.stderr` per INTG-01
- `get_collection()` (not `get_or_create_collection`) — fail-fast pattern from Phase 9 continues

### Integration Points
- Tools live in `server.py` alongside the lifespan and `AppContext` definition
- `chromadb.Collection.query()` — semantic search: accepts `query_texts`, `n_results`, `where` (metadata filter dict)
- `chromadb.Collection.get()` — direct ID lookup: accepts `ids` list — used for talk metadata enrichment lookup after paragraph search

### ChromaDB Where Filter Notes
- Metadata filters use ChromaDB's `where` dict syntax: `{"speaker_name": {"$contains": "Holland"}}` — verify operator availability in installed chromadb version
- Exact match: `{"conference_year": 2013}`, `{"conference_month": "April"}`
- Combined filters: `{"$and": [{"conference_year": 2013}, {"conference_month": "April"}]}`

</code_context>

<specifics>
## Specific Ideas

- The user explicitly wants speaker normalization offloaded to Claude — this is a deliberate architectural choice, not a shortcut. Do not add server-side lookup tables.
- The search → disambiguate → get_talk flow was explicitly validated: Claude uses `search(collection="talks")` to find candidate talks, presents options to user, then calls `get_talk(talk_id=...)` with the selected ID.
- Result shape was carefully considered: `snippet + speaker_name + title + conference_year + conference_month + talk_id` — exactly these 6 fields, nothing more.

</specifics>

<deferred>
## Deferred Ideas

### Gap Phase: Paragraph Metadata Enrichment (INSERT BEFORE PHASE 10)
The `paragraphs` ChromaDB collection does not store `speaker_name`, `title`, `conference_year`, or `conference_month` — these fields only exist in the `talks` collection. This is a design oversight identified during Phase 10 discussion.

**Required fix:** Add a gap phase (e.g., 9.5) that enriches paragraph records in ChromaDB with talk-level metadata. Options:
- Targeted ChromaDB migration script: query talks collection, update each talk's paragraph records' metadata fields
- Re-run Phase 6 after updating `ParagraphData` model and `prepare_paragraph_records()` to accept `TalkMetadata`

**Impact:** Until this is resolved, paragraph search results cannot return `speaker_name`/`title`/`conference_year`/`conference_month` without a secondary lookup. Phase 10 planning should either address this gap first or use the secondary lookup as a temporary bridge.

**Suggested action:** Run `/gsd:insert-phase` to add this as Phase 9.5 before proceeding to Phase 10 planning.

</deferred>

---

*Phase: 10-tools-normalization*
*Context gathered: 2026-03-31*
