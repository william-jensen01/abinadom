# Backlog

Deferred work with enough context to pick up cold. Newest/most-actionable first.

---

## Revisit `group_by_talk` vector-routing workaround if Weaviate is upgraded

**Status:** Working as intended via a workaround. Revisit only after a Weaviate
version/config change.

**Finding (live stack `10.0.0.231:8765`, verified 2026-07-01):** on this Weaviate
version, `hybrid()` + `group_by` returns **zero groups** — the grouped result dict is
empty regardless of query. Only the `near_vector()` + `group_by` path returns groups.
(Confirmed by running the identical grouped query both ways against the live stack.)

**Current workaround (in `server.py` `search()`):** whenever `group_by_talk=True`,
grouping is routed through `near_vector` regardless of `alpha` — `search_mode` reports
`"vector_grouped"`. It requires a query vector, so when the embedding service is down we
return a clear message instead of empty results. The trade-off (documented in the
`search` docstring and `MCP_INSTRUCTIONS`): **grouped results are always vector-ranked;
`alpha` applies only to the flat, non-grouped path.**

**Also fixed alongside it (not a workaround — a real bug):** the grouped-output code had
iterated `result.groups` as a list reading `.belongs_to_group`, but this weaviate-client
returns a dict `{group_value: GroupObject}` keyed by `.name`. That path had never worked.

**Revisit when:** Weaviate is upgraded or reconfigured. Re-run the two-way probe
(`hybrid`+`group_by` vs `near_vector`+`group_by`). If hybrid grouping returns groups,
consider honoring `alpha` on the grouped path too (route grouped hybrid through
`hybrid()` when `alpha` is in `(0, 1)`), and drop the "grouped is always vector-ranked"
caveat from the docs.

---

## Denormalize `speaker_id` + `speaker_name` onto all collections (pipeline)

**Status:** Postponed. Keep the current fuzzy `speaker_name` filter as-is for now.

**Finding (live schema, verified 2026-07-01):** speaker fields are only partially
denormalized across the four Weaviate collections.

| Collection | `speaker_id` | `speaker_name` |
|---|---|---|
| `ConferenceTalks` (talks) | ✅ int | ✅ text |
| `ConferenceTalkParagraphs` (paragraphs) | ❌ absent | ✅ text |
| `ConferenceTalkCitations` (citations) | ❌ absent | ❌ absent |
| `ConferenceTalkFootnotes` (footnotes) | ❌ absent | ❌ absent |

`speaker_id` is 100% populated **on talks** (5,838/5,838), but it does not exist on the
other collections. The loader schemas confirm this (`loaders/weaviate_loader.py`:
`_paragraph_properties` has `speaker_name` only; `_citation_properties` /
`_footnote_properties` have neither — only `talk_id`).

**Why it matters:**
1. **Blocks dual-mode speaker filtering.** We wanted a single `speaker` param that
   accepts an int (→ exact `speaker_id`) or a string (→ fuzzy `speaker_name` `like`).
   Because `search` defaults to `paragraphs`, an int → `speaker_id` filter binds to a
   property that isn't there and matches nothing. Int-mode would only work on `talks`.
2. **Existing latent bug.** The current fuzzy filter
   `Filter.by_property("speaker_name").like(...)` also has no field to bind to on
   `citations`/`footnotes`, so `search(collection="citations", speaker=...)` silently
   returns nothing today.

**Proposed change (pipeline):**
- Add `speaker_id` (INT) and `speaker_name` (TEXT) to the paragraph, citation, and
  footnote schemas in `loaders/weaviate_loader.py`.
- Populate them in `loaders/shared_transforms.py` (the prepare_* / rich_metadata
  functions already carry talk metadata per record — denormalize speaker fields the
  same way `conference_year`/`title` are).
- Reindex / reload the affected collections.

**Tool updates after the pipeline change:**
- Implement dual-mode `speaker` (int → exact `speaker_id`, string → fuzzy
  `speaker_name`) uniformly across all collections.
- Remove the id→name resolution workaround (would otherwise be needed to make int-mode
  work on paragraphs without this schema change).
- Fix the silent no-match on citations/footnotes speaker filtering.

**Interim design if we ever need int-mode before the reload:** resolve `speaker_id` →
distinct `speaker_name`(s) via one `talks` lookup, then filter the target collection by
`speaker_name` (OR the variants). Works on talks + paragraphs; citations/footnotes still
unsupported until denormalized.

---

## Embedding model: nomic-embed-text vs. alternatives (talks + scriptures)

