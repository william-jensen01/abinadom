# Roadmap — BYU Scripture Citation Index RAG System

## Milestones

- ✅ **v1.0 General Conference Pipeline** — Phases 1–8 (shipped 2026-03-27)
- 📋 **v2.0 MCP Server** — Phases 9–11 (planned)

## Phases

<details>
<summary>✅ v1.0 General Conference Pipeline (Phases 1–8) — SHIPPED 2026-03-27</summary>

- [x] Phase 1: DB Enrichment (5/5 plans) — completed 2026-03-20
- [x] Phase 2: Code Quality (2/2 plans) — completed 2026-03-21
- [x] Phase 3: Bug Audit & Fixes (3/3 plans) — completed 2026-03-22
- [x] Phase 4: Test Coverage (3/3 plans) — completed 2026-03-24
- [x] Phase 5: ChromaDB Loader (3/3 plans) — completed 2026-03-25
- [x] Phase 6: Pipeline Orchestrator (2/2 plans) — completed 2026-03-26
- [x] Phase 7: Full Run & Verification (2/2 plans) — completed 2026-03-27
- [x] Phase 8: Topic Metadata (1/1 plan) — completed 2026-03-27

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

### v2.0 MCP Server (Planned)

**Milestone Goal:** Expose ChromaDB via a local MCP server so Claude Desktop can search by meaning, read full talks, and engage conversationally with General Conference content.

- [ ] **Phase 9: Server Foundation** — Reliable server startup: absolute path resolution, Ollama health check, collection warmup, stdio transport
- [ ] **Phase 10: Tools & Normalization** — Working `search` and `get_talk` tools with speaker/date/collection normalizers and clean output
- [ ] **Phase 11: Claude Desktop Integration** — End-to-end connection: Claude Desktop config wired and system prompt established

## Phase Details

### Phase 9: Server Foundation
**Goal**: The MCP server starts reliably, warms up all collections, and fails fast with actionable errors when dependencies are missing
**Depends on**: Phase 8 (ChromaDB populated and verified)
**Requirements**: CORE-01, CORE-02, CORE-03, INTG-01
**Success Criteria** (what must be TRUE):
  1. Server launched from any working directory finds ChromaDB collections (no silent empty-DB creation)
  2. Server launched without Ollama running exits immediately with a clear error message (not a cryptic stack trace)
  3. Server launched successfully has all 4 ChromaDB collections loaded before any tool call arrives
  4. All server log output goes to stderr; stdout carries only MCP protocol messages
**Plans:** 0/1 plans executed
Plans:
- [ ] 09-01-PLAN.md — Install mcp SDK, create server.py with startup validation, unit tests

### Phase 09.1: Paragraph Metadata Enrichment (INSERTED)

**Goal:** Enrich paragraph ChromaDB records with talk-level metadata (speaker_name, title, conference_year, conference_month) so Phase 10 search results return the full 6-field shape without secondary lookup
**Requirements**: Unblocks CORE-04, TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05
**Depends on:** Phase 9
**Plans:** 1/1 plans complete

Plans:
- [ ] 09.1-01-PLAN.md — Enrich prepare_paragraph_records with talk metadata injection, add VER-06

### Phase 10: Tools & Normalization
**Goal**: Users can perform semantic search and retrieve full talks through tools that accept natural language inputs and return clean, readable results
**Depends on**: Phase 9
**Requirements**: CORE-04, CORE-05, CORE-06, TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05
**Success Criteria** (what must be TRUE):
  1. User can issue a natural-language query and receive relevant results from any of the 4 collections
  2. User can pass an informal speaker name ("Holland", "Elder Holland") and get results attributed to the correct speaker
  3. User can pass an informal date ("2020", "April 2020") and get results filtered to the right conference
  4. User can retrieve the full ordered text of a talk by ID, with paragraphs in narrative sequence
  5. Search results contain readable snippet text only — no internal pipeline fields exposed
**Plans:** 1/2 plans executed
Plans:
- [x] 10-01-PLAN.md — TDD helper functions: _build_where_filter, _matches_speaker, _format_search_result, _parse_talk_id
- [ ] 10-02-PLAN.md — Implement search and get_talk MCP tools with integration tests

### Phase 11: Claude Desktop Integration
**Goal**: Claude Desktop is connected to the MCP server and engages with LDS content as an informed discussion partner
**Depends on**: Phase 10
**Requirements**: INTG-02, INTG-03
**Success Criteria** (what must be TRUE):
  1. Claude Desktop connects to the MCP server using an absolute virtualenv path in `claude_desktop_config.json` without errors
  2. Claude responds to LDS content questions conversationally, drawing on the `search` and `get_talk` tools without needing prompting from the user
  3. System prompt establishes Claude's role so that it synthesizes and discusses content rather than merely returning raw tool output
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. DB Enrichment | v1.0 | 5/5 | Complete | 2026-03-20 |
| 2. Code Quality | v1.0 | 2/2 | Complete | 2026-03-21 |
| 3. Bug Audit & Fixes | v1.0 | 3/3 | Complete | 2026-03-22 |
| 4. Test Coverage | v1.0 | 3/3 | Complete | 2026-03-24 |
| 5. ChromaDB Loader | v1.0 | 3/3 | Complete | 2026-03-25 |
| 6. Pipeline Orchestrator | v1.0 | 2/2 | Complete | 2026-03-26 |
| 7. Full Run & Verification | v1.0 | 2/2 | Complete | 2026-03-27 |
| 8. Topic Metadata | v1.0 | 1/1 | Complete | 2026-03-27 |
| 9. Server Foundation | v2.0 | 0/1 | Planned    |  |
| 9.1 Paragraph Metadata Enrichment | v2.0 | 0/1 | Planned | - |
| 10. Tools & Normalization | v2.0 | 1/2 | In Progress|  |
| 11. Claude Desktop Integration | v2.0 | 0/? | Not started | - |
