# Retrospective — BYU Scripture Citation Index RAG System

---

## Milestone: v1.0 — General Conference Pipeline

**Shipped:** 2026-03-27
**Phases:** 8 | **Plans:** 21 | **Duration:** 9 days (2026-03-19 → 2026-03-27)

### What Was Built

- `talk_metadata` table DDL, 5 migrated backfill scripts, Church API preview fetcher (4,006 entries), Phase 1 LEFT JOIN enrichment overlay
- `config/pipeline_config.py` centralizing all constants; logging standardized; root scripts relocated; duplicate cache manager removed
- 15 Phase 2 + 4 extractor bugs fixed at root cause; 52-talk audit with zero additional bugs; regression tests with `BUG-NN` docstrings
- E2E integration tests (5 talks × all phases), schema validation gate (`SchemaError`), Phase 1 edge cases, Phase 5 adversarial inputs
- Phase 6 ChromaDB loader: 4-collection transformation, annotation paragraph split, dependency-ordered batch insertion, verification report
- `scripts/run_pipeline.py` orchestrator: skip-if-processed, `--force`, 1000-talk write buffer
- 5,838 GC talks fully processed: 5,838 talks / 202,175 paragraphs / 67,307 citations / 25,608 footnotes in ChromaDB — all VER checks passed
- Topic metadata enrichment: `TalkMetadata.topics: List[str]`, GROUP_CONCAT subquery, Phase 6 document text and ChromaDB metadata, 12 tests

### What Worked

- **DB enrichment first** — restructuring `talk_metadata` before any pipeline work meant Phase 1 was clean before other phases touched it
- **Bug-audit before Phase 6** — finding and fixing 15 bugs before ChromaDB load prevented bad data from entering the vector store
- **Sequential dependency ordering** — each phase depending on the previous kept scope clean and rework minimal
- **52-talk audit** — running the audit script against a curated sample gave high confidence before the full 5,838-talk run
- **Annotation paragraph three-way split** — excluded from paragraphs collection, text folded into talk metadata, citations preserved — elegant design decision that held up perfectly

### What Was Inefficient

- ROADMAP.md Progress table wasn't kept in sync during execution — all requirements stayed "Pending" throughout; the archive required manual traceability reconstruction
- Some phase SUMMARY.md files used inconsistent schemas (some YAML frontmatter, some ad hoc headers) making automated one-liner extraction unreliable
- Quick tasks (3 hot-fixes mid-milestone) interrupted phase flow — could be batched or deferred more aggressively

### Patterns Established

- `pipenv run py` is the required Python invocation; `encoding='utf-8'` needed for all file reads on Windows cp1252
- ChromaDB `EphemeralClient` is a singleton — tests need `fresh_client` fixture that deletes collections between runs
- No `include=['ids']` param in ChromaDB skip check (raises `ValueError`) — use `.get()` without include param
- `GROUP_CONCAT` with pipe delimiter (`|`) aligns with `_flatten_metadata` pipe-join convention for `List[str]` fields
- `logging.basicConfig` belongs only in orchestrator/caller — extractors use `logging.getLogger(__name__)` only

### Key Lessons

- Trust the verification script — running `verify_pipeline.py` after the full run surfaced the VER-05 topics check gap immediately
- Annotation paragraphs need special handling at every phase boundary — document this decision prominently for Milestone 2
- Schema validation at startup (lazy per `Database` instance) is the right pattern for fail-fast without breaking test fixtures
- Topic metadata extension (Phase 8) was a clean add-on with zero rework — shows the layered architecture absorbed new requirements well

### Cost Observations

- Model mix: balanced profile (sonnet-heavy with occasional opus for planning)
- Sessions: ~10 sessions over 9 days
- Notable: Phases 3 and 6 were the most expensive (bug-hunting and orchestrator architecture); Phase 8 was the most efficient (1 plan, clean extension)

---

## Milestone: v2.0 — MCP Server

**Shipped:** 2026-04-03
**Phases:** 5 (9, 9.1, 10, 11, 12) | **Plans:** 7 | **Duration:** 2 days (2026-04-02 → 2026-04-03)

