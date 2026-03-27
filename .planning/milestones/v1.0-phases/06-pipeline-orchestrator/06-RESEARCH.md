# Phase 6: Pipeline Orchestrator - Research

**Researched:** 2026-03-26
**Domain:** Python CLI script orchestration, tqdm progress bars, ChromaDB existence checks, per-talk streaming pipeline
**Confidence:** HIGH

## Summary

Phase 6 builds `scripts/run_pipeline.py` — a production-hardened wrapper around the already-working extraction pipeline. All six phases of extraction (Phase 1 metadata through Phase 6 ChromaDB insertion) are already implemented. The orchestrator's job is to: (1) fetch all GC talk IDs from SQLite, (2) loop over them with tqdm progress, (3) skip already-processed talks by querying ChromaDB, (4) run each talk through `process_talk_pipeline()` + `validate_talk()` + `load_talk_bundles()`, (5) buffer bundles and flush every CHROMADB_BATCH_SIZE talks, and (6) write failures to `data/failed_talks.json` incrementally.

The canonical implementation model is `scripts/run_audit.py`, which already demonstrates the per-talk error handling, argparse, logging, and phase import patterns. The orchestrator extends that skeleton with tqdm, ChromaDB skip logic, a buffer-and-flush loop, and a `--force` flag.

The only open discrepancy requiring a planner decision is the `CHROMADB_BATCH_SIZE` default: `config/pipeline_config.py` already sets it to 5000, but PIPE-04 says 500–1000. The CONTEXT.md note (specifics section) confirms the planner must reconcile this.

**Primary recommendation:** Build `scripts/run_pipeline.py` directly from the `run_audit.py` skeleton. Reuse `process_talk_pipeline()` for Phases 1–4, `validate_talk()` for Phase 5, and `load_talk_bundles()` for Phase 6. Use ChromaDB `get()` for skip detection. Add tqdm with `tqdm.write()` for mid-run output. Buffer bundles between flushes; do not call `load_talk_bundles()` per-talk.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Use ChromaDB as the source of truth for "already processed." On each talk, query `conference_talks` to check if `talk_id` exists before processing. No separate state file or progress DB.

**D-02:** When any unhandled exception occurs during per-talk extraction, log at ERROR level and skip the talk — continue with the next talk_id.

**D-03:** Write a `data/failed_talks.json` file listing all failed talk_ids and their error messages. Updated after each failure.

**D-04:** Validation failures (`validation_report.is_valid is False`) treated the same as extraction failures: logged at WARNING, talk skipped, included in final summary.

**D-05:** Use `tqdm` progress bar for the full run. Install `tqdm` as a runtime dependency. No per-talk INFO log lines during normal processing — use `tqdm.write()` for any mid-run log output.

**D-06:** Print a final summary after the run completes: total processed, skipped (already done), failed, validation-failed, and elapsed time.

**D-07:** Flush accumulated bundles to ChromaDB every `CHROMADB_BATCH_SIZE` talks (from `config/pipeline_config.py`, default 5000). Flush remaining bundles at end of run.

**D-08:** If run is interrupted mid-buffer, unprocessed bundles since last flush are not in ChromaDB. On resume, those talk_ids are re-processed. This is correct behavior.

**D-09:** Orchestrator lives at `scripts/run_pipeline.py`. Invoked via `pipenv run py scripts/run_pipeline.py [--force]`.

### Claude's Discretion

- Exact tqdm bar format (description text, unit label, position)
- Whether to add `--dry-run` flag (count talks without inserting)
- Exact structure of `failed_talks.json` schema

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PIPE-01 | Single orchestrator script runs per-talk streaming loop (Phases 1–6) across all 7,659 GC talks | `process_talk_pipeline()` + `validate_talk()` + `load_talk_bundles()` cover all phases; `fetch_all_talks()` fetches all rows with a single query |
| PIPE-02 | Progress tracked by `talk_id`; interrupted run resumes from last successfully processed talk | ChromaDB `conference_talks` collection stores `talk_id` in metadata; `get(ids=["talk_{id}"])` is the existence check; re-run detects and skips already-present IDs |
| PIPE-03 | Skip-if-processed mode is default; `--force` flag re-processes already-completed talks | `argparse` `--force` flag disables skip check; without it, ChromaDB lookup guards each talk |
| PIPE-04 | ChromaDB write buffer size configurable; default 500–1000 talks per flush | `CHROMADB_BATCH_SIZE` in `config/pipeline_config.py`; **discrepancy: currently set to 5000, not 500–1000 — planner must reconcile** |
</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| tqdm | 4.67.3 (installed) | Progress bar for the main loop | D-05 locked decision; already available via pip |
| chromadb | installed | Skip-if-processed existence check + final load | Already used by phase6_chromadb_loader.py |
| argparse | stdlib | `--force` flag parsing | Established pattern in run_audit.py and process_all.py |
| json | stdlib | `failed_talks.json` write | D-03 pattern |
| logging | stdlib | ERROR/WARNING log output | Project standard: `logger = logging.getLogger(__name__)` |
| time | stdlib | Elapsed time in final summary (D-06) | Simple `time.time()` start/end |

