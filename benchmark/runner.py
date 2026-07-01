"""
Benchmark runner CLI for vector DB performance evaluation.

Orchestrates upsert → benchmark → JSON report across Weaviate and Qdrant.
All 10 benchmark dimensions: upsert speed, serial latency, filtered/unfiltered latency,
scalability curve, latency-under-load, memory delta, cold/warm latency, determinism, recall@k.

Usage:
    pipenv run py benchmark/runner.py --help
    pipenv run py benchmark/runner.py --db weaviate --upsert-limit 10 --query-limit 10
    pipenv run py benchmark/runner.py --db all --upsert-limit 50 --query-limit 50
"""

import argparse
import json
import logging
import math
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import weaviate

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.metrics import (
    ConcurrencyMetrics,
    MemoryMetrics,
    QueryMetrics,
    ScalabilityCurveEntry,
    UpsertMetrics,
    recall_at_k,
)
from benchmark.queries import CANONICAL_QUERIES
from config.schemas import PARAGRAPH_CONFIG
from db import content_db, core_db
from extractors.phase3_citation_extraction import fetch_all_books
from extractors.phase5_validation import validate_talk
from extractors.pipeline import process_talk_pipeline
from loaders import BaseLoader
from loaders.embeddings import embed, embed_batch
from loaders.qdrant_loader import QdrantLoader
from loaders.weaviate_loader import WeaviateLoader
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _get_all_gc_talk_ids() -> list[int]:
    """Return all GC talk IDs from core DB ordered by ID (identical to scripts/run_pipeline.py)."""
    rows = core_db.select(
        "SELECT t.ID FROM talk t INNER JOIN conference_talk ct ON ct.TalkID = t.ID ORDER BY t.ID"
    )
    return [row["ID"] for row in rows]


def _compute_query_metrics(latencies_ms: list[float], failed: int = 0) -> QueryMetrics:
    """Derive QueryMetrics from a list of per-query latency samples (in milliseconds)."""
    if not latencies_ms:
        return QueryMetrics(
            p50_ms=0.0, p95_ms=0.0, p99_ms=0.0,
            mean_ms=0.0, min_ms=0.0, max_ms=0.0,
            query_count=0, failed_queries=failed,
        )
    sorted_lat = sorted(latencies_ms)
    n = len(sorted_lat)

    def percentile(p: float) -> float:
        # Nearest-rank (1-based): rank = ceil(p/100 * n), then convert to 0-based index
        idx = max(0, math.ceil(p / 100.0 * n) - 1)
        return sorted_lat[idx]

    return QueryMetrics(
        p50_ms=percentile(50),
        p95_ms=percentile(95),
        p99_ms=percentile(99),
        mean_ms=statistics.mean(latencies_ms),
        min_ms=min(latencies_ms),
        max_ms=max(latencies_ms),
        query_count=n,
        failed_queries=failed,
    )


def _poll_memory(samples: list[int], stop_event: threading.Event, interval_s: float = 0.150) -> None:
    """Background daemon: poll process RSS every ~150ms until stop_event is set.

    Appends RSS values in bytes (int) to samples.
    """
    proc = psutil.Process()
    while not stop_event.is_set():
        samples.append(proc.memory_info().rss)
        time.sleep(interval_s)


# ---------------------------------------------------------------------------
# Thread-local storage for per-thread loader instances (D-05)
# ---------------------------------------------------------------------------
_tls = threading.local()
_worker_loaders_lock = threading.Lock()
_worker_loaders: list = []


def _init_worker(db_name: str, config: "argparse.Namespace") -> None:
    """ThreadPoolExecutor initializer: create a per-thread loader and track for explicit close."""
    _tls.loader = _build_loader(db_name, config)
    with _worker_loaders_lock:
        _worker_loaders.append(_tls.loader)


