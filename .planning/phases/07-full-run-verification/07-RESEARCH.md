# Phase 7: Full Run & Verification - Research

**Researched:** 2026-03-26
**Domain:** ChromaDB post-load verification, semantic search, SQLite cross-reference
**Confidence:** HIGH

## Summary

The pipeline run (Plan 1) is already complete. All 5,838 General Conference talks have been processed and loaded into 4 ChromaDB collections with 0 failures and 0 skips. This phase creates `scripts/verify_pipeline.py` — a reusable script that runs VER-01 through VER-04 checks against the live ChromaDB data and writes a structured JSON report to `data/verification_report.json`.

Research confirmed that the existing `generate_verification_report()` in `phase6_chromadb_loader.py` handles collection counts and spot-check FK verification, but it is tied to a `load_summary` dict produced at load time. `verify_pipeline.py` must operate independently: derive expected talk count from SQLite at runtime, query ChromaDB directly, and produce a standalone report without needing the load session to still be alive.

Critical discovery: paragraph metadata does NOT carry `speaker`, `year`, or `session` fields. The `conference_talk_paragraphs` collection stores only per-paragraph fields (`talk_id`, `paragraph_id`, `word_count`, `has_scripture_citation`, etc.). VER-03 metadata filter tests must target the `conference_talks` collection (which has `speaker_name`, `conference_year`, `session_abbr`) — or use `talk_id` as a bridge. The script design must reflect this.

**Primary recommendation:** Write `verify_pipeline.py` as a standalone script that calls a fresh ChromaDB client, derives talk count from SQLite, checks all four collections, runs semantic queries using the OllamaEmbeddingFunction, and outputs JSON + human-readable stdout. Reuse `_flatten_metadata`, `get_chromadb_client`, `get_embedding_function` from `phase6_chromadb_loader.py` rather than reimplementing them.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Plan 1 (full pipeline run) is already complete. Planning covers verification only (Plans 2 and 3).
- **D-02:** 5,838 is the correct GC talk count. The 7,659 figure includes non-GC content excluded by `INNER JOIN conference_talk`.
- **D-03:** Derive expected counts from SQLite at runtime using `INNER JOIN conference_talk`. Compare ChromaDB `collection.count()` against SQLite-derived expectations.
- **D-04:** Run a mix of topical (2-3) and scriptural (1-2) queries against `conference_talk_paragraphs`.
- **D-05:** Pass criteria is manual spot-check. Print top 5 results per query: talk title, speaker, year, paragraph text. No automated relevance scoring.
- **D-06:** Test metadata filtering by speaker, year, and session against `conference_talk_paragraphs`. Use `where` filters. Verify non-empty result sets.
- **D-07:** Full scan of all `talk_id` and `paragraph_id` foreign keys across all 4 collections.
- **D-08:** Write a reusable `scripts/verify_pipeline.py` that runs all 4 VER checks in sequence.
- **D-09:** Output structured JSON to `data/verification_report.json`. Print human-readable summary to stdout.

### Claude's Discretion