### No New Dependencies Required (Except tqdm)

tqdm is already installed in the virtualenv (version 4.67.3) but is not yet listed in Pipfile. It must be added as a runtime dependency.

**Installation:**
```bash
pipenv install tqdm
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tqdm | rich.progress | tqdm is lighter, already installed, fits existing simple script style |
| data/failed_talks.json | SQLite table | JSON is simpler for a one-script output file; human-readable for post-run review |
| ChromaDB existence check | Separate state.json | ChromaDB is truth per D-01; avoids divergence if collection is deleted/rebuilt |

---

## Architecture Patterns

### Recommended Project Structure

No new directories required. Single new file:

```
scripts/
├── run_pipeline.py      # new — full pipeline orchestrator
├── run_audit.py         # existing — model/template for run_pipeline.py
├── process_all.py       # existing
└── ...

data/
├── chromadb/            # existing — PersistentClient path
└── failed_talks.json    # new — written incrementally per D-03
```

### Pattern 1: Main Loop with Buffer and Flush

The orchestrator accumulates `TalkBundle` objects in a list, flushing to ChromaDB every `CHROMADB_BATCH_SIZE` talks. The key insight: `load_talk_bundles()` is called at flush points, not per-talk.

```python
# Source: extractors/pipeline.py + extractors/phase6_chromadb_loader.py
pending_bundles: list[TalkBundle] = []
processed_since_flush = 0

for talk_id in tqdm(all_talk_ids, unit="talk", desc="Processing"):
    # Skip check (D-01)
    if not force:
        existing = talks_col.get(ids=[f"talk_{talk_id}"])
        if existing["ids"]:
            skipped_count += 1
            continue

    try:
        result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, PARAGRAPH_CONFIG)
        validation = validate_talk(result.metadata, result.paragraphs, result.citations, result.footnotes, db=core_db)
        bundle = (result.metadata, result.paragraphs, result.citations, result.footnotes, validation)

        if not validation.is_valid:
            # D-04: treat same as failure
            validation_failed_count += 1
            _record_failure(talk_id, "validation failed", failed_talks)
        else:
            pending_bundles.append(bundle)
            processed_since_flush += 1

        if processed_since_flush >= CHROMADB_BATCH_SIZE:
            load_talk_bundles(pending_bundles, chroma_client, embedding_fn)
            pending_bundles.clear()
            processed_since_flush = 0

    except Exception as exc:
        logger.error("talk_id=%d failed: %s", talk_id, exc)
        _record_failure(talk_id, str(exc), failed_talks)  # D-03: write incrementally

# Final flush
if pending_bundles:
    load_talk_bundles(pending_bundles, chroma_client, embedding_fn)
