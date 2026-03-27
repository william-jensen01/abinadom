# Phase 6: Pipeline Orchestrator - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 06-pipeline-orchestrator
**Areas discussed:** Progress tracking, Talk failure handling, Run output, Buffer flush timing

---

## Progress Tracking

| Option | Description | Selected |
|--------|-------------|----------|
| Check ChromaDB directly | Query conference_talks for talk_id on each run. No extra state file. | ✓ |
| Flat JSON/text file | Write processed talk_ids to data/pipeline_progress.json after each flush. | |
| SQLite progress table | New table in data/pipeline.db with talk_id, status, timestamp. | |

**User's choice:** Check ChromaDB directly (recommended)
**Notes:** Guarantees skip logic reflects actual data; eliminates state divergence if collection is deleted and rebuilt.

---

## Talk Failure Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Log ERROR + skip, continue run | Consistent with Phase 5 D-10. Failed talk_ids in final summary. | |
| Log ERROR + skip, write failed_talks.json | Same, plus dedicated failed_talks.json with errors per talk_id. | ✓ |
| Abort on first unhandled exception | Hard-fail the run on any error. | |

**User's choice:** Log ERROR + skip, write failed_talks.json
**Notes:** failed_talks.json enables easy post-run review and targeted retry with --force.

---

## Run Output

| Option | Description | Selected |
|--------|-------------|----------|
| tqdm progress bar | Standard progress bar with ETA. Requires installing tqdm. | ✓ |
| Periodic log summaries | INFO log every N talks. Fits existing logging conventions, no extra dependency. | |
| Log INFO per talk | One INFO line per talk. Verbose at scale. | |

**User's choice:** tqdm progress bar (recommended)
**Notes:** tqdm not currently in Pipfile; needs to be added. Use tqdm.write() for mid-run log output.

---

## Buffer Flush Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Every N talks + final flush | Flush every CHROMADB_BATCH_SIZE, then remainder at end. | ✓ |
| Final flush only | Hold all bundles in memory, single insert at end. | |
| Every talk (no buffer) | Call loader after each talk. Loses batch efficiency. | |

**User's choice:** Every N talks + final flush (recommended)
**Notes:** Matches PIPE-04 intent. On interruption, unprocessed bundles since last flush are re-processed on resume (correct behavior per D-01 ChromaDB check).

---

## Claude's Discretion

- Exact tqdm bar format (description text, unit label)
- Whether to add `--dry-run` flag
- Exact schema of failed_talks.json

## Deferred Ideas

None.
