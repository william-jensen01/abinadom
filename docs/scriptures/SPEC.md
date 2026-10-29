# Scriptures — v1 Specification

**Status:** Planned (spec + phase plan complete; not yet implemented). See §13 for phases.
**Scope:** Add a searchable, retrievable **scripture verse** corpus alongside the existing
conference-talk corpus, sourced from the core DB (`db/core.52.db`). Milestone-sized; to be broken into phases.

---

## 1. Goal

Today the corpus contains conference talks + citation *references* only — **the words of
scripture are not searchable content anywhere.** When an LLM wants a verse's text it falls
back to training-data recall. v1 makes scripture a **first-class searchable corpus**:
semantic + hybrid search over verse text, exact-reference retrieval, and grounded
composition with the existing talk tools.

**One line:** v1 = *"the scriptures become a first-class searchable corpus."*
v2 (future, separate) = *"the scriptures become a navigable study library"* (headings,
cross-references, Topical Guide — requires a Church-API scrape).

---

## 2. Scope

### In (v1)
- Canonical verse text (`Flag='S'`) — 42,006 verses across OT, NT, BoM, D&C, PoGP.
- JST verses (`Flag='J'` parallel + `Flag='F'` fragments/expansions) — ~31k, marked
  `variant='jst'`.
- A single **`ScriptureVerses`** Weaviate collection (verse-only).
- New MCP tool `get_verse`; `search` and `corpus_stats` extended to the new collection.
- Windowed embedding (see §6) on the **existing Ollama / nomic** stack.

### Out (deferred to v2 — Church-API "study apparatus" milestone)
- **Chapter/section headings & intros.** The DB's `Flag='H'` rows exist **only for the 138
  D&C sections** — zero headings for OT, NT, BoM, PoGP. Loading them now ships a lopsided
  feature (1 of 5 volumes) and forces an extra `record_type` field. Complete, uniform
  headings require the Church API, so **all headings land together in v2.** Net effect: v1
  has a single `variant` field and **no `record_type`.**
- Chapter summaries, footnote cross-reference apparatus (`a`/`b`/`c` → Topical Guide, Bible
  Dictionary, related verses), verse↔verse graph. **None of this exists in `core.db`** —
  every one of the 125,406 citations has a *talk* source; there are no scripture→scripture
  references in the data.

### v1 vs v2 at a glance
| | v1 (`core.52.db`) | v2 (Church API) |
|---|---|---|
| Content | Canonical (`S`) + JST (`J`,`F`) verse text | v1 **plus** study apparatus |
| Adds | Searchable scripture, `get_verse`, hybrid+semantic | Headings (all volumes), summaries, footnote cross-refs, TG, verse↔verse graph |
| Data shape | Clean, already-relational; no scraping | New source; HTML scrape + parse (like talk Phases 1–4) |
| Field impact | `variant` only | reintroduces `record_type`/heading records + cross-ref model |

v1 stands alone and delivers real value; v2 is purely additive on top.

---

## 3. Data source

Read directly from the core DB (per project rule, via schema-aware access — never open the
DB file ad hoc). The filename is **versioned** — currently `db/core.52.db`, where the `.52`
rolls with conference updates; resolve the path the same way `scripts/UPDATE.py` and the
talk pipeline already do rather than hardcoding a literal name. Two tables:

**`scripture`** (73,408 rows) — atomic unit is the verse, partitioned by `Flag`:
| Flag | Count | Meaning | v1? |
|------|-------|---------|-----|
| `S` | 42,006 | Canonical verse text (10 are non-verse front matter — see note) | ✅ `variant=standard` |
| `J` | 29,902 | JST parallel (OT + NT) | ✅ `variant=jst` |
| `F` | 1,359 | JST fragments/expansions | ✅ `variant=jst` |
| `H` | 138 | D&C section headings (`Verse` NULL) | ❌ v2 |
| `E` | 3 | Decorative "THE END" HTML markers | ❌ junk, always excluded |

