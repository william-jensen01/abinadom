# Phase 4: Test Coverage - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Integration and edge-case tests that prove phases compose correctly and handle boundary conditions, including adversarial inputs. Three tracks: (1) end-to-end integration test across all phases with real DB, (2) Phase 1 edge case tests using in-memory SQLite fixtures, (3) Phase 5 adversarial tests for malformed and boundary inputs. No new extraction capabilities added.

</domain>

<decisions>
## Implementation Decisions

### Integration Test (QUAL-04)
- **D-01:** Connect to the real DB read-only (`db/core.52.db` + `db/content.52.db`). No fixtures or copied DB — tests run against actual data to catch real-world shape issues.
- **D-02:** Hardcode 3-5 specific `talk_id` values chosen during planning (one old/new era, one footnote-heavy, one citation-rich). Stable and explicit — Claude selects these during planning by querying the DB.
- **D-03:** Assert schema + non-empty at each phase boundary: required fields present with correct types, at least one record per phase. Catches contract breaks without being brittle to data changes.
- **D-04:** Run all phases 1–5 end-to-end. Include Phase 1 DB query — full integration path including the DB→Phase 1 boundary.
- **D-05:** New file: `tests/test_pipeline_integration.py` (exception to Phase 3 D-08 co-location pattern — integration test warrants its own file per QUAL-04 spec).

### Phase 1 Edge Cases (QUAL-05)
- **D-06:** Use in-memory SQLite fixtures (not real DB talk_ids, not mocked DB layer). Build minimal SQLite DBs with only the rows needed per test — consistent with existing Phase 2–4 approach of HTML fixture strings.
- **D-07:** All three edge cases are required: missing speaker, unusual session type (e.g., welfare/sustaining session), talk with no URL.

### Schema Validation (QUAL-06)
- **D-08:** Schema validation lives in `db/__init__.py` — runs when the DB module is first used, natural home since DB module already owns connection setup and is imported by every phase.
- **D-09:** Hard fail on mismatch — raise an exception that halts the pipeline immediately with a clear error message. No warn-and-continue.

### Phase 5 Adversarial Tests (QUAL-10)
- **D-10:** All four categories required:
  - Missing/None fields (e.g., `paragraph_id=None`, `talk_id=None`)
  - Wrong ID formulas (IDs that don't match expected pattern)
  - Empty collections (0 paragraphs, 0 citations, 0 footnotes)
  - Extreme counts (200+ paragraphs, very long text strings)
- **D-11:** Adversarial tests extend the existing `tests/test_phase5.py` — consistent with Phase 3 D-08 co-location pattern.

### Claude's Discretion
- Specific `talk_id` values to hardcode for integration tests (Claude queries DB during planning to find representative talks)
- Exact threshold values for "extreme counts" adversarial tests
- Which expected tables/columns to validate in schema check

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Test Coverage Requirements
- `.planning/REQUIREMENTS.md` §Code Quality (QUAL) — QUAL-04, QUAL-05, QUAL-06, QUAL-10 acceptance criteria

### Pipeline Architecture (for data contract assertions)
- `docs/PIPELINE_SPEC.md` — Phase-to-phase data contracts and output schemas for each phase

### Existing Test Patterns
- `tests/test_phase1.py` — Reference for Phase 1 test patterns (schema, validators, DB interaction)
- `tests/test_phase5.py` — Reference for Phase 5 test patterns (sanity checks, ChromaDB readiness)

### DB Module
- `db/__init__.py` — Where schema validation will be added; owns connection setup

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db/__init__.py` — DB connection module; schema validation added here (D-08)
- `extractors/pipeline.py` — `process_talk_pipeline()` orchestrates Phases 2–4 for a single talk; integration test should use this
- `config/pipeline_config.py` — Processing constants; integration tests use these rather than hardcoding
- `tests/test_phase5.py` — Existing Phase 5 test file; adversarial tests extend this

### Established Patterns
- Phase 2–4 tests use string HTML fixtures, not real DB — Phase 1 edge case tests follow same philosophy with in-memory SQLite
- `encoding='utf-8'` on all file I/O (Phase 1 fix) — applies to any test file I/O
- `logger = logging.getLogger(__name__)` — logging standard

### Integration Points
- `tests/test_pipeline_integration.py` — new file to create; uses real DB read-only with hardcoded talk_ids
- `db/__init__.py` — schema validation logic added here, called on DB open
- `tests/test_phase1.py` — Phase 1 edge case tests added here using in-memory SQLite fixtures
- `tests/test_phase5.py` — adversarial test cases added here

### Note: No test_pipeline_integration.py yet
The integration test file does not exist. Phase 1 edge case tests will extend the existing `tests/test_phase1.py`.

</code_context>

<specifics>
## Specific Ideas

- Integration test: Claude picks specific `talk_id` values during planning by querying `db/core.52.db` for representative talks (one early era, one recent, one footnote-heavy, one citation-rich, one with an unusual session).
- Schema validation: validate that expected tables (e.g., `talk`, `speaker`, `conference_talk`, etc.) and key columns exist on DB open — no need to validate every row, just structure.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-test-coverage*
*Context gathered: 2026-03-23*
