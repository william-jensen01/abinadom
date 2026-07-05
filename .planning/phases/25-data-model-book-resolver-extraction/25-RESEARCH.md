# Phase 25: Data Model, Book Resolver & Extraction - Research

**Researched:** 2026-07-05
**Domain:** Offline SQLite → Python data extraction (scripture verse corpus), text cleaning, name canonicalization
**Confidence:** HIGH — every data claim below was verified by direct read-only queries against the live `db/core.52.db` in this session

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Nearly all of Phase 25's design is **locked by `docs/scriptures/SPEC.md` §12 "Resolved decisions"** (see canonical refs). Those are carried forward, not re-decided. The discussion resolved the SPEC's one genuinely-open item (Open Q1: HTML/encoding cleaning scope).

#### Text Cleaning (EXT-03) — resolved Open Q1
- **D-01:** Add a purpose-built `clean_verse_text(raw)` helper to `extractors/html_parsing_utils.py` (per the "shared utilities live in html_parsing_utils / separate files" convention). Contract: bytes/str in → clean `str` out, **unconditional "no residual HTML tags" post-condition**, unit-testable without DB fixtures.
- **D-02:** Implementation shape: fast-path `if '<' not in text: return html.unescape(text.strip())` for the ~99% plaintext verses; fall back to BeautifulSoup `get_text()` (DOM-level, not regex) when markup is present. Keeps the no-tags guarantee strong while avoiding BS4 overhead on the common case — perf is a non-issue across ~73k rows.
- **D-03:** The helper owns the UTF-8 **decode** step too (SPEC: `Text` is stored as UTF-8 bytes), so extraction gets a single decode+clean entry point.
- **Rejected:** reusing `parse_html()` as-is (built for full talk pages, returns `None` on empty, semantically mismatched for 5-word fragments); pure `html.unescape` + regex tag-strip (weaker formal guarantee, known regex-on-HTML edge cases).

#### Book-Name Mojibake Repair (EXT-04)
- **D-04:** Repair the mangled em-dash with a **targeted deterministic replacement** `'�' → '—'` (em-dash), **scoped to the `book` table fields** (`FullName`, `CiteAbbr`), run **once in `book_resolver.canonicalize()`** at resolver build time — not per verse.
- **D-05:** Document the invariant that justifies this: within the closed, enumerable 99-row `book` table, every U+FFFD in a name is a lost em-dash byte. If a future DB version introduces a different bad byte in book names, a validation/unit test should catch it.
- **Rejected — `ftfy`:** definitively the **wrong tool** for this failure mode. ftfy recovers *wrong-codec* text (e.g. `â€"` → `—`) where the original bytes survive. The mojibake here is the Unicode **replacement character (U+FFFD)** — the em-dash byte was already *lost* during a prior bad decode, so there is nothing for ftfy to re-decode; it passes U+FFFD through unchanged. Adding the dependency would give false confidence and fix nothing.
- **Rejected — closed-set hardcode by `book_id`:** zero false-positive risk but brittle to DB version bumps and more code for the same result.

> ⚠️ **Research finding on D-04/D-05 (see Summary and Pitfall 1):** direct byte-level inspection of `core.52.db` this session shows the em-dash is stored as **valid UTF-8 `\xe2\x80\x94` (U+2014)** and **zero U+FFFD characters exist anywhere in the `book` table or verse `Text`**. The '�' previously observed was a Windows-console rendering artifact, not data corruption. D-04's replacement remains in place as a harmless defensive no-op guard, and D-05's unit test becomes the real deliverable (assert no U+FFFD survives canonicalize; assert book 404 FullName == "Joseph Smith—Matthew" with a true U+2014). This does not overturn the decision — it changes what the tests must assert against.

### Claude's Discretion (planner/executor)
- Exact `BookVerses` container shape and grouping-key representation.
- SQL/join structure for reading `scripture` ⋈ `book` (+parent for `volume`), using the existing `from db import CORE_DB_PATH` access pattern.
- Internal structure of the resolver alias lookup (as long as it accepts FullName / Abbr / CiteAbbr / word↔digit ordinals / "D&C" / "Doctrine and Covenants", case/period/space-insensitive, and returns the canonical digit-form `book`).

### Deferred Ideas (OUT OF SCOPE)
- **Resolver failure/ambiguity contract** (raise vs return `None` on unresolvable input; alias-collision precedence) — surfaced as a candidate gray area but not selected. The SPEC's resolver contract (§9) covers the accepted input forms; the error-path detail can be settled by the planner or deferred to Phase 28 where `get_verse`/`search` consume it.
- **Test data strategy** (live `core.52.db` vs synthetic fixtures vs both for the 41,996 assertion) — surfaced but not selected. Both patterns exist in the repo; planner's call.
- Study apparatus, headings, cross-refs, late chunking, embedding-model swap — all explicitly **v2 / out of scope** per REQUIREMENTS.md.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXT-01 | Read `S`/`J`/`F` verses from `core.52.db` into `ScriptureVerse` objects, joined to `book` (+parent for `volume`), grouped by (book, chapter, variant) | Verified: `scripture` (73,408 rows) and `book` (99 rows) schemas; no 3-level nesting exists, so one self-join on `ParentBookID` yields `volume`; `db.core_db` read-only Database instance already exists. See "Verified Data Facts" + Code Examples §1 |
| EXT-02 | Exclude 10 NULL-`Verse` `S` rows and 3 `E` rows → exactly 41,996 canonical | Verified live: `Flag='S' AND Verse IS NOT NULL` = **41,996 exactly**; the 10 NULL-Verse rows enumerated (IDs 31106-31109, 37714, 41507-41508, 42001-42003); NULL-Verse occurs only in `S` (10) and `H` (138) — never in `J`/`F` |
| EXT-03 | UTF-8 decode + clean light HTML via `html_parsing_utils`; non-empty, no residual tags | Verified: `Text` cells return **`bytes`** from sqlite3 (BLOB storage class); 0 UTF-8 decode failures across all 73,267 S/J/F rows; only **20 actual verses contain tags** (all D&C 77, `<br />` only); 2 verses contain `&nbsp;`. Pitfalls 2-3 document the `\xa0` and `get_text()` separator traps with empirically verified behavior |
| EXT-04 | Digit-form book normalization, `Sections`→"Doctrine and Covenants", em-dash repair | Verified: exactly 4 word-ordinal books (205/206/215/216 First/Second/Third/Fourth Nephi); Sections=book 302 (`CiteAbbr='D&C'`, parent=4); em-dash in books 404/405 is **valid UTF-8 U+2014, not U+FFFD** (see Pitfall 1) |
| EXT-05 | Derived `reference` (CiteAbbr format), `variant` (standard/jst), raw `source_flag` | Verified: all 94 verse-bearing books' `CiteAbbr` values inventoried (see Code Examples §3 data notes); single-chapter books enumerated (13); Sections' CiteAbbr is already "D&C" so `reference` needs no special case |
| RES-01 | `book_resolver.resolve()` accepts FullName/Abbr/CiteAbbr/word-ordinals/"D&C"/"Doctrine and Covenants" → canonical digit-form name | Verified: full 94-book alias inventory extracted; only normalized alias collision in the whole table is `d&c` (volume 4 vs Sections 302 — benign, both canonicalize to "Doctrine and Covenants"); long-form FullNames ("The Epistle to the Romans", "To the Hebrews") documented as a resolver coverage gap with recommendation (Pitfall 5) |
</phase_requirements>

## Summary

Phase 25 is a pure/offline extraction phase over a small, clean, fully-enumerable dataset. Every load-bearing claim in the SPEC was re-verified this session against the live `core.52.db`: flag counts match exactly (S=42,006, J=29,902, F=1,359, H=138, E=3), the NULL-`Verse` exclusion yields **exactly 41,996** canonical rows, D&C verses all live in book 302 "Sections", and the four Nephi books are the only word-ordinal FullNames. The cleaning burden is far smaller than the SPEC feared: after exclusions, only **20 real verses contain any HTML** (all D&C 77, `<br />` only, `Flag='S'`) and only **2 verses contain an entity** (`&nbsp;`). The locked D-02 fast-path/BS4-fallback design is therefore validated by the data.

One SPEC/CONTEXT assumption is **factually wrong and matters for test design**: there is **no U+FFFD mojibake in the database**. The em-dash in "Joseph Smith—Matthew" / "JS—M" (books 404/405) is stored as valid UTF-8 `\xe2\x80\x94` and sqlite3 returns it as a correct `str` containing U+2014. The '�' seen in the SPEC author's console (and reproducible in any cp1252 Windows console) is a **display artifact**, not data corruption. The locked `'�' → '—'` replacement is a harmless idempotent no-op and can stay as a defensive guard, but tests must be written against the real data shape (U+2014 present, U+FFFD absent) — a test that injects U+FFFD fixtures and asserts repair would test a scenario the data never exhibits, while the meaningful assertions are "no U+FFFD after canonicalize" and "book 404 resolves with a true em-dash".

The second research contribution is a complete resolver-input inventory: all 94 child-book `FullName`/`Abbr`/`CiteAbbr` triplets were extracted (see Code Examples). This surfaces a gap the SPEC missed: several common book names ("Romans", "Hebrews", "Acts" is fine, "Abraham", "Articles of Faith", "Song of Solomon") do not match any raw alias because `FullName` uses long forms ("The Epistle to the Romans", "To the Hebrews", "The Book of Abraham", "The Articles of Faith", "The Song of Solomon"). RES-01's "any common input form" needs prefix-stripped alias variants — a build-time detail well within the resolver's discretionary internals.

**Primary recommendation:** Build extraction as a single parameterized query through the existing `db.core_db` instance (`Flag IN ('S','J','F') AND Verse IS NOT NULL`), decode `Text` bytes in `clean_verse_text()` (D-03), and build the resolver alias table from all 94 child books plus 5 volumes with generated alias variants (period/space/case-folded, em-dash↔hyphen↔space folded, word↔digit ordinals, leading-article-stripped). Test against the live DB with the established skip-if-unavailable pattern, plus synthetic fixtures for `clean_verse_text` edge cases.

## Project Constraints (from CLAUDE.md)

Directives extracted from `./CLAUDE.md` that bind this phase's plans:

1. **Never open DB files directly** — use `scripts/db_schema_extractor.py` for inspection; production code goes through the `db` module (`from db import core_db` / `CORE_DB_PATH`). [CITED: CLAUDE.md §Process]
2. **pipenv for everything** — all commands are `pipenv run py ...`, tests are `pipenv run py -m pytest <file>`. [CITED: CLAUDE.md §Environment]
3. **Update the Project Structure Index** in CLAUDE.md when adding files to `extractors/`, `models/`, `config/`, `tests/` — this phase adds 5+ files, so the index update must be a plan task. [CITED: CLAUDE.md §Project Structure Index]
4. **Shared utilities in separate files / config helpers in config/** — `book_resolver.py` goes in `config/`, `clean_verse_text` goes in `html_parsing_utils.py` (per locked D-01). [CITED: CLAUDE.md + MEMORY.md feedback]
5. **Simplicity First / Minimal Impact** — do not touch the talk pipeline paths; new files only, except the `html_parsing_utils.py` sibling helper and `pipeline_config.py` constants. [CITED: CLAUDE.md §Core Principles]
6. **Verification Before Done** — run tests and demonstrate the 41,996 assertion before marking complete. [CITED: CLAUDE.md §4]

## Architectural Responsibility Map

This is a backend data-pipeline phase (no browser/CDN tiers). Tiers here are pipeline layers:

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| DB access (read `scripture` ⋈ `book`) | Extractor (`extractors/scripture_extraction.py`) | `db` module (connection/schema) | Extraction owns queries; `db.Database` owns connection, read-only mode, timeouts |
| UTF-8 decode + HTML/entity cleaning | Shared utility (`extractors/html_parsing_utils.py::clean_verse_text`) | — | Locked D-01/D-03: one decode+clean entry point, unit-testable without DB |
| Book-name canonicalization (build-time) | Resolver (`config/book_resolver.py::canonicalize`) | — | Locked D-04: name repair + digit-form + Sections override happen once at resolver build, not per verse |
| User-input book resolution (query-time) | Resolver (`config/book_resolver.py::resolve`) | — | RES-01: shared later by Phase 27 pipeline + Phase 28 tools; must be dependency-free of Weaviate/Ollama |
| Data shape (`ScriptureVerse`, `BookVerses`) | Models (`models/scripture_data.py`) | — | Mirrors `models/talk_metadata.py` / `paragraph_data.py` pattern |
| Reference derivation (`"1 Ne. 3:7"`) | Extractor (uses resolver's canonicalized book records) | Models (stored field) | Derived at extraction from CiteAbbr + chapter + verse; stored on the dataclass |
| Constants (`SCRIPTURE_*`) | Config (`config/pipeline_config.py`) | — | Established convention: all phase constants centralized |
| Verification of exclusion/normalization | Tests (`tests/test_scripture_extraction.py`, `tests/test_book_resolver.py`) | — | Phase checkpoint is green unit tests incl. the 41,996 assertion |

**Misassignment guards:** the extractor must NOT contain its own name-normalization logic (that's `canonicalize()`'s job — extractor consumes the resolver's canonical book records); the resolver must NOT read verse rows (book table only); `clean_verse_text` must NOT know about books or references (text in → text out).

## Standard Stack

Everything needed is already installed. **This phase introduces zero new dependencies.**

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `sqlite3` (via `db.core_db`) | stdlib | Read `scripture`/`book` tables read-only | Existing `db.Database` wrapper: read-only URI mode, timeout handler, dict rows, lazy schema validation [VERIFIED: codebase `db/__init__.py`] |
| Python stdlib `dataclasses` | stdlib | `ScriptureVerse`, `BookVerses` | Every existing model (`TalkMetadata`, `ParagraphData`, …) is a dataclass [VERIFIED: codebase `models/`] |
| Python stdlib `html` (`html.unescape`) | stdlib | Entity decoding on the fast path (D-02) | Locked decision; handles `&amp;`/`&nbsp;` (the only 2 entity types present in the data) [VERIFIED: DB scan — entities found: `amp`×5, `nbsp`×24, all in the 10 excluded rows except 2 verses] |
| beautifulsoup4 | 4.14.3 (installed) | DOM-level tag stripping fallback in `clean_verse_text` | Already a hard dependency used across Phases 1-4; locked D-02 [VERIFIED: `pipenv run py -c "import bs4; bs4.__version__"` → 4.14.3] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | installed (repo standard) | Run the new unittest-style test files | `pipenv run py -m pytest tests/test_scripture_extraction.py tests/test_book_resolver.py` [VERIFIED: CLAUDE.md convention + 11 existing test files] |
| stdlib `unittest` | stdlib | Test classes (repo mixes unittest-style classes run under pytest) | Follow `tests/test_phase1.py` structure [VERIFIED: codebase] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| BS4 fallback for 20 tag-bearing verses | regex tag-strip | Rejected in CONTEXT (weaker guarantee); do not revisit |
| `'�'→'—'` defensive guard | `ftfy` | Rejected in CONTEXT; additionally now proven unnecessary — no mojibake exists in the data [VERIFIED: byte-level scan of all 99 book rows and 73,267 verse rows: 0×U+FFFD, 0 UTF-8 decode failures] |
| `db.core_db` shared instance | raw `sqlite3.connect(CORE_DB_PATH)` | Raw connect violates the project's schema-aware-access rule and loses read-only + timeout protection |

**Installation:** none required.

**Version verification:** no packages to verify — nothing is installed this phase. BS4 4.14.3 confirmed installed and importable in the project venv this session.

## Package Legitimacy Audit

**No external packages are installed in this phase.** All imports are Python stdlib (`sqlite3`, `dataclasses`, `html`, `re`, `unittest`) or already-installed project dependencies (`beautifulsoup4` 4.14.3, `pytest`).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — | — | — | — | — | — | No new installs |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Verified Data Facts (queried live this session)

All facts below are `[VERIFIED: read-only queries via db.core_db against db/core.52.db, 2026-07-05]`.

| Fact | Value |
|------|-------|
| `scripture` flag counts | S=42,006 · J=29,902 · F=1,359 · H=138 · E=3 (total 73,408) |
| NULL-`Verse` rows by flag | S=10, H=138 — **zero** in J/F/E |
| Canonical count (`S`, `Verse IS NOT NULL`) | **41,996 exactly** |
| The 10 excluded `S` rows | IDs 31106 (Title Page), 31107 (Introduction), 31108/31109 (Testimonies of Three/Eight Witnesses), 37714 (D&C Explanatory Intro), 41507/41508 (Official Declarations 1-2), 42001-42003 (Abraham Facsimiles 1-3) |
| Books holding those 10 rows | 7 dedicated books (201-204, 301, 303, 403) that hold **zero real verses** — the `Verse IS NOT NULL` filter removes these books from the corpus entirely |
| `book` table | 99 rows: 5 volumes (`ParentBookID` NULL: OT=1, NT=2, BoM=3, D&C=4, PoGP=5) + 94 child books; **no 3-level nesting** (every verse's book's parent is a volume) |
| Books carrying S/J/F verses | 94 distinct BookIDs; after NULL-Verse exclusion, **87** books carry real verses |
| D&C shape | Book 302 `FullName='Sections'`, `Abbr='sec'`, `CiteAbbr='D&C'`, `NumChapters=138`, parent=4 ("Doctrine and Covenants", itself `CiteAbbr='D&C'`) — 3,654 S rows |
| Word-ordinal books (the ONLY four) | 205 "First Nephi", 206 "Second Nephi", 215 "Third Nephi", 216 "Fourth Nephi" (Abbr/CiteAbbr already digit-form: `1 ne`/`1 Ne.` …) |
| Em-dash names | Books 404 (`Joseph Smith—Matthew` / `JS—M`) and 405 (`Joseph Smith—History` / `JS—H`) — stored as **valid UTF-8 U+2014**; sqlite3 returns correct `str`; **zero U+FFFD anywhere** |
| `scripture.Text` Python type | **`bytes`** (BLOB storage class despite TEXT column decl) — decode required; `book` name fields return `str` |
| UTF-8 decode of all 73,267 S/J/F texts | 0 failures, 0 empty, 0 U+FFFD |
| Verses containing `<` (after exclusion) | **20**, all `S`, all D&C 77 (Q&A format), only tag: `<br />`; 1 of the 20 has a `<br>` with no adjacent whitespace |
| Verses containing entities (after exclusion) | **2** (`&nbsp;`): D&C 135:5 and JS—H 1:3 |
| Non-ASCII verse texts | 9,880 rows (curly quotes, em-dashes — all valid UTF-8) |
| `Verse<1` or `Chapter<1` rows | 0 |
| Duplicate `(BookID, Chapter, Verse)` keys across S/J/F | 30,837 — confirms dedup key must be `scripture.ID` |
| Normalized alias collisions across FullName/Abbr/CiteAbbr | Exactly one: `d&c` (volume 4 vs book 302) — benign, both → "Doctrine and Covenants" |
| Single-chapter books (`NumChapters=1`) | 13: Obadiah, Philemon, 2 John, 3 John, Jude, Enos, Jarom, Omni, Words of Mormon, Fourth Nephi, JS—Matthew, JS—History, The Articles of Faith |
| JST coverage | J/F rows exist across essentially all OT+NT books (e.g. Leviticus J×859, Ruth J×85) — `J` is a near-complete Bible parallel, not only changed verses (relevant to Phase 26, noted for accuracy) |
| Existing citations corpus book values | Stores raw `FullName` — "First Nephi" (2,145 citations), "Sections" (29,408 citations) — see Integration Notes |

## Architecture Patterns

### System Architecture Diagram

```
                    db/core.52.db  (read-only, via db.core_db)
                          │
        ┌─────────────────┴──────────────────┐
        │ SELECT … FROM book                 │ SELECT … FROM scripture s
        │ (all 99 rows, once)                │ JOIN book b ON b.ID = s.BookID
        │                                    │ LEFT JOIN book p ON p.ID = b.ParentBookID
        ▼                                    │ WHERE s.Flag IN ('S','J','F')
config/book_resolver.py                      │   AND s.Verse IS NOT NULL
  canonicalize()  ── build-time ──┐          ▼
  · em-dash guard (no-op, tested) │   extractors/scripture_extraction.py
  · First→1 … Fourth→4            │     │  per row:
  · Sections → "Doctrine and      │     │  1. clean_verse_text(Text bytes)   ◄── extractors/html_parsing_utils.py
    Covenants" (canonical book)   │     │     (decode UTF-8 → fast-path unescape
  · alias table:                  ├────►│      or BS4 get_text fallback)
    FullName/Abbr/CiteAbbr        │     │  2. book fields from canonicalized
    + generated variants          │     │     book record (digit form, volume)
  resolve(user_input) ── query-time     │  3. variant = S→standard, J/F→jst
    (consumed by Phases 27 & 28)        │  4. reference = f"{cite_abbr} {ch}:{v}"
                                        ▼
                              models/scripture_data.py
                                ScriptureVerse (per row, dedup key scripture_id)
                                      │ group by (book, chapter, variant)
                                      ▼
                                BookVerses containers  ──► consumed by Phase 26
                                                            (windowing/validation)
Tests: tests/test_book_resolver.py (resolver, no DB needed after build-input fixture)
       tests/test_scripture_extraction.py (exclusion→41,996, normalization, reference,
       clean_verse_text edge cases; live-DB with skip guard + synthetic fixtures)
```

Primary use case trace: DB row → decode/clean → canonical book lookup → `ScriptureVerse` → grouped `BookVerses` → (Phase 26).

### Recommended Project Structure
```
models/
└── scripture_data.py        # ScriptureVerse dataclass + BookVerses container (mirrors talk_metadata.py / paragraph_data.py)
config/
├── book_resolver.py         # canonicalize() + resolve(); no Weaviate/Ollama imports
└── pipeline_config.py       # + WEAVIATE_SCRIPTURE_COLLECTION_NAMES, SCRIPTURE_WINDOW_RADIUS=1, SCRIPTURE_BATCH_SIZE=500
extractors/
├── scripture_extraction.py  # read → clean → normalize → group
└── html_parsing_utils.py    # + clean_verse_text(raw) sibling helper (edit, not new file — locked D-01)
tests/
├── test_scripture_extraction.py
└── test_book_resolver.py
```

### Pattern 1: Read-only DB access through `db.core_db`
**What:** Use the existing shared `Database` instance — parameterized `select()`, read-only URI mode, 5s timeout handler, rows as dicts.
**When to use:** All extraction queries.
**Example:**
```python
# Source: db/__init__.py (existing project code)
from db import core_db  # Database(CORE_DB_PATH, read_only=True)

rows = core_db.select(
    """
    SELECT s.ID, s.BookID, s.Chapter, s.Verse, s.Flag, s.Text,
           b.Abbr, b.CiteAbbr, b.FullName,
           p.FullName AS volume
    FROM scripture s
    JOIN book b ON b.ID = s.BookID
    LEFT JOIN book p ON p.ID = b.ParentBookID
    WHERE s.Flag IN ('S', 'J', 'F') AND s.Verse IS NOT NULL
    ORDER BY s.BookID, s.Chapter, s.Verse, s.ID
    """
)
```
Note: `EXPECTED_CORE_TABLES` in `db/__init__.py` currently validates `book` only on `["ID","Abbr","FullName"]` and does not list `scripture` at all. Validation only checks listed tables, so this works as-is; **recommended hardening** (small, optional): extend `EXPECTED_CORE_TABLES` with `"scripture": ["ID","BookID","Chapter","Verse","Flag","Text"]` and add `CiteAbbr`/`ParentBookID`/`NumChapters` to `book` so a future DB version bump fails loudly. [VERIFIED: codebase]

### Pattern 2: `clean_verse_text` — decode + fast path + DOM fallback (locked D-01/D-02/D-03)
**What:** Single decode+clean entry point with an unconditional no-residual-tags post-condition.
**When to use:** Every `Text` value; also directly unit-tested with synthetic strings.
**Example:**
```python
# Source: locked CONTEXT decisions D-01/D-02/D-03 + behavior verified empirically this session
import html, re
from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")

def clean_verse_text(raw) -> str:
    """bytes/str in -> clean str out; guaranteed no residual HTML tags."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw  # D-03; 0 decode failures verified corpus-wide
    if "<" not in text:                                            # ~99.97% of verses (verified: only 20/73,257 have '<')
        cleaned = html.unescape(text.strip())
    else:
        cleaned = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    # Normalize NBSP from &nbsp;/unescape, collapse whitespace (mirrors render_span_text idiom)
    cleaned = _WS.sub(" ", cleaned.replace(" ", " ")).strip()
    return cleaned
```
Two verified behaviors force the last line — see Pitfalls 2 and 3.

### Pattern 3: Resolver two-function shape (locked in CONTEXT/SPEC)
**What:** `canonicalize()` runs once at build time over the 99 `book` rows and produces (a) canonical book records (digit-form name, Sections override, volume attached) and (b) a normalized alias → canonical-name lookup. `resolve(user_input)` is a pure dict lookup after applying the same normalization to the input.
**When to use:** Extraction consumes the canonical records; Phases 27/28 consume `resolve()`.
**Example:**
```python
# Source: SPEC §9 contract + verified book-table inventory
import re

_ORDINALS = {"first": "1", "second": "2", "third": "3", "fourth": "4"}

def _norm(s: str) -> str:
    """Case/period/space-insensitive alias key; folds em-dash/hyphen to space."""
    s = s.lower().replace("—", " ").replace("-", " ")
    s = s.replace(".", "").replace("&", " and ")   # "d&c" and "D. & C." fold together
    return re.sub(r"\s+", " ", s).strip()

def _digit_form(full_name: str) -> str:
    first, _, rest = full_name.partition(" ")
    if first.lower() in _ORDINALS and rest:
        return f"{_ORDINALS[first.lower()]} {rest}"   # "First Nephi" -> "1 Nephi"
    return full_name
```
Alias table build (per canonical book): register `_norm()` of FullName, Abbr, CiteAbbr, the digit-form name, the word-ordinal form (reverse bridge: "1 nephi" ↔ "first nephi"), and **prefix-stripped variants** of FullName ("The ", "The Epistle to ", "The Epistle of ", "To the ", "The Book of ") so "Romans", "Hebrews", "James", "Moses", "Abraham", "Articles of Faith", "Song of Solomon" resolve (see Pitfall 5). For D&C, both book 4 (volume) and book 302 (Sections) aliases map to canonical "Doctrine and Covenants" — the only collision in the table, and it is self-consistent. [VERIFIED: alias-collision scan over all 99 rows found only `d&c`]

### Pattern 4: Test strategy — both repo patterns apply (planner's call per CONTEXT)
- **Live-DB tests with skip guard** (like `tests/test_phase1.py` uses in-memory SQLite, and `tests/conftest.py` uses availability-skip fixtures): the 41,996 assertion and full-corpus invariants (no tags survive, no U+FFFD, all books digit-form) belong here, guarded by `os.path.exists(CORE_DB_PATH)` skip. The full S/J/F scan ran in seconds this session — corpus-wide assertions are cheap.
- **Synthetic fixtures**: `clean_verse_text` edge cases (bytes in, entities, `<br>` jam, empty), resolver alias forms, digit-form mapping — no DB needed. Resolver tests can also feed `canonicalize()` a hand-built 99-row-shaped list of dicts to stay DB-free.

### Anti-Patterns to Avoid
- **Normalizing book names per verse row** — canonicalize once over 99 book rows at resolver build time (locked D-04 scoping); the extractor joins verses to already-canonical book records.
- **String operations on `Text` in SQL** (`LIKE '%<%'` etc.) — `Text` cells are BLOB storage class; do content checks in Python after decode. [VERIFIED: db_schema_extractor sample shows `b'...'` values]
- **Building fixtures containing U+FFFD to test "repair"** — the data never contains U+FFFD; test the real shape (U+2014) plus the invariant "no U+FFFD after canonicalize" (D-05's test).
- **Importing Weaviate/Ollama/loader modules into `book_resolver.py` or the extractor** — Phase 25 must run with no live stack; keep imports stdlib + bs4 + `db` only.
- **A second normalization path in `server.py`'s `_normalize_book`** — do not extend it; it stays as-is for `find_by_scripture` (SPEC explicitly says resolver is NOT reusable from it).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML tag stripping | regex `<[^>]+>` stripper | `BeautifulSoup(...).get_text(separator=" ")` | Locked D-02; regex-on-HTML edge cases; BS4 already a dependency |
| Entity decoding | manual `&amp;`/`&nbsp;` replace table | `html.unescape` | stdlib, complete entity table; only `amp`/`nbsp` exist in data but unescape costs nothing |
| Encoding repair | byte-level heuristics or `ftfy` | plain `bytes.decode("utf-8")` | Verified: the corpus is 100% valid UTF-8; there is nothing to repair |
| DB connection management | new sqlite3 wrapper | `db.core_db` | Existing read-only + timeout + schema-validation wrapper |
| Deterministic grouping/containers | custom dict-of-dict machinery | dataclass container mirroring `TalkParagraphs` | Established repo pattern; Phase 26 consumes it |

**Key insight:** this domain's complexity is *inventory knowledge* (which rows to exclude, which names to normalize, which aliases exist), not algorithms. The research above enumerates the entire inventory, so plans can be written against exact, closed lists rather than defensive generality.

## Common Pitfalls

### Pitfall 1: The em-dash "mojibake" does not exist in the data — don't test a phantom
**What goes wrong:** Tests/fixtures built around U+FFFD (`'�'`) repair would pass vacuously or, worse, assert `FullName` contains '�' pre-repair and fail against the real DB.
**Why it happens:** The SPEC author observed '�' in a Windows console. Verified this session: book 404 `FullName` bytes are `Joseph Smith\xe2\x80\x94Matthew` — valid UTF-8 U+2014; sqlite3 returns a correct `str`; zero U+FFFD in all 99 book rows and all 73,267 verse texts. The '�' was cp1252 console rendering of UTF-8 output.
**How to avoid:** Keep D-04's `name.replace('�', '—')` as a defensive no-op guard (locked decision, harmless). Write D-05's test as the real deliverable: assert `canonicalize()` output contains no U+FFFD in any name, and assert `resolve("Joseph Smith—Matthew")`, `resolve("joseph smith-matthew")` (hyphen), and `resolve("js h")` all work with true U+2014 canonical output.
**Warning signs:** a fixture literally containing `'�'`; printing book names to a Windows console and "seeing" corruption. `[VERIFIED: byte-level scan]`

### Pitfall 2: `html.unescape("&nbsp;")` yields `\xa0`, not a space
**What goes wrong:** The D-02 fast path leaves a non-breaking space in D&C 135:5 and JS—History 1:3 (the only 2 entity-bearing verses), which then leaks into stored `text` and embeddings.
**Why it happens:** Verified empirically: `html.unescape('grace&nbsp;and')` → `'grace\xa0and'`.
**How to avoid:** After unescape/get_text, normalize ` ` → `' '` and collapse whitespace — the exact idiom `render_span_text` already uses in `html_parsing_utils.py`.
**Warning signs:** `\xa0` appearing in cleaned text assertions. `[VERIFIED: empirical run + DB scan]`

### Pitfall 3: `get_text()` without separator jams words across `<br />`
**What goes wrong:** `BeautifulSoup('Q. What?<br />A. It is.').get_text()` → `'Q. What?A. It is.'` — verified. 20 real verses (all of D&C 77) contain `<br />`; 1 of them has no whitespace adjacent to the tag.
**How to avoid:** `get_text(separator=" ")` then collapse whitespace. Verified that `separator=" "` does not alter plain text.
**Warning signs:** `"?A."` in cleaned D&C 77 output. `[VERIFIED: empirical run + DB scan]`

### Pitfall 4: `scripture.Text` arrives as `bytes` — everywhere
**What goes wrong:** `text.strip()`/`'<' in text` raise `TypeError` when handed bytes; SQL `LIKE` filters on Text silently misbehave on BLOB cells.
**Why it happens:** Cells carry BLOB storage class despite `TEXT` column declaration; both raw sqlite3 and `db.core_db.select()` return `bytes` for these cells (book name fields return `str`).
**How to avoid:** `clean_verse_text` accepts bytes-or-str and decodes first (locked D-03). Do content inspection in Python post-decode, never in SQL.
**Warning signs:** `TypeError: a bytes-like object is required` or `startswith` failures. `[VERIFIED: db_schema_extractor sample + query layer]`

### Pitfall 5: RES-01's "any common input form" is broader than the raw alias columns
**What goes wrong:** `resolve("Romans")`, `resolve("Hebrews")`, `resolve("Abraham")`, `resolve("Articles of Faith")`, `resolve("Song of Solomon")` fail if the alias table only registers raw FullName/Abbr/CiteAbbr — the DB stores `'The Epistle to the Romans'`/`'rom'`/`'Rom.'`, `'To the Hebrews'`/`'heb'`/`'Heb.'`, `'The Book of Abraham'`/`'abr'`/`'Abr.'`, `'The Articles of Faith'`/`'a of f'`/`'A of F'`, `'The Song of Solomon'`/`'song'`/`'Song'`.
**How to avoid:** Generate prefix-stripped alias variants at build time ("The ", "The Epistle to ", "The Epistle of ", "To the ", "The Book of ", "The Song of" → keep "Song of Solomon"). Closed set — verified against the complete 94-book inventory; stripping introduces no new collisions.
**Warning signs:** resolver tests only exercising Nephi/D&C forms and passing while common Bible names fail. `[VERIFIED: full alias inventory + collision scan]`

### Pitfall 6: Exclusion filter must combine Flag AND Verse conditions
**What goes wrong:** Filtering only `Verse IS NOT NULL` still admits `E` rows (all 3 have… actually `E` rows must be excluded by Flag) and filtering only `Flag IN ('S','J','F')` still admits the 10 front-matter rows.
**How to avoid:** `WHERE Flag IN ('S','J','F') AND Verse IS NOT NULL` — verified to yield exactly 41,996 S + 29,902 J + 1,359 F. NULL-Verse never occurs in J/F, so the compound filter loses no JST rows.
**Warning signs:** counts of 42,006 or 41,999-ish, or `<img>`/`<center>` HTML reaching `clean_verse_text` (only the excluded rows contain those tags).

### Pitfall 7: Resolver alias space includes books that have no verses
**What goes wrong:** "Official Declarations", "Title Page", "Facsimiles", "BM Intro." etc. are legitimate `book` rows (and the 5 volume rows have aliases like `'ot'`/`'Old Testament'`) but resolve to books with zero retrievable verses — `get_verse` in Phase 28 would return empty for a "successful" resolution.
**How to avoid (recommendation, planner discretion):** build the alias table from verse-bearing child books only (the 87), plus the D&C container mapping; either omit volumes/front-matter books or mark them non-verse targets. Document the choice — Phase 28's error contract (deferred per CONTEXT) will build on it.
**Warning signs:** `resolve("OT")` returning a volume name that `get_verse` can't serve. `[VERIFIED: 7 zero-verse child books enumerated]`

### Pitfall 8: Grouping/ordering must key on `scripture.ID` for dedup
**What goes wrong:** Using `(BookID, Chapter, Verse)` as a unique key collapses S/J twins — 30,837 such duplicate keys exist.
**How to avoid:** `scripture_id` is the dedup key (SPEC: UUID = `verse_{scripture_id}` later); grouping is `(book, chapter, variant)` so S and J of the same chapter land in different groups.
**Warning signs:** total ScriptureVerse count < 73,257. `[VERIFIED: duplicate-key count]`

## Code Examples

### 1. Extraction query (verified shape — see Pattern 1)
Covered in Architecture Patterns Pattern 1; `ORDER BY s.BookID, s.Chapter, s.Verse, s.ID` gives deterministic order and pre-sorts for grouping.

### 2. Variant + reference derivation (data-verified inputs)
```python
# Source: SPEC §4/§12 + verified book inventory
VARIANT_BY_FLAG = {"S": "standard", "J": "jst", "F": "jst"}

# reference uses the (possibly em-dash-bearing) CiteAbbr — needs no D&C special case:
# book 302 CiteAbbr is already 'D&C'  ->  "D&C 45:32"
# 1 Nephi CiteAbbr is '1 Ne.'         ->  "1 Ne. 3:7"
# Jude (single-chapter) stays uniform ->  "Jude 1:3"
reference = f"{cite_abbr} {chapter}:{verse}"
```

### 3. Canonical book derivation (verified special cases — the complete list)
```python
# Source: verified against all 94 child books in core.52.db
# The ONLY FullName -> canonical transformations required by EXT-04:
#   205 'First Nephi'  -> '1 Nephi'
#   206 'Second Nephi' -> '2 Nephi'
#   215 'Third Nephi'  -> '3 Nephi'
#   216 'Fourth Nephi' -> '4 Nephi'
#   302 'Sections'     -> 'Doctrine and Covenants'   (D&C flatness override)
# Everything else: canonical book = FullName verbatim (incl. long forms like
# 'The Epistle to the Romans' — see Open Question 2).
# volume = parent FullName; verified: no grandparents, single join suffices.
```

### 4. Live-DB test with skip guard (repo pattern)
```python
# Source: pattern from tests/test_phase1.py / tests/conftest.py
import os, unittest
from db import CORE_DB_PATH

@unittest.skipUnless(os.path.exists(CORE_DB_PATH), "core DB not available")
class TestExtractionAgainstLiveDB(unittest.TestCase):
    def test_canonical_count_is_exactly_41996(self):
        verses = extract_scripture_verses()
        standard = [v for v in verses if v.variant == "standard"]
        self.assertEqual(len(standard), 41996)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Talk pipeline: heavy HTML scraping (5 phases) | Scripture data is already relational — extraction collapses to read→decode→clean→normalize | v5.0 SPEC | No scraping code; this phase is small and fully offline |
| `server.py _normalize_book` (title-caser) for book input | Dedicated `book_resolver` with alias table | This phase | Resolver becomes the single normalization authority for the scripture corpus (Phases 27-28) |
| Assumed U+FFFD mojibake repair need | Verified clean UTF-8; repair is a defensive no-op + tests | This research | Test design changes (Pitfall 1); no data migration needed |

**Deprecated/outdated:** nothing in this phase's dependency set; BS4 4.14.3 is current stable.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Users of `resolve()` will input short common names ("Romans", "Hebrews", "Abraham") that don't match any raw DB alias column | Pitfall 5 / Pattern 3 | Low — adding prefix-stripped aliases costs a few lines; if users never type these, the aliases are inert |
| A2 | Phase 26+ consumers want `BookVerses` keyed by the *canonical* book name (not `book_id`) | Architecture | Low — container shape is explicitly planner discretion; grouping key choice is internal |

Everything else in this document is `[VERIFIED]` against the live database, the codebase, or empirical runs — no user confirmation needed beyond the D-04 test-design note already flagged inline in User Constraints.

## Open Questions (RESOLVED)

> **Resolution (Phase 25 planning, 2026-07-05):** All three questions below are resolved in executable plan content.
> - **Q1 (resolver failure contract): RESOLVED** — `resolve()` returns `Optional[str]` (`None` on miss), locked in `25-02` Task 1 with a docstring-contract acceptance criterion; error-message wrapping deferred to Phase 28.
> - **Q2 (long-form FullNames): RESOLVED** — FullNames stay verbatim (spec-conformant); adopted in `25-02`'s behavior list. Display-name remapping would be a REQUIREMENTS change, not a Phase 25 tweak.
> - **Q3 (citations-corpus inconsistency): RESOLVED (informational)** — carried into `25-03`'s SUMMARY output note for Phase 28 consumers.

1. **Resolver failure contract (raise vs `None`)** — deferred per CONTEXT.
   - What we know: SPEC §9 defines accepted inputs; Phase 28 consumes the error path.
   - What's unclear: exception vs sentinel on unresolvable input.
   - Recommendation: return `Optional[str]` (`None` on miss) — cheapest for Phase 28 to wrap in a tool-level error message; document in docstring so Phase 28 doesn't guess. Planner may lock this.

2. **Canonical value for long-form FullNames** — `book` for Romans will be **"The Epistle to the Romans"** (EXT-04 normalizes only Nephi ordinals + Sections + em-dash; everything else is FullName verbatim).
   - What we know: requirements and SPEC lock the normalization list; SPEC's examples never showed the awkward cases ("The Acts", "To the Hebrews", "The Epistle to the Romans", "The Song of Solomon", "The Book of Moses/Abraham", "The Articles of Faith").
   - What's unclear: whether users/planner find "The Epistle to the Romans" acceptable as the stored/filterable `book` value and resolver output.
   - Recommendation: keep FullName verbatim in Phase 25 (spec-conformant, and changing it would ripple into VAL-01/Phase 28 expectations); the resolver's alias coverage makes *input* ergonomic regardless. Surface to the user at plan time if they want "Romans"-style display names — that would be a REQUIREMENTS change, not a discretionary tweak.

3. **Pre-existing cross-corpus inconsistency (informational, not this phase's to fix)** — the citations corpus stores `book` = raw FullName ("First Nephi" ×2,145, "Sections" ×29,408), so `find_by_scripture("1 Nephi")` (title-cased to "1 Nephi") cannot match those stored values today. The new scripture corpus will store "1 Nephi"/"Doctrine and Covenants". Phase 28 may want `book_resolver` to bridge (canonical → FullName reverse map) — worth a note in the plan's downstream-effects section so it isn't rediscovered as a bug.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `db/core.52.db` | Extraction + live-DB tests | ✓ (queried this session) | schema matches SPEC | Synthetic-fixture tests still run; live tests skip |
| Python via pipenv (`pipenv run py`) | Everything | ✓ (all verification ran through it) | project venv | — |
| beautifulsoup4 | `clean_verse_text` fallback | ✓ | 4.14.3 | — |
| pytest | Test runner | ✓ (repo standard, 11+ test files) | installed | stdlib unittest runner |
| Weaviate / Ollama / Docker | **Not needed** — phase is pure/offline | n/a | — | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none missing.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (running unittest-style test classes — repo convention) |
| Config file | none (no pytest.ini/pyproject; tests use `sys.path.append` header pattern) |
| Quick run command | `pipenv run py -m pytest tests/test_scripture_extraction.py tests/test_book_resolver.py -x -q` |
| Full suite command | `pipenv run py -m pytest tests/ -q` (live-service tests auto-skip via conftest port checks) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXT-01 | S/J/F rows → ScriptureVerse with volume join + grouping | unit (live-DB, skip-guarded) | `pipenv run py -m pytest tests/test_scripture_extraction.py -x -q` | ❌ Wave 0 (phase deliverable) |
| EXT-02 | Exactly 41,996 canonical; no NULL-Verse or E rows survive | unit (live-DB) | same | ❌ Wave 0 |
| EXT-03 | `clean_verse_text`: bytes in, no tags out, `\xa0`/`<br>` handling, D&C 77 spot checks | unit (synthetic + live spot check) | same | ❌ Wave 0 |
| EXT-04 | Digit-form book, Sections override, em-dash integrity (no U+FFFD post-canonicalize) | unit | `pipenv run py -m pytest tests/test_book_resolver.py -x -q` | ❌ Wave 0 |
| EXT-05 | `reference` CiteAbbr format ("1 Ne. 3:7", "D&C 45:32", "Jude 1:3"); variant/source_flag mapping | unit (synthetic) | `... tests/test_scripture_extraction.py` | ❌ Wave 0 |
| RES-01 | All alias forms resolve; case/period/space/dash-insensitive; common short names | unit (synthetic) | `... tests/test_book_resolver.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** quick run command above (the two new files only — seconds)
- **Per wave merge:** `pipenv run py -m pytest tests/ -q` (full suite; existing 11 test files must stay green — especially `tests/test_html_parsing_utils.py` after the `clean_verse_text` addition)
- **Phase gate:** full suite green including the live-DB 41,996 assertion before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_scripture_extraction.py` — covers EXT-01…EXT-05 (phase deliverable, not pre-existing gap)
- [ ] `tests/test_book_resolver.py` — covers EXT-04, RES-01 (phase deliverable)
- Framework install: none needed — pytest + fixtures infrastructure already in place; no conftest changes required (new tests need no live services)

## Security Domain

This phase is an offline, read-only, local-data pipeline: no network, no auth, no user-facing endpoints (resolver input handling ships to users only in Phase 28).

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (no live services touched) |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes (narrow) | `resolve()` treats input as an opaque lookup key — normalization is pure string ops; never interpolate user input into SQL (resolver reads the book table via parameterized `db.core_db.select` or a pre-fetched list) |
| V6 Cryptography | no | — |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via book-name input | Tampering | Parameterized queries only (already the `db.Database` idiom); resolver does dict lookups, not query construction |
| Unexpected DB writes | Tampering | `core_db` is read-only mode (`file:...?mode=ro`) — keep using the shared instance, never construct a writable connection |
| Malicious HTML in verse text (stored XSS at some future surface) | Tampering | `clean_verse_text`'s unconditional no-tags post-condition is itself the mitigation; the unit test asserting no `<` survives is the control |

## Integration Notes (for the planner)

- **`book_resolver` is the shared dependency** consumed by Phase 27 (pipeline) and Phase 28 (`get_verse`/`search`). Its canonical output must equal the stored `book` value exactly — which this phase controls end-to-end, so add a test asserting `resolve(x) in {v.book for v in extracted}` for representative x.
- **Config constants** (`WEAVIATE_SCRIPTURE_COLLECTION_NAMES = {"verses": "ScriptureVerses"}`, `SCRIPTURE_WINDOW_RADIUS = 1`, `SCRIPTURE_BATCH_SIZE = 500`) are added now per SPEC §8/§13 even though only Phase 26/27 consume the latter two.
- **CLAUDE.md Project Structure Index** must be updated with the 4-5 new files (maintenance rule).
- **`html_parsing_utils.py` edit** is the only touch to existing shared code — `tests/test_html_parsing_utils.py` must stay green; `clean_verse_text` gets its own tests (either in that file per module convention, or in `test_scripture_extraction.py` — planner's call, but pick one home).
- **Do not modify** `server.py`, loaders, or the talk extractors in this phase.

## Sources

### Primary (HIGH confidence)
- Live `db/core.52.db` — read-only verification queries via the project `db` module (flag counts, exclusions, book inventory, byte-level encoding scan, tag/entity census, alias collisions) — run 2026-07-05 this session
- `scripts/db_schema_extractor.py` output — `scripture`/`book` schemas, storage-class evidence
- Codebase: `db/__init__.py`, `extractors/html_parsing_utils.py`, `config/pipeline_config.py`, `models/talk_metadata.py`, `extractors/phase3_citation_extraction.py`, `server.py`, `tests/test_phase1.py`, `tests/conftest.py`
- Empirical stdlib/BS4 behavior runs in the project venv (`html.unescape` NBSP, `get_text` separator, bs4 4.14.3)
- `docs/scriptures/SPEC.md` (design authority) + `.planning/phases/25-.../25-CONTEXT.md` (locked decisions)

### Secondary (MEDIUM confidence)
- none needed — no external web research performed; the phase introduces no new dependencies and all domain questions were answerable from the primary sources above (no search providers configured: brave/exa/firecrawl all false in init context)

### Tertiary (LOW confidence)
- none

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; everything verified installed and working
- Architecture: HIGH — locked by SPEC/CONTEXT; discretionary areas mapped with verified data inventories
- Pitfalls: HIGH — each pitfall reproduced or measured against the real database this session
- Data facts: HIGH — every count/claim queried live, including the two SPEC corrections (no U+FFFD; long-form FullNames)

**Research date:** 2026-07-05
**Valid until:** stable — data facts hold until the next conference DB version bump (`core.53.db`+); re-verify flag counts and the 41,996 assertion after any `scripts/UPDATE.py` run
