---
phase: 25
slug: data-model-book-resolver-extraction
status: final
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-05
updated: 2026-07-27
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (running unittest-style test classes — repo convention) |
| **Config file** | none (no pytest.ini/pyproject; tests use `sys.path.append` header pattern) |
| **Quick run command** | `pipenv run py -m pytest tests/test_html_parsing_utils.py tests/test_book_resolver.py tests/test_scripture_data.py tests/test_scripture_extraction.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -q` (live-service tests auto-skip via conftest port checks) |
| **Estimated runtime** | ~15 seconds (new unit tests); full suite dominated by skip-guarded live-DB reads |

The quick-run command names all four test targets the phase touches. Wave 1's three plans write to
three different files (`test_html_parsing_utils.py`, `test_book_resolver.py`,
`test_scripture_data.py`), so a per-plan run alone samples only one third of the phase; the
combined command is what makes the sampling rate meaningful across parallel plans. Files that do
not exist yet are skipped by pytest's collection error only if named alone — run the command from
Wave 1 onward, once each plan's first task has created its file.

---

## Sampling Rate

- **After every task commit:** Run the quick-run command above (all four targets).
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -q` — the 11 pre-existing test
  files must stay green, especially `tests/test_html_parsing_utils.py` after the `clean_verse_text`
  addition (25-01) and `tests/test_phase1.py` after the `EXPECTED_CORE_TABLES` change (25-04-01).
- **Before `/gsd-verify-work`:** Full suite green, including the live-DB 41,996 canonical-verse
  assertion (25-04-04) and the CLI stats demonstration (25-04-05).
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 25-01-01 | 01 | 1 | EXT-03 | T-25-01 | `clean_verse_text` no-residual-tag post-condition (no `<` survives markup input) | unit (synthetic) | `pipenv run py -m pytest tests/test_html_parsing_utils.py -x -q` | ✅ exists (extended) | ⬜ pending |
| 25-02-01 | 02 | 1 | EXT-04 | — | N/A | unit (synthetic) | `pipenv run py -m pytest tests/test_book_resolver.py -x -q` | ⬜ created by task | ⬜ pending |
| 25-02-02 | 02 | 1 | RES-01 | — | N/A | unit (synthetic) | `pipenv run py -m pytest tests/test_book_resolver.py -x -q` | ⬜ created by 25-02-01 | ⬜ pending |
| 25-02-03 | 02 | 1 | RES-01, EXT-04 | T-25-02, T-25-03, T-25-10 | `resolve()` treats input as an opaque lookup key (no SQL interpolation); read-only `core_db` only; `ast` import-hygiene assertion | unit (synthetic + live-DB, skip-guarded) | `pipenv run py -m pytest tests/test_book_resolver.py -x -q` | ⬜ created by 25-02-01 | ⬜ pending |
| 25-03-01 | 03 | 1 | EXT-05 | T-25-11, T-25-10 | `ScriptureVerse.__post_init__` rejects rather than coerces; `ast` import-hygiene assertion | unit (synthetic) | `pipenv run py -m pytest tests/test_scripture_data.py -x -q` | ⬜ created by task | ⬜ pending |
| 25-03-02 | 03 | 1 | EXT-01 | — | N/A | unit (synthetic) | `pipenv run py -m pytest tests/test_scripture_data.py -x -q` | ⬜ created by 25-03-01 | ⬜ pending |
| 25-03-03 | 03 | 1 | EXT-05 | T-25-13 | scripture collection name asserted disjoint from every talk collection name | unit (synthetic) | `pipenv run py -m pytest tests/test_scripture_data.py -x -q` | ⬜ created by 25-03-01 | ⬜ pending |
| 25-04-01 | 04 | 2 | EXT-01 | T-25-03 | `EXPECTED_CORE_TABLES` declares `scripture` + the three `book` columns (asserted directly, so omission goes red) | unit (synthetic fixtures) | `pipenv run py -m pytest tests/ -q` | ✅ exists (extended) | ⬜ pending |
| 25-04-02 | 04 | 2 | EXT-01, EXT-02 | T-25-03 | no comparison/pattern clause on the text column; read-only `core_db` only | unit (synthetic + live-DB, skip-guarded) | `pipenv run py -m pytest tests/test_scripture_extraction.py -x -q` | ⬜ created by task | ⬜ pending |
| 25-04-03 | 04 | 2 | EXT-03, EXT-04, EXT-05 | T-25-01, T-25-14 | transform raises on unknown book id / flag / empty cleaned text — never skips | unit (synthetic) | `pipenv run py -m pytest tests/test_scripture_extraction.py -x -q` | ⬜ created by 25-04-02 | ⬜ pending |
| 25-04-04 | 04 | 2 | EXT-01, EXT-02, EXT-04, EXT-05 | T-25-01, T-25-14 | corpus-wide invariants: exactly 41,996 standard + 73,257 total, no residual `<`, unique scripture ids, resolver round-trip | unit (live-DB, skip-guarded) | `pipenv run py -m pytest tests/test_scripture_extraction.py -x -q` | ⬜ created by 25-04-02 | ⬜ pending |
| 25-04-05 | 04 | 2 | EXT-02 | — | N/A | smoke (live-DB) | `pipenv run py -m extractors.scripture_extraction --stats \| grep 41996` | n/a (CLI) | ⬜ pending |
| 25-04-06 | 04 | 2 | — (docs maintenance) | — | N/A | smoke | inline `pipenv run py -c` index assertion (see 25-04-PLAN.md Task 6) | n/a (CLAUDE.md) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

No separate Wave-0 scaffolding is needed: every test target is produced by the tdd task whose
subject it verifies, in the same commit, so no task carries an `<automated>MISSING` marker.

- [x] `tests/test_html_parsing_utils.py` — already exists; 25-01-01 adds a `clean_verse_text` class (EXT-03)
- [x] `tests/test_book_resolver.py` — created by 25-02-01 (EXT-04, RES-01)
- [x] `tests/test_scripture_data.py` — created by 25-03-01 (EXT-01, EXT-05)
- [x] `tests/test_scripture_extraction.py` — created by 25-04-02 (EXT-01…EXT-05)
- [x] `tests/test_phase1.py` — already exists; 25-04-01 extends `TestSchemaValidation`
- [x] Framework install: **none needed** — pytest + fixture infrastructure already in place; no
  conftest changes required (no new test needs a live service)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | All phase behaviors have automated verification | — |

*All phase behaviors have automated verification. 25-04-05 exists so a human can read 41,996 off
the terminal, but the command asserts the number as well as printing it — it is a demonstration,
not a manual-only check.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none exist — every target is an in-plan tdd deliverable)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, revision pass 2026-07-27)
