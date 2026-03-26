# Phase 7: Full Run & Verification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 07-full-run-verification
**Areas discussed:** Semantic queries, Verification artifact, Record count approach

---

## Semantic Queries

| Option | Description | Selected |
|--------|-------------|----------|
| Topical | LDS doctrine topics only | |
| Scriptural | Scripture-reference queries only | |
| Mix of both | 2-3 topical + 1-2 scripture-based | ✓ |

**User's choice:** Mix of both

---

| Option | Description | Selected |
|--------|-------------|----------|
| Claude picks | Representative LDS topics and scriptures | ✓ |
| I have specific ones | User specifies exact queries | |

**User's choice:** Claude picks (representative topical + scriptural)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Manual spot-check | Print top 5 results, engineer eyeballs them | ✓ |
| Result count only | Pass if n_results >= 3 | |

**User's choice:** Manual spot-check — print results with title, speaker, text for human review

---

## Verification Artifact

| Option | Description | Selected |
|--------|-------------|----------|
| Reusable script | scripts/verify_pipeline.py | ✓ |
| One-off queries | Ad-hoc notebook/inline queries | |

**User's choice:** Reusable script at scripts/verify_pipeline.py

---

| Option | Description | Selected |
|--------|-------------|----------|
| Console report | Structured PASS/FAIL to stdout | |
| Written JSON report | Output to data/verification_report.json | ✓ |

**User's choice:** Written JSON report (+ stdout summary)

---

## Record Count Approach

| Option | Description | Selected |
|--------|-------------|----------|
| SQLite-derived | Query SQLite INNER JOIN conference_talk at runtime | ✓ |
| Non-zero + ratio check | Verify collections non-empty with ratio heuristic | |

**User's choice:** SQLite-derived authoritative counts

---

| Option | Description | Selected |
|--------|-------------|----------|
| Update acceptance criteria | Update ROADMAP.md from 7,659 to GC-only count | ✓ |
| Leave roadmap as-is | Note discrepancy in report only | |

**User's choice:** Update acceptance criteria — confirmed 5,838 is the correct GC count. The other "talks" aren't General Conference.

---

## Claude's Discretion

- FK integrity implementation approach (VER-04) — not discussed; full scan at Claude's discretion
- Exact semantic query strings within topical+scriptural mix
- Specific speaker/year/session values for VER-03 metadata filter tests
- JSON schema for verification_report.json

## Deferred Ideas

None.