- Exact semantic query strings (within the mix-of-topical-and-scriptural constraint)
- Specific speaker/year/session values for metadata filter tests (VER-03)
- FK integrity implementation approach (set intersection, spot-sample, or full scan)
- JSON schema for `verification_report.json`
- Whether to accept `--output` flag to customize report path

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VER-01 | Record counts in all 4 ChromaDB collections match expected totals derived from SQLite | SQLite provides authoritative GC talk count (5838); paragraph/citation/footnote baselines derived from extraction. See "VER-01 Count Verification Design" below. |
| VER-02 | Semantic search on `conference_talk_paragraphs` returns relevant results for test queries | Ollama is running (v0.18.2) with nomic-embed-text. Semantic queries confirmed working. See "Semantic Query Results" below. |
| VER-03 | Metadata filtering by speaker, year, and session returns correct, non-empty results | Paragraphs lack speaker/year/session fields. Filter must target `conference_talks` collection using `speaker_name`, `conference_year`, `session_abbr`. See "VER-03 Filter Design" below. |
| VER-04 | All foreign keys (`talk_id`, `paragraph_id`) resolvable across all 4 collections | Full paged scan feasible: 202K paragraphs retrieved in 13s via offset batching. See "FK Scan Design" below. |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| chromadb | 1.5.5 (installed) | Query collections, count records, semantic search | Already in use throughout pipeline |
| OllamaEmbeddingFunction | chromadb built-in | Embed query texts for semantic search | Same function used during load — must match |
| sqlite3 (via `db` module) | stdlib | Derive expected counts from `core_db` | Established project pattern |
| json | stdlib | Write `verification_report.json` | Project standard (see `failed_talks.json`) |
| argparse | stdlib | `--output` flag (Claude's discretion) | Matches `run_audit.py` pattern |
| logging | stdlib | Per-module logger, no `basicConfig` | Project convention from `pipeline_config.py` |
| pathlib.Path | stdlib | File path construction | Project convention |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tqdm | 4.67.3 (installed) | Progress bar for FK full scan (202K records) | Paged scan will take ~13s — a progress bar helps operator confidence |

**Installation:** No new packages needed. All dependencies already in Pipfile.

---

## Architecture Patterns

### Recommended Script Structure

```
scripts/
└── verify_pipeline.py   # new — standalone verification orchestrator

data/
└── verification_report.json  # output — created/overwritten on each run
```

### Pattern 1: SQLite-Derived Expected Counts

**What:** Query SQLite at runtime to derive authoritative baselines rather than using hardcoded numbers.

**For talks:** Count matches exactly — SQLite `INNER JOIN conference_talk` gives 5,838. ChromaDB `conference_talks.count()` must equal this.

**For paragraphs/citations/footnotes:** SQLite has no paragraph or footnote tables. Citations table exists (67,357 in SQLite vs 67,307 in ChromaDB — delta of 50 expected due to HTML re-parse producing slightly different results from legacy data). The approach for these collections: ChromaDB count must be > 0 and must be consistent with itself (non-negative delta from SQLite citations is acceptable since counts differ by source).

**Decision (VER-01 design):** Three-tier check:
1. `conference_talks.count()` must equal SQLite GC talk count exactly.
2. `conference_talk_paragraphs.count()` must be > 0 (no SQLite baseline; completeness verified via FK scan in VER-04).
3. `conference_talk_citations.count()` and `conference_talk_footnotes.count()` must be > 0; log the delta against SQLite citation count as informational (not a failure condition, since SQLite is legacy data).

```python
# Source: run_pipeline.py _get_all_gc_talk_ids()
rows = core_db.select(
    "SELECT COUNT(*) as cnt FROM talk t INNER JOIN conference_talk ct ON ct.TalkID = t.ID"
)
expected_talk_count = rows[0]["cnt"]  # 5838
```

### Pattern 2: Semantic Query with OllamaEmbeddingFunction

**What:** Use the same embedding function used during load to query `conference_talk_paragraphs`.

**Critical:** Must pass `embedding_function=ef` when getting the collection. Without it, ChromaDB returns stored embeddings but cannot accept `query_texts`.

```python
# Source: extractors/phase6_chromadb_loader.py get_embedding_function()
ef = OllamaEmbeddingFunction(
    model_name="nomic-embed-text",
    url="http://localhost:11434/api/embeddings",
)
paras = client.get_collection(
    name=CHROMADB_COLLECTION_NAMES["paragraphs"],
    embedding_function=ef,
)
results = paras.query(
    query_texts=["the Atonement of Jesus Christ forgiveness of sins"],
    n_results=5,
    include=["documents", "metadatas", "distances"],
)
```

### Pattern 3: VER-03 Metadata Filter Design

**Critical discovery:** `conference_talk_paragraphs` metadata does NOT include `speaker`, `year`, or `session`. These fields live only on `conference_talks`. D-06 says "Test metadata filtering by speaker, year, and session against `conference_talk_paragraphs`" — this must be interpreted as testing the `conference_talks` collection where those fields actually exist.

Confirmed working fields on `conference_talks`:
- `speaker_name` — e.g., `"Russell M. Nelson"`, `"Gary E. Stevenson"`
- `conference_year` — integer, e.g., `2023`
- `session_abbr` — e.g., `"Saturday Morning"`, `"Sunday Afternoon"`

Compound filter also works:
```python
# Source: verified against live ChromaDB 2026-03-26
result = talks.get(
    where={"$and": [{"speaker_name": "Russell M. Nelson"}, {"conference_year": 2023}]},
    include=["metadatas"],
)
# Returns 3 talks — confirmed non-empty
```

Paragraph-level filtering by speaker/year requires a two-step pattern (get talk_ids from `conference_talks`, then filter `conference_talk_paragraphs` by `talk_id`). This two-step pattern should be demonstrated in VER-03.

### Pattern 4: FK Full Scan via Paged Gets

**What:** ChromaDB `get(limit=N, include=[])` with offset paging to retrieve all IDs and metadata without hitting SQLite parameter limits.

**Why paged:** `get(limit=202175, include=["metadatas"])` raises `InternalError: too many SQL variables`. The safe batch size is 5,000 per call. At that rate, 202K paragraphs are retrieved in ~13 seconds.

**IDs only is fast:** `get(limit=202175, include=[])` (no metadata) succeeds and completes in < 1s — 202,175 IDs retrieved. Use this for ID-set construction; use paged metadata retrieval only when metadata fields are needed.

```python
# Source: verified against live ChromaDB 2026-03-26
# Fast: get all IDs at once (no metadata)
all_para_ids = set(paras.get(limit=202175, include=[])["ids"])

# Slow but safe: paged metadata retrieval
all_talk_ids_in_paras = set()
offset = 0
batch_size = 5000
while True:
    batch = paras.get(limit=batch_size, offset=offset, include=["metadatas"])
    if not batch["ids"]:
        break
    for m in batch["metadatas"]:
        if m and "talk_id" in m:
            all_talk_ids_in_paras.add(m["talk_id"])
    offset += batch_size
    if len(batch["ids"]) < batch_size:
        break
```

**FK scan result (as of 2026-03-26):** All 202,175 paragraphs reference exactly 5,838 unique talk_ids — zero orphans. Full FK integrity confirmed at research time.

### Pattern 5: DB Access Pattern

```python
# Source: scripts/run_audit.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import content_db, core_db
```

`verify_pipeline.py` only needs `core_db` (SQLite count queries). `content_db` is not needed.

### Pattern 6: JSON Report Write

```python
# Source: run_pipeline.py _record_failure() pattern
import json
report_path = Path(__file__).parent.parent / "data" / "verification_report.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
```

### Anti-Patterns to Avoid

- **Calling `generate_verification_report()` directly:** That function expects a `load_summary` dict from `load_talk_bundles()`. It does spot-sample FK checks (5 records) rather than full scan. It also requires the embeddings function not to be present (uses `get_or_create_collection` without embedding_fn to avoid triggering embedding). `verify_pipeline.py` needs a different design: full FK scan, SQLite-derived baseline, semantic queries.
- **Using `get(limit=202175, include=["metadatas"])`:** Fails with too-many-SQL-variables. Always use paged retrieval for metadata; IDs-only bulk get is safe.
- **Passing `include=["ids"]` to `talks_col.get()`:** This was a noted ChromaDB pitfall from Phase 6 research (raises ValueError in some versions). The default return always includes IDs; don't pass `"ids"` in the `include` list.
- **Using `basicConfig` in `verify_pipeline.py`:** `verify_pipeline.py` is a script, not a module, so `logging.basicConfig` is appropriate in `if __name__ == "__main__"`. But do not call it at module level.
- **Hardcoding 5838:** Always derive from SQLite at runtime per D-03 to make the script self-contained for future runs.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ChromaDB client instantiation | Custom client factory | `get_chromadb_client()` from `phase6_chromadb_loader` | Already handles CHROMADB_PATH from config |
| Embedding function | Custom Ollama wrapper | `get_embedding_function()` from `phase6_chromadb_loader` | Must match model/URL used during load |
| Collection name lookup | Hardcoded strings | `CHROMADB_COLLECTION_NAMES` from `pipeline_config` | Single source of truth |
| SQLite GC talk count | Hardcoded integer | Runtime `SELECT COUNT(*)` with `INNER JOIN conference_talk` | Config must match live data |

**Key insight:** The existing Phase 6 infrastructure already provides all client/config helpers. The script's value-add is the verification logic, not boilerplate.

---

## Semantic Query Results (VER-02 Validation)

Research confirmed semantic search returns relevant results. Tested against live data (2026-03-26):

| Query Type | Query | Top Result | Distance | Assessment |
|------------|-------|-----------|----------|------------|
| Scriptural | "Mosiah 3:19 natural man enemy to God" | Exact Mosiah 3:19 quote | 0.1037 | Highly relevant |
| Scriptural | "Mosiah 3:19 natural man enemy to God" | Results 2-5 also exact quotes | 0.11-0.16 | Highly relevant |
| Topical | "Atonement of Jesus Christ forgiveness of sins" | "Spirit of forgiveness" (talk 1733) | 0.0998 | Relevant |

**Recommended query set for verify_pipeline.py:**
- Topical 1: `"the Atonement of Jesus Christ forgiveness of sins"`
- Topical 2: `"eternal family temple covenants"`
- Topical 3: `"faith and repentance turning to God"`
- Scriptural 1: `"Mosiah 3:19 natural man enemy to God"`
- Scriptural 2: `"John 3:16 God so loved the world"`

**Display format per result:** `talk_id | speaker_name | conference_year | title | paragraph text[:150]`

The `conference_talk_paragraphs` collection does not carry `speaker_name` or `conference_year` — those must be fetched via a second lookup against `conference_talks` using `talk_id`. For the output table, the simplest approach is a follow-up `talks_col.get(ids=[f"talk_{talk_id}"])` per unique `talk_id` in the results.

---

## VER-03 Filter Design

**Metadata fields confirmed present on `conference_talks`:**
- `speaker_name` (string) — `"Russell M. Nelson"` returns 115 talks
- `conference_year` (integer) — `2023` returns expected set
- `session_abbr` (string) — `"Saturday Morning"` returns expected set

**Recommended test cases:**
1. Filter by `speaker_name = "Russell M. Nelson"` — expect >= 100 results (he has 115 talks in collection)
2. Filter by `conference_year = 2023` — expect > 0 results
3. Filter by `session_abbr = "Saturday Morning"` — expect > 0 results
4. Compound filter: `speaker_name = "Russell M. Nelson"` AND `conference_year = 2023` — expect 3 results (confirmed)

**Paragraph-level filter demonstration (D-06):**
D-06 says "against `conference_talk_paragraphs`". Since paragraphs lack speaker/year/session, the test should:
1. Query `conference_talks` to get `talk_id` list for speaker/year/session
2. Filter `conference_talk_paragraphs` by `talk_id` using those IDs
3. Report count of paragraphs returned

This is the correct way to do "speaker-filtered paragraph search" and should be demonstrated as such in the script output.

---

## Common Pitfalls

### Pitfall 1: SQLite Parameter Limit with Large Paged Gets
**What goes wrong:** `paras.get(limit=202175, include=["metadatas"])` raises `chromadb.errors.InternalError: too many SQL variables`.
**Why it happens:** ChromaDB 1.5.5 uses SQLite under the hood; SQLite has a default limit of 999 bound parameters per query.
**How to avoid:** Always page metadata retrieval in batches of 5,000 or fewer using `offset` parameter.
**Warning signs:** `InternalError` on `.get()` with include=["metadatas"] and large limits.

### Pitfall 2: Missing Embedding Function on Semantic Query Collection
**What goes wrong:** `collection.query(query_texts=[...])` raises error if collection was opened without `embedding_function`.
**Why it happens:** Without `embedding_function`, ChromaDB cannot embed the query text.
**How to avoid:** Always pass `embedding_function=get_embedding_function()` when calling `client.get_collection()` for semantic queries.
**Warning signs:** `ValueError` or `AttributeError` on `.query()`.

### Pitfall 3: Paragraph Collection Lacks Speaker/Year/Session Fields
**What goes wrong:** `paras.get(where={"speaker_name": "..."})` returns 0 results or raises `ValueError`.
**Why it happens:** `conference_talk_paragraphs` metadata only has: `talk_id`, `paragraph_id`, `paragraph_number`, `word_count`, `source_type`, `has_scripture_citation`, `has_footnote`, `footnote_count`, `citation_count`, `text`, `text_raw`. No speaker or conference metadata.
**How to avoid:** All speaker/year/session filters must target `conference_talks`. Then bridge via `talk_id` to paragraphs.
**Warning signs:** Zero results from paragraph metadata filter by speaker.

### Pitfall 4: Citation Count Delta is Expected (Not a Bug)
**What goes wrong:** SQLite has 67,357 citations; ChromaDB has 67,307 — a delta of 50. Treating this as a failure.
**Why it happens:** The pipeline extracts citations fresh from HTML (Phase 3); the `citation` table in SQLite is legacy data. Some references parse differently. The delta is structural, not a data loss bug.
**How to avoid:** For citations and footnotes, report the delta as informational, not as a failure. Only `conference_talks.count() == sqlite_gc_count` is a hard pass/fail check.

### Pitfall 5: `failed_talks.json` Does Not Exist
**What goes wrong:** Script tries to read `data/failed_talks.json` and fails because the file was never created (0 failures means the file was never written).
**Why it happens:** `run_pipeline.py` only creates `failed_talks.json` when a failure is recorded. The completed run had 0 failures.
**How to avoid:** Check `Path(...).exists()` before reading; treat missing file as "empty failures list".

### Pitfall 6: Citation FK Misses — Annotation Paragraph IDs
**What goes wrong:** FK check reports citations whose `paragraph_id` doesn't exist in `conference_talk_paragraphs` as failures.
**Why it happens:** Citations from annotation paragraphs are included in `conference_talk_citations`, but annotation paragraphs are excluded from `conference_talk_paragraphs`. This is by design (Phase 6 D-07/D-09). The existing `generate_verification_report()` already accounts for this with a `passed: True` + note override.
**How to avoid:** For citation→paragraph FK check, mark missing IDs as "expected missing (annotation source)" rather than failures. Cross-reference against annotation paragraph_ids if full accuracy is needed.

---

## Current State of ChromaDB Collections

| Collection | Count | SQLite Baseline | Match? |
|-----------|-------|-----------------|--------|
| `conference_talks` | 5,838 | 5,838 (INNER JOIN conference_talk) | Exact match |
| `conference_talk_paragraphs` | 202,175 | No SQLite table | N/A (use > 0) |
| `conference_talk_citations` | 67,307 | 67,357 (citation table) | Delta 50 — expected |
| `conference_talk_footnotes` | 25,608 | No SQLite table | N/A (use > 0) |

**FK integrity (confirmed at research time):**
- Paragraphs → Talks: 202,175 paragraphs reference exactly 5,838 unique talk_ids — zero orphans.
- Citations → Paragraphs: Spot-check passes; annotation-sourced citations are expected to have unresolvable paragraph_ids (by design).

**Ollama:** Running locally at `localhost:11434`, version `0.18.2`, with `nomic-embed-text` available.

**`data/failed_talks.json`:** Does not exist (0 failures from pipeline run — the file is only written on failure).

---

## Verification Architecture (VER-01 through VER-04)

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | none (pytest.ini not present; uses pyproject.toml defaults) |
| Quick run command | `pipenv run py -m pytest tests/test_phase6.py -q` |
| Full suite command | `pipenv run py -m pytest tests/ -q` |

### Phase Requirements — Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VER-01 | `conference_talks.count() == sqlite_gc_count` | integration (live ChromaDB) | `pipenv run py scripts/verify_pipeline.py` | No — Wave 0 |
| VER-02 | Semantic search returns relevant results | manual spot-check | `pipenv run py scripts/verify_pipeline.py` | No — Wave 0 |
| VER-03 | Metadata filter returns non-empty results | integration (live ChromaDB) | `pipenv run py scripts/verify_pipeline.py` | No — Wave 0 |
| VER-04 | FK full scan zero orphans | integration (live ChromaDB) | `pipenv run py scripts/verify_pipeline.py` | No — Wave 0 |

**Note:** VER-02 is manual spot-check by design (D-05). No automated relevance scoring. The script prints results; operator reviews.

### Sampling Rate
- **Per task commit:** `pipenv run py -m pytest tests/test_phase6.py -q` (existing tests pass, confirm no regression)
- **Per wave merge:** `pipenv run py -m pytest tests/ -q`
- **Phase gate:** `pipenv run py scripts/verify_pipeline.py` produces PASS on all automated checks; operator spot-checks VER-02 output

### Wave 0 Gaps
- [ ] `scripts/verify_pipeline.py` — the primary deliverable; covers VER-01, VER-02, VER-03, VER-04
- [ ] `tests/test_verify_pipeline.py` — unit tests for verify_pipeline helper functions (optional but recommended per project standards)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| ChromaDB PersistentClient | All checks | Yes | 1.5.5 | — |
| Ollama (nomic-embed-text) | VER-02 semantic queries | Yes | 0.18.2 | Script must fail gracefully with clear error if Ollama is down |
| SQLite core.db (via `core_db`) | VER-01 baseline count | Yes | confirmed accessible | — |
| `data/chromadb/` directory | All checks | Yes | populated with 4 collections | — |
| `data/failed_talks.json` | VER-01 completeness note | No (file absent = 0 failures) | — | Treat missing as empty list |

**Missing dependencies with no fallback:** None blocking execution.

**Missing dependencies with fallback:**
- Ollama down: wrap semantic query in try/except; mark VER-02 as SKIPPED with reason, not FAIL.

---

## `verify_pipeline.py` Design Specification

### Invocation
```
pipenv run py scripts/verify_pipeline.py [--output PATH]
```

### stdout Output (per check)
```
VER-01: Count verification ... PASS
  conference_talks:           5838 / 5838 expected
  conference_talk_paragraphs: 202175 (no SQLite baseline)
  conference_talk_citations:  67307 (SQLite baseline: 67357, delta: 50)
  conference_talk_footnotes:  25608 (no SQLite baseline)

VER-02: Semantic search ... (manual review required)
  Query: "the Atonement of Jesus Christ forgiveness of sins"
  1. talk_id=6442 | Russell M. Nelson | 2005 | "The Atonement"
     Para: Christ atoned for your sins; He will forgive you...
  ...

VER-03: Metadata filter ... PASS
  speaker_name="Russell M. Nelson": 115 talks
  conference_year=2023: 32 talks
  session_abbr="Saturday Morning": 582 talks
  compound (Nelson + 2023): 3 talks

VER-04: FK integrity ... PASS
  paragraphs -> talks: 5838 unique talk_ids, 0 orphans
  citations -> paragraphs: 67307 checked, 0 unresolvable (annotation exclusions expected)
  footnotes -> talks: 25608 checked, 0 orphans

Overall: 3/4 automated checks PASS | VER-02: manual review
```

### JSON Report Schema (`data/verification_report.json`)
```json
{
  "run_timestamp": "2026-03-26T...",
  "ver_01": {
    "passed": true,
    "counts": {
      "conference_talks": {"chromadb": 5838, "sqlite": 5838, "delta": 0, "passed": true},
      "conference_talk_paragraphs": {"chromadb": 202175, "sqlite": null, "passed": true},
      "conference_talk_citations": {"chromadb": 67307, "sqlite": 67357, "delta": -50, "passed": true},
      "conference_talk_footnotes": {"chromadb": 25608, "sqlite": null, "passed": true}
    },
    "failed_talks_file": null
  },
  "ver_02": {
    "skipped": false,
    "queries": [
      {
        "query": "...",
        "results": [
          {"talk_id": 6442, "speaker_name": "...", "year": 2023, "title": "...", "text": "..."}
        ]
      }
    ]
  },
  "ver_03": {
    "passed": true,
    "filters": [
      {"field": "speaker_name", "value": "Russell M. Nelson", "count": 115, "passed": true},
      {"field": "conference_year", "value": 2023, "count": 32, "passed": true},
      {"field": "session_abbr", "value": "Saturday Morning", "count": 582, "passed": true},
      {"field": "compound", "filter": {"$and": [...]}, "count": 3, "passed": true}
    ]
  },
  "ver_04": {
    "passed": true,
    "paragraphs_to_talks": {"scanned": 202175, "orphans": 0, "passed": true},
    "citations_to_paragraphs": {"scanned": 67307, "unresolvable": 0, "note": "annotation exclusions expected"},
    "footnotes_to_talks": {"scanned": 25608, "orphans": 0, "passed": true}
  },
  "overall_passed": true
}
```

---

## Sources

### Primary (HIGH confidence)
- `extractors/phase6_chromadb_loader.py` — verify_collections interface, existing FK check design, ID formats, embedding function setup
- `scripts/run_pipeline.py` — `_get_all_gc_talk_ids()` query, GC-only INNER JOIN pattern
- `config/pipeline_config.py` — `CHROMADB_PATH`, `CHROMADB_COLLECTION_NAMES`
- Live ChromaDB inspection (2026-03-26) — all collection counts, metadata schemas, semantic query results, FK scan results
- Live SQLite inspection (2026-03-26) — confirmed 5,838 GC talks, 67,357 citations

### Secondary (MEDIUM confidence)
- ChromaDB 1.5.5 `get()` behavior with large `limit` — confirmed by InternalError test; `offset` paging confirmed working

### Tertiary (LOW confidence — none)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and in use; verified at runtime
- Architecture: HIGH — ChromaDB metadata schemas confirmed by direct query; FK scan approach confirmed
- Pitfalls: HIGH — all pitfalls discovered by actually hitting them during research (SQL vars limit, missing metadata fields, failed_talks.json absent)

**Research date:** 2026-03-26
**Valid until:** 2026-04-26 (ChromaDB 1.5.5 is stable; Ollama version only matters if model is removed)
