"""
Metric dataclasses for vector DB benchmark measurements.

Consumed by benchmark/runner.py (Phase 22) to record and compare
upsert speed, query latency, concurrency throughput, and memory delta
across ChromaDB, Weaviate, and Qdrant.
"""

from dataclasses import dataclass


@dataclass
class UpsertMetrics:
    """Measures bulk insert performance."""

    total_records: int
    elapsed_seconds: float
    records_per_second: float


@dataclass
class QueryMetrics:
    """Measures query latency across a workload (p50/p95/p99 profile)."""

    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float
    query_count: int
    failed_queries: int = 0  # default=0 — must be last per Python @dataclass rules


@dataclass
class ConcurrencyMetrics:
    """Measures throughput under concurrent query load."""

    workers: int
    total_queries: int
    elapsed_seconds: float
    throughput_qps: float


@dataclass
class MemoryMetrics:
    """Measures process memory delta during a benchmark operation."""

    baseline_mb: float
    peak_mb: float
    delta_mb: float


def recall_at_k(baseline_ids: list[str], candidate_ids: list[str], k: int) -> float:
    """
    Compute recall@k: fraction of baseline_ids[:k] that appear in candidate_ids[:k].

    Args:
        baseline_ids:   Ground-truth ranked list (e.g., ChromaDB results).
        candidate_ids:  Candidate ranked list (e.g., Weaviate or Qdrant results).
        k:              Evaluation depth (top-k cutoff).

    Returns:
        Float in [0.0, 1.0]. Example: recall_at_k(["a","b","c"], ["a","c","d"], k=3)
        returns 0.6666... (2 overlapping IDs / k=3).
    """
    if k == 0:
        return 0.0
    baseline_set = set(baseline_ids[:k])
    candidate_set = set(candidate_ids[:k])
    return len(baseline_set & candidate_set) / k