# ---------------------------------------------------------------------------
# BenchmarkRunner class
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """
    Orchestrates all 10 benchmark dimensions for a single vector DB.

    Args:
        loader:   Concrete loader instance (WeaviateLoader or QdrantLoader).
        queries:  CANONICAL_QUERIES list (8 entries from benchmark/queries.py).
        config:   Parsed argparse.Namespace with: upsert_limit, query_limit, workers, output.
        db_name:  String identifier for the DB ("weaviate", "qdrant").
    """

    def __init__(
        self,
        loader: BaseLoader,
        queries: list[dict[str, Any]],
        config: argparse.Namespace,
        db_name: str,
    ) -> None:
        """
        Initialize the benchmark runner for a single vector DB.

        Args:
            loader:   Concrete loader instance (WeaviateLoader or QdrantLoader).
            queries:  CANONICAL_QUERIES list (8 entries from benchmark/queries.py).
            config:   Parsed argparse.Namespace with upsert_limit, query_limit, workers, output.
            db_name:  String identifier for the DB ("weaviate", "qdrant").
        """
        self._loader = loader
        self._queries = queries
        self._config = config
        self._db_name = db_name
        self._book_cache: dict = {}  # populated in run_upsert_phase()
        self._talk_ids: list[int] = []  # populated in run_upsert_phase()
        self.results: dict[str, Any] = {
            "db": db_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # -----------------------------------------------------------------------
    # Helper methods
    # -----------------------------------------------------------------------

    def _query_db(self, query: dict[str, Any]) -> list[str] | None:
        """Issue one canonical query; return list of result IDs.

        Returns:
            list[str]: Query results (may be empty if the collection has no matches).
            None:      Query raised an exception (genuine failure).
        """
        try:
            return self._loader.query(
                collection=query["collection"],
                query_text=query["query_text"],
                k=query["k"],
                filter=query.get("filter"),
            )
        except Exception as e:
            logger.warning("Query failed [%s] %s: %s", self._db_name, query["query_text"][:40], e)
            return None

    def _timed_query(self, q: dict[str, Any]) -> float | None:
        """Issue one query and return latency in ms, or None on failure."""
        try:
            t0 = time.monotonic()
            self._loader.query(
                collection=q["collection"],
                query_text=q["query_text"],
                k=q["k"],
                filter=q.get("filter"),
            )
            return (time.monotonic() - t0) * 1000.0
        except Exception as e:
            logger.warning("[%s] concurrent query failed: %s", self._db_name, e)
            return None

    # -----------------------------------------------------------------------
    # Measurement methods (ordered per run_all() call sequence in Plan 03)
    # -----------------------------------------------------------------------

    def run_memory_upsert(self) -> None:
        """
        Capture RSS baseline and start background polling before upsert starts (D-07).
        After upsert completes, call _finalize_memory_upsert() to stop polling and record the peak.
        Stores intermediate state in self._mem_upsert_baseline_bytes, self._mem_upsert_samples,
        self._mem_upsert_stop, and self._mem_upsert_poller.
        """
        proc = psutil.Process()
        self._mem_upsert_baseline_bytes = proc.memory_info().rss
        self._mem_upsert_samples: list[int] = []
        self._mem_upsert_stop = threading.Event()
        self._mem_upsert_poller = threading.Thread(
            target=_poll_memory, args=(self._mem_upsert_samples, self._mem_upsert_stop), daemon=True
        )
        self._mem_upsert_poller.start()
        logger.info("[%s] memory upsert baseline: %.1f MB", self._db_name, self._mem_upsert_baseline_bytes / 1024**2)

    def _finalize_memory_upsert(self) -> None:
        self._mem_upsert_stop.set()
        self._mem_upsert_poller.join(timeout=1.0)
        baseline_mb = self._mem_upsert_baseline_bytes / 1024**2
        peak_bytes = max(self._mem_upsert_samples) if self._mem_upsert_samples else self._mem_upsert_baseline_bytes
        peak_mb = peak_bytes / 1024**2
        self.results["memory_upsert"] = asdict(MemoryMetrics(
            baseline_mb=baseline_mb,
            peak_mb=peak_mb,
            delta_mb=peak_mb - baseline_mb,
        ))

    def run_upsert_phase(self) -> UpsertMetrics:
        """
        Load all --upsert-limit talks from SQLite into the target DB.
        Enforces the load gate: ALL upserts complete before method returns.
        Records UpsertMetrics and stores in self.results["upsert"].
        """
        all_ids = _get_all_gc_talk_ids()
        if self._config.upsert_limit is not None:
            talk_ids = all_ids[: self._config.upsert_limit]
        else:
            talk_ids = all_ids
        self._talk_ids = talk_ids

        book_cache = fetch_all_books(core_db)
        self._book_cache = book_cache

        logger.info("[%s] load gate: upserting %d talks", self._db_name, len(talk_ids))
        total_records = 0
        t0 = time.monotonic()

        def _load_one_talk(talk_id: int) -> int:
            """Worker: process pipeline + load one talk. Returns 1 on success, 0 on skip/error."""
            try:
                result = process_talk_pipeline(content_db, core_db, talk_id, book_cache, PARAGRAPH_CONFIG)
                if not result.success:
                    logger.warning(
                        "[%s] pipeline failed talk_id=%d: %s",
                        self._db_name,
                        talk_id,
                        "; ".join(result.errors),
                    )
                    return 0
                validation = validate_talk(
                    result.metadata, result.paragraphs, result.citations, result.footnotes, db=core_db
                )
                if not validation.is_valid:
                    logger.warning("[%s] validation failed talk_id=%d", self._db_name, talk_id)
                    return 0
                bundle = (result.metadata, result.paragraphs, result.citations, result.footnotes, validation)
                _tls.loader.load(bundle)
                return 1
            except Exception as e:
                logger.warning("[%s] upsert error talk_id=%d: %s", self._db_name, talk_id, e)
                return 0

        # Reset per-pool tracker so only this pool's loaders are closed after exit
        with _worker_loaders_lock:
            _worker_loaders.clear()

        with ThreadPoolExecutor(
            max_workers=self._config.workers,
            initializer=_init_worker,
            initargs=(self._db_name, self._config),
        ) as executor:
            futures = {executor.submit(_load_one_talk, tid): tid for tid in talk_ids}
            for fut in as_completed(futures):
                total_records += fut.result()

        # Close worker loaders immediately after pool exits (not deferred to process exit).
        with _worker_loaders_lock:
            for ldr in _worker_loaders:
                ldr.close()
            _worker_loaders.clear()

        elapsed = time.monotonic() - t0
        rps = total_records / elapsed if elapsed > 0 else 0.0
        metrics = UpsertMetrics(total_records=total_records, elapsed_seconds=elapsed, records_per_second=rps)
        self.results["upsert"] = asdict(metrics)
        logger.info("[%s] load gate cleared: %d records in %.1fs", self._db_name, total_records, elapsed)
        return metrics

    def run_cold_warm(self) -> None:
        """
        Cold: issue first canonical query immediately after load gate clears.
        Warm: issue the same query 9 more times consecutively; record mean.
        Stores cold_ms, warm_mean_ms, query_text in self.results["cold_warm"].
        ORDERING: This method MUST be the first query-issuing call after run_upsert_phase().
        """
        q = self._queries[0]
        t0 = time.monotonic()
        self._query_db(q)
        cold_ms = (time.monotonic() - t0) * 1000.0

        warm_samples: list[float] = []
        for _ in range(9):
            t1 = time.monotonic()
            self._query_db(q)
            warm_samples.append((time.monotonic() - t1) * 1000.0)

        warm_mean_ms = statistics.mean(warm_samples) if warm_samples else 0.0
        self.results["cold_warm"] = {
            "cold_ms": cold_ms,
            "warm_mean_ms": warm_mean_ms,
            "query_text": q["query_text"],
        }
        logger.info("[%s] cold=%.1fms warm_mean=%.1fms", self._db_name, cold_ms, warm_mean_ms)

    def run_serial_latency(self) -> QueryMetrics:
        """
        Issue --query-limit canonical queries sequentially (1 thread).
        Cycles through CANONICAL_QUERIES to fill the query budget.
        Stores QueryMetrics in self.results["query_latency_serial"].
        """
        latencies: list[float] = []
        failed = 0
        queries = [self._queries[i % len(self._queries)] for i in range(self._config.query_limit)]
        for q in queries:
            t0 = time.monotonic()
            ids = self._query_db(q)
            elapsed = (time.monotonic() - t0) * 1000.0
            if ids is None:
                failed += 1
            else:
                latencies.append(elapsed)
        metrics = _compute_query_metrics(latencies, failed)
        self.results["query_latency_serial"] = asdict(metrics)
        logger.info("[%s] serial latency p50=%.1fms p99=%.1fms", self._db_name, metrics.p50_ms, metrics.p99_ms)
        return metrics

    def run_filtered_unfiltered(self) -> None:
        """
        Segregate CANONICAL_QUERIES by filter is None (6 unfiltered, 2 filtered).
        Issue each group's queries; store separate QueryMetrics blocks.
        Stores results in self.results["query_latency_unfiltered"] and ["query_latency_filtered"].
        """
        unfiltered = [q for q in self._queries if q.get("filter") is None]
        filtered = [q for q in self._queries if q.get("filter") is not None]

        def _run_group(group: list[dict]) -> QueryMetrics:
            lats: list[float] = []
            fails = 0
            for q in group:
                t0 = time.monotonic()
                ids = self._query_db(q)
                elapsed = (time.monotonic() - t0) * 1000.0
                if ids is None:
                    fails += 1
                else:
                    lats.append(elapsed)
            return _compute_query_metrics(lats, fails)

        uf_metrics = _run_group(unfiltered) if unfiltered else None
        f_metrics = _run_group(filtered) if filtered else None
        self.results["query_latency_unfiltered"] = asdict(uf_metrics) if uf_metrics else None
        self.results["query_latency_filtered"] = asdict(f_metrics) if f_metrics else None
        logger.info(
            "[%s] unfiltered q_count=%d filtered q_count=%d",
            self._db_name,
            uf_metrics.query_count if uf_metrics else 0,
            f_metrics.query_count if f_metrics else 0,
        )

    def run_scalability_curve(self) -> list[ScalabilityCurveEntry]:
        """
        Issue --query-limit queries at each of [1, 5, 10, 20] workers via ThreadPoolExecutor.
        Same total query count at every level for fair QPS comparison.
        Stores list[ScalabilityCurveEntry] in self.results["scalability_curve"].
        """
        worker_levels = [1, 5, 10, 20]
        curve: list[ScalabilityCurveEntry] = []
        queries_pool = [self._queries[i % len(self._queries)] for i in range(self._config.query_limit)]

        for n_workers in worker_levels:
            latencies: list[float] = []
            t_start = time.monotonic()
            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                futures = [executor.submit(self._timed_query, q) for q in queries_pool]
                for fut in as_completed(futures):
                    ms = fut.result()
                    if ms is not None:
                        latencies.append(ms)
            elapsed = time.monotonic() - t_start
            qps = len(latencies) / elapsed if elapsed > 0 else 0.0
            qm = _compute_query_metrics(latencies)
            entry = ScalabilityCurveEntry(
                workers=n_workers,
                throughput_qps=qps,
                p50_ms=qm.p50_ms,
                p95_ms=qm.p95_ms,
                p99_ms=qm.p99_ms,
            )
            curve.append(entry)
            logger.info("[%s] scalability workers=%d qps=%.1f p50=%.1fms", self._db_name, n_workers, qps, qm.p50_ms)

        self.results["scalability_curve"] = [asdict(e) for e in curve]
        return curve

    def run_memory_query(self) -> None:
        """
        Measure peak RSS during a concurrent query phase using a background daemon thread.
        Runs --query-limit queries at --workers concurrency while polling RSS at ~150ms.
        Stores MemoryMetrics in self.results["memory_query"].
        """
        proc = psutil.Process()
        baseline_bytes = proc.memory_info().rss
        samples: list[int] = []  # RSS in bytes
        stop_event = threading.Event()
        poller = threading.Thread(target=_poll_memory, args=(samples, stop_event), daemon=True)
        poller.start()

        queries_pool = [self._queries[i % len(self._queries)] for i in range(self._config.query_limit)]
        with ThreadPoolExecutor(max_workers=self._config.workers) as executor:
            futures = [executor.submit(self._timed_query, q) for q in queries_pool]
            for fut in as_completed(futures):
                fut.result()  # drain results

        stop_event.set()
        poller.join(timeout=1.0)

        peak_bytes = max(samples) if samples else baseline_bytes
        baseline_mb = baseline_bytes / 1024**2
        peak_mb = peak_bytes / 1024**2
        self.results["memory_query"] = asdict(MemoryMetrics(
            baseline_mb=baseline_mb,
            peak_mb=peak_mb,
            delta_mb=peak_mb - baseline_mb,
        ))
        logger.info("[%s] memory query baseline=%.1fMB peak=%.1fMB", self._db_name, baseline_mb, peak_mb)

    def run_latency_under_load(self) -> None:
        """
        Compute latency_degradation_ratio = p50_at_N_workers / p50_serial.
        N = --workers (default 10). Reads from self.results["scalability_curve"].
        Stores ConcurrencyMetrics in self.results["concurrency"].
        Requires run_serial_latency() and run_scalability_curve() to have run first.
        """
        serial_p50 = self.results["query_latency_serial"]["p50_ms"]
        curve = self.results["scalability_curve"]
        # Find scalability_curve entry matching --workers
        n = self._config.workers
        entry = next((e for e in curve if e["workers"] == n), None)
        if entry is None:
            # Fall back to the last entry if --workers is not in [1,5,10,20]
            entry = curve[-1] if curve else {"workers": n, "throughput_qps": 0.0, "p50_ms": 0.0}

        ratio = entry["p50_ms"] / serial_p50 if serial_p50 > 0 else 1.0
        total_queries = self._config.query_limit
        elapsed = total_queries / entry["throughput_qps"] if entry["throughput_qps"] > 0 else 0.0
        self.results["concurrency"] = asdict(ConcurrencyMetrics(
            workers=entry["workers"],
            total_queries=total_queries,
            elapsed_seconds=elapsed,
            throughput_qps=entry["throughput_qps"],
        )) | {"latency_degradation_ratio": ratio}
        logger.info("[%s] latency_degradation_ratio=%.2f at %d workers", self._db_name, ratio, n)

    def run_determinism(self) -> None:
        """
        Issue each canonical query 10 times; compute Jaccard stability score.
        Jaccard = |intersection of all 10 run ID sets| / |union of all 10 run ID sets|.
        Score=1.0 means all 10 runs returned identical top-k IDs.
        Stores list of {query_text, stability_score} in self.results["determinism"].
        """
        determinism_results = []
        for q in self._queries:
            all_id_sets: list[set[str]] = []
            for _ in range(10):
                ids = self._query_db(q)
                all_id_sets.append(set(ids) if ids is not None else set())
            if all_id_sets:
                intersection = set.intersection(*all_id_sets)
                union = set.union(*all_id_sets)
                score = len(intersection) / len(union) if union else 1.0
            else:
                score = 0.0
            determinism_results.append({"query_text": q["query_text"], "stability_score": score})
            logger.info("[%s] determinism '%s...' score=%.3f", self._db_name, q["query_text"][:30], score)
        self.results["determinism"] = determinism_results

    def run_recall(self, chroma_baseline: dict[str, list[str]] | None = None) -> None:
        """
        Compute mean recall@k10 and recall@k50 against a ground-truth baseline.
        chroma_baseline: dict mapping query_text -> list of ground-truth result IDs.
        If None (no baseline available): self.results["recall"] = None.
        """
        if chroma_baseline is None:
            self.results["recall"] = None
            logger.info("[%s] recall: null (no baseline available)", self._db_name)
            return

        k10_scores: list[float] = []
        k50_scores: list[float] = []
        for q in self._queries:
            baseline_ids = chroma_baseline.get(q["query_text"], [])
            # Do NOT skip empty baselines — they contribute recall=0.0 to the mean,
            # keeping the denominator consistent across all N queries.
            candidate_ids = self._query_db(q) or []
            k10_scores.append(recall_at_k(baseline_ids, candidate_ids, k=10))
            # For k50, re-query with k=50
            try:
                candidate_ids_50 = self._loader.query(
                    collection=q["collection"],
                    query_text=q["query_text"],
                    k=50,
                    filter=q.get("filter"),
                )
            except Exception:
                candidate_ids_50 = candidate_ids
            if len(baseline_ids) < 50:
                logger.debug(
                    "[%s] recall@k50: baseline has only %d results for '%s'",
                    self._db_name, len(baseline_ids), q["query_text"],
                )
            k50_scores.append(recall_at_k(baseline_ids, candidate_ids_50, k=50))

        mean_k10 = statistics.mean(k10_scores) if k10_scores else 0.0
        mean_k50 = statistics.mean(k50_scores) if k50_scores else 0.0
        self.results["recall"] = {"mean_k10": mean_k10, "mean_k50": mean_k50}
        logger.info("[%s] recall@k10=%.3f recall@k50=%.3f", self._db_name, mean_k10, mean_k50)

    def run_all(self, chroma_baseline: "dict[str, list[str]] | None" = None) -> dict:
        """
        Sequence all 10 benchmark dimensions in order.
        Returns the assembled report dict (self.results) ready for JSON serialization.

        ORDERING CONTRACT (SPEC Req 10):
            1. run_memory_upsert()        — capture RSS baseline BEFORE upsert starts
            2. run_upsert_phase()         — load gate; all upserts complete before return
            3. _finalize_memory_upsert()  — capture RSS AFTER upsert completes
            4. run_cold_warm()            — FIRST query after load gate clears (cold read)
            5. run_serial_latency()       — serial p50/p95/p99 at 1 worker
            6. run_filtered_unfiltered()  — split QueryMetrics by filter presence
            7. run_scalability_curve()    — [1,5,10,20] workers, same --query-limit at each
            8. run_memory_query()         — peak RSS during concurrent query phase
            9. run_latency_under_load()   — degradation ratio from scalability_curve
           10. run_determinism()          — Jaccard stability across 10 runs per query
           11. run_recall() — recall@k (always null; no baseline DB)

        Args:
            chroma_baseline: Reserved for future use. Always None (no baseline DB available).
        """
        logger.info("[%s] === benchmark start ===", self._db_name)

        # Step 1: Memory baseline before upsert
        self.run_memory_upsert()

        # Step 2: Load gate — all upserts complete before ANY query
        self.run_upsert_phase()

        # Step 3: Memory after upsert
        self._finalize_memory_upsert()

        # Step 4: Cold/warm — MUST be the first query-issuing method after load gate
        self.run_cold_warm()

        # Steps 5–9: Query benchmarks
        self.run_serial_latency()
        self.run_filtered_unfiltered()
        self.run_scalability_curve()
        self.run_memory_query()
        self.run_latency_under_load()
        self.run_determinism()

        # Step 10: recall@k (null — no baseline DB)
        self.run_recall(chroma_baseline)

        logger.info("[%s] === benchmark complete ===", self._db_name)
        return self.results


# ---------------------------------------------------------------------------
# Module-level functions: CLI, report writing, loader factory, baseline
# ---------------------------------------------------------------------------

def _write_report(report: dict, output_dir: str) -> Path:
    """
    Write report dict to {output_dir}/{db}_{YYYYMMDD_HHMMSS}.json.
    Creates output_dir if it does not exist (mkdir -p).
    Returns the Path of the written file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    db = report.get("db", "unknown")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = out / f"{db}_{ts}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info("Report written: %s", filename)
    return filename


def _build_loader(db_name: str, config: argparse.Namespace) -> BaseLoader:
    """Instantiate the correct loader for db_name, injecting a pre-built client."""
    if db_name == "weaviate":
        client = weaviate.connect_to_local(
            host=os.environ.get("BENCHMARK_WEAVIATE_HOST", "localhost"),
            port=int(os.environ.get("BENCHMARK_WEAVIATE_PORT", "8080")),
            grpc_port=int(os.environ.get("BENCHMARK_WEAVIATE_GRPC_PORT", "50051")),
        )
        return WeaviateLoader(
            client=client,
            embed_fn=embed_batch,
            batch_size=100,
        )
    elif db_name == "qdrant":
        client = QdrantClient(
            host=os.environ.get("BENCHMARK_QDRANT_HOST", "localhost"),
            port=int(os.environ.get("BENCHMARK_QDRANT_PORT", "6333")),
        )
        return QdrantLoader(
            client=client,
            embed_fn=embed_batch,
            batch_size=100,
        )
    else:
        raise ValueError(f"Unknown db: {db_name!r}. Must be one of: weaviate, qdrant")



def _build_argparser() -> argparse.ArgumentParser:
    """Build the argparse CLI definition per SPEC Req 1."""
    parser = argparse.ArgumentParser(
        description="Run vector DB performance benchmarks and emit a structured JSON report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db",
        choices=["weaviate", "qdrant", "all"],
        default="all",
        help="Target DB to benchmark. 'all' benchmarks both in order: weaviate -> qdrant.",
    )
    parser.add_argument(
        "--upsert-limit",
        type=int,
        default=None,
        dest="upsert_limit",
        help="Number of talks to load from SQLite into the target DB. Load all talks if not specified.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Delete and recreate collections before loading. Scope matches --db (per D-01).",
    )
    parser.add_argument(
        "--query-limit",
        type=int,
        default=100,
        dest="query_limit",
        help="Total number of queries to issue per benchmark dimension (cycled through CANONICAL_QUERIES).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Worker count for upsert parallelism and latency-under-load measurement. Default 10.",
    )
    parser.add_argument(
        "--output",
        default="benchmark/results/",
        help="Directory to write JSON report files. Created if absent.",
    )
    return parser


def main() -> None:
    """
    Iterate over resolved DB list, run all benchmark dimensions per DB, write JSON reports.

    DB ordering for --db all: weaviate -> qdrant.

    Error handling:
    - A target DB unreachable at connection time: log ERROR, skip that DB, continue, exit non-zero.
    """
    parser = _build_argparser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    if args.db == "all":
        db_list = ["weaviate", "qdrant"]
    else:
        db_list = [args.db]

    # Validate Ollama reachability before starting any DB work.
    try:
        embed("hello", model="nomic-embed-text")
    except Exception as e:
        logger.error("Ollama unreachable: %s — ensure Ollama is running with nomic-embed-text pulled", e)
        sys.exit(1)

    had_failure = False

    for db_name in db_list:
        loader: "BaseLoader | None" = None

        # Pre-flight: reset collections before loading.
        # Reset creates a temporary client, deletes collections, then returns.
        # The subsequent _build_loader() call will recreate them via _ensure_schema.
        if args.reset:
            try:
                if db_name == "weaviate":
                    WeaviateLoader.reset(
                        host=os.environ.get("BENCHMARK_WEAVIATE_HOST", "localhost"),
                        port=int(os.environ.get("BENCHMARK_WEAVIATE_PORT", "8080")),
                        grpc_port=int(os.environ.get("BENCHMARK_WEAVIATE_GRPC_PORT", "50051")),
                    )
                elif db_name == "qdrant":
                    QdrantLoader.reset(
                        host=os.environ.get("BENCHMARK_QDRANT_HOST", "localhost"),
                        port=int(os.environ.get("BENCHMARK_QDRANT_PORT", "6333")),
                    )
                logger.info("[%s] reset complete — collections deleted, loader will recreate", db_name)
            except Exception as e:
                logger.error("[%s] reset failed: %s — aborting this DB", db_name, e)
                had_failure = True
                continue

        try:
            loader = _build_loader(db_name, args)
        except Exception as e:
            logger.error("[%s] Failed to connect to DB: %s — skipping", db_name, e)
            had_failure = True
            continue

        try:
            runner = BenchmarkRunner(
                loader=loader,
                queries=CANONICAL_QUERIES,
                config=args,
                db_name=db_name,
            )
            report = runner.run_all()
            _write_report(report, args.output)
        except Exception as e:
            logger.error("[%s] Benchmark failed: %s", db_name, e)
            had_failure = True
        finally:
            if loader is not None:
                loader.close()

    if had_failure:
        sys.exit(1)


if __name__ == "__main__":
    main()
