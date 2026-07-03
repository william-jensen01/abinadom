# Roadmap — BYU Scripture Citation Index RAG System

## Milestones

- ✅ **v1.0 General Conference Pipeline** — Phases 1–8 (shipped 2026-03-27)
- ✅ **v2.0 MCP Server** — Phases 9–12 (shipped 2026-04-03)
- ✅ **v3.0 Remote MCP** — Phases 13–19 (shipped 2026-04-17)
- ✅ **v4.0 Vector DB Migration** — Phases 20–24 (shipped 2026-07-02)
- 🚧 **v5.0 Scriptures** — Phases 25–29 (in progress)

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

<details>
<summary>✅ v2.0 MCP Server (Phases 9–12) — SHIPPED 2026-04-03</summary>

- [x] Phase 9: Server Foundation (1/1 plans) — completed 2026-04-02
- [x] Phase 9.1: Paragraph Metadata Enrichment (1/1 plans) — completed 2026-04-02
- [x] Phase 10: Tools & Normalization (2/2 plans) — completed 2026-04-02
- [x] Phase 11: Claude Desktop Integration (2/2 plans) — completed 2026-04-03
- [x] Phase 12: Tech Debt & Validation Cleanup (1/1 plans) — completed 2026-04-03

Full details: `.planning/milestones/v2.0-ROADMAP.md`

</details>

<details>
<summary>✅ v3.0 Remote MCP (Phases 13–19) — SHIPPED 2026-04-17</summary>

- [x] Phase 13: HTTP Transport (2/2 plans) — completed 2026-04-03
- [x] Phase 14: Auth Module (3/3 plans) — completed 2026-04-04
- [x] Phase 15: Docker Compose & Config (2/2 plans) — completed 2026-04-04
- [x] Phase 16: Caddy & Cloudflare Tunnel (2/2 plans) — completed 2026-04-05
- [x] Phase 16.1: OAuth 2.0 for Claude Desktop (5/5 plans) — completed 2026-04-13
- [x] Phase 16.2: FastAPI MCP Protocol Rewrite (2/2 plans) — completed 2026-04-09
- [x] Phase 17: Operator Docs (4/4 plans) — completed 2026-04-13
- [x] Phase 18: Cleanup of Previous Phases (3/3 plans) — completed 2026-04-14
- [x] Phase 19: FastMCP + ScaleKit Server (3/3 plans) — completed 2026-04-16

Full details: `.planning/milestones/v3.0-ROADMAP.md`

</details>

<details>
<summary>✅ v4.0 Vector DB Migration (Phases 20–24) — SHIPPED 2026-07-02</summary>

- [x] Phase 20: Benchmark Infrastructure & Framework (4/4 plans) — completed 2026-04-20
- [x] Phase 21: DB Loaders (5/5 plans) — completed 2026-04-22
- [x] Phase 22: Benchmark Runner (3/3 plans) — completed 2026-04-24
- [x] Phase 22.1: Address Recall@k = 0.0 Bug (3/3 plans) — completed 2026-04-26
- [x] Phase 22.2: Optimize Benchmark Loaders for Efficiency (4/4 plans) — completed 2026-05-06
- [x] Phase 23: Benchmark Execution & Decision (2/2 plans) — completed 2026-05-08
- [x] Phase 24: Production Migration (9/9 plans) — completed 2026-07-02

Full details: `.planning/milestones/v4.0-ROADMAP.md`

</details>

### 🚧 v5.0 Scriptures (In Progress)

**Milestone Goal:** Make the LDS scripture canon a first-class searchable corpus alongside conference talks — semantic + hybrid search over verse text, exact-reference retrieval, and grounded composition with the existing talk tools. Sourced entirely from `db/core.52.db`.

- [ ] **Phase 25: Data Model, Book Resolver & Extraction** - Turn `core.52.db` rows into clean, canonical `ScriptureVerse` objects in memory
- [ ] **Phase 26: Windowing & Validation** - Compute the embed string and catch data defects before load
- [ ] **Phase 27: Loader, Schema & Orchestrator** - Embed and upsert verses into Weaviate, idempotently and resumably
- [ ] **Phase 28: MCP Tool Surface** - Expose scripture retrieval to LLM clients
- [ ] **Phase 29: Full Load & Post-Load Verification** - Load the complete corpus and prove it with SCR-01…06

## Phase Details

### Phase 25: Data Model, Book Resolver & Extraction
**Goal**: Clean, canonical `ScriptureVerse` objects are producible from `core.52.db` in memory — no live stack required
**Depends on**: Nothing (first v5.0 phase; shares `html_parsing_utils` and project patterns from Phase 24)
**Requirements**: EXT-01, EXT-02, EXT-03, EXT-04, EXT-05, RES-01
**Success Criteria** (what must be TRUE):
  1. The extractor produces exactly 41,996 canonical (`standard`) verse objects — all 10 NULL-`Verse` front-matter rows are excluded and no `E`-flag rows appear in output
  2. Every `book` field uses canonical digit form: "First Nephi" → "1 Nephi", "Sections" → "Doctrine and Covenants", em-dash mojibake in `FullName`/`CiteAbbr` is repaired
  3. Every verse carries a derived `reference` in CiteAbbr format ("1 Ne. 3:7", "D&C 45:32", "Jude 1:3") and a `variant` of "standard" or "jst"
  4. `book_resolver.resolve()` accepts any common input form (FullName, Abbr, CiteAbbr, word-ordinals like "First Nephi", "D&C", "Doctrine and Covenants") and returns the canonical digit-form book name
  5. Unit tests are green for exclusion logic, digit-form normalization, D&C `Sections` override, CiteAbbr reference format, and all resolver alias forms