```

### Pattern 2: ChromaDB Skip Detection

ChromaDB `collection.get(ids=[...])` returns `{"ids": [...], "documents": [...], ...}`. If the ID exists, `result["ids"]` will be non-empty. This is the mechanism for D-01.

```python
# Source: verified against chromadb PersistentClient API (installed version)
existing = talks_col.get(ids=[f"talk_{talk_id}"])
already_processed = len(existing["ids"]) > 0
```

Note: `include=["ids"]` is NOT valid in the installed chromadb version (raises ValueError). Call `.get(ids=[...])` with default include — it returns ids, documents, and metadatas automatically.

### Pattern 3: Talk ID Fetching

Two approaches are available. Use option A (simpler, avoids N+1 per-row overhead):

**Option A — fetch just IDs:**
```python
# Source: db/__init__.py Database.select() API
rows = core_db.select("SELECT t.ID FROM talk t INNER JOIN conference_talk ct ON ct.TalkID = t.ID ORDER BY t.ID")
all_talk_ids = [row["ID"] for row in rows]
```

**Option B — reuse existing fetch_all_talks():**
```python
# Source: extractors/phase1_talk_metadata.py
from extractors.phase1_talk_metadata import fetch_all_talks
rows = fetch_all_talks(core_db)
all_talk_ids = [row["talk_id"] for row in rows]
```

Option A is preferred for the orchestrator — it fetches only IDs upfront (lightweight), and Phase 1 data is re-fetched per-talk inside `process_talk_pipeline()`. Option B pre-fetches all metadata into memory before the loop starts, which is unnecessary overhead for 7,659 rows, but not harmful.

Confirmed total: `conference_talk` table has 5,838 GC talks; `talk` table has 7,659 total. The orchestrator should process only GC talks (those joined to `conference_talk`).

### Pattern 4: book_cache Initialization

`process_talk_pipeline()` requires a `book_cache` dict. This is loaded once before the loop:

```python
# Source: extractors/phase3_citation_extraction.py fetch_all_books()
from extractors.phase3_citation_extraction import fetch_all_books
book_cache = fetch_all_books(core_db)  # 99 rows, loaded once at startup
```

### Pattern 5: Incremental failed_talks.json Write

Per D-03, the file must be updated after each failure so it's available if the run is killed:

```python
# Write/overwrite on each failure
def _record_failure(talk_id: int, error: str, failed_talks: list) -> None:
    failed_talks.append({"talk_id": talk_id, "error": error})
    with open(FAILED_TALKS_PATH, "w", encoding="utf-8") as f:
        json.dump(failed_talks, f, indent=2, ensure_ascii=False)
```

### Pattern 6: tqdm with tqdm.write()

Per D-05, avoid print() or logger INFO inside the loop — use tqdm.write() to avoid breaking the bar:

```python
from tqdm import tqdm
# Mid-run output (errors/warnings surfaced to operator):
tqdm.write(f"[WARN] talk_id={talk_id} validation failed")
# NOT: print(...) or logger.info(...)
```

### Pattern 7: argparse (established project pattern)

```python
# Source: scripts/run_audit.py argparse pattern
import argparse

def main() -> None:
    parser = argparse.ArgumentParser(description="Run full pipeline across all GC talks")
    parser.add_argument("--force", action="store_true", help="Re-process already-loaded talks")
    args = parser.parse_args()