**Status:** Parked. Investigated during the scriptures-v1 spec discussion. **Verdict:
stay on `nomic-embed-text` for now**; no alternative beats it decisively enough to
justify a re-embed. Revisit only if scripture-verse recall proves weak in eval, or if we
adopt in-process serving for another reason (see late chunking below).

**Context.** Embeddings are served via **Ollama `/api/embeddings`** (`config/ollama.py`),
one HTTP call per text, returning a single pooled **768-d** vector — no token-level
access. Model is hardcoded to `nomic-embed-text` in `get_embedding_function()`
(`OllamaEmbedder` already parameterizes `model=`, so a per-collection model map would be
a small change, not a rearchitecture). nomic was chosen for its **8192-token context**
(long talk paragraphs).

**The two corpora have different retrieval profiles:**

| | Talks | Scriptures |
|---|---|---|
| Unit | 100–400-word paragraphs (long) | 20–40-word verses (short) |
| Language | Modern English | Archaic English (KJV/BoM/D&C) |
| Dominant need | long context + thematic semantics | short-text precision + **lexical recall** (users recall fragments) |
| Key lever | vector semantics | **hybrid** — the BM25 half matters *more* |

**Head-to-head (directional, ~Jan 2026 memory, mixed MTEB versions — RE-VERIFY on
current MTEB/BEIR before acting; the *retrieval* subscore is what matters, not MTEB
overall avg):**

| Model | Params | Dims | Max ctx | Retrieval vs nomic | Sparse/hybrid | License | Ollama-native |
|---|---|---|---|---|---|---|---|
| **nomic-embed-text-v1.5** *(incumbent)* | 137M | **768** | 8192 | **baseline** (~55 BEIR) | dense only | Apache | ✅ |
| gte-large-en-v1.5 | 434M | 1024 | 8192 | +2–3 | dense only | Apache | ✅ |
| arctic-embed-l-v2.0 | 568M | 1024 (MRL) | 8192 | +1–3 | dense only | Apache | ✅ |
| bge-large-en-v1.5 | 335M | 1024 | **512** ⚠️ | +0–1 | dense only | MIT | ✅ |
| mxbai-embed-large-v1 | 335M | 1024 | **512** ⚠️ | +0–1 | dense only | Apache | ✅ |
| bge-m3 | 568M | 1024 | 8192 | ~0 to +1 (dense) | **native dense+sparse+ColBERT** | MIT | ⚠️ dense-only in Ollama |
| jina-embeddings-v3 | 572M | 1024 | 8192 | +2–3 | dense (+late-chunk) | **CC-BY-NC** 🚫 | ❌ (in-process) |
| stella_en_1.5B_v5 | 1.5B | 1024+ | 8k | +5–7 | dense only | MIT | ❌ (heavy) |
| gte-Qwen2-1.5B-instruct | 1.5B | 1536 | 32k | +5–8 | dense only | Apache | ⚠️ heavy |

**Analysis vs. the incumbent:**
- **Same-paradigm upgrades** (dense, 8192 ctx, Ollama): `gte-large-en-v1.5` /
  `arctic-embed-l-v2.0`, ~**+1–3 BEIR**. Real but modest; costs **768→1024d (+33%
  index/memory)** and a full re-embed + revalidation. Storage delta is trivial at our
  size (~75k verses + ~5.8k talks); the re-embed/revalidation is the real cost.
- **nomic's edge is quality-per-byte / per-ms** — 768d, 137M params, the most compact
  and fastest here. Every model that *clearly* out-retrieves it (stella, gte-Qwen2) is
  4–11× larger and won't sit comfortably in Ollama alongside other workloads.
- **Short-context trap:** `bge-large`/`mxbai` cap at **512 tokens** — disqualifying for
  talk paragraphs; only ever viable as a scripture-only model.
- **bge-m3** is only worth it as a deliberate **hybrid-architecture bet served in-process
  (FlagEmbedding)** to use its learned-sparse output. Via Ollama it's dense-only ≈
  "nomic-ish at 1024d," i.e. a net downgrade (more storage, no retrieval gain). Its
  differentiator (better lexical recall for "I-remember-a-phrase" scripture queries)
  **largely overlaps with just tuning the BM25 half of the existing Weaviate hybrid** —
  which costs nothing.

**Bottom line:** for v1, **keep nomic**. The couple-point gainers (arctic/gte) are
nice-to-haves gated on a re-embed; bge-m3's win needs an in-process serving change whose
benefit is mostly reachable by hybrid tuning. **Highest-ROI embedding work is not a model
swap — it's (a) hybrid/BM25 tuning and (b) adding nomic's `search_document:` /
`search_query:` task prefixes** (✅ done 2026-10-28: `config/embedding.py` applies them; requires a full re-embed). API models (Voyage-3, OpenAI `text-embedding-3-large`, Cohere v3) are top-tier but
break the self-hosted/local-data posture and add per-query cost — out on architecture
grounds, not quality.

