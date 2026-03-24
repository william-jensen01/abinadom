# Phase 5: ChromaDB Loader - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 05-chromadb-loader
**Areas discussed:** Document text, Metadata field selection, Invalid talk handling, ChromaDB client setup

---

## Document Text (What to Store)

| Option | Description | Selected |
|--------|-------------|----------|
| Title + talk_preview | Title + preview from Church API; falls back to title-only when preview absent | ✓ |
| Title only | Consistent across all 7,659 talks; lower semantic signal | |
| Title + kicker + preview | Maximum content; kicker is often speaker's calling (noise) | |

**User's choice:** Title + talk_preview (fallback: title only)
**Notes:** User asked for Claude's reasoning first before deciding. Key factor: title-alone gives poor signal for short/evocative GC titles. Preview was specifically fetched from Church API to enrich talk-level search. Kicker rejected due to noise (often ecclesiastical calling, not content).

---

## Metadata Field Selection

| Option | Description | Selected |
|--------|-------------|----------|
| All non-None fields | Include every dataclass field that isn't None | ✓ |
| Curated minimal set | Only fields known to be used for filtering in Milestone 2 | |
| You decide | Claude picks reasonable defaults per collection | |

**User's choice:** All non-None fields
**Notes:** Keeps metadata rich for future filtering. ChromaDB ignores unused fields. Planner determines exact field list per collection by reading model dataclasses.

---

## Invalid Talk Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Skip + log, continue run | Log talk_id + errors at WARNING, skip insertion, continue | ✓ |
| Abort the entire run | Any invalid talk halts the pipeline | |
| Insert with a flag | Insert anyway with is_valid=False metadata | |

**User's choice:** Skip + log, continue run
**Notes:** Consistent with fail-safe hybrid used elsewhere. One bad talk should not block 7,658 good ones.

---

## ChromaDB Client Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent client, path in pipeline_config.py | CHROMADB_PATH in config/pipeline_config.py; tests use tmp dir | ✓ |
| Persistent client, path as argument | Caller supplies path; more flexible but more boilerplate | |
| Configurable via env var | 12-factor style; adds indirection for personal-use tool | |

**User's choice:** Persistent client, path in pipeline_config.py
**Notes:** Consistent with how all other pipeline constants are handled.

---

## Claude's Discretion

- Verification report format
- Batch size default value
- Retry logic for failed ChromaDB batches

## Deferred Ideas

None.