> **Exclude non-verse `S` rows (verified against `core.52.db`):** 10 `S` rows have **NULL
> `Verse`** — they are front matter, not verses: the BoM Title Page / Introduction / Testimony
> of Three & Eight Witnesses, the D&C Explanatory Introduction, Official Declarations 1–2, and
> the three Abraham Facsimiles (pure `<img>` HTML). **Drop every `S` row with NULL `Verse`** →
> effective canonical count **41,996**. (Official Declarations are canonical but verse-less →
> a v2 candidate, not a v1 verse.)

Columns: `ID, BookID, Chapter, Verse, Flag, Text`. **`Text` is stored as UTF-8 bytes** →
decode. Verses (`S/J/F`) are largely plain text; watch for light inline HTML (e.g. `<i>`
for KJV supplied/italicized words) → clean via `extractors/html_parsing_utils.py`.

> **Note:** the same `(BookID, Chapter, Verse)` can exist as both `S` and `J` (e.g. Genesis
> 8:19 appears twice). Dedup key is therefore the row's `ID` (→ `verse_{ID}`), and `variant`
> disambiguates the two texts.

**`book`** (99 rows) — hierarchical via `ParentBookID`. Top-level (`ParentBookID` NULL) =
5 volumes (Old Testament, New Testament, Book of Mormon, Doctrine and Covenants, Pearl of
Great Price). 94 child books (Genesis=101, First Nephi=205, …) carry: `Abbr, CiteAbbr,
FullName, NumChapters, URLPath`. **`volume` = the parent book's `FullName`.** Three verified
findings shape `book`/`reference` derivation:
> - **D&C is flat.** Its section verses all live in one child book **302, `FullName="Sections"`**
>   (`Chapter` = section 1–138), parented to the "Doctrine and Covenants" volume. The generic
>   rule (`book` = child `FullName`) would render **"Sections 45:32"** — wrong. **Special-case:
>   the `Sections` container's display `book` = "Doctrine and Covenants"** (its `CiteAbbr` is
>   already `"D&C"`, so the CiteAbbr-based `reference` needs no special-case). Only D&C has
>   this shape; every other volume has properly citable child books.
> - **Numbered-book naming is inconsistent → normalize to digits.** `FullName` is digit-form
>   for **17 of 21** numbered books ("1 Samuel", "2 John", "1 Corinthians") but **word-form for
>   the 4 BoM Nephi books** ("First Nephi" … "Fourth Nephi"). The canonical `book` value
>   normalizes all to the **long digit form** ("1 Nephi") via a closed `{First→1 … Fourth→4}`
>   map; `Abbr`/`CiteAbbr` already use digits ("1 ne" / "1 Ne."). The resolver (§7/§9) maps any
>   input form onto this canonical `book`.
> - **Encoding artifacts in names.** Some `FullName`/`CiteAbbr` carry a mangled em-dash
>   ("Joseph Smith—Matthew" stored as `Joseph Smith�Matthew`, `JS�M`) → clean at extraction,
>   not just in verse `Text`.

---

## 4. Data model (`models/scripture_data.py`, new)

```
@dataclass
class ScriptureVerse:
    scripture_id: int      # scripture.ID (PK) — dedup key
    book_id: int           # child book id
    book: str              # canonical digit-form name ("Genesis", "1 Nephi", "1 Corinthians"); "First Nephi"->"1 Nephi", D&C "Sections"->"Doctrine and Covenants"
    book_abbr: str         # book.Abbr
    cite_abbr: str         # book.CiteAbbr ("Alma", "1 Ne.", "D&C")
    volume: str            # parent book FullName ("Book of Mormon")
    chapter: int
    verse: int
    variant: str           # "standard" (S) | "jst" (J, F)
    source_flag: str       # raw S/J/F — provenance (cf. citation parse_source)
    reference: str         # CiteAbbr-based citation, e.g. "1 Ne. 3:7", "D&C 45:32" (derived, stored)
    text: str              # clean verse text (returned to caller)
    context_window: str    # the windowed string actually embedded (see §6)
```

Plus a `BookVerses` / container type for per-(book, chapter, variant) grouping during
windowing, mirroring the `TalkParagraphs`-style containers.

---

## 5. Weaviate collection schema

