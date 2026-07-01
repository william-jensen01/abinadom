# Backlog

Deferred work with enough context to pick up cold. Newest/most-actionable first.

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
