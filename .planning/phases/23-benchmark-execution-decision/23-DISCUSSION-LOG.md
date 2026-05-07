# Phase 23: Benchmark Execution & Decision - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-07
**Phase:** 23-benchmark-execution-decision
**Areas discussed:** DB reset before full run, Official run parameters, Winner decision criteria, Decision report format

---

## DB Reset Before Full Run

| Option | Description | Selected |
|--------|-------------|----------|
| Add --reset flag to runner | Runner calls collection delete+recreate per DB before loading. Self-contained, repeatable. | ✓ |
| docker compose down -v && up | Wipe Docker volumes manually. Simple but a manual step. | |
| Document as manual pre-flight | Note in plan that DBs must be cleared; zero code change. | |

**User's choice:** Add --reset flag

| Sub-option | Description | Selected |
|--------|-------------|----------|
| Delete and recreate collections | Delete via DB API, let loader __init__/_ensure_schema recreate. Same path as fresh stack. | ✓ |
| Delete all records in-place | delete_many / batch delete. Trickier across 3 DB APIs. | |
| You decide | Leave to planner. | |

**Reset scope:** Matches `--db` flag (reset only the targeted DB(s))

---

## Official Run Parameters

| Parameter | Options considered | Selected |
|-----------|-------------------|----------|
| --upsert-limit | 5838 hardcoded / all talks (no limit) / lower ceiling | None (all talks) — user noted the number can change, prefers semantic "cover everything" |
| --query-limit | 100 / 200 / 500 | 500 — user clarified purpose (latency sample size, not query diversity) then chose maximum statistical confidence |
| --workers | 4 / 8 / you decide | 4 (keep current default) |

**Notes:** User asked why cycling the 8 canonical queries was necessary — explained that
cycling builds up latency sample count for stable percentile estimates (p50/p95/p99 require
~50+ data points). After that clarification, user chose 500.

---

## Winner Decision Criteria

| Option | Description | Selected |
|--------|-------------|----------|
| Recall@k dominant | Correctness first, performance secondary | |
| Composite weighted score | Explicit weights per dimension | |
| Latency dominant | Sub-30ms p50 as primary signal | |
| Pick the obvious winner | Name winner with brief rationale, no formal scoring | |

**User's choice:** "I honestly have no idea"

**Outcome:** Claude offered a recommendation — recall@k as a correctness gate, operational
metrics (latency, upsert speed, memory, cold-start) as the tiebreaker. User agreed with
this framing and the winner-after-data-is-in approach.

| Sub-option | Selected |
|--------|----------|
| Winner named only after full data is in | ✓ |
| Pre-select and confirm with data | |

---

## Recall@k Framing (emerged during discussion)

**User raised:** "Everything is based off ChromaDB — how could we accurately depict whether
a DB is truly better and not just returning the same as ChromaDB?"

**Claude's response:** Since all DBs use the same embedding model (nomic-embed-text via
Ollama), all three compute identical vectors. recall@k measures ANN fidelity (how closely
each DB's approximate nearest neighbors match ChromaDB's exact baseline), not retrieval
quality. To measure true quality, you'd need to benchmark different embedding models —
which requires ground-truth labels or LLM-as-judge scoring.

**User response:** "So I'd essentially need to benchmark different embedding models."

**Resolution:** recall@k is framed in DECISION.md as a correctness/fidelity check. True
quality benchmarking is deferred to a future phase. Operational metrics drive the winner.

---

## Decision Report Format

| Option | Description | Selected |
|--------|-------------|----------|
| Table + narrative | Comparison table + narrative per dimension | ✓ |
| ADR-style | Context/Decision/Rationale/Consequences | |
| Minimal summary | Winner + 3 reasons + JSON links | |

**Report location:** `benchmark/DECISION.md` (user chose this over `docs/benchmark/DECISION.md`)

**Authoring:** Written by executor after full run completes, using real numbers. No template/placeholder approach.

**Winner placement:** Clear winner declared upfront, justification follows.

---

## Claude's Discretion

- Exact wording of the recall@k framing in DECISION.md
- Table layout and column ordering in DECISION.md
- Whether to include a "Production implications for Phase 24" section

## Deferred Ideas

- **Embedding model evaluation** — True retrieval quality benchmarking requires comparing
  embedding models (nomic-embed-text vs mxbai-embed-large, etc.) with ground-truth
  labels or LLM-as-judge evaluation. Out of scope for Phase 23; future phase.