**Plans**: TBD

### Phase 26: Windowing & Validation
**Goal**: Every verse has a correctly bounded embed string and all data defects are caught before the live stack is touched
**Depends on**: Phase 25
**Requirements**: EMB-01, EMB-02, VAL-01, VAL-02
**Success Criteria** (what must be TRUE):
  1. `standard` verses have a `context_window` of reference prefix + sequence-adjacent, chapter-clamped neighbors — no neighbor from a different chapter or a JST row ever appears
  2. `jst` verses have a `context_window` of reference prefix + own text only (no neighbors), and their raw `text` is stored separately
  3. Validation rejects verses with empty/HTML-contaminated `text`, `chapter < 1`, `verse < 1`, or `variant` not in {standard, jst}; no NULL-`Verse` row survives to this stage
  4. Validation fires gap/non-monotonic warnings on real defects in `standard` verse sequences and stays silent on normal JST sparsity (non-contiguous `J`/`F` groups)
**Plans**: TBD

### Phase 27: Loader, Schema & Orchestrator
**Goal**: Scripture verses are idempotently loadable into Weaviate with correct vectors, schema, and resume support
**Depends on**: Phase 26
**Requirements**: LOAD-01, LOAD-02, LOAD-03
**Success Criteria** (what must be TRUE):
  1. Loading a small subset (e.g. a single book) produces Weaviate `ScriptureVerses` objects with non-null vectors and all properties correctly populated
  2. The `ScriptureVerses` schema is created idempotently — running schema-ensure on an existing collection does not error or corrupt data
  3. Re-running the orchestrator over the same subset is a no-op (resume keys on `verse_exists`; already-loaded verses are skipped)
  4. Running with `--force` re-embeds and overwrites existing objects; the README documents that radius/model config changes require `--force`
**Plans**: TBD

### Phase 28: MCP Tool Surface
**Goal**: LLM clients can retrieve exact scripture verses and run semantic search over the canon
**Depends on**: Phase 27
**Requirements**: TOOL-01, TOOL-02, TOOL-03
**Success Criteria** (what must be TRUE):
  1. `get_verse("Alma", 32, 21)` returns the correct verse; `get_verse("Alma", 32, 26, 43)` returns an ordered range; `get_verse("Alma", 32)` returns the whole chapter in order — no Ollama call is made
  2. Single-chapter shorthand works: `get_verse("Jude", 3)` resolves to Jude 1:3; `variant="both"` returns canonical and JST texts for the same reference ordered by verse then variant
  3. `search` over `scripture_verses` returns canonical-only results by default; `book`, `volume`, `chapter`, and `variant` filters narrow results correctly; book/chapter inputs are normalized through `book_resolver`
  4. `corpus_stats` over `scripture_verses` returns correct counts groupable by `volume`, `book`, or `variant` (e.g. standard vs JST split)
**Plans**: TBD

### Phase 29: Full Load & Post-Load Verification
**Goal**: The complete S+J+F corpus is in Weaviate and all six verification checks pass
**Depends on**: Phase 28
**Requirements**: VRFY-01, VRFY-02
**Success Criteria** (what must be TRUE):
  1. SCR-01: total object count ≈ 41,996 canonical + correct JST count; SCR-02: all 5 volumes (OT, NT, BoM, D&C, PoGP) are present
  2. SCR-03: spot-check verses (John 3:16, Alma 32:21, 1 Nephi 3:7) are retrievable with correct text via `get_verse`
  3. SCR-04 + SCR-05: `variant` distribution matches DB counts; no empty `text` or missing `context_window` fields
  4. SCR-06: semantic search for "faith" and "charity" returns thematically on-target verses
  5. CLAUDE.md Project Structure Index is updated with all new files from Phases 25–29
**Plans**: TBD

## Progress Table

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1–8. General Conference Pipeline | v1.0 | 21/21 | Complete | 2026-03-27 |
| 9–12. MCP Server | v2.0 | 7/7 | Complete | 2026-04-03 |
| 13–19. Remote MCP | v3.0 | 26/26 | Complete | 2026-04-17 |
| 20. Benchmark Infrastructure & Framework | v4.0 | 4/4 | Complete | 2026-04-20 |
| 21. DB Loaders | v4.0 | 5/5 | Complete | 2026-04-22 |
| 22. Benchmark Runner | v4.0 | 3/3 | Complete | 2026-04-24 |
| 22.1. Address Recall@k = 0.0 Bug | v4.0 | 3/3 | Complete | 2026-04-26 |
| 22.2. Optimize Benchmark Loaders for Efficiency | v4.0 | 4/4 | Complete | 2026-05-06 |
| 23. Benchmark Execution & Decision | v4.0 | 2/2 | Complete | 2026-05-08 |
| 24. Production Migration | v4.0 | 9/9 | Complete | 2026-07-02 |
| 25. Data Model, Book Resolver & Extraction | v5.0 | 0/TBD | Not started | - |
| 26. Windowing & Validation | v5.0 | 0/TBD | Not started | - |
| 27. Loader, Schema & Orchestrator | v5.0 | 0/TBD | Not started | - |
| 28. MCP Tool Surface | v5.0 | 0/TBD | Not started | - |
| 29. Full Load & Post-Load Verification | v5.0 | 0/TBD | Not started | - |