### What Was Built

- FastMCP server with startup validation: absolute ChromaDB path resolution, Ollama health check via live embedding, 4-collection warmup using `get_collection()` guard
- Paragraph metadata denormalized into ChromaDB records at load time (speaker_name, title, conference_year, conference_month) — Phase 9.1 inserted when Phase 10 planning revealed the gap
- Four pure helper functions TDD-tested; `search` and `get_talk` MCP tools wired to ChromaDB; 38 server tests green
- OLLAMA_URL env var, FastMCP `mcp.instructions`, tool docstring hints for collection selection and search-first workflow
- Claude Desktop config template + adaptive system prompt — end-to-end verified with proactive tool use and conversational synthesis
- All 4 phase VALIDATION.md files Nyquist-compliant; OLLAMA_URL consolidated to single source of truth

### What Worked

- **Gap insertion mid-milestone** — discovering the paragraph metadata gap during Phase 10 planning, inserting Phase 9.1 immediately, and not trying to patch Phase 10 retroactively kept the plan clean
- **TDD for helper functions first** — Phase 10 Plan 01 (pure helpers) before Plan 02 (MCP tools) made integration testing trivial; helpers were already proven correct
- **Phase 12 tech debt cleanup** — running Nyquist validation and closing SUMMARY frontmatter gaps before archival meant no residual debt carried into v3.0
- **FastMCP lifespan pattern** — startup validation inside `@asynccontextmanager` ensures all dependencies are checked before the first tool call; error messages are actionable

### What Was Inefficient

- Worktree environment required `pipenv install` + `pipenv install --dev` before tests could run in Phase 12 — environment setup friction added time
- The v2.0-MILESTONE-AUDIT.md was generated before Phase 12 existed; audit status was `tech_debt` rather than `passed`, requiring a judgment call to proceed (Phase 12 was specifically created to address it)
- ROADMAP.md checkbox states lagged behind actual completion during execution — required manual correction notes in the audit report

### Patterns Established

- Speaker filtering as Python post-filter (not ChromaDB `where`) — ChromaDB 1.5.5 metadata string filters are silently broken; fetch 4× limit to compensate
- `get_collection()` not `get_or_create_collection()` as startup guard — prevents silent empty-DB creation when cwd is unknown
- Decimal phase insertion (N.1) when a gap is found mid-planning — cleaner than retrofitting existing phase scope
- Two-layer MCP prompting: `mcp.instructions` for tool-level hints, `config/SYSTEM_PROMPT.md` for persona — both layers needed for conversational behavior

### Key Lessons

- Paragraph-level metadata denormalization at load time is essential for token-efficient MCP tools — a secondary lookup per search result would double ChromaDB calls and bloat context
- Claude Desktop config requires absolute virtualenv Python path as the `command` field — relative paths fail silently when Claude Desktop spawns with unknown cwd
- Nyquist validation is worth running before milestone archival — it surfaces documentation gaps that are cheap to fix now and expensive to reconstruct later
- A `tech_debt` audit status is not a blocker if a Phase N+1 is scoped to close all items before archival

### Cost Observations

- Model mix: balanced profile (sonnet for execution, opus for planning)
- Sessions: ~3 sessions over 2 days
- Notable: Milestone 2 was dramatically faster than Milestone 1 (2 days vs 9 days) — pipeline foundation meant no data wrangling; MCP layer was purely additive

---

## Milestone: v3.0 — Remote MCP

**Shipped:** 2026-04-17
**Phases:** 9 (13, 14, 15, 16, 16.1, 16.2, 17, 18, 19) | **Plans:** 26 | **Duration:** 14 days (2026-04-03 → 2026-04-17)

### What Was Built

- Streamable HTTP transport replacing stdio; `MCP_HOST`/`MCP_PORT` env vars; `GET /health` with live Ollama + ChromaDB checks
- Bearer token auth module (KeyStore ABC, SqliteKeyStore, BearerAuthMiddleware, manage_keys.py CLI) — later replaced by OAuth
- Docker Compose deployment: Dockerfile (python:3.12-slim), docker-compose.yml (bind mounts, healthcheck), .env.example
- Caddy + cloudflared infra Compose stack: TLS termination and stable public HTTPS URL via Cloudflare Tunnel
- OAuth 2.1 convergence across 4 phases (Auth0 JWKSVerifier → FastAPI JSON-RPC dispatcher → ScaleKit built-in provider)
- Operator docs: connection guide, self-deploy guide, root README entry point
- Dead code cleanup: SqliteKeyStore, BearerAuthMiddleware, manage_keys.py, static bearer token path all removed in Phase 18
- Native FastMCP 3.2.4 server with two-mode ScalekitProvider auth (local passthrough / remote OAuth); 449 tests green; FastAPI removed

### What Worked

- **Two-mode auth pattern** — checking SCALEKIT_ env vars at startup to select auth mode was a clean mental model; local dev needs zero config, production is fully locked down
- **infra/ as separate Compose stack** — decoupling proxy (Caddy + cloudflared) from app (mcp-server) meant each could be restarted independently; external Docker network pattern held up perfectly
- **ScaleKit built-in provider** — once discovered, replaced hundreds of lines of manual JWT wiring with a few constructor params; the right abstraction was worth waiting for
- **Phase 18 dead code cleanup** — deleting the entire static bearer token path (4 files) before archival improved test clarity dramatically and removed a future maintenance burden

### What Was Inefficient

- **Auth strategy pivots** — four distinct approaches tried before ScaleKit (Auth0 JWKSVerifier, manual JWT, mcpauth resource-server mode, FastAPI JSON-RPC dispatcher) generated significant rework across Phases 16.1 and 16.2
- **Phase 16.2 FastAPI rewrite was superseded** — the full FastAPI + JSON-RPC dispatcher (Phase 16.2) was rendered obsolete by the FastMCP + ScaleKit native approach (Phase 19); ~2 phases of work were thrown away
- **Static bearer tokens (Phase 14) fully deleted (Phase 18)** — implementing then removing the entire SqliteKeyStore auth path was a direction change that could have been avoided with earlier OAuth research

### Patterns Established

- Two-mode server: `auth=None` when SCALEKIT_ vars absent, `ScalekitProvider(...)` when present — single binary, two operational modes
- `DebugTokenVerifier` for local testing without ScaleKit credentials — test infrastructure mirrors production auth surface
- infra/ Compose stack owns the `proxy` Docker network; app Compose stack joins as `external: true` — clean multi-stack pattern
- Delete dead auth code before milestone archival — never carry superseded auth paths forward

### Key Lessons

- OAuth integration is more complex than it looks — reserve 3–4 phases for auth strategy convergence when the OAuth provider is unknown at milestone start
- Native framework integrations (ScalekitProvider) are worth waiting for over manual wiring; research the provider's SDK before committing to a custom approach
- Static API keys are a useful milestone 1 stepping stone but should be scoped as temporary from the start if OAuth is the end goal
- Cloudflare Tunnel + Caddy is an excellent pattern for exposing a home-hosted server: zero port forwarding, TLS handled at edge, IP hidden

### Cost Observations

- Model mix: sonnet-heavy for execution, opus for planning and research
- Sessions: ~15 sessions over 14 days
- Notable: Auth convergence (Phases 16.1 + 16.2 + 18) was the most expensive stretch — 12 plans across 3 phases, significant rework; Phase 19 was comparatively fast once the right abstraction was identified

---

## Cross-Milestone Trends

| Metric | v1.0 | v2.0 | v3.0 |
|--------|------|------|------|
| Duration | 9 days | 2 days | 14 days |
| Phases | 8 | 5 (incl. 9.1) | 9 (incl. 16.1, 16.2) |
| Plans | 21 | 7 | 26 |
| Files changed | 52 | 46 | 165 |
| LOC added | +10,357 | +7,042 | +21,389 |
| LOC removed | -744 | -97 | -845 |
| Bugs fixed | 15 | 0 (new system) | 0 (direction changes) |
| Tests added | ~290 | ~38 (server) | ~411 (38 → 449) |
