# Milestones

## v3.0 Remote MCP (Shipped: 2026-04-17)

**Phases completed:** 9 phases, 26 plans, 32 tasks

**Key accomplishments:**

- `scripts/manage_keys.py` operator CLI — create/revoke/list API keys with clean error handling and token-shown-once guarantee
- docker-compose.yml with bind-mount volumes, 60s-start healthcheck, and host.docker.internal; .env.example documenting the 5-variable operator contract
- Shared infra Compose stack with Caddy (reverse proxy) and cloudflared (Cloudflare Tunnel), MCP server wired in via Docker external network with ports removed
- Complete operator walkthrough from zero (no Cloudflare account) to HTTPS endpoint via Caddy + Cloudflare Tunnel, with human verification checkpoint pending
- Auth0 tenant configured and Claude OAuth flow verified end-to-end against live server at lds-sci.williambjensen.com
- Root README.md created as the project entry point with tools description, Guides table, Quick Start, and Tech Stack

---

## v1.0 General Conference Pipeline (Shipped: 2026-03-27)

**Phases completed:** 8 phases, 21 plans, 18 tasks

**Key accomplishments:**

- Built `talk_metadata` table DDL, migrated 5 backfill scripts, and upgraded Phase 1 extractor with LEFT JOIN enrichment overlay (kicker, talk_preview, speaker_role_id)
- Church API preview fetcher (`api/fetch_talk_previews.py`) populated 4,006 talk previews with requests_cache idempotency
- Centralized all config constants into `config/pipeline_config.py`; standardized logging; relocated root scripts to `scripts/`; cleaned duplicate cache manager
- Fixed 15 known Phase 2 + 4 extractor bugs at root cause; 52-talk audit confirmed no additional bugs; all fixes covered by `BUG-NN` regression tests
- Built Phase 6 ChromaDB loader: transformation for 4 collections, annotation paragraph handling, dependency-ordered batch insertion, post-load verification report
- `scripts/run_pipeline.py` orchestrator: skip-if-processed default, `--force` flag, 1000-talk write buffer; E2E integration tests, schema validation gate, adversarial tests
- Ran all 5,838 GC talks through full pipeline; all VER checks passed — counts, semantic search, metadata filters, FK integrity; topic metadata (GROUP_CONCAT → `List[str]`) added throughout

## v2.0 MCP Server (Shipped: 2026-04-03)

**Phases completed:** 5 phases (9, 9.1, 10, 11, 12), 7 plans

**Key accomplishments:**

- FastMCP server with lifespan startup validation: absolute ChromaDB path resolution, Ollama health check via live embedding, and 4-collection warmup guard using get_collection() not get_or_create_collection()
- Paragraph metadata denormalized into ChromaDB records at load time (speaker_name, title, conference_year, conference_month) — eliminates secondary lookup in search results
- Four pure helper functions (_build_where_filter, _matches_speaker, _format_search_result, _parse_talk_id) TDD-tested; search and get_talk MCP tools wired to ChromaDB with 38 tests green
- OLLAMA_URL env var wired with localhost fallback, FastMCP instructions describing the 5,838-talk corpus, tool docstring hints for collection selection
- Claude Desktop config template and adaptive system prompt — end-to-end connection verified with proactive tool use and conversational synthesis
- All 4 phase VALIDATION.md files Nyquist-compliant, SUMMARY frontmatter complete, OLLAMA_URL single-source consolidated in server.py

---
