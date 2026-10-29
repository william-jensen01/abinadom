## Fetch & Build (2026-10-29) — spec: `docs/update/FETCH_BUILD_SPEC.md`

Order: fetch side first (it's what makes the JSON), then build side, then the spec's Verification list.

### A. Shared helpers
- [x] `utils/json_io.py`: `write_json(path, records, key="uri", reverse=False)` per spec, plus `merge_by_key(existing, new, key)` (new entries replace old)
- [x] `utils/church_api.py`: `API_BASE_URL`, `REQUEST_TIMEOUT`, `cached_session()` / `fresh_session()` (one place instead of four copies)

### B. Fetch-side scripts (no import-time `install_cache`, session passed in, keyed by URI, no SCI DB)
- [x] `api/fetch_talk_previews.py`: `fetch_conference_talk_uris(year, month, session)`, `fetch_talk_preview(uri, session)`; `main()` takes `--conference YYYY-MM | --all`, merges into `talk_previews.json` via `write_json`; drop `get_conferences` / `get_uri_gc_lookup`
- [x] `process_topic_talks/extract_talk_metadata.py`: `fetch_talk_metadata(uri, session)`; drop DB read, `talkID`, the `from_cache` gate and `print`; results in input order (no `as_completed`)
- [x] `scripts/process_topics.py`: `fetch_topics_index(session)` → `topics.json`; `process_topics(topics, session)`; entries sorted `uri` desc; a failed topic aborts instead of writing `[]` (decision 3)
- [x] `scripts/fetch.py`: steps 1–5, one cached + one fresh session, summary (talks fetched, missing title/role/data_aid/preview, new topics)
- [x] Normalize commit: rewrite the 4 JSON files through `write_json`, dropping `talkID`, no other data change; commit alone

### C. Build-side scripts
- [x] `create_talk_metadata_table.py`: `talk_uri_lookup(db)` → `{uri: talk_id}` from `uri_gc` + `uri_l`, plus `find_talk_by_uri(lookup, uri)`; collisions reported
- [x] `backfill_talk_metadata.py`, `backfill_talk_preview.py`, `backfill_topics.py`: look up by URI; ignore `talkID`; `backfill_topics` stops reading `talk.URI_GC`
- [x] `backfill_talk_metadata_role_extraction.py`: "skip existing" reads `talk_metadata.speaker_role_id` (decision 2)
- [x] Stop adding dead columns to `talk` (`URI_L`, `URI_GC`, `speaker_role_id`, `data_aid`): nothing outside the migration scripts reads them
- [x] All backfills: `--core-db` / `--content-db`; each exposes a `run(core_db_path, content_db_path, ...)` that `build.py` calls
- [x] `scripts/build.py --version N [--force]`: steps 0–11; match report printed and saved to `db/build_report.N.json` (gitignored like the DBs)
- [x] Update CLAUDE.md index (new files) and the spec's checklist

### D. Verification (spec list)
- [ ] Build `.53` vs `.52` backfill output, every diff explained (blocked: `db/core.52.db` provided is the raw release, need the enriched copy)
- [x] `fetch --conference 2025-10` reproduces the JSON; run twice → empty `git diff`
- [x] `fetch --conference 2026-04` + `build` → 35 April 2026 talks with full data
- [x] Match report shows only expected categories
- [x] `tests/test_pipeline_integration.py`, `tests/test_phase1.py` pass on built `.53`; unit tests for `write_json`, merge, URI lookup
- [ ] `run_pipeline.py` + `verify_weaviate_pipeline.py` (operator step if it needs Weaviate)

### Decisions (proposed)
1. **Drop `talkID` in the normalize commit, replace on merge** (approved 2026-10-29). Nothing reads it after the change; fetch can't produce it.
2. **Fix role extraction's skip filter** (approved). It checks `talk.speaker_role_id`, which nothing writes any more (step 5 writes `talk_metadata`), so step 6 would overwrite every Church role with the HTML one.
3. **Topic fetch errors abort `fetch`** (approved; retry once first) before any write; today one failure writes `"entries": []` and would silently wipe that topic from the committed file.
4. `db/core.53.db` is currently a 0-byte file; `build` will treat it as an existing build and need `--force` (or delete it).

### Review (2026-10-29)
- Commits: `ec68663` normalize JSON (data identical to HEAD with talkID ignored), `e954e78` fetch code, `2eab025` data 2025-10 + topics refresh, then build code and data 2026-04.
- Fetch 2025-10: the 34 existing entries are unchanged, `11eyring` (sustaining) added. A second run left `git diff` empty.
- Topics: the API now returns `author` and `translatedTopic` on every entry. Two new topics. 16 report entries were untagged upstream. `values` is listed in the index but its page is 404, so its 11 old entries are kept.
- Build .53 after fetch 2026-04: 4041/4050 G talks matched (99.8%, 18 via corrections). Unmatched: 9 Ensign-only talks; 3 Church URIs (2 sustainings, 1 audit report). No duplicates, no stale corrections. All 35 April 2026 talks have data_aid, role, preview and URI. Build takes about 9 minutes.
- Tests: 526 passed, 2 failed, 2 skipped. The 2 failures (`test_metrics` John filter, `test_server` tools list 404) don't touch the fetch/build code. Replaced the snapshot topic counts (333/16162) in test_phase1 with counts derived from the JSON.
- .55 (2026-10-29): first SCI release with Oct 2026. 4078/4087 matched; all 37 Oct 2026 talks complete; no renumbering .53→.55 (34 Oct 2020 talks re-dated, still match). Default `SCI_DB_VERSION` → 55. Match report now splits expected/unexpected (all 0 unexpected on .55); step 3 skips blank URLs (was 2219 warnings).
- Still open: the `.52` comparison (the `db/core.52.db` provided is the raw release), and `run_pipeline.py` + `verify_weaviate_pipeline.py` (operator step).


## Embedding: Ollama → llama-server + nomic task prefixes (2026-10-28)

Contract: `config/embedding.py` — `get_embedding_function(url=None, task="document"|"query")`,
`resolve_embedding_url()` (env `EMBEDDING_URL`, default `http://localhost:8080`),
`LlamaCppEmbedder` (POST `/v1/embeddings`, sub-batches of 64, reorders by `index`).
`BaseLoader(..., query_embed_fn=None)` → `self.query_embed_fn` (defaults to `embed_fn`).

- [x] Write `config/embedding.py`; delete `config/ollama.py`
- [x] `BaseLoader.query_embed_fn`; `.env.example` → `EMBEDDING_URL`
- [x] server.py: query task, rename `/health` key `ollama`→`embedding`, search_mode `keyword_only_embedding_unavailable`; tests/test_server.py
- [x] scripts (run_pipeline, verify_weaviate, verify_chromadb) + loaders query() use `query_embed_fn`; tests/test_phase6_orchestrator.py
- [x] benchmark/runner.py port; delete loaders/embeddings.py + tests/test_embeddings.py; conftest fixture; new tests/test_embedding.py
- [x] CLAUDE.md index, backlog/spec notes
- [x] Full test suite green
- [x] Live check against llama-server on truenas:8090 (2026-10-29): 768-dim, batching/order OK, `/health` ok
- [x] Live test reads `EMBEDDING_URL` (was the stale `BENCHMARK_EMBEDDING_*` vars)
- [ ] Re-embed all talks: `run_pipeline.py --force` against llama-server (operator step)

### Review
- Full suite: 464 passed / 5 failed / 47 skipped — the 5 failures are pre-existing (identical on stashed baseline: 455 passed / 5 failed).
- Verified live 2026-10-29 (via Tailscale IP 100.90.131.107 — `truenas` doesn't resolve on this box, MagicDNS is off): query "what is faith" scores 0.82 vs a faith doc and 0.40 vs a flour recipe; the prefix changes the vector (cos 0.78 with vs without); 150 texts in 3 sub-batches take 4.4s and come back in order; `/health` → `{"status":"ok","embedding":"reachable","weaviate":"reachable"}`.
- Root cause of missing prefixes: Phase 24-07 ported chromadb's OllamaEmbeddingFunction 1:1 (raw text, one request per text).
- verify_chromadb_pipeline.py: chromadb 1.5 rejects non-chromadb embedding functions, so collections are opened without one and VER-02 passes `query_embeddings`.
- Removed `ollama` from Pipfile/Pipfile.lock (no remaining imports).

## Unified Pipeline Plan

### Root Problems Identified

1. **Critical Bug**: Phase 2 calls `marker.decompose()` on the global soup *before* `str(element)` is captured into `text_raw` — so Phase 4 can never find `noteMarker` elements because Phase 2 already destroyed them.
2. **Isolation**: Phase 2 owns `parse_html()` and `find_body_container()` privately instead of sharing them via `html_parsing_utils.py`.
3. **Redundant parsing**: Each paragraph's HTML is parsed 3× total (Phase 2 once, Phase 3 once per para, Phase 4 once per para).
4. **Dead fields**: `ParagraphData.has_scripture_citation`, `citation_count`, `has_footnote`, `footnote_count` are never populated.

---

### Phase A — Fix the Critical Bug (Phase 2)

**`phase2_paragraph_extraction.py`**

- Remove the global `soup.find_all(class_="noteMarker") → decompose()` block from `extract_paragraphs()`.
- Add `_element_clean_text(element)` helper that deepcopies the element, strips noteMarkers from the copy, and returns clean text — leaving the original element (and thus `text_raw`) intact.
- Replace all `element.get_text(...)` calls that produce the `"text"` key with `_element_clean_text(element)`.

**Result**: `text_raw` now preserves `<sup class="noteMarker">` for Phase 4. `text` is still clean.

---

### Phase B — Promote Shared Utilities

**`html_parsing_utils.py`** (additions):
- Move `parse_html()` and `find_body_container()` here from Phase 2.
- Add `ParagraphHTMLContext` class:
  - Wraps a paragraph's `text_raw`, lazily parses it once, caches the soup.
  - `soup` property → read-only cached parse for discovery (`find_all`)
  - `fresh_soup()` method → new parse for mutating operations (`decompose`, `replace_with`)
  - `find_citation_spans()` and `find_note_markers()` convenience methods

**`phase2_paragraph_extraction.py`**: import `parse_html` and `find_body_container` from `html_parsing_utils`, remove local definitions.

---

### Phase C — Refactor Phases 3 & 4 to Accept Shared Context

**`phase3_citation_extraction.py`** and **`phase4_footnote_extraction.py`**:
- Add optional `ctx: Optional[ParagraphHTMLContext] = None` to the per-paragraph extraction functions.
- Add optional `contexts: Optional[Dict[int, ParagraphHTMLContext]] = None` to the talk-level orchestrators.
- When `ctx` is provided, use `ctx.soup` for element discovery (skips redundant re-parse).
- Mutating operations (position calculation via `filter_paragraph_around_anchor`) continue using `ctx.fresh_soup()` — isolation is preserved.
- `ctx=None` default means all existing callers work unchanged.

---

### Phase D — New Unified Orchestrator

**`extractors/pipeline.py`** (new file):

```
process_talk_pipeline(content_db, core_db, talk_id, book_cache, configs...)
  → Phase 2: extract paragraphs
  → build Dict[paragraph_id → ParagraphHTMLContext]
  → Phase 3: citations (with shared contexts)
  → Phase 4: footnotes (with shared contexts)
  → return TalkPipelineResult(paragraphs, citations, footnotes, warnings, errors)
```

`TalkPipelineResult` holds all three phase outputs plus merged diagnostics. The back-fill of `ParagraphData` fields (citation/footnote counts) happens automatically because Phase 3 & 4 already mutate the objects in-place.

---

### Key Risks

| Risk | Mitigation |
|---|---|
| `deepcopy` on every paragraph may be slow | Benchmark; fallback to `BeautifulSoup(str(element))` if needed |
| Phase 3/4 accidentally mutating `ctx.soup` | Discovery uses `ctx.soup`; mutations use `ctx.fresh_soup()` — enforced by convention |
| Stanza lines still call `get_text()` on sub-elements | `_element_clean_text()` should be applied at the stanza level, not per-line |
| Logger namespace changes when moving `find_body_container` | Minor, cosmetic only |

---

### Implementation Order

```
Phase A  →  Phase B  →  Phase C  →  Phase D
(bug fix)   (shared)   (optional   (pipeline
             utils)      ctx arg)    module)
```