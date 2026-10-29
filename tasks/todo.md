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