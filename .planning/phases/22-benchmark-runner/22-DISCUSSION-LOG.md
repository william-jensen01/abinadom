# Phase 22: Benchmark Runner — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-23
**Phase:** 22-benchmark-runner
**Areas discussed:** Runner organization, DB failure handling, Memory peak sampling, JSON serialization

---

## Runner Organization

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level functions | Each dimension is a top-level function; main() passes a mutable results dict. Matches scripts/run_pipeline.py pattern. | |
| BenchmarkRunner class | Class holds loader, config, and self.results. Methods per dimension. main() instantiates once per DB. Consistent with Phase 21 loader pattern. | ✓ |

**User's choice:** BenchmarkRunner class
**Notes:** User questioned the recommendation of module-level functions. After discussion, agreed that the class approach is a closer match to the Phase 21 loader pattern — both involve connection state and a loop over many calls (bundles for loaders, benchmark dimensions for the runner). Module-level functions were the initial recommendation based on run_pipeline.py style, but the class is the better analogy for this use case.

---

## DB Failure Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Skip + continue, exit non-zero | Log ERROR, skip failed DB, continue with others, exit with non-zero code to signal partial failure. | ✓ |
| Fail fast, abort whole run | Any DB unreachable → abort immediately with non-zero exit. Consistent with SPEC's Ollama fail-fast rule. | |
| Skip + continue, exit 0 | Log WARNING, skip failed DB, exit 0. Permissive — CI green even on partial runs. | |

**User's choice:** Skip + continue, exit non-zero
**Notes:** ChromaDB is always benchmarked first (SPEC Req 14 ordering), so the recall@k baseline is established before Weaviate/Qdrant are attempted. Skipping a later DB does not break recall computation for the surviving DB reports.

---

## Memory Peak Sampling

| Option | Description | Selected |
|--------|-------------|----------|
| Polling thread | Background daemon thread samples RSS every ~150ms during concurrent phase. peak_mb = max(all samples). | ✓ |
| Before/after snapshots | Sample before and after ThreadPoolExecutor completes. peak_mb = max(before, after). Simpler but may miss transient peaks. | |
| Worker-side sampling | Each worker thread samples its own RSS at task completion. Adds overhead to every query call. | |

**User's choice:** Polling thread
**Notes:** Chosen for accuracy — captures true peak even if memory is freed before the concurrent phase completes. Daemon thread requires no explicit cleanup.

---

## JSON Serialization

| Option | Description | Selected |
|--------|-------------|----------|
| dataclasses.asdict() + new dataclass | Uniform asdict() for all metrics. New ScalabilityCurveEntry dataclass in benchmark/metrics.py. | ✓ |
| dataclasses.asdict() + plain dict for curve | asdict() for existing metrics; plain dicts for scalability curve entries. | |
| Custom to_dict() on each dataclass | Add to_dict() method to each dataclass. Modifies Phase 20 deliverables for no practical gain. | |

**User's choice:** dataclasses.asdict() + new ScalabilityCurveEntry dataclass
**Notes:** Consistent with the project's existing asdict() usage in shared_transforms.py. ScalabilityCurveEntry fields: workers, throughput_qps, p50_ms, p95_ms, p99_ms.

---

## Claude's Discretion

- Exact memory polling interval (100–200ms range)
- Logging format for benchmark progress
- Internal helper method names within BenchmarkRunner
- Whether BenchmarkRunner exposes a reset() method or is re-instantiated per DB

## Deferred Ideas

None — discussion stayed within phase scope.
