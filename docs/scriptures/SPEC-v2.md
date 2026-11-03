# Scriptures — v2 Specification (Church API first)

**Status:** Draft, 2026-11-02. Not yet implemented. Replaces the plan in `SPEC.md` (v1, core.db-only),
which stays as reference. Decisions carried over from v1 are listed in §13.
**Scope:** Add the standard works as a corpus. The text, chapter headings, summaries and footnotes
come from the Church API and are stored as the site shows them. JST text comes from the SCI core DB.
The work is a milestone, broken into phases in §11.

---

## 1. Goal

Right now the corpus holds conference talks and *references* to scripture. The scripture text is not
searchable anywhere, and none of the study material around it is stored (summaries, headings,
footnotes, cross-references).

v2 does two things:

1. **Archive the scriptures as the Church publishes them.** Every chapter page is kept exactly as the
   API returns it, so a later study platform can render it the way the website does without fetching
   it again.
2. **Make the scriptures searchable through MCP.** That means semantic and keyword search over verses,
   exact-reference retrieval, footnotes and cross-references alongside each verse, and links from
   verses to the conference talks that cite them.

**One line:** *the scriptures become a stored, searchable study library, captured once and rebuilt
offline.*

---

## 2. Sources and what each one owns

| Source | Owns | Why |
|---|---|---|
| **Church API** (`/study/api/v3/language-pages/type/content?lang=eng&uri=/scriptures/...`) | Verse text, chapter title/number, `study-summary`, `study-intro` (D&C section headings), footnotes and their references, the table of contents, media links, front matter, Official Declarations, the JST appendix, study helps (TG/BD/GS) | It is the authoritative edition, footnotes are already parsed into structured fields, and coverage is the same across all five volumes |
| **SCI core DB** (`scripture` table, `Flag ∈ {J, F}`) | The full JST (Inspired Version) text, 31,261 verses, **in JST chapter/verse numbering** (§5) | The website publishes only JST *excerpts* (the appendix); core.db has the whole text |
| **SCI core DB** (`citation`, `citation_verse`) | Talk → verse citation edges, keyed `(BookID, Chapter, Verses/MinVerse/MaxVerse)`; `Flag='J'` (753 rows) marks JST citations | Already in use by `find_by_scripture` |

**Which core.db file:** the build output `db/core.55.db` is currently an empty 0-byte file, so the JST
audit (§5) was run against the raw SCI release `db/sci/core.55.db`, opened read-only. The scripture
build reads the same JST rows from whichever file `db/` points to. Text is stored as UTF-8 BLOBs, and
J/F text contains no HTML.

core.db is read **only** through the existing `db/` helpers. Per the project rule, it is never opened
ad hoc.

### What the API returns (sampled 2026-11-02)

The `content` endpoint returns `{meta, content: {head, body, associated, footnotes}, pids,
tableOfContentsUri, uri, ...}`:

- **`content.body`** is the page HTML. Verses are `<p class="verse" data-aid="…" id="pN">` with a
  `<span class="verse-number">`. The header holds `title-number`, `study-summary` (chapter summary),
  and for D&C `study-intro` (the section heading). Footnote markers are
  `<a class="study-note-ref" href="#note2_a">` wrapped around the word they annotate.