**Multi-model (nomic for talks, different for scriptures):** feasible — each `search`
targets one collection, so a collection is safe as long as it's *queried with the model
it was indexed with*. Keep model selection as a **config value keyed by collection-group,
defaulting to nomic**, so it's a one-line change + routing lookup later, eval-gated. Do
not build the routing now (YAGNI).

**Revisit when:** scripture eval shows weak verse recall; or we move to in-process serving
(then reassess arctic/gte/bge-m3/jina together); or a new model shows a *decisive* (not
+1–3) retrieval gain at comparable size/license.

---

## Late chunking for scripture verses (and paragraphs)

**Status:** Intriguing, parked for a dedicated deep-dive. **Not v1** — blocked by the
current serving stack.

**What it is.** Naive chunking embeds each chunk in isolation
(`chunk → transformer → pool → vector`), so the vector knows nothing outside itself. Late
chunking (Jina, 2024) reverses the order: run the **whole document** through the
transformer first (attention sees full context), *then* pool per-chunk over the
already-contextualized token embeddings:

```
whole chapter → tokenize → transformer (attention across all tokens)
             → slice token spans per verse → pool each span → per-verse vectors
```

Each verse vector becomes chapter-aware — directly fixing scripture's context-starvation
(`"And it came to pass that they did…"` embedded alone is meaningless; late-chunked over
the chapter, antecedents/pronouns resolve into the vector). Same benefit applies to talk
paragraphs (talk-aware paragraph vectors).

**Why it's blocked today.** Late chunking needs the model's **token-level
`last_hidden_state`** plus per-chunk span boundaries. **Ollama's embedding endpoint
returns only the final pooled vector** — no token access. So this is *not* an `embed_fn`
tweak; it requires **replacing the serving path** with in-process `sentence-transformers`
/ HF `transformers` (load the model in-process, read hidden states, pool spans yourself).
That's a new heavy dependency, model-in-process memory, a different call contract, and ops
changes — a large blast radius touching the **shared** embedding surface (the four
`prepare_*` fns + `prepare_talk_bundle` in `shared_transforms.py`, both loaders'
`query()`, and `server.py`'s query embedding). The talk pipeline shares that contract, so
it's affected too.

**Cheaper approximation used in scriptures-v1 instead (B+C windowing):** embed a
reference-prefixed, chapter-bounded neighbor window
(`"{book} {chapter}:{verse}\n{prev}\n{this}\n{next}"`, radius configurable), store the
clean verse alone. Fits the current Ollama string contract with **zero blast radius** and
captures much of the contextual benefit. This is the v1 approach; late chunking is the
"true optimum" upgrade path.

**Deep-dive should cover:** which model to serve in-process (jina-v3 supports late
chunking natively but is CC-BY-NC; nomic/others via custom pooling), span-boundary
tracking per verse/paragraph, chapter/talk-length vs. model context limits, batching &
throughput on the new serving path, and whether the quality gain over B+C windowing
justifies the serving-stack migration. Pairs naturally with the embedding-model revisit
above (same in-process threshold).

---

## Other deferred suggestions (from the search-improvements review)

Parked, not scheduled. Revisit if a use case pushes them up.

- **`speaker_role` filter/metadata** — `talks.speaker_role_id` is 68% populated
  (era-gated: 0% pre-1970) **and** stored as an unlabeled INT. Needs a role lookup
  table + is boost-only, not a hard filter.
- **Footnote scripture lookup** — `footnotes` store only raw text + context, no
  structured `book`/`chapter`/`verse`. Extending `find_by_scripture` to footnotes
  requires new extraction, not a tool tweak.
- **`find_by_scripture` precision edges** — `is_jst` (JST vs standard) filter and
  non-contiguous `verse_list` (INT_ARRAY) matching are not handled; current overlap
  logic uses `verse_start`/`verse_end` only.
- **`talk_duration`** — will not be implemented (no source data; not in schema).
- **Exact-phrase search** — Weaviate has no true phrase search; only approximable via
  `like` substring.
- **Related-talks tool** — trivial `near_vector` reuse on a talk's vector; low marginal
  value over re-searching.
- **Declined (anti-patterns for an LLM client):** boolean AND/OR/NOT query parser,
  autocomplete/suggestions, "did you mean" zero-result recovery — the calling model
  already covers these; `corpus_stats` serves the "list speakers/years" need.
