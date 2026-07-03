# Requirements: BYU Scripture Citation Index RAG System — v5.0 Scriptures

**Defined:** 2026-07-03
**Core Value:** All LDS content searchable by meaning — find how scriptures are cited, applied, and discussed across decades of conference talks and discourse.
**Spec:** `docs/scriptures/SPEC.md`

## v5.0 Requirements

Requirements for the Scriptures milestone. Each maps to exactly one roadmap phase. v1 = **verse text only** (headings, cross-refs, and study apparatus deferred to v2).

### Extraction & Data Model

- [ ] **EXT-01**: Canonical (`S`) and JST (`J`,`F`) verses are read from `core.52.db` (versioned path resolved like the talk pipeline) into `ScriptureVerse` objects, joined to `book` (+ parent for `volume`), grouped by (book, chapter, variant)
- [ ] **EXT-02**: Non-verse `S` rows with NULL `Verse` (10 front-matter rows) and decorative `E` rows are excluded — effective canonical count ≈ 41,996
- [ ] **EXT-03**: Verse `Text` is UTF-8-decoded and cleaned of light inline HTML/entities via `html_parsing_utils`; `text` is stored non-empty with no residual tags
- [ ] **EXT-04**: Book names are normalized to canonical digit form — Nephi word-ordinals → digits ("First Nephi" → "1 Nephi"), D&C `Sections` container → "Doctrine and Covenants", and em-dash mojibake in `FullName`/`CiteAbbr` repaired
- [ ] **EXT-05**: Each verse carries a derived, stored `reference` (CiteAbbr-based: "1 Ne. 3:7", "D&C 45:32", "Jude 1:3"), `variant` (`standard`|`jst`), and raw `source_flag` (S/J/F) provenance

### Book Resolution

- [ ] **RES-01**: `config/book_resolver.py` resolves any common input form (`FullName`, `Abbr`, `CiteAbbr`, case-insensitive, word↔digit ordinals, "D&C"/"Doctrine and Covenants") to the canonical digit-form `book`, and is shared by both `get_verse` and `search`

### Embedding & Windowing

- [ ] **EMB-01**: `standard` verses embed a reference-prefixed, chapter-clamped, sequence-adjacent neighbor window at `SCRIPTURE_WINDOW_RADIUS` (default 1, config-gated) — no cross-chapter bleed, never windowed against a JST twin
- [ ] **EMB-02**: `jst` verses embed reference-prefixed but un-windowed (sparse corpus); every verse has a `context_window`, and the raw `text` is stored separately from the embedded string

### Validation

- [ ] **VAL-01**: Per-verse / per-chapter validation enforces non-empty tag-free `text`, `verse ≥ 1`, `chapter ≥ 1`, `variant ∈ {standard, jst}`, canonical digit-form `book`, and no surviving NULL-`Verse` row
- [ ] **VAL-02**: `standard`-only verse-gap / non-monotonic warnings fire on real defects, while expected JST sparsity (non-contiguous `J`/`F` groups) is not warned

### Loading & Orchestration

- [ ] **LOAD-01**: `ScriptureLoader(BaseLoader)` ensures the `ScriptureVerses` Weaviate collection schema idempotently (vectorizer disabled, deterministic UUID = `generate_uuid5("verse_{scripture_id}")`)
- [ ] **LOAD-02**: `ScriptureLoader` batch-embeds `context_window` via the injected `embed_fn` and upserts verse records with `SCRIPTURE_BATCH_SIZE` batching
- [ ] **LOAD-03**: `scripts/run_scripture_pipeline.py` streams, resumes (`verse_exists`), and supports `--force` (documented: config changes like radius/model require `--force`)

### MCP Tool Surface

- [ ] **TOOL-01**: `get_verse(book, chapter, verse_start, verse_end, variant)` returns ordered verse / range / whole-chapter results with single-chapter shorthand and `variant` standard/jst/both — a pure filter query with no Ollama dependency
- [ ] **TOOL-02**: `search` accepts `scripture_verses` with `book`/`volume`/`chapter`/`variant` filters, defaults to `variant=standard`, and normalizes `book`/`chapter` inputs through `book_resolver`
- [ ] **TOOL-03**: `corpus_stats` covers `scripture_verses`, groupable by `volume`, `book`, or `variant`

### Full Load & Verification

- [ ] **VRFY-01**: The full S+J+F corpus is loaded into `ScriptureVerses` via `run_scripture_pipeline.py`
- [ ] **VRFY-02**: `scripts/verify_weaviate_scripture.py` implements and passes SCR-01…06 — object count ≈ 41,996 canonical + JST, all 5 volumes present, spot-check verses retrievable, `variant` distribution matches DB, no empty `text`/`context_window`, semantic sanity ("faith"/"charity")

## v2 Requirements

Deferred to the Church-API "study apparatus" milestone. Tracked but not in this roadmap.

### Study Apparatus

- **APPR-01**: Chapter/section headings and intros for all 5 volumes (requires Church API; `core.db` has headings for D&C only)
- **APPR-02**: Chapter summaries
- **APPR-03**: Footnote cross-reference apparatus (Topical Guide, Bible Dictionary, related verses)
- **APPR-04**: verse↔verse cross-reference graph
- **APPR-05**: Official Declarations and other verse-less canonical front matter as retrievable records (reintroduces `record_type`)

## Out of Scope

Explicitly excluded from v5.0. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Study apparatus (headings, summaries, cross-refs, TG, verse↔verse graph) | Requires Church-API scrape; none of it exists in `core.db` — deferred to v2 |
| Headings for D&C only (`Flag='H'`, 138 rows) | Loading 1 of 5 volumes ships a lopsided feature and forces an extra `record_type` field; all headings land together in v2 |
| Official Declarations / verse-less front matter | Canonical but verse-less (NULL `Verse`) — v2 candidate, not a v1 verse |
| Late chunking | True contextual optimum but needs token-level hidden states Ollama's endpoint doesn't expose; parked in `backlog.md` |
| Embedding-model swap / multi-model routing | Same-paradigm gains gated on a re-embed; YAGNI for v1 — stay on nomic, keep model config-expressible |
| `group_by_chapter` in `search` | Collides with the `hybrid`+`group_by` Weaviate limitation; use `book ∧ chapter` filter instead |
| Denormalized `citation_count` / `citing_talk_ids` on verses | `get_verse` + `find_by_scripture` already serve verse↔talks navigation live with zero denormalization |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXT-01 | Phase 25 | Pending |
| EXT-02 | Phase 25 | Pending |
| EXT-03 | Phase 25 | Pending |
| EXT-04 | Phase 25 | Pending |
| EXT-05 | Phase 25 | Pending |
| RES-01 | Phase 25 | Pending |
| EMB-01 | Phase 26 | Pending |
| EMB-02 | Phase 26 | Pending |
| VAL-01 | Phase 26 | Pending |
| VAL-02 | Phase 26 | Pending |
| LOAD-01 | Phase 27 | Pending |
| LOAD-02 | Phase 27 | Pending |
| LOAD-03 | Phase 27 | Pending |
| TOOL-01 | Phase 28 | Pending |
| TOOL-02 | Phase 28 | Pending |
| TOOL-03 | Phase 28 | Pending |
| VRFY-01 | Phase 29 | Pending |
| VRFY-02 | Phase 29 | Pending |

**Coverage:**
- v5.0 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-03*
*Last updated: 2026-07-03 — traceability filled in after roadmap creation (Phases 25–29)*