- **`content.footnotes`** is a dict keyed `note{verse}_{letter}`. Each entry has `marker` ("2a"),
  `pid` (the verse's `data-aid`), `context` (the anchored word), `text` (HTML), and `referenceUris`
  (`[{type, href, text}]`, already parsed).
- **Footnote categories seen** (`data-note-category`): `cross-ref`, `tg`, `trn` (Hebrew/Greek
  translation notes, Gen 1), `ie` (D&C 45). The complete set is an audit item (§12).
- **`meta`** has `title`, `canonicalUrl`, and `audio[]`. **`associated`** has the videos tied to a
  paragraph.
- **The table of contents:** fetching a volume URI (e.g. `/scriptures/bofm`) returns a body of links
  to every page in it: 259 links for the BoM, from `title-page` to `moro/10`, plus `pronunciation`
  and `reference`.

| Sample | Verses | Footnotes | Notable classes |
|---|---|---|---|
| `bofm/alma/32` | 43 | 65 | `title-number`, `study-summary`, `verse` |
| `dc-testament/dc/45` | 75 | 171 | adds `study-intro` |
| `ot/gen/1` | 31 | 56 | `trn` footnotes |
| `dc-testament/od/1` | 0 | 0 | `office`, `salutation`, `signature` (non-verse document) |
| `pgp/abr/fac-1` | 0 | 0 | facsimile (image + explanation) |
| `jst/jst-gen/1-8` | 0 | 0 | `study-intro` only (a pointer to Moses) |
| `tg/faith` | 0 | 0 | `entry` (study help) |

Page kinds therefore vary. The parser dispatches on content, and raw storage does not care what kind
a page is.

---

## 3. Scope

### In
- Every page reachable from the five volume tables of contents (OT, NT, BoM, D&C, PoGP): chapters,
  sections, front matter, Official Declarations, facsimiles.
- Chapter summaries, D&C section intros, all footnotes and their parsed references.
- JST text from core.db as its own book, linked to the KJV through the Church's `jst` footnotes (§5).
- Weaviate collections for verses and chapters (§6), plus MCP tools (§9).
- Talk ↔ verse links through core.db citations.

### Out (later milestone, but nothing is lost)
- **Study helps:** TG, BD, the Guide to the Scriptures, Triple Combination
  Index, maps, photos. Footnote refs **point** to them and those refs are stored now (§4). The pages
  themselves are fetched in phase 6 or later.
- Multi-hop graph traversal (pgGraph etc., see `SPEC.md` §11). One-hop cross-refs come from SQLite.
- Media (audio/video) files. Only their URLs are kept, inside the raw JSON.
- Languages other than English. `lang` is a column from day one so this stays open.
- A study-platform UI.

---

## 4. `scripture.db`: the source of truth

This is a new file, separate from core/content. It changes rarely and on its own schedule (edition
updates, not conferences), and a study platform should be able to use it without the talk data. The
path is `db/scripture.db`.

**Size:** roughly 1,600 chapters, plus front matter and later the study helps. Alma 32 alone is
~42KB of body HTML. Tens to low hundreds of MB, so this is **not committed to git** (unlike the
conference JSON). Where it is backed up and shipped is an open question (§12).

### 4.1 Raw layer (written only by fetch, append-only)

```sql
raw_page (
  uri           TEXT NOT NULL,        -- "/scriptures/bofm/alma/32"
  lang          TEXT NOT NULL,        -- "eng"
  fetched_at    TEXT NOT NULL,        -- ISO-8601 UTC
  content_hash  TEXT NOT NULL,        -- sha256 of the normalized response JSON
  status        INTEGER NOT NULL,     -- HTTP status
  json          TEXT NOT NULL,        -- the response, unmodified
  PRIMARY KEY (uri, lang, content_hash)
)
-- view raw_latest: newest row per (uri, lang)
```

- A new row is added **only when the hash changes**. Edition changes therefore keep a history, and a
  re-fetch that finds no change writes nothing.
- This layer is what the study platform renders. Nothing downstream edits it.

### 4.2 Normalized layer (written only by build, safe to drop and rebuild)

```sql
volume    (volume_id, uri, title, abbr, sort)                  -- ot, nt, bofm, dc-testament, pgp
book      (book_id, volume_id, uri, name, abbr, cite_abbr, sort, num_chapters, core_book_id)
page      (page_id, uri, book_id NULL, kind, title, sort)      -- kind: chapter|section|front_matter|declaration|facsimile|...
chapter   (chapter_id, page_id, book_id, number, title, summary, intro, summary_html, intro_html)
verse     (verse_id, chapter_id, book_id, chapter, verse, aid, pid_html_id,   -- aid = data-aid, html id = "p32"
           text, text_html)
jst_verse (jst_verse_id, core_id, book_id, chapter, verse,      -- JST numbering, all J+F rows
           source_flag, text)                                    -- source_flag F = in the Church edition
footnote  (footnote_id, verse_id, note_key, marker, letter, context, text, text_html)  -- note_key "note2_a"
footnote_ref (footnote_id, seq, category, ref_type, href, label,
              target_uri, target_book_id NULL, target_chapter NULL,
              target_verse_start NULL, target_verse_end NULL,
              target_help NULL,                                  -- e.g. "tg/poor" for study-help refs
              target_jst_verse_id NULL)                          -- category 'jst' refs (§5)
build_meta (key, value)                                          -- build_id (§9), source hashes, core.db version, build time
```

- **IDs:** `verse.aid` (the Church `data-aid`) is stored as a stable external ID. Internal IDs are
  build-local integers. Anything that leaves the db (Weaviate UUIDs, MCP output) uses a natural key:
  `verse_{book_uri}_{chapter}_{verse}`, never the build-local integer.
- **`text` vs `text_html`:** `text` is clean plain text (verse numbers and footnote markers removed,
  KJV italics flattened). `text_html` keeps the markup for rendering.
- **`footnote_ref`** is the verse→verse and verse→study-help edge list. Short refs like `"7:22"`
  that inherit the book from the previous ref are resolved using `href`, which is always
  fully qualified. Never parse the label.
- **`book.core_book_id`** maps to core.db `book.ID`, for the JST import and the citation join.

---

## 5. JST: its own book, linked only where the Church links it

### 5.1 What the data is (audited 2026-11-02, `db/sci/core.55.db` + Church API)

core.db holds the **whole JST** for the OT and NT (every book except the Song of Solomon), 31,261
verses, **in JST chapter/verse numbering**. The same reference is often a different verse:
J Genesis 8:19 is KJV Genesis 6:14. F Genesis 1:1 is Moses 1:1. J Matthew 3:1 is KJV Matthew 2:1.
core.db has no JST↔KJV crosswalk.

| Flag | Rows | Meaning (`db/sql-queries.md`: "F = JST footnoted, J = JST only", verified) |
|---|---|---|
| `F` | 1,359 | **The JST the Church's Bible shows**, as `jst`-category footnotes or JST appendix passages. KJV Exodus 7 has `jst` footnotes on vv. 1, 3, 13, and F Exodus 7 is exactly 7:1, 7:3, 7:13. All 97 appendix chapters that could be mapped to a core.db book are F chapters. |
| `J` | 29,902 | **The rest of the Inspired Version.** ~85% is word-identical to the KJV, and many "changes" are spelling or punctuation ("snuffdishes", "O/Oh"). Not shown in the Church edition. |

Talk citations with `Flag='J'` (753 rows) use JST numbering.

### 5.2 Approach

**We do not compute any JST↔KJV pairing.** The Church has already paired the part that matters.

1. **Import all J and F rows into `jst_verse`**, in JST numbering, unchanged. It is a separate book
   ("JST Genesis"), readable by its own references. This is the complete copy for the study platform
   and the target for JST talk citations.
2. **Link to the KJV only through the Church's own links.** `jst`-category footnotes on KJV verses
   (e.g. KJV Ex 7:3 → "JST Ex. 7:3 …") and JST appendix passages are parsed like any other footnote
   reference into `footnote_ref` (`category = 'jst'`, target = a JST reference). The target is looked
   up in `jst_verse` **by reference**. Footnotes often abbreviate the JST text with "…", and core.db
   supplies the full verse.
3. **KJV verses with a `jst` footnote** get `has_jst = true` and `jst_refs`.
4. **Only `F` verses are searchable** (`variant="jst"`, ~1.4k objects). `J` stays readable by
   reference but is not embedded: it mostly duplicates the KJV, and separating real changes from
   spelling variants is exactly the fuzzy work this approach avoids.
5. **Moses and Joseph Smith—Matthew** (the PoGP parallels to JST Gen 1–8 and Matt 24) are linked
   through the Church's ordinary cross-reference footnotes. No special table.
6. Rows with `Flag ∈ {S, H, E}` from core.db are **not read**. The API is the canonical source.

**Accepted cost:** meaningful J-only changes are not searchable or linked from the KJV verse. They
remain readable in JST numbering. Computed alignment of the full Inspired Version is in the backlog
(§14) if it is ever needed.

**Must be confirmed in phase 0 / 2** (one chapter and the appendix list were checked, not the whole
corpus):
- Every F row is reached by a `jst` footnote or an appendix passage. Unreached F rows are reported.
  They stay searchable, just without a KJV link.
- Appendix pages state their KJV ranges in a parseable form.
If coverage is badly incomplete, computed alignment comes back **only for the gaps**.

JST verses are never embedded with a neighbour window (§7).

---

## 6. Weaviate collections

`config/pipeline_config.py`:

```python
WEAVIATE_SCRIPTURE_COLLECTION_NAMES = {
    "verses":   "ScriptureVerses",
    "chapters": "ScriptureChapters",
}
```

### `ScriptureVerses` (one object per canonical verse, plus one per `F` JST verse)

UUIDs:
- KJV/canonical: `generate_uuid5("verse_{book_uri}_{chapter}_{verse}")`
- JST: `generate_uuid5("jst_{book_uri}_{jst_chapter}_{jst_verse}")`

Properties: `variant` (`standard` | `jst`), `book`, `book_uri`, `cite_abbr`, `volume`, `chapter`
INT, `verse` INT (in that variant's numbering), `reference` ("1 Ne. 3:7" / "JST Gen. 8:19"),
`text`, `has_jst` BOOL and `jst_refs` TEXT[] (standard only), `kjv_refs` TEXT[] (jst only, from the
Church's `jst` footnotes; may be empty), `aid`, `footnote_count` INT, `context_window`, `doc_id_str`.

One vector per object. Using one collection with a `variant` filter (rather than named vectors)
follows from §5: JST objects have their own numbering and are not 1:1 with KJV verses. Expected size
is ~42k standard + ~1.4k JST objects.

Search defaults to `variant = standard`. `variant="jst"` searches only the `F` JST verses, and
`"both"` searches both.

**Footnotes are not separate Weaviate objects.** They are returned from `scripture.db` by
`get_verse`. They are short and tied to one verse, and embedding them adds noise. Revisit only if
footnote text search turns out to be wanted.

### `ScriptureChapters` (one object per chapter/section/document page)

UUID = `generate_uuid5("chapter_{page_uri}")`. Properties: `book`, `volume`, `chapter`, `reference`
("Alma 32", "D&C 45"), `title`, `summary`, `intro`, `kind`, `verse_count`. A single vector over
`title + intro + summary`.

This is what answers "which chapter is about X" without verses swamping the results. It also holds
Official Declarations and front matter (as `kind`), which have no verses.

**Server startup:** `_validate_collections` requires every collection to exist and be non-empty. The
scripture collections are added to that check **only once loaded**, either behind a config flag or
as a separate optional list. Otherwise the server cannot start mid-milestone.

---

## 7. Embedding

Unchanged from v1 §6, with the stack updated:

- Embedder: `config/embedding.py` (llama-server, `nomic-embed-text`), **`task="document"`** for
  loading and `task="query"` for queries.
- Canonical `text` vector: `"{book} {chapter}:{verse}\n{prev}\n{this}\n{next}"`. The window is
  chapter-bounded, neighbours are taken from the verse-ordered sequence, and the radius is
  `SCRIPTURE_WINDOW_RADIUS` (default 1).
- JST objects: `"JST {book} {chapter}:{verse}\n{text}"`, no window. Only `F` verses are
  embedded (§5.2).
- `ScriptureChapters` vector: `"{reference}: {title}\n{intro}\n{summary}"`.
- Changing any embed string or the radius requires `--force` (resume checks existence, not
  content).

Volume: ~42k standard verse vectors, ~1.4k JST vectors, and ~1.6k chapter vectors.

---

## 8. Pipeline

```
Church API ──fetch_scriptures──▶ scripture.db raw_page
                                        │
core.db (J/F, book) ────────────────────┤
                                        ▼
                         build_scriptures ──▶ scripture.db normalized tables
                                                   │
                         run_scripture_pipeline ──▶ Weaviate (ScriptureVerses, ScriptureChapters)
                                                   │
                         server.py ◀── reads Weaviate + scripture.db (footnotes, refs)
```

| Step | File (new unless noted) | Network | Does |
|---|---|---|---|
| Fetch | `scripts/fetch_scriptures.py`, `utils/church_api.py` (reuse) | yes | Walk the five volume TOCs, fetch each page with the `content` endpoint, insert into `raw_page` if the hash changed. Uses the existing throttle (≤2 req/s), retries, and User-Agent. Resumable: `--only-missing` skips URIs already stored. `--refresh` re-fetches and records only changes. |
| Parse | `extractors/scripture_page.py` | no | One `raw_page` → page/chapter/verse/footnote/footnote_ref rows. Dispatches on page kind. Pure functions over the JSON, with golden-file tests. |
| JST import | `extractors/scripture_jst.py` | no | Read core.db `J`/`F` through `db/` into `jst_verse`. Resolve `category='jst'` footnote refs to `jst_verse` by reference (§5). |
| Build | `scripts/build_scriptures.py` | no | Drop and rebuild the normalized layer from `raw_latest` + core.db in one transaction. Write `build_meta`. Run validation (§10). |
| Load | `loaders/scripture_loader.py` (`ScriptureLoader(BaseLoader)`), `loaders/shared_transforms.py` (`prepare_verse_records`, `prepare_chapter_records`) | embedder | Ensure the schema exists (idempotent), batch-embed, upsert by deterministic UUID. After a complete load, write `build_id` to `ScriptureMeta` (§9). |
| Orchestrate | `scripts/run_scripture_pipeline.py` | embedder | Streams verses by book. Resume, `--force`, `--book` (for the one-book slice). |
| Verify | `scripts/verify_weaviate_scripture.py` | no | SCR checks (§10). |
| Publish (optional) | `scripts/publish_scriptures.py` | yes | Upload `scripture.db` and its manifest (`build_id`, sha256) to object storage for `SCRIPTURE_DB_URL` deployments (§9). The manifest is uploaded last, so a server never sees a manifest for a file that isn't there yet. |

`docs/update/HOW_UPDATES_WORK.md` gets a scripture section. Conference updates never touch it, and
a scripture refresh is a manual, rare run.

---

## 9. MCP tool surface

### `get_verse` (new)
```
get_verse(book, chapter, verse_start=None, verse_end=None,
          include_footnotes=True, include_jst=False, include_citing_talks=False)
  -> {reference, chapter_summary, verses: [{reference, verse, text,
       jst?: [{reference, text}],
       footnotes?: [{marker, context, text, refs: [{category, label, target}]}]}],
      citing_talks?: [...]}
```
- Reads come from **`scripture.db`**, not Weaviate. No embedding, so it works when llama-server is
  down. Ordered, deterministic, complete.
- Book input goes through the resolver (§13). The single-chapter shorthand from v1 is kept
  (`("Jude", 3)`).
- `include_jst` attaches the JST verse(s) the Church's `jst` footnotes point to. A JST reference as input
  (`book="JST Genesis"`, or a `numbering="jst"` argument) reads `jst_verse` directly in JST
  numbering.
- `include_citing_talks` joins core.db `citation`/`citation_verse` on (BookID, Chapter, verse
  within MinVerse..MaxVerse) and returns talk IDs/titles that work with `get_talk`. `Flag='J'`
  citations are matched through `jst_verse`.

### `get_chapter_overview` (new, cheap)
Returns the chapter title, intro, summary, verse count, and the most-referenced cross-ref targets.
This is the "orient me" call before pulling verses.

### `search` (extended)
- New collections: `scripture_verses`, `scripture_chapters`.
- Filters: `book`, `volume`, `chapter`, `variant` (`standard` default | `jst` | `both`).
- Hybrid `alpha` as today. Keyword search matters most here, because people remember KJV phrasing.

### `find_cross_references` (new)
`find_cross_references(book, chapter, verse)` returns outgoing `footnote_ref` scripture targets
(grouped by footnote) and **incoming** refs (other verses whose footnotes point here). One hop, from
SQLite. This is the verse↔verse graph without a graph engine.

### `corpus_stats` (extended)
Adds both scripture collections, grouped by `volume`/`book`/`has_jst`.

### `find_by_scripture` (unchanged)
It still returns talks citing a reference. `get_verse(include_citing_talks=True)` covers the same
link in the other direction.

**Server dependency:** `server.py` gains a read-only `scripture.db` connection, opened through a new
`db/` helper with the same 5s timeout and the same "a slow query returns `[]`" behaviour. The same
file is the data source for the future study platform, so it has to be deployed anyway.

1. **Never baked into the image; delivered one of two ways.** `.dockerignore` keeps excluding
   `*.db`, so the image stays code-only and no Church content is pushed to the registry. Either
   way the server ends up querying a **local** SQLite file through the same `db/` helper. Only how
   the file arrives differs:
   - **Mount (`SCRIPTURE_DB_PATH`):** `scripture.db` is mounted read-only into the `mcp-server`
     container (e.g. `/data/scripture.db`). Updating means replacing the file and restarting the
     container.
   - **Snapshot URL (`SCRIPTURE_DB_URL`, takes precedence over the path):** for when a mount isn't
     possible. The file is published to private object storage (S3/R2/B2 or similar), next to a
     small manifest `{build_id, sha256, size, built_at}`. At startup the server fetches the
     manifest. If its cached copy (`SCRIPTURE_DB_CACHE_DIR`, default `/data/cache`) has a
     different `build_id`, it downloads to a temp file, checks the sha256, and renames it into place
     in one step. It then opens it read-only like a mounted file. Auth is a signed URL or an access
     key in the environment, never in the image. If the download or checksum fails, it keeps
     using the previous cached copy if there is one. Otherwise scripture is unavailable (rule 3).
     A new build reaches a running server on restart. Polling for updates is out of scope.
   - A study platform can mount the same file or pull the same snapshot.
   - **Not chosen:** querying a hosted database live over HTTP (a network round trip per call and
     a new failure mode), or calling the platform's API (it would tie MCP uptime to the platform).
     Hosted SQLite with a local replica (e.g. Turso's embedded replicas) is equivalent to the
     snapshot option and could replace it later without changing the query code.
2. **Build ID check (file ↔ Weaviate).** Search hits come from Weaviate, and the details (footnotes,
   cross-refs, JST) come from `scripture.db`. Both must come from the same build.
   - `build_scriptures` writes `build_meta.build_id` = a hash of the normalized tables' content.
     The build is deterministic, so rebuilding identical data keeps the same ID.
   - After a **complete** load, the loader writes that ID to a one-object, vectorless
     `ScriptureMeta` collection. If the stored ID differs from the file's, the loader treats the
     run as `--force` (resume-by-existence would otherwise keep objects from the old build).
   - At startup the server reads both. On a mismatch it logs a warning naming both IDs and the fix
     ("re-run `run_scripture_pipeline.py`") and reports it in `/health`. It still starts.
3. **Scripture is optional at startup.** If neither `SCRIPTURE_DB_URL` nor `SCRIPTURE_DB_PATH`
   yields a usable file, or the
   scripture collections aren't loaded, the scripture tools return a clear "scripture corpus not
   available" message, and the talk tools are unaffected (see the startup note in §6).

---

## 10. Validation and verification

**Build-time (`build_scriptures`):**
- Every TOC link has a `raw_latest` row. Missing ones are listed and fail the build.
- Verse count per chapter equals the number of `<p class="verse">` in the body. Canonical verses
  run 1..N with no gaps.
- Every `footnote.verse_id` resolves (the footnote's `pid` = the verse's `aid`). Every
  `study-note-ref` in the body has a footnote entry, and the reverse.
- Every scripture-type `footnote_ref` resolves to a `book`. Unresolved ones are reported, not fatal.
- `text` contains no HTML, no verse numbers, and no footnote markers.
- JST: `jst_verse` count = core.db J+F (31,261 on core.55). Every `jst` footnote ref resolves to a
  `jst_verse`. Report F rows that no footnote or appendix passage reaches (expected ≈0). KJV Ex 7:3
  links to JST Ex 7:3.
- Chapter counts per book = `book.num_chapters` (TOC-derived).

**Post-load (`verify_weaviate_scripture.py`):**
- SCR-01 `ScriptureVerses` count = canonical verses + `F` rows.
- SCR-02 all five volumes present. `ScriptureChapters` count = chapter pages.
- SCR-03 spot checks: John 3:16, Alma 32:21, 1 Ne. 3:7, D&C 45:32. KJV Ex 7:3 has `has_jst` and
  `jst_refs` containing "JST Ex. 7:3".
- SCR-04 `variant` distribution and `has_jst` count match `scripture.db`.
- SCR-05 no empty `context_window`, and every object has a vector.
- SCR-06 semantic sanity: "faith as a seed" → Alma 32. "Charity suffereth long" (BM25) → 1 Cor 13 /
  Moro 7. Chapter search "plan of salvation" → plausible chapters.

---

## 11. Phase plan

The order is: **pure data work first, then a thin end-to-end slice, then widen.** Phases 1–3 need
no Weaviate and no embedder. Phase 1 is the only one that uses the network.

### Phase 0 — Audit and spec lock
**Goal:** answer §12 with real numbers before writing code.
- Fetch a handful of pages per volume and kind (already partly done, see §2). List every
  `data-note-category` and `p` class across a broader sample.
- ~~JST overlap and flag meaning~~ — done 2026-11-02 (§5.1).
- ~~Citation key~~ — done: (BookID, Chapter, verse range), `Flag='J'` = JST numbering (§2).
- Check `jst` footnote / appendix coverage of F rows on a broader sample, and how appendix pages
  state KJV ranges (§12 Q1).
**Checkpoint:** §12 questions answered in this file. Spec marked locked.

### Phase 1 — Fetch → raw store
**New:** `db/scripture_schema.sql` (raw layer), `scripts/fetch_scriptures.py`, tests with a fake
session.
**Checkpoint:** a full fetch stores every TOC page. A second run inserts 0 rows. Interrupting and
resuming works. Volume and duration are recorded (expect ~15–20 min at 2 req/s).

### Phase 2 — Parse and normalize
**New:** `extractors/scripture_page.py`, `config/book_resolver.py`, normalized schema,
`scripts/build_scriptures.py`, golden fixtures (Alma 32, D&C 45, Gen 1, OD 1, Abr fac-1, a
single-chapter book).
**Checkpoint:** all §10 build checks pass on the full raw store. The build is deterministic (two
builds produce the same content hashes).

### Phase 3 — JST import and Church-link resolution
**New:** `extractors/scripture_jst.py`, JST appendix fetch + parse (moved forward from phase 6),
tests (KJV Ex 7:3 → JST Ex 7:3, an appendix passage, JST numbering lookup "JST Gen 8:19").
**Checkpoint:** `jst_verse` = core.db J+F. All `jst` refs resolve. F coverage reported.

### Phase 4 — Weaviate slice: verses and chapters
**New:** `ScriptureLoader`, transforms, `run_scripture_pipeline.py`, `get_verse`,
`get_chapter_overview`, the `search` extension, the `scripture.db` helper (`SCRIPTURE_DB_PATH`),
`ScriptureMeta` and the build ID check, and optional scripture at startup (§9).
- **Load one small book first** (Enos or Jude). Exercise every tool against it, including
  `variant="jst"` search and footnotes in `get_verse`.
- Tests: mismatched build IDs give a warning and `/health` flag. A missing file or unloaded
  collections leave the talk tools working.
- Then the full load.
**Checkpoint:** the slice tools pass. A full load passes SCR-01…06.

### Phase 5 — Cross-references and talk links
**New:** `find_cross_references`, `include_citing_talks`, `corpus_stats` extension.
`docker-compose.yml` gets the read-only `scripture.db` mount and `SCRIPTURE_DB_PATH`, or the
snapshot settings (`SCRIPTURE_DB_URL`, a cache volume). `publish_scriptures.py` if URL delivery is
used. `docs/DEPLOY.md`
documents both delivery modes and the build ID warning. Snapshot download (`SCRIPTURE_DB_URL`) is
built here, with tests: same `build_id` means no download, a bad checksum keeps the previous copy,
an unreachable URL with no cache means scripture is unavailable and talk tools still work.
**Checkpoint:** "Alma 32:21 with footnotes, cross-refs both ways, and citing talks" works in one or
two calls on the deployed server.

### Phase 6 — Study helps (likely its own milestone)
Fetch the TG/BD/GS pages (the JST appendix moved to phase 3) referenced by `footnote_ref.target_help`, using the same raw →
normalize pattern. Decide then whether they become a Weaviate collection.

**Dependencies:** 0 → 1 → 2 → 3 → 4 → 5. Phase 3 can run in parallel with late phase 2 (it only
needs `book.core_book_id`). Phase 4's tools can be built against the one-book slice before the full
load.

---

## 12. Open questions (Phase 0 answers these)

1. **JST link coverage:** does every `F` row get reached by a `jst` footnote or an appendix passage,
   and do appendix pages state their KJV ranges in a parseable form? (§5.2.) If coverage is badly
   incomplete, computed alignment comes back for the gaps only.
2. **Footnote categories:** the full set beyond `cross-ref`, `tg`, `trn`, `ie` (likely `bd`, `gs`,
   `jst`, `alt`, `or`, `hebrew`/`greek`, …). Each needs a `category` value and a ref parser.
3. **Page kinds:** the full list across the five TOCs (chapters, front matter, declarations,
   facsimiles, BoM pronunciation guide, …). Decide which become `ScriptureChapters` objects and
   which are raw-only.
4. ~~**Citation join key**~~ — resolved: `(BookID, Chapter, Verses/MinVerse/MaxVerse)` plus
   `citation_verse`. `Flag='J'` citations use JST numbering. The 10 front-matter `S` rows have
   `Verse = 0` in core.55 (v1 recorded NULL), which no longer matters because the API supplies canonical text.
5. **Backup and delivery of `scripture.db`:** where is it backed up (not git)? For mounts, is it
   built on the host or copied after a local build? For URL deployments, which object store, and how
   are credentials issued? (Decided: never baked into the image. Delivered by a read-only mount or a
   checksummed snapshot URL, §9. The snapshot bucket can double as the backup.)
6. **Copyright:** the KJV text is public domain, but the footnotes, summaries, headings and study
   helps are © Intellectual Reserve. Personal MCP use is fine. A public study platform that
   reproduces them needs a licensing answer before launch. Fetching and storing does not.
7. **Edition drift:** when a refresh finds changed pages, is rebuilding automatic, or does it need a
   review of the diff first?

---

## 13. Carried over from v1 (`SPEC.md`), still decided

- **Book resolver** (`config/book_resolver.py`): accepts full names, abbreviations, cite
  abbreviations, word/digit ordinals ("First Nephi" / "1 Nephi" / "1 Ne."), and "D&C". Its
  canonical output is the long digit form. It is now built from the **API TOC** plus a
  `core_book_id` crosswalk, instead of from core.db `book`. Old aliases are kept so user input
  that worked before still works.
- **`reference`** uses the cite-abbreviation form ("1 Ne. 3:7", "D&C 45:32"). Single-chapter books
  stay uniform ("Jude 1:3").
- **The embed string differs from the stored text** (`context_window` is embedded, `text` is
  returned). Canonical verses are windowed. JST is never windowed.
- **`SCRIPTURE_WINDOW_RADIUS = 1`**, set in config.
- **There is one `ScriptureLoader`** on `BaseLoader` for the scripture collections. The talk loader is
  untouched.
- **`variant` defaults to `standard`** in search. JST must be asked for explicitly.
- **There is no `citation_count` / `citing_talk_ids` on verses.** The talk links are live joins.

### Changed from v1
- **The source** of canonical text and headings moves from core.db to the Church API. core.db
  supplies JST and citations only.
- **JST** is its own book in **its own numbering**, linked to the KJV only through the Church's `jst`
  footnotes and appendix (§5). v1 matched JST to KJV by reference, which pairs the wrong verses
  (J Gen 8:19 = KJV Gen 6:14). Only `F` (~1.4k) is embedded, not all ~31k.
- **`record_type` is dropped.** Chapters have their own collection.
- **New:** `scripture.db`, the raw archive, `get_chapter_overview`, `find_cross_references`,
  footnotes in `get_verse`.

---

## 14. Deferred
- Study helps as a corpus (phase 6+).
- Multi-hop traversal, pgGraph / pgContext (see `SPEC.md` §11). Re-evaluate once
  `find_cross_references` usage shows a need for multi-hop.
- An embedding model revisit and late chunking (`backlog.md`).
- Footnote text as its own vector collection.
- Computed JST↔KJV alignment of the full Inspired Version (`J` rows), and embedding meaningful
  J-only changes. A 2026-11-02 trial alignment found ~26.45k identical, ~4.8k changed (many spelling
  only), and 4 JST-only verses.
- Other languages (`lang` column already present).
- A study-platform renderer over `raw_page`.
