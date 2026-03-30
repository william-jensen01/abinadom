# Requirements: BYU Scripture Citation Index RAG System

**Defined:** 2026-03-30
**Milestone:** v2.0 MCP Server
**Core Value:** All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks and discourse, with full referential integrity between talks, paragraphs, citations, and footnotes.

## v2.0 Requirements

Requirements for the MCP Server milestone. Each maps to roadmap phases.

### Foundation

- [ ] **CORE-01**: Server resolves ChromaDB path to absolute at startup (prevents silent empty-DB creation when Claude Desktop spawns with unknown working directory)
- [ ] **CORE-02**: Server performs Ollama health check at startup and fails fast with a clear error if unreachable
- [ ] **CORE-03**: Server warms up all 4 ChromaDB collections at startup before accepting tool calls
- [ ] **CORE-04**: User can pass informal speaker names ("Holland", "Elder Holland") and server resolves to canonical form ("Jeffrey R. Holland")
- [ ] **CORE-05**: User can pass informal year/season values ("2020", "April 2020") and server normalizes to structured metadata filters
- [ ] **CORE-06**: User can pass collection aliases ("talks", "paragraphs", "citations", "footnotes") that resolve to internal ChromaDB collection names

### Tools

- [ ] **TOOL-01**: User can perform semantic search across any of the 4 collections with a natural language query
- [ ] **TOOL-02**: User can filter search results by speaker, year, conference season, and/or collection
- [ ] **TOOL-03**: Search returns readable snippet text (no internal pipeline fields), default 5 results, max 20
- [ ] **TOOL-04**: User can retrieve full ordered text of a talk by talk ID
- [ ] **TOOL-05**: `get_talk` returns paragraphs sorted by narrative position (position field)

### Integration

- [ ] **INTG-01**: MCP server runs via stdio transport; all logging goes to stderr only (no stdout pollution)
- [ ] **INTG-02**: User can connect to the MCP server from Claude Desktop via `claude_desktop_config.json` with absolute virtualenv path
- [ ] **INTG-03**: Claude engages with LDS content conversationally via a system prompt that establishes its role as an informed discussion partner

## Future Requirements

### Remote Access (Milestone 3)

- **RMOT-01**: User can connect to MCP server from Claude mobile app
- **RMOT-02**: Server accessible across machines (hosting, Tailscale, or VPS)
- **RMOT-03**: Auth tokens or equivalent for remote access security

### Expanded Content (Milestone 4+)

- **CONT-01**: Journal of Discourse content searchable
- **CONT-02**: Standard LDS scripture canon searchable (OT, NT, BOM, D&C, POGP)

## Out of Scope

| Feature | Reason |
|---------|--------|
| list/browse tool | 5,838 records cannot be paginated conversationally — semantic search covers it |
| Writes from MCP | Pipeline is the write path; MCP is read-only |
| HTTP transport | Single-user local use; stdio is simpler and sufficient |
| ChatGPT integration | Deferred — requires hosted server (Milestone 3) |
| `get_database_info` tool | Extra tokens every session — tool descriptions + normalizers cover discovery |
| Exact topic `where` filters | Topics stored as pipe-joined strings; semantic search handles topic queries |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 9 | Pending |
| CORE-02 | Phase 9 | Pending |
| CORE-03 | Phase 9 | Pending |
| CORE-04 | Phase 10 | Pending |
| CORE-05 | Phase 10 | Pending |
| CORE-06 | Phase 10 | Pending |
| TOOL-01 | Phase 10 | Pending |
| TOOL-02 | Phase 10 | Pending |
| TOOL-03 | Phase 10 | Pending |
| TOOL-04 | Phase 10 | Pending |
| TOOL-05 | Phase 10 | Pending |
| INTG-01 | Phase 9 | Pending |
| INTG-02 | Phase 11 | Pending |
| INTG-03 | Phase 11 | Pending |

**Coverage:**
- v2.0 requirements: 14 total
- Mapped to phases: 14 ✓
- Unmapped: 0

---
*Requirements defined: 2026-03-30*
*Last updated: 2026-03-30 — traceability filled after roadmap creation*
