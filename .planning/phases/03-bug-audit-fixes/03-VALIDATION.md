---
phase: 3
slug: bug-audit-fixes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-23
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none (default discovery) |
| **Quick run command** | `pipenv run py -m pytest tests/test_phase2.py tests/test_phase4.py -v --tb=short` |
| **Full suite command** | `pipenv run py -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pipenv run py -m pytest tests/test_phase2.py tests/test_phase4.py -v --tb=short`
- **After every plan wave:** Run `pipenv run py -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | BUGS-01 | manual | `test -f BUGS.md` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 0 | BUGS-01 | smoke | `test -f config/audit_sample.json` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 0 | BUGS-01 | smoke | `test -f scripts/run_audit.py` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | BUGS-02 | unit | `pipenv run py -m pytest tests/test_phase4.py::TestFootnoteTextRendering::test_rbrackdotrdquo_gives_compound_suffix -v` | ✅ | ⬜ pending |
| 03-02-02 | 02 | 1 | BUGS-02 | unit | `pipenv run py -m pytest tests/test_phase2.py -v` | ✅ | ⬜ pending |
| 03-02-03 | 02 | 1 | BUGS-02 | unit | `pipenv run py -m pytest tests/ -v` | ✅ | ⬜ pending |
| 03-03-01 | 03 | 2 | BUGS-03 | unit | `pipenv run py -m pytest tests/ -v` | ✅ (partial) | ⬜ pending |
| 03-03-02 | 03 | 2 | BUGS-03 | unit | `pipenv run py -m pytest tests/test_phase4.py::TestFootnoteTextRendering -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `BUGS.md` — bug catalogue file (one row per bug: ID, Phase, Description, Status)
- [ ] `config/audit_sample.json` — empty array `[]` initially; user populates with talk_ids before audit runs
- [ ] `scripts/run_audit.py` — audit driver script (runs phases 1–5 per talk_id in audit_sample.json)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Bug catalogue completeness | BUGS-01 | Audit run by human reviewing output | Run `pipenv run py scripts/run_audit.py`, review output, record all errors in BUGS.md |
| All bugs have root-cause fixes (not workarounds) | BUGS-02 | Requires code review judgment | Review each fix commit — confirm it addresses root cause, not just symptoms |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
