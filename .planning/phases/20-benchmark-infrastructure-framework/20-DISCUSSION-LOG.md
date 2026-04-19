# Phase 20: Benchmark Infrastructure & Framework - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-18
**Phase:** 20-benchmark-infrastructure-framework
**Areas discussed:** prepare_* extraction strategy, Metric dataclass fields, Canonical query content

---

## prepare_* Extraction Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Move + thin re-export in phase6 | Functions move to shared_transforms.py; phase6 gets import block | ✓ |
| Independent implementation in shared_transforms | Fresh implementations with phase6 untouched | |
| Phase6 imports from shared_transforms (reverse) | shared_transforms is clean; phase6 imports from it internally | |

**User's choice:** Move + thin re-export in phase6

---

### Follow-up: test_phase6.py backward compatibility

| Option | Description | Selected |
|--------|-------------|----------|
| Add backward-compat alias | phase6 keeps `_flatten_metadata = flatten_metadata` | ✓ |
| Update test_phase6 imports | Change test_phase6 to import from loaders.shared_transforms | |

**User's choice:** Add backward-compat alias (`_flatten_metadata = flatten_metadata` in phase6)

---

## Metric Dataclass Fields

### QueryMetrics

| Option | Description | Selected |
|--------|-------------|----------|
| p50 / p95 / p99 + mean | Standard latency profile | |
| p50 / p95 / p99 + mean + min/max | Full latency profile with outlier detection | ✓ |

**User's choice:** Full latency profile (p50/p95/p99/mean/min/max + query_count + failed_queries=0)

### UpsertMetrics / ConcurrencyMetrics / MemoryMetrics

| Option | Description | Selected |
|--------|-------------|----------|
| Standard minimal set | No error tracking fields | ✓ |
| Add error tracking | Each dataclass gets error_count field | |

**User's choice:** Standard minimal set

---

## Canonical Query Content

### Thematic Domains (paragraph queries)

| Option | Selected |
|--------|----------|
| Doctrinal core (faith, atonement, resurrection, eternal family, repentance) | ✓ |
| Scripture application (how prophets applied specific scriptures) | ✓ |
| Historical/prophetic events (Restoration, pioneers, Joseph Smith) | ✓ |
| Practical living (family prayer, Sabbath, temple, missionary work) | ✓ |

**User's choice:** All 4 themes selected

### Citation Query Filter

| Option | Description | Selected |
|--------|-------------|----------|
| book_name filter | `{"book_name": "John"}` on a citation query | ✓ |
| conference_year filter | Filter paragraphs to a specific year | |

**User's choice:** `book_name` filter — e.g., `{"query_text": "light of the world", "k": 10, "collection": "citations", "filter": {"book_name": "John"}}`

### k Value

| Option | Selected |
|--------|----------|
| k=10 | ✓ |
| k=5 | |
| Mixed | |

**User's choice:** k=10 for all queries

---

## Claude's Discretion

- Exact query text strings within approved themes
- Docker image tags for Weaviate and Qdrant (not selected for discussion)
- `TalkBundle` type definition if needed

## Deferred Ideas

- Docker image version selection — researcher will determine stable recent versions
