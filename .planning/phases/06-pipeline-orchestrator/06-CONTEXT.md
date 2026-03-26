# Phase 6: Pipeline Orchestrator - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a single orchestrator script (`scripts/run_pipeline.py`) that drives the full Phases 1–6 pipeline across all 7,659 General Conference talks in a per-talk streaming loop, with resume-from-last-processed capability, skip-if-processed default, `--force` re-process flag, and configurable ChromaDB write buffer flush. No changes to Phases 1–6 extractors.

</domain>

<decisions>
## Implementation Decisions

### Progress Tracking

- **D-01:** Use ChromaDB as the source of truth for "already processed." On each talk, query `conference_talks` to check if `talk_id` exists before processing. No separate state file or progress DB. This guarantees the skip logic reflects actual data and eliminates state divergence if a collection is deleted and rebuilt.

### Talk Failure Handling

- **D-02:** When any unhandled exception occurs during per-talk extraction (any phase), log at ERROR level and skip the talk — continue with the next talk_id. Consistent with fail-safe hybrid (Phase 5 D-10).
- **D-03:** Write a `data/failed_talks.json` file listing all failed talk_ids and their error messages. Updated after each failure. This enables easy post-run review and targeted retry with `--force`.
- **D-04:** Validation failures (`validation_report.is_valid is False`) are treated the same as extraction failures: logged at WARNING, talk skipped, included in the final summary. Already established by Phase 5 D-10.

### Run Output

- **D-05:** Use `tqdm` progress bar for the full run. Install `tqdm` as a runtime dependency. No per-talk INFO log lines during normal processing — use `tqdm.write()` for any mid-run log output to avoid breaking the bar.
- **D-06:** Print a final summary after the run completes: total processed, skipped (already done), failed, validation-failed, and elapsed time.

### Buffer Flush Timing

- **D-07:** Flush accumulated bundles to ChromaDB every `CHROMADB_BATCH_SIZE` talks (from `config/pipeline_config.py`, default 5000). Flush any remaining bundles at end of run. This matches PIPE-04 intent and balances memory usage against write frequency.
- **D-08:** If the run is interrupted mid-buffer, the unprocessed bundles since the last flush are not in ChromaDB. On resume, those talk_ids are re-processed (ChromaDB check in D-01 won't find them). This is correct behavior — no partial-bundle corruption.

### Script Location and Invocation

- **D-09:** Orchestrator lives at `scripts/run_pipeline.py`, consistent with other pipeline scripts (`run_audit.py`, `process_all.py`). Invoked via `pipenv run py scripts/run_pipeline.py [--force]`.

### Claude's Discretion

- Exact tqdm bar format (description text, unit label, position)
- Whether to add `--dry-run` flag (count talks without inserting)
- Exact structure of failed_talks.json schema

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Pipeline Orchestrator Requirements
- `.planning/REQUIREMENTS.md` §Pipeline Orchestrator (PIPE) — PIPE-01 through PIPE-04 acceptance criteria

### Existing Orchestration Patterns
- `scripts/run_audit.py` — Per-talk loop pattern: `from db import content_db, core_db`, error handling, talk-by-talk processing
- `extractors/pipeline.py` — `process_talk_pipeline()` orchestrates Phases 2–4 per talk; the new orchestrator wraps this plus Phase 5 and Phase 6

### Phase 6 Loader (what the orchestrator calls)
- `extractors/phase6_chromadb_loader.py` — Already built; receives list of validated bundles, batch-inserts into all 4 collections
- `.planning/phases/05-chromadb-loader/05-CONTEXT.md` §decisions — D-12 through D-14 define how the loader is instantiated (PersistentClient, OllamaEmbeddingFunction)

### Configuration
- `config/pipeline_config.py` — CHROMADB_PATH, CHROMADB_BATCH_SIZE, CHROMADB_COLLECTION_NAMES — all used by orchestrator

### Phase 5 Validation
- `extractors/phase5_validation.py` — `validate_talk()` produces ValidationReport; orchestrator calls this before Phase 6 and checks `is_valid`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/run_audit.py` — Near-identical per-talk loop with `content_db`/`core_db`, argparse pattern, same Phase 1–5 imports; orchestrator is a production-hardened version of this
- `extractors/pipeline.py` — `process_talk_pipeline()` is the Phase 2–4 wrapper; call this + Phase 5 + Phase 6 loader per talk
- `config/pipeline_config.py` — Add nothing new; `CHROMADB_BATCH_SIZE` already defined

### Established Patterns
- `from db import content_db, core_db` — standard DB import for scripts
- `logger = logging.getLogger(__name__)` — logging standard; no `basicConfig` in modules
- `encoding='utf-8'` on all file I/O
- argparse in scripts (see `run_audit.py`, `process_all.py`)

### Integration Points
- `scripts/run_pipeline.py` — new file; the full pipeline entry point
- Phase 6 loader is called at buffer flush points, not per-talk — orchestrator accumulates validated bundles in a list, flushes every CHROMADB_BATCH_SIZE talks

### No existing resume/skip infrastructure
- Skip-if-processed is new behavior; ChromaDB existence check is the mechanism (D-01)
- `data/failed_talks.json` is a new file; `data/` directory already exists (has `chromadb/` inside it)

</code_context>

<specifics>
## Specific Ideas

- `failed_talks.json` should be written incrementally (after each failure) so it's available even if the run is killed mid-way
- tqdm bar should show talk_id or count in the description so the operator knows where to resume if they need to look up a specific talk
- CHROMADB_BATCH_SIZE default is 5000 in pipeline_config.py, but PIPE-04 says 500–1000. Planner should note this discrepancy and confirm correct default.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 06-pipeline-orchestrator*
*Context gathered: 2026-03-26*
