# Phase 4: Test Coverage - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-23
**Phase:** 04-test-coverage
**Areas discussed:** Integration test design, Edge case simulation, Schema validation behavior, Adversarial test scope

---

## Integration Test Design

| Option | Description | Selected |
|--------|-------------|----------|
| Real DB, read-only | Connect to db/core.52.db and db/content.52.db directly. Catches real-world shape issues, no fixtures to maintain. | ✓ |
| Copied test DB | Copy a slice of real DB into a test fixture DB. Stable but requires setup and may drift. | |
| You decide | Claude chooses based on existing test patterns. | |

**User's choice:** Real DB, read-only

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcode specific talk_ids | Pick representative talk_ids upfront. Stable and explicit. | ✓ |
| Query the DB dynamically | SELECT talks matching criteria at test time. Flexible but non-deterministic. | |
| You decide | Claude picks during planning. | |

**User's choice:** Hardcode specific talk_ids

| Option | Description | Selected |
|--------|-------------|----------|
| Schema + non-empty | Assert required fields with correct types and at least one record per phase. | ✓ |
| Exact counts | Assert exact paragraph/citation/footnote counts. Brittle to data changes. | |
| Cross-phase ID integrity only | Assert talk_id/paragraph_id resolve across phases only. | |

**User's choice:** Schema + non-empty

| Option | Description | Selected |
|--------|-------------|----------|
| All phases 1–5 end-to-end | Full pipeline including Phase 1 DB query. | ✓ |
| Phases 2–5 only | Use pre-built Phase 1 output as fixtures. | |

**User's choice:** All phases 1–5 end-to-end

---

## Edge Case Simulation

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory SQLite fixtures | Build minimal in-memory SQLite DBs per test. Consistent with existing HTML fixture approach. | ✓ |
| Real DB, specific talk_ids | Find real talks with missing data in core.52.db. Fragile if DB changes. | |
| Mock the DB layer | Patch Database class to return crafted Row dicts. Further from real behavior. | |

**User's choice:** In-memory SQLite fixtures

| Option | Description | Selected |
|--------|-------------|----------|
| All three required | Missing speaker, unusual session type, talk with no URL — all explicitly in QUAL-05. | ✓ |
| Missing speaker only | Smallest scope. | |
| You decide | Claude determines coverage from DB schema. | |

**User's choice:** All three required (missing speaker, unusual session, no URL)

---

## Schema Validation Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| In db/__init__.py | Runs when DB module is first used. Natural home — DB module owns connection setup. | ✓ |
| In phase1_talk_metadata.py | Runs at pipeline start. Awkward — schema validation is a DB concern. | |
| Standalone scripts/validate_schema.py | Explicit utility callable independently. Won't auto-run without orchestrator. | |

**User's choice:** In db/__init__.py

| Option | Description | Selected |
|--------|-------------|----------|
| Hard fail with clear error | Raise exception, halt pipeline immediately. Matches QUAL-06 requirement. | ✓ |
| Warn and continue | Log warning, let pipeline run. Risk of silent corruption. | |

**User's choice:** Hard fail with clear error

---

## Adversarial Test Scope

| Category | Selected |
|----------|----------|
| Missing/None fields (paragraph_id=None, talk_id=None) | ✓ |
| Wrong ID formulas (IDs not matching expected pattern) | ✓ |
| Empty collections (0 paragraphs, 0 citations, 0 footnotes) | ✓ |
| Extreme counts (200+ paragraphs, very long text) | ✓ |

**User's choice:** All four categories

| Option | Description | Selected |
|--------|-------------|----------|
| Extend test_phase5.py | Consistent with Phase 3 D-08 co-location pattern. | ✓ |
| New tests/test_phase5_adversarial.py | Isolated, runnable separately. More files. | |

**User's choice:** Extend test_phase5.py

---

## Claude's Discretion

- Specific talk_id values to hardcode for integration tests (queried from DB during planning)
- Exact threshold values for "extreme counts" adversarial tests
- Which tables/columns to validate in startup schema check

## Deferred Ideas

None — discussion stayed within phase scope.
