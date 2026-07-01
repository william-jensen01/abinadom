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
