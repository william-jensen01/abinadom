"""
Unit tests for benchmark/metrics.py and benchmark/queries.py.

Tests all four metric dataclasses, recall_at_k, and CANONICAL_QUERIES structure.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest
from benchmark.metrics import (
    QueryMetrics,
    UpsertMetrics,
    ConcurrencyMetrics,
    MemoryMetrics,
    recall_at_k,
)
from benchmark.queries import CANONICAL_QUERIES


# =============================================================================
# Tests: UpsertMetrics
# =============================================================================


class TestUpsertMetrics:
    def test_instantiation(self):
        """UpsertMetrics can be constructed and fields are accessible."""
        m = UpsertMetrics(total_records=10, elapsed_seconds=1.5, records_per_second=6.67)
        assert m.total_records == 10
        assert m.elapsed_seconds == 1.5
        assert m.records_per_second == 6.67

    def test_zero_records(self):
        """UpsertMetrics accepts zero records (empty upsert run)."""
        m = UpsertMetrics(total_records=0, elapsed_seconds=0.0, records_per_second=0.0)
        assert m.total_records == 0


# =============================================================================
# Tests: QueryMetrics
# =============================================================================


class TestQueryMetrics:
    def test_instantiation_with_defaults(self):
        """QueryMetrics can be constructed; failed_queries defaults to 0."""
        m = QueryMetrics(
            p50_ms=10.0,
            p95_ms=20.0,
            p99_ms=30.0,
            mean_ms=15.0,
            min_ms=5.0,
            max_ms=35.0,
            query_count=100,
        )
        assert m.p50_ms == 10.0
        assert m.p95_ms == 20.0
        assert m.p99_ms == 30.0
        assert m.mean_ms == 15.0
        assert m.min_ms == 5.0
        assert m.max_ms == 35.0
        assert m.query_count == 100
        assert m.failed_queries == 0  # default

    def test_failed_queries_can_be_set(self):
        """failed_queries can be explicitly provided."""
        m = QueryMetrics(
            p50_ms=10.0,
            p95_ms=20.0,
            p99_ms=30.0,
            mean_ms=15.0,
            min_ms=5.0,
            max_ms=35.0,
            query_count=100,
            failed_queries=3,
        )
        assert m.failed_queries == 3


# =============================================================================
# Tests: ConcurrencyMetrics
# =============================================================================


class TestConcurrencyMetrics:
    def test_instantiation(self):
        """ConcurrencyMetrics can be constructed and all fields are accessible."""
        m = ConcurrencyMetrics(
            workers=4,
            total_queries=100,
            elapsed_seconds=10.0,
            throughput_qps=10.0,
        )
        assert m.workers == 4
        assert m.total_queries == 100
        assert m.elapsed_seconds == 10.0
        assert m.throughput_qps == 10.0


# =============================================================================
# Tests: MemoryMetrics
# =============================================================================


class TestMemoryMetrics:
    def test_instantiation(self):
        """MemoryMetrics can be constructed and all fields are accessible."""
        m = MemoryMetrics(baseline_mb=100.0, peak_mb=150.0, delta_mb=50.0)
        assert m.baseline_mb == 100.0
        assert m.peak_mb == 150.0
        assert m.delta_mb == 50.0


# =============================================================================
# Tests: recall_at_k
# =============================================================================


class TestRecallAtK:
    def test_spec_acceptance_criterion(self):
        """SPEC Req 5 acceptance criterion: 2 of 3 candidates overlap -> 2/3."""
        result = recall_at_k(["a", "b", "c"], ["a", "c", "d"], k=3)
        assert abs(result - 2 / 3) < 1e-9

    def test_k_zero_returns_zero(self):
        """k=0 always returns 0.0 (no candidates to evaluate)."""
        result = recall_at_k(["a"], ["a"], k=0)
        assert result == 0.0

    def test_perfect_overlap(self):
        """All candidates present in retrieved set -> 1.0."""
        result = recall_at_k(["a", "b", "c"], ["a", "b", "c"], k=3)
        assert result == 1.0

    def test_no_overlap(self):
        """No candidates present in retrieved set -> 0.0."""
        result = recall_at_k(["a", "b", "c"], ["d", "e", "f"], k=3)
        assert result == 0.0

    def test_k_truncates_retrieved_list(self):
        """Only first k items of the retrieved list are considered."""
        # retrieved has "a" at position 4 (beyond k=2), so it should NOT count
        result = recall_at_k(["a"], ["x", "y", "a"], k=2)
        assert result == 0.0


# =============================================================================
# Tests: CANONICAL_QUERIES
# =============================================================================


class TestCanonicalQueries:
    def test_minimum_count(self):
        """CANONICAL_QUERIES must have at least 7 entries."""
        assert len(CANONICAL_QUERIES) >= 7

    def test_all_have_required_keys(self):
        """Every entry must have query_text, k, collection, and filter keys."""
        required_keys = {"query_text", "k", "collection", "filter"}
        for q in CANONICAL_QUERIES:
            assert required_keys.issubset(q.keys()), (
                f"Query missing keys: {required_keys - set(q.keys())} in {q}"
            )

    def test_all_have_k_ten(self):
        """Every entry must have k == 10 (SPEC Req 6 and CONTEXT D-08)."""
        for q in CANONICAL_QUERIES:
            assert q["k"] == 10, f"Expected k=10, got k={q['k']} in {q}"

    def test_has_john_filter(self):
        """At least one entry must have filter == {'book_name': 'John'} (CONTEXT D-10)."""
        has_john = any(
            q.get("filter", {}).get("book_name") == "John"
            for q in CANONICAL_QUERIES
        )
        assert has_john, "No CANONICAL_QUERIES entry with filter={'book_name': 'John'}"

    def test_all_collections_are_strings(self):
        """The collection field must be a non-empty string in every entry."""
        for q in CANONICAL_QUERIES:
            assert isinstance(q["collection"], str) and q["collection"], (
                f"Invalid collection value in {q}"
            )

    def test_all_query_texts_are_strings(self):
        """The query_text field must be a non-empty string in every entry."""
        for q in CANONICAL_QUERIES:
            assert isinstance(q["query_text"], str) and q["query_text"], (
                f"Invalid query_text in {q}"
            )