```

### Pattern 8: Logging Setup (scripts only)

Scripts call `logging.basicConfig()` in `if __name__ == "__main__"` — never in modules. No per-talk INFO lines during normal operation (tqdm bar owns stdout).

```python
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,  # Only warnings/errors reach terminal during tqdm run
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    main()
```

### Anti-Patterns to Avoid

- **Calling `load_talk_bundles()` per-talk:** The loader is designed to receive a batch — calling it per talk creates 7,659 separate ChromaDB write transactions. Always buffer.
- **Using `include=["ids"]` in ChromaDB `.get()`:** The installed chromadb version raises `ValueError: Expected include item to be one of documents, embeddings, metadatas, distances, uris, data, got ids`. Use default include and check `result["ids"]`.
- **Calling `print()` inside the tqdm loop:** Breaks the progress bar rendering. Use `tqdm.write()`.
- **Writing failed_talks.json only at end:** The run can be interrupted. Write incrementally per D-03.
- **Importing `logging.basicConfig` in extractors:** Project standard prohibits it in modules. Only in script `__main__` blocks.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ChromaDB batch insertion | Custom upsert loop | `insert_collection()` from phase6_chromadb_loader.py | Already handles `create_batches()`, SQLite param limits, progress logging |
| Phase 1–4 extraction | Re-implement phases | `process_talk_pipeline()` from extractors/pipeline.py | Single HTML parse, shared contexts, all error handling built-in |
| Phase 5 validation | Re-implement checks | `validate_talk()` from extractors/phase5_validation.py | Complete cross-collection integrity checks |
| Progress display | Custom print loop | `tqdm` | Thread-safe, handles terminal width, supports `tqdm.write()` |
| Book abbreviation lookup | Inline dict | `fetch_all_books(core_db)` | Already exists in phase3_citation_extraction.py |

**Key insight:** The orchestrator is integration code only. Every extraction, validation, and insertion function already exists and is tested. The orchestrator's logic surface is minimal: loop, skip check, buffer management, error capture, final summary.

---

## Common Pitfalls

### Pitfall 1: CHROMADB_BATCH_SIZE Discrepancy

**What goes wrong:** `config/pipeline_config.py` sets `CHROMADB_BATCH_SIZE = 5000`, but PIPE-04 specifies a default of 500–1000 talks per flush.

**Why it happens:** The constant was set during Phase 6 loader implementation without coordinating with PIPE-04 acceptance criteria.

**How to avoid:** Planner must explicitly decide the correct default and update `pipeline_config.py` if needed. Both values are technically valid — 5000 means fewer flushes per run (more memory used between flushes), while 500–1000 means more frequent flushes (less memory, more write transactions). For 7,659 talks, 5000 means two flushes total (at talk 5000 and end of run). This is likely fine but contradicts PIPE-04 acceptance criteria.

**Recommendation:** Set `CHROMADB_BATCH_SIZE = 1000` in pipeline_config.py to match PIPE-04 literal requirements.

### Pitfall 2: process_talk_pipeline() PARAGRAPH_CONFIG vs dict

**What goes wrong:** `process_talk_pipeline()` takes `config: Dict[str, Any]` — the caller must pass `PARAGRAPH_CONFIG` (from `config/schemas.py`), not the raw `pipeline_config.py` constants.

**Why it happens:** Two config representations exist: raw constants in pipeline_config.py and assembled dicts in schemas.py. The pipeline functions consume the dict form.

**How to avoid:** Import `PARAGRAPH_CONFIG` from `config.schemas`, not from `config.pipeline_config`.

### Pitfall 3: GC talks vs all talks

**What goes wrong:** `talk` table has 7,659 rows but only 5,838 are in `conference_talk` (GC talks). If the orchestrator queries `SELECT ID FROM talk` without joining `conference_talk`, non-GC talks are included. Non-GC talks likely have no HTML in `content_db` and will fail Phase 2.

**Why it happens:** The CONTEXT.md says "7,659 General Conference talks" but that number actually counts all talks in the `talk` table, not just GC entries. The `conference_talk` join filters to true GC talks.

**How to avoid:** Use an INNER JOIN to `conference_talk` when fetching talk IDs, or use `fetch_all_talks()` which already includes this join in `build_talk_metadata_query()`.

**Warning signs:** Large number of Phase 2 "no HTML content found" failures in the first test run.

### Pitfall 4: ChromaDB include parameter API mismatch

**What goes wrong:** Calling `.get(ids=[...], include=["ids"])` raises `ValueError` in the installed chromadb version. The string `"ids"` is not a valid include value.

**Why it happens:** Some chromadb documentation examples suggest `include=["ids"]` but this is not valid — IDs are always returned by default.

**How to avoid:** Call `.get(ids=[f"talk_{talk_id}"])` without specifying `include`. IDs are always included in the response.

### Pitfall 5: Partial buffer loss on interrupt

**What goes wrong:** If the run is killed mid-buffer (between flush points), talks processed since the last flush are not in ChromaDB. On resume, they will be re-processed.

**Why it happens:** Per D-08, this is intentional — the ChromaDB check (D-01) only skips talks that were fully committed in a previous flush.

**How to avoid:** This is not a bug — document it in script help text so operators understand resume semantics. Consider CHROMADB_BATCH_SIZE of 1000 so at most 1000 talks are re-processed on interrupt.

### Pitfall 6: validate_talk() signature mismatch

**What goes wrong:** `validate_talk()` in phase5_validation.py has signature `validate_talk(metadata, paragraphs, citations, footnotes, db=None)`. The `db` parameter is optional and enables DB-dependent checks. The orchestrator should pass `db=core_db` to get full validation.

**How to avoid:** Pass `db=core_db` explicitly. Without it, some DB-dependent checks are silently skipped with warnings.

---

## Code Examples

### Full Orchestrator Skeleton

```python
# Source: run_audit.py pattern + phase6_chromadb_loader.py API
# scripts/run_pipeline.py

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm
from db import content_db, core_db
from config.schemas import PARAGRAPH_CONFIG
from config.pipeline_config import CHROMADB_BATCH_SIZE, CHROMADB_COLLECTION_NAMES
from extractors.pipeline import process_talk_pipeline
from extractors.phase3_citation_extraction import fetch_all_books
from extractors.phase5_validation import validate_talk
from extractors.phase6_chromadb_loader import (
    get_chromadb_client, get_embedding_function, load_talk_bundles, TalkBundle
)

