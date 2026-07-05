---
phase: 25
slug: data-model-book-resolver-extraction
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-05
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (running unittest-style test classes — repo convention) |
| **Config file** | none (no pytest.ini/pyproject; tests use `sys.path.append` header pattern) |
| **Quick run command** | `pipenv run py -m pytest tests/test_scripture_extraction.py tests/test_book_resolver.py -x -q` |
| **Full suite command** | `pipenv run py -m pytest tests/ -q` (live-service tests auto-skip via conftest port checks) |
| **Estimated runtime** | ~15 seconds (new unit tests); full suite dominated by skip-guarded live-DB reads |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_scripture_extraction.py tests/test_book_resolver.py -x -q`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -q` (existing 11 test files must stay green — especially `tests/test_html_parsing_utils.py` after the `clean_verse_text` addition)
- **Before `/gsd-verify-work`:** Full suite must be green, including the live-DB 41,996 canonical-verse assertion
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {25-01-01} | 01 | 1 | EXT-01 | — | N/A | unit (live-DB, skip-guarded) | `pipenv run py -m pytest tests/test_scripture_extraction.py -x -q` | ❌ W0 | ⬜ pending |
| {25-01-02} | 01 | 1 | EXT-02 | — | N/A | unit (live-DB) | `pipenv run py -m pytest tests/test_scripture_extraction.py -x -q` | ❌ W0 | ⬜ pending |
| {25-01-03} | 01 | 1 | EXT-03 | T-25-01 | `clean_verse_text` no residual HTML tags (no `<` survives) | unit (synthetic + live spot check) | `pipenv run py -m pytest tests/test_scripture_extraction.py -x -q` | ❌ W0 | ⬜ pending |
| {25-01-04} | 01 | 1 | EXT-04 | — | N/A | unit | `pipenv run py -m pytest tests/test_book_resolver.py -x -q` | ❌ W0 | ⬜ pending |
| {25-01-05} | 01 | 1 | EXT-05 | — | N/A | unit (synthetic) | `pipenv run py -m pytest tests/test_scripture_extraction.py -x -q` | ❌ W0 | ⬜ pending |
| {25-01-06} | 01 | 1 | RES-01 | T-25-02 | `resolve()` treats input as opaque lookup key; no SQL interpolation | unit (synthetic) | `pipenv run py -m pytest tests/test_book_resolver.py -x -q` | ❌ W0 | ⬜ pending |

*Task IDs are placeholders until the planner finalizes plan/task numbering; requirement rows are authoritative.*
*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_scripture_extraction.py` — covers EXT-01…EXT-05 (phase deliverable, not a pre-existing gap)
- [ ] `tests/test_book_resolver.py` — covers EXT-04, RES-01 (phase deliverable)
- [ ] Framework install: **none needed** — pytest + fixtures infrastructure already in place; no conftest changes required (new tests need no live services)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | All phase behaviors have automated verification | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
