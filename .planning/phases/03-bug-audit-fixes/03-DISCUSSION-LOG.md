# Phase 3: Bug Audit & Fixes — Discussion Log

**Date:** 2026-03-23
**Phase:** 03-bug-audit-fixes

---

## Areas Discussed

All four gray areas were selected for discussion.

---

## Area 1: Audit Sample Selection

**Q: How many talks should the audit run through all phases?**
A: ~20 talks. User wants to configure this themselves (not algorithm-selected).

**Q: How should sample talks be selected?**
A: Curated by the user — not random, not seeded from failures.

**Q: Where should the sample list live?**
A: Config file — `config/audit_sample.json` as a list of talk_ids.

---

## Area 2: Known Bugs Starting Point

**Q: How should the existing 11 failing tests relate to the audit?**
A: Fix known failures first — get to a clean test baseline before running the broader audit.

Known failures at time of discussion:
- 10 in `tests/test_phase2.py` (paragraph extraction logic)
- 1 in `tests/test_phase4.py` (encoding issue: `]."` → replacement character)

---

## Area 3: Bug Catalogue Format

**Q: What format should the bug catalogue take?**
A: Single markdown table — one `BUGS.md` file.

**Q: What fields per bug?**
A: Minimal — ID, Phase, Description, Status. Root cause and fix details go in commits.

---

## Area 4: Regression Test Placement

**Q: Where should regression tests go?**
A: Existing `tests/test_phase*.py` files — co-located with the phase they cover.

**Q: How much test coverage per bug?**
A: One test per bug — enough to fail if the fix were reverted.

---

*Generated: 2026-03-23*