logger = logging.getLogger(__name__)

FAILED_TALKS_PATH = Path(__file__).parent.parent / "data" / "failed_talks.json"


def _get_all_gc_talk_ids() -> list[int]:
    rows = core_db.select(
        "SELECT t.ID FROM talk t INNER JOIN conference_talk ct ON ct.TalkID = t.ID ORDER BY t.ID"
    )
    return [row["ID"] for row in rows]


def _record_failure(talk_id: int, error: str, failed_talks: list) -> None:
    """Append failure and write file immediately (D-03)."""
    failed_talks.append({"talk_id": talk_id, "error": error})
    with open(FAILED_TALKS_PATH, "w", encoding="utf-8") as f:
        json.dump(failed_talks, f, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full pipeline across all GC talks")
    parser.add_argument("--force", action="store_true", help="Re-process already-loaded talks")
    args = parser.parse_args()

    start_time = time.time()
    book_cache = fetch_all_books(core_db)
    chroma_client = get_chromadb_client()
    embedding_fn = get_embedding_function()
    talks_col = chroma_client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["talks"], embedding_function=embedding_fn
    )

    all_talk_ids = _get_all_gc_talk_ids()

    pending_bundles: list[TalkBundle] = []
    processed_since_flush = 0
    skipped_count = 0
    failed_count = 0
    validation_failed_count = 0
    failed_talks: list[dict] = []

    for talk_id in tqdm(all_talk_ids, unit="talk", desc="Pipeline"):
        # Skip check (D-01, D-03)
        if not args.force:
            existing = talks_col.get(ids=[f"talk_{talk_id}"])
            if existing["ids"]:
                skipped_count += 1
                continue

        try:
            result = process_talk_pipeline(
                content_db, core_db, talk_id, book_cache, PARAGRAPH_CONFIG
            )
            if not result.success:
                raise RuntimeError("; ".join(result.errors))

            validation = validate_talk(
                result.metadata, result.paragraphs, result.citations, result.footnotes, db=core_db
            )

            if not validation.is_valid:
                tqdm.write(f"[WARN] talk_id={talk_id} validation failed")
                _record_failure(talk_id, f"validation: {validation.errors}", failed_talks)
                validation_failed_count += 1
                continue

            bundle: TalkBundle = (
                result.metadata, result.paragraphs, result.citations, result.footnotes, validation
            )
            pending_bundles.append(bundle)
            processed_since_flush += 1

            if processed_since_flush >= CHROMADB_BATCH_SIZE:
                load_talk_bundles(pending_bundles, chroma_client, embedding_fn)
                pending_bundles.clear()
                processed_since_flush = 0

        except Exception as exc:
            logger.error("talk_id=%d failed: %s", talk_id, exc)
            tqdm.write(f"[ERROR] talk_id={talk_id}: {exc}")
            _record_failure(talk_id, str(exc), failed_talks)
            failed_count += 1

    # Final flush
    if pending_bundles:
        load_talk_bundles(pending_bundles, chroma_client, embedding_fn)

    elapsed = time.time() - start_time
    total_processed = len(all_talk_ids) - skipped_count
    print(f"\nRun complete in {elapsed:.1f}s")
    print(f"  Processed:         {total_processed}")
    print(f"  Skipped (cached):  {skipped_count}")
    print(f"  Failed:            {failed_count}")
    print(f"  Validation failed: {validation_failed_count}")
    if failed_talks:
        print(f"  Failed talks log:  {FAILED_TALKS_PATH}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    main()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-talk ChromaDB flush | Buffer N talks, flush in batch | Phase 6 loader design | Fewer write transactions, better throughput |
| Separate state file for resume | ChromaDB as truth (D-01) | Phase 6 context discussion | Eliminates state divergence on collection rebuild |

**Deprecated/outdated:**
- Passing `include=["ids"]` to ChromaDB `.get()`: Invalid in chromadb >= 0.5.x. IDs are always returned. Do not include in the `include` list.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| tqdm | Progress bar (D-05) | Yes (virtualenv) | 4.67.3 | None — required per D-05 |
| chromadb | Skip check + loader | Yes | installed | None — core dependency |
| ollama service | Embedding function | Not verified | — | Run will fail at embed time; can pass `embedding_fn=None` for testing |
| SQLite core.52.db | Talk IDs + metadata | Yes | 5,838 GC / 7,659 total | None — required |
| SQLite content.52.db | HTML content (Phase 2) | Yes | — | None — required |
| Pipfile tqdm entry | Reproducible installs | **Missing** | — | Add `tqdm = "*"` to [packages] |

**Missing dependencies with no fallback:**
- `tqdm` in Pipfile: currently installed in virtualenv but not declared. `pipenv install tqdm` needed to add to Pipfile.lock.

**Missing dependencies with fallback:**
- ollama service: only needed at runtime when embedding is triggered. Tests can pass `embedding_fn=None`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (installed) |
| Config file | none (discovered by default) |
| Quick run command | `pipenv run py -m pytest tests/test_pipeline_orchestrator.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 | Per-talk loop calls all 6 phases for each talk_id | unit (mock) | `pytest tests/test_pipeline_orchestrator.py::test_full_loop -x` | Wave 0 |
| PIPE-02 | Already-in-ChromaDB talks are skipped on resume | unit (mock) | `pytest tests/test_pipeline_orchestrator.py::test_resume_skips_processed -x` | Wave 0 |
| PIPE-03 | Default mode skips; `--force` reprocesses | unit (mock) | `pytest tests/test_pipeline_orchestrator.py::test_force_flag -x` | Wave 0 |
| PIPE-04 | Buffer flushes at CHROMADB_BATCH_SIZE boundary | unit (mock) | `pytest tests/test_pipeline_orchestrator.py::test_buffer_flush -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pipenv run py -m pytest tests/test_pipeline_orchestrator.py -x -q`
- **Per wave merge:** `pipenv run py -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_pipeline_orchestrator.py` — covers all PIPE-01 through PIPE-04 tests above (does not exist yet)

---

## Open Questions

1. **CHROMADB_BATCH_SIZE default value**
   - What we know: `pipeline_config.py` has 5000; PIPE-04 says 500–1000
   - What's unclear: Which value should be canonical
   - Recommendation: Change `CHROMADB_BATCH_SIZE` to 1000 in `pipeline_config.py` to satisfy PIPE-04 literal acceptance criteria. This means 6–8 flushes for a full run instead of 2, which is negligible overhead and safer on interrupt.

2. **--dry-run flag (discretion area)**
   - What we know: Listed under Claude's Discretion
   - What's unclear: Whether the planner wants to include it
   - Recommendation: Include it. Costs one extra `if args.dry_run: continue` guard before the load step. Useful for validating talk counts without writing to ChromaDB.

3. **validate_talk() DB checks with core_db**
   - What we know: `validate_talk(db=None)` silently skips DB-dependent checks
   - What's unclear: Whether the orchestrator should pass `db=core_db` for full validation
   - Recommendation: Pass `db=core_db` — the orchestrator has core_db available and should run all checks.

---

## Sources

### Primary (HIGH confidence)

- `scripts/run_audit.py` — verified orchestration skeleton, argparse pattern, phase imports
- `extractors/pipeline.py` — verified `process_talk_pipeline()` signature and return type
- `extractors/phase6_chromadb_loader.py` — verified `load_talk_bundles()` API, `TalkBundle` type alias
- `extractors/phase5_validation.py` — verified `validate_talk()` signature
- `extractors/phase3_citation_extraction.py` — verified `fetch_all_books()` and `fetch_all_talks()` patterns
- `config/pipeline_config.py` — verified `CHROMADB_BATCH_SIZE = 5000` (current value)
- `db/__init__.py` — verified `Database.select()` API
- Live chromadb instance probe — verified `include=["ids"]` raises ValueError; confirmed `get(ids=[...])` works without include parameter

### Secondary (MEDIUM confidence)

- tqdm 4.67.3 installed in virtualenv — `tqdm.write()` is the correct API for writing inside a tqdm loop without breaking the bar (standard tqdm documented behavior)

### Tertiary (LOW confidence)

None.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified in installed virtualenv
- Architecture: HIGH — derived directly from reading existing code, no assumptions
- Pitfalls: HIGH — ChromaDB include bug verified live; GC/all-talks discrepancy verified by querying both tables; PARAGRAPH_CONFIG vs pipeline_config discrepancy verified by reading both files

**Research date:** 2026-03-26
**Valid until:** 2026-06-26 (stable domain — no fast-moving dependencies)
