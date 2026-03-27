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

## Cross-Milestone Trends

| Metric | v1.0 |
|--------|------|
| Duration | 9 days |
| Phases | 8 |
| Plans | 21 |
| Files changed | 52 |
| LOC added | +10,357 |
| LOC removed | -744 |
| Bugs fixed | 15 |
| Tests added | ~290 |