Collection **`ScriptureVerses`**, vectors self-provided (vectorizer disabled), UUID =
`generate_uuid5(f"verse_{scripture_id}")` — same deterministic-idempotent pattern as talks.

Properties: `scripture_id` INT, `book_id` INT, `book` TEXT, `book_abbr` TEXT,
`cite_abbr` TEXT, `volume` TEXT, `chapter` INT, `verse` INT, `variant` TEXT,
`source_flag` TEXT, `reference` TEXT, `text` TEXT, `context_window` TEXT, `doc_id_str` TEXT.

**Storage rich, filter surface lean:** all fields stored (cheap); only
`book`, `volume`, `chapter`, `variant` are exposed as `search` filter params (see §9).
`verse`/abbrs are stored-but-not-filter-exposed (pinpointing is `get_verse`'s job).

---

## 6. Embedding strategy — reference-prefixed, canonical-only neighbor window

Verses are single sentences; embedding them bare is context-starved. v1 prefixes every verse
with its reference and, **for canonical (`standard`) verses only, adds a chapter-bounded
neighbor window** — the same embed-≠-store split the `citations` loader uses (embed
`context_window`, store raw `text`).

```
# standard (S): reference prefix + neighbor window
context_window = "{book} {chapter}:{verse}\n{prev_text}\n{this_text}\n{next_text}"
# jst (J, F): reference prefix + the verse alone — no neighbors
context_window = "{book} {chapter}:{verse}\n{this_text}"
text           = clean verse text alone
embed_fn(context_window)   # nomic via Ollama, list[str] -> list[list[float]]
```

- The reference prefix is a zero-cost dose of contextual anchoring (disambiguates "faith"
  in Alma 32 from Hebrews 11) without an LLM generating summaries we don't have.
- **Windowing applies to canonical verses only (verified rationale).** Canonical `S` chapters
  are **perfectly contiguous** — all 1,583 (book, chapter) groups start at verse 1 with zero
  gaps — so neighbor windows are clean. **JST is sparse:** it stores only the verses Joseph
  Smith changed, so **19% of `J` and 46% of `F`** chapter-groups are non-contiguous (a
  chapter's verses might be `{19, 22, 30}`). Windowing those would splice semantically
  non-adjacent verses, so **JST verses are embedded reference-prefixed but un-windowed.** This
  also erases gap-handling complexity entirely. *(Deliberate v1 simplification — surface it in
  the pipeline README so it doesn't read as an oversight.)*
- **Neighbor selection for `S` (correctness-critical):**
  1. same `book_id` **and** same `chapter` (clamp at edges — no cross-chapter bleed);
  2. neighbors are **adjacent in the ordered-by-`verse` sequence** within the group (S is
     contiguous, so this equals `verse±radius`; the sequence rule is what keeps chapter edges
     correct);
  3. `standard` only — JST is never windowed, so a KJV verse can never be windowed against its
     JST twin.
- **Window radius is configurable** (`SCRIPTURE_WINDOW_RADIUS`, default `1`) — eval picks
  1 vs 2. Not hardcoded.
- Queries are embedded as-is (no window).

**Why this and not more:** late chunking (the true optimum) requires token-level hidden
states that Ollama's endpoint doesn't expose → a serving-stack change with large blast
radius across the shared embedding surface. Parked in `backlog.md` ("Late chunking"). The
model choice (stay on nomic) and multi-model routing are analyzed in `backlog.md`
("Embedding model"). Both are non-blocking for v1.

---

## 7. Pipeline stages

Far simpler than the talk pipeline — data is already relational and clean, so there is **no
HTML scraping**. The pipeline collapses to read → decode/clean → window → validate → load.

| Stage | Where (new unless noted) | Does |
|-------|--------------------------|------|
| 1. Extract | `extractors/scripture_extraction.py` | Read `scripture` (Flag ∈ S,J,F, **excluding NULL-`Verse` rows**) joined to `book` (+parent for `volume`); decode UTF-8 bytes; clean light HTML **and name-encoding artifacts** via `html_parsing_utils`; **normalize `book` to canonical digit form** (Nephi word→digit "1 Nephi", D&C `Sections`→"Doctrine and Covenants", em-dash repair); build `ScriptureVerse` rows grouped by (book, chapter, variant). |
| 2. Window | same module | Compute `context_window` per §6 — neighbor window for `standard`, reference-prefix-only for `jst`. |
| 3. Validate | `extractors/scripture_validation.py` | Per-verse + per-chapter sanity (see §10). |
| 4. Transform | `loaders/shared_transforms.py` → new `prepare_verse_records()` | `(document=context_window, meta, doc_id=verse_{id}, vector)` tuples; reuse `rich_metadata`. |
| 5. Load | new `ScriptureLoader` (sibling of `WeaviateLoader`, both on `BaseLoader`) | Ensure `ScriptureVerses` schema (idempotent); batch-embed `context_window`; upsert via deterministic UUID. |
| Orchestrate | `scripts/run_scripture_pipeline.py` | Streaming, resume (`verse_exists`), `--force`, batching — mirrors `run_pipeline.py`. |

**Loader design decision:** add a **separate `ScriptureLoader`** rather than overload
`WeaviateLoader.load(TalkBundle)`. The talk loader's `load()` is bundle-shaped across 4
collections; scripture is a different shape (v1: the single `ScriptureVerses` collection). A
focused sibling keeps the talk path untouched (minimal impact) while sharing `BaseLoader`
(embed_fn + batch_size DI) and the schema-idempotency pattern. The name is deliberately
**`ScriptureLoader`, not `ScriptureVerseLoader`** — this loader *owns the scripture corpus*
and is meant to grow `record_type` handling in v2 (headings, summaries) rather than spawn a
parallel loader per collection. (The v2 verse↔verse cross-reference graph is edge-shaped,
not a text document, and may get its own small builder — that is not a second document
loader.)

---

## 8. Config / naming changes (`config/pipeline_config.py`)

```
WEAVIATE_SCRIPTURE_COLLECTION_NAMES = {"verses": "ScriptureVerses"}
SCRIPTURE_WINDOW_RADIUS = 1          # neighbor window radius (eval-tunable)
SCRIPTURE_BATCH_SIZE = 500           # loader batch size
```

Embedding model stays `nomic-embed-text` (Ollama). Keep model selection expressible as a
**config value keyed by collection-group, defaulting to nomic**, so a future per-corpus
model is a one-line change + routing lookup (do not build routing now — see backlog).

---

## 9. MCP tool surface

### `search` (extend)
- Add `"scripture_verses"` as a valid `collection`.
- Exposed filters: **`book`, `volume`, `chapter`, `variant`**.
- **Defaults to `variant=standard`.** JST is ~42% of the corpus (31k of ~73k); returning it
  unfiltered would swamp canonical results. `search` over `scripture_verses` returns canonical
  only unless the caller sets `variant` (`jst`, or `both` to include JST). `book`/`chapter`
  filter inputs are normalized through the same resolver as `get_verse` (see below).
- `alpha` hybrid blend works as-is; **hybrid matters *more* here** — users recall KJV
  fragments (`"charity suffereth long"` → BM25) as often as themes (`"patience in love"` →
  vector).
- No `group_by_chapter` in v1 (collides with the `hybrid`+`group_by` Weaviate limitation in
  `backlog.md`). The LLM gets a chapter via a `book ∧ chapter` filter and reasons over the
  returned verses — retrieval primitive, not answer engine.

### `get_verse` (new — the `get_talk` analog)
```
get_verse(book, chapter, verse_start=None, verse_end=None, variant="standard")
  -> ordered list of {reference, book, chapter, verse, text, variant}
  # get_verse("Alma", 32, 21)        -> Alma 32:21
  # get_verse("Alma", 32, 26, 43)    -> Alma 32:26–43 in order
  # get_verse("Alma", 32)            -> the whole chapter, in order
  # get_verse("Genesis", 8, 19, variant="both") -> KJV + JST side by side
```
Pure filter query — **no embedding / no Ollama** (works even when Ollama is down, like
`find_by_scripture`). Makes verse text quotable without a semantic round-trip.

- **`variant` accepts `standard` (default), `jst`, or `both`.** `both` returns the canonical
  and JST texts of the same reference together (the one JST comparison feature v1 supports),
  ordered by verse then variant.
- **Full ordered chapter or verse range = `get_verse`** (deterministic, complete, in
  scripture order). A **thematic subset *within* a chapter = `search` + `book ∧ chapter`
  filter** (relevance-ranked top-k, not the full ordered chapter). E.g. "give me all of Alma
  32" → `get_verse("Alma", 32)`; "the verses in Alma 32 about faith as a seed" → `search`.
- **Book resolution → dedicated resolver sub-module** (`config/book_resolver.py`, new; shared
  by `get_verse` **and** `search` filters). It is **not** reusable from `find_by_scripture`
  (whose `_normalize_book` is only a title-caser). The resolver builds a lookup from the `book`
  table over `FullName` + `Abbr` + `CiteAbbr`, normalizes case/periods/spaces, bridges
  **word↔digit ordinals** ("1 Nephi" / "First Nephi" / "1 Ne."), maps "D&C" /
  "Doctrine and Covenants" onto the D&C container, and repairs the em-dash mojibake.
  **Canonical output = the digit-form `book`** ("1 Nephi") — the same value stored on the
  verse, so resolver output and stored `book` are always identical.
- **Single-chapter books** (Jude, Obadiah, Enos, Words of Mormon, the Articles of Faith, …):
  `get_verse` accepts **both** `get_verse("Jude", 1, 3)` and the shorthand
  `get_verse("Jude", 3)` (lone numeric arg read as the verse, chapter defaults to 1);
  `get_verse("Jude")` returns the whole book. Stored `reference` stays uniform "Jude 1:3".

### `corpus_stats` (extend)
- Add `scripture_verses`; groupable by `volume`, `book`, or `variant` (e.g. verse counts
  per volume, standard vs JST split).

### `find_by_scripture` (unchanged)
- Still returns *talks* that cite a reference. Combined with `get_verse`, this gives
  **verse ↔ talks** navigation with **zero denormalization** — no `citation_count` /
  `citing_talk_ids` on verse objects (deliberately dropped; those two tools already serve
  both directions live).
- **Caveat (pre-existing):** the `citation` table spans **7,415 distinct TalkIDs** vs the
  **5,838** talks in the searchable `ConferenceTalks` corpus, so some cited talks (JD
  discourses, etc.) fall outside the retrievable set. `find_by_scripture` returns what is in
  the corpus — coverage is broad but not exhaustive; this is existing behavior, not a
  scripture-v1 regression.

---

## 10. Validation & verification

**Validation (Stage 3, per-verse / per-chapter):**
- `text` non-empty after decode + clean; no residual HTML tags (verses **and** book names).
- `verse >= 1`, `chapter >= 1`; `variant ∈ {standard, jst}`; **no NULL-`Verse` row survived
  extraction** (the 10 front-matter rows are dropped).
- `book` is canonical digit form — never "Sections" (D&C override) and never a word-ordinal
  ("First Nephi" → "1 Nephi"); D&C `reference` renders as "D&C …".
- **`standard` only:** per (book, chapter) warn on verse-number gaps / non-monotonic
  sequences — canonical is contiguous, so any gap is a real defect. **JST gaps are expected
  and NOT warned** (sparse by nature; 19% of `J` / 46% of `F` groups are non-contiguous).
- Chapter count per book sanity vs `book.NumChapters` (warn).
- `context_window` present for every verse; for `standard` it did not cross chapter
  boundaries; for `jst` it contains only the reference prefix + own `text` (no neighbors).

**Post-load verification (`scripts/verify_weaviate_scripture.py`, new — SCR-01…):**
- SCR-01 object count = expected (S+J+F, minus NULL-verse and validation drops; canonical
  ≈ 41,996).
- SCR-02 all 5 volumes present.
- SCR-03 spot-check known verses retrievable (John 3:16, Alma 32:21, 1 Nephi 3:7).
- SCR-04 `variant` distribution matches DB counts.
- SCR-05 no empty `text`; no missing `context_window`.
- SCR-06 semantic sanity (search "faith" / "charity" returns on-theme verses).

---

## 11. Deferred / future (non-blocking, see `backlog.md`)
- **v2 study apparatus** (Church API): headings for all volumes, summaries, footnote
  cross-references, Topical Guide, verse↔verse graph. Reintroduces `record_type`.
  - **Traversal engine for the edge-shaped graph — consider `pgGraph`.** §7 and §12 both
    flag that the v2 verse↔verse graph is *edge-shaped, not a text document*, and leave the
    mechanism open. Weaviate finds records by meaning; it does not walk an edge, so today a
    multi-hop query costs one round-trip per hop plus a Python join, and fan-out grows at
    each hop. `pgGraph` (Evokoa, Apache-2.0, Rust/pgrx, PG 14–18) compiles FKs into an
    in-memory CSR array and serves BFS / shortest-path / neighborhood as index lookups.
    Only half the edges exist today: `core.52.db` already holds talk→citation→verse-reference
    edges, but **verse↔verse edges do not exist** (§2) — they arrive with the v2 Church-API
    scrape. **Composes with Weaviate rather than replacing it** — Weaviate resolves the entry
    record semantically, `pgGraph` traverses from it; the CSR is a read-only artifact.
    Unlocks "talks citing the cross-refs of verse X", shortest citation path between two
    talks, everything within N hops of a verse. Costs: a Postgres instance, mirroring the
    relevant `core.52.db` tables (SQLite, the current source of truth) into it — or migrating
    the source of truth — a `cargo-pgrx` build, and one `BaseLoader` sibling. Caveats:
    unevaluated here — the Phase 20–22.2 benchmark
    harness (`BaseLoader`, `shared_transforms`, `benchmark/runner.py`) is the cheap path to
    a real verdict; unbounded traversal can crash a DB, so depth/frontier limits are
    mandatory.
  - **Sibling extension — `pgContext`** (Evokoa, Apache-2.0, Rust): "a full AI search engine
    built into Postgres" — a pgvector drop-in fusing ~10 retrieval methods into one ranked
    pass. Together the two extensions are what *Polygres* packages; both are Apache-2.0 and
    **self-hostable** — only the managed dashboard is cloud-only, and this project needs no
    dashboard. `pgContext` is therefore a legitimate 4th loader in the Phase 20–22.2
    harness, **not** a presumptive swap: Weaviate won Phase 23 on measured numbers (serial
    p50 42ms, filtered p50 51ms, recall@k10=0.9875) and any replacement must beat that on
    the same 8 canonical queries. The real draw is **one store for all three access
    patterns** — relational filter, edge traversal, vector search — which would retire the
    Phase 9.1 denormalization tax (see VER-06 `--force` re-run) and let `find_by_scripture`
    run as a native relational query instead of a vector-store lookup. (`get_verse` is
    already a pure filter query in v1 — §9 — so it gains little.)
  - Sequencing: evaluate at v2 planning, not during v1. Do not let either extension touch
    the v1 verse path.
- **Embedding model revisit** — stay on nomic for v1; arctic/gte are same-paradigm +1–3
  BEIR gated on a re-embed; bge-m3's win needs in-process serving.
- **Late chunking** — true contextual optimum; blocked by Ollama serving path.
- **Multi-model routing** — feasible, config-gated, YAGNI for v1.
- **nomic task prefixes** (`search_document:`/`search_query:`) — ✅ resolved 2026-10-28 in
  `config/embedding.py` (llama-server embedder); scripture loading must use `task="document"`.

---

## 12. Open questions
1. **HTML / encoding scope** — confirm across the *full* S/J/F set how much inline
   HTML/entities the verse `Text` contains (sampling showed plain text; KJV italics may use
   `<i>`), **and** the extent of the em-dash mojibake in `book` `FullName`/`CiteAbbr`. Decide
   clean-vs-preserve at validation time. *(The only genuinely-open item — needs sampling of
   the real data.)*

### Resolved (confirmed decisions)
- **Book resolution → new sub-module** (`config/book_resolver.py`), shared by `get_verse` and
  `search` filters. **Accept all common-sense forms** — `FullName`, `Abbr`, `CiteAbbr`,
  case-insensitive, word↔digit ordinals ("1 Nephi"/"First Nephi"/"1 Ne."), "D&C". **Not**
  reusable from `find_by_scripture` (its `_normalize_book` is a naive title-caser). SCR-03
  fixtures may use any accepted form.
- **Windowing scope** — **canonical (`standard`) only.** Canonical chapters are contiguous;
  JST is sparse (19% `J` / 46% `F` groups non-contiguous), so JST is embedded
  reference-prefixed but **un-windowed** (§6). Erases gap-handling complexity.
- **`reference` format** — **CiteAbbr-based** ("1 Ne. 3:7", "D&C 45:32", "Alma 32:21").
  Single-chapter books stay uniform ("Jude 1:3").
- **`book` field** — canonical **long digit form** ("1 Nephi", not "First Nephi"): normalize
  the 4 BoM Nephi word-ordinals to digits, apply the D&C **`Sections`→"Doctrine and Covenants"**
  override, repair the em-dash. Uniform across the corpus; `cite_abbr`/`reference` hold the
  abbreviation. This is also the resolver's canonical output.
- **Exclude non-verse `S` rows** — the 10 NULL-`Verse` front-matter rows are dropped
  (canonical ≈ 41,996).
- **`get_verse` single-chapter ergonomics** — accepts both `("Jude", 1, 3)` and shorthand
  `("Jude", 3)`; `("Jude")` returns the whole book.
- **`reference` field** — **stored** (derived at build, persisted for convenience).
- **`source_flag`** — **kept.** Preserves the raw J-vs-F provenance that `variant` collapses
  (mirrors the talk pipeline's `parse_source`). Low-risk, stored-not-filtered.
- **`get_verse` variant** — **defaults to `standard`; also accepts `jst` and `both`** (§9).
- **Window radius** — **default `1`** (`SCRIPTURE_WINDOW_RADIUS`, config-gated). Radius 2 is
  a tune-later knob, not a design decision — bump only if eval shows recall gains that beat
  the precision cost. Non-blocking for v1.
- **Loader** — **separate `ScriptureLoader`** on `BaseLoader` (not a generalized
  `WeaviateLoader`). One loader owns the scripture collection(s) and grows `record_type`
  handling in v2. The v2 verse↔verse cross-reference graph is edge-shaped (not a text
  document), so it may warrant its own small builder — that does not undercut a single
  document loader.

---

## 13. Phase plan

Five phases, mostly linear (each gates the next). Every phase ends at a **verifiable
checkpoint** — a passing test suite and/or an observable artifact — so nothing is "done" on
assertion alone. Phases 1–2 are pure/offline (no Weaviate, no Ollama) and fully unit-testable;
3–5 touch the live stack.

### Phase 1 — Data model, book resolver & extraction
**Goal:** turn `core.52.db` rows into clean, canonical `ScriptureVerse` objects in memory.
**New files:** `models/scripture_data.py` (`ScriptureVerse`, `BookVerses` container),
`config/book_resolver.py`, `extractors/scripture_extraction.py`,
`tests/test_scripture_extraction.py`, `tests/test_book_resolver.py`.
**Config:** add `WEAVIATE_SCRIPTURE_COLLECTION_NAMES`, `SCRIPTURE_WINDOW_RADIUS`,
`SCRIPTURE_BATCH_SIZE` to `config/pipeline_config.py`.
**Tasks:**
- `book_resolver`: build alias lookup from the `book` table (FullName/Abbr/CiteAbbr), define
  the canonical **digit-form** name, word↔digit ordinal bridge, D&C `Sections` + "D&C" mapping,
  em-dash repair. One `canonicalize()` (build-time) + `resolve(user_input)` (query-time).
- Extraction: read `scripture` (Flag ∈ S,J,F) joined to `book` (+parent volume); **exclude
  NULL-`Verse` rows**; decode UTF-8 bytes; clean light HTML via `html_parsing_utils`; set
  `book`/`cite_abbr`/`reference`/`volume`/`variant`/`source_flag`; group by (book, chapter,
  variant). Resolves **open Q1** (HTML/encoding scope) by sampling during dev.
**Checkpoint:** unit tests green — exclusion (41,996 canonical), digit-form `book`
(incl. "1 Nephi"), D&C → "Doctrine and Covenants", CiteAbbr `reference`, resolver accepts all
input forms.

### Phase 2 — Windowing & validation
**Goal:** compute the embed string and catch data defects before load.
**New files:** `extractors/scripture_validation.py`, `models/` validation piece,
`tests/test_scripture_windowing.py`, `tests/test_scripture_validation.py`.
**Tasks:**
- Windowing (in the extractor module): **standard** = reference prefix + sequence-adjacent,
  chapter-clamped neighbor window at `SCRIPTURE_WINDOW_RADIUS`; **jst** = reference prefix +
  own text, no neighbors (§6).
- Validation (§10): text/HTML, `verse/chapter >= 1`, variant set, S-only gap warnings (JST
  gaps expected), `NumChapters` sanity, window-boundary checks.
**Checkpoint:** windowing unit tests cover chapter edges, radius 1 vs 2, S-vs-JST divergence;
validation flags injected defects and stays quiet on normal JST sparsity.

### Phase 3 — Loader, schema & orchestrator
**Goal:** embed and upsert verses into Weaviate, idempotently and resumably.
**New files:** `loaders/scripture_loader.py` (`ScriptureLoader(BaseLoader)`),
`scripts/run_scripture_pipeline.py`; extend `loaders/shared_transforms.py` with
`prepare_verse_records()`. Tests: `tests/test_scripture_loader.py`.
**Tasks:**
- `ScriptureLoader`: ensure `ScriptureVerses` schema (idempotent), batch-embed `context_window`
  via injected `embed_fn`, upsert on `generate_uuid5("verse_{id}")`.
- Orchestrator: streaming, resume (`verse_exists`), `--force`, batching — mirrors
  `run_pipeline.py`. **Document that config changes (radius/model) require `--force`** (resume
  keys on existence, not content).
**Checkpoint:** load a single book (e.g. Jude / a small chapter set) → objects present with
vectors + correct props; re-run is a no-op (idempotent); `--force` re-embeds.

### Phase 4 — MCP tool surface
**Goal:** expose retrieval to the LLM.
**Edits:** `server.py` (+ `tests/test_server.py`).
**Tasks:**
- `get_verse` (new): resolver-backed book input, ordered range, single-chapter shorthand,
  `variant` standard/jst/both, pure filter query (no Ollama).
- `search` (extend): `scripture_verses` collection; filters `book/volume/chapter/variant`;
  **default `variant=standard`**; filter inputs normalized through `book_resolver`.
- `corpus_stats` (extend): `scripture_verses`, groupable by `volume`/`book`/`variant`.
**Checkpoint:** tool tests against the Phase-3 subset — `get_verse("Alma",32)` returns the
ordered chapter, `("Jude",3)` shorthand works, `variant="both"` unions S+JST, `search` returns
canonical-only by default, `corpus_stats` counts match.

### Phase 5 — Full load & post-load verification
**Goal:** the whole corpus loaded and proven.
**New files:** `scripts/verify_weaviate_scripture.py` (SCR-01…06).
**Tasks:** run `run_scripture_pipeline.py` over all S+J+F; implement and run SCR-01…06 (§10).
**Checkpoint:** SCR-01 count ≈ 41,996 canonical + JST; all 5 volumes; spot-check verses
retrievable; `variant` distribution matches DB; no empty `text`/`context_window`; semantic
sanity ("faith"/"charity"). Update CLAUDE.md Project Structure Index with the new files.

**Dependency chain:** 1 → 2 → 3 → 4 → 5. Phases 1–2 are parallel-safe against each other only
loosely (2 imports Phase-1 types); 4 can be built against the Phase-3 subset before the Phase-5
full load. The `book_resolver` (Phase 1) is the one shared dependency reused by both the
pipeline and the tools.
