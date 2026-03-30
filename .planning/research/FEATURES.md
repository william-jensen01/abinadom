# MCP Feature Research — Tool Design Patterns

## Table Stakes (Must Have)

- `search` tool — semantic query + optional `where` metadata filter + `collection` parameter
- `get_talk` tool — full ordered paragraphs by talk ID
- Readable prose text output (not raw JSON/internal fields)
- `isError` handling on tool failure
- Claude Desktop config entry wiring server

## Differentiators

- **Server-side fuzzy normalization** — user types "Nelson" → server resolves to "Russell M. Nelson" before ChromaDB filter. Same for conference ("April 2020" → year=2020, season=April)
- **`where` filter on `search`** — essential for "what did Eyring teach about X?" style queries. Without it, semantic search returns results regardless of speaker/year
- **Strip internal pipeline fields** — do NOT expose `extraction_timestamp`, `parse_pattern`, `text_raw`, `source_type` etc. to Claude. Return only content-relevant fields
- **Collection-aware results** — search returns different fields per collection (talks: title/speaker/year; paragraphs: text/position/talk_id; citations: book/chapter/verse/context)

## Anti-Features (Explicitly Excluded)

- No list/browse tool — 5,838 records cannot be paginated conversationally
- No writes from MCP — pipeline is the write path, MCP is read-only
- No HTTP transport in v2.0 — stdio only for local Claude Desktop
- No pagination on get_talk — return full talk, let Claude manage context

## Token Budget

- Default `n_results=5`, cap at 20
- ~260 tokens per result at default settings
- 5 results ≈ 1,300 tokens — acceptable overhead
- Return text blocks, not JSON blobs

## Hard Dependencies

- **Ollama must be running** with `nomic-embed-text` — same embedding model used during pipeline load. Wrong model = nonsensical similarity scores. Server should fail fast with a clear error if Ollama unavailable.

## Collection Field Map (What to Expose)

| Collection | Expose | Strip |
|------------|--------|-------|
| talks | talk_id, title, speaker, year, conference, topics, preview | extraction_timestamp, raw pipeline fields |
| paragraphs | paragraph_id, talk_id, text, position, speaker, year | text_raw, source_type, parse_pattern |
| citations | citation_id, paragraph_id, talk_id, book, chapter, verses, context_window | extraction_timestamp, internal parse fields |
| footnotes | footnote_id, talk_id, text, reference_type, context_window | internal fields |
