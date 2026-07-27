---
phase: 25-data-model-book-resolver-extraction
granularity: standard
plans: 4
date: 2026-07-27
---

# Phase 25 Decomposition

## Seams found

- **Interface seam — text cleaning.** Contract: *"UTF-8 bytes or str in, clean str out, never any
  residual HTML tag."* `clean_verse_text` knows nothing about books, references, or the DB; the
  extractor needs only that one sentence. Also a **blast-radius seam**: this is the phase's only
  edit to `extractors/html_parsing_utils.py`, a module the entire talk pipeline (Phases 1-4)
  imports — isolating it keeps the revert surface one commit wide.

- **Interface seam — book canonicalization.** Contract: *"give it the 99 `book` rows, get back
  canonical digit-form book records plus an alias lookup; `resolve(str) -> Optional[str]` returns
  exactly the name those records store."* The resolver reads the `book` table only — never verse
  rows — so it is provable with hand-built row fixtures and needs nothing from extraction.

- **Interface seam — record shape.** Contract: *"`ScriptureVerse` carries the SPEC §4 fields;
  `BookVerses` groups them by (book, chapter, variant)."* Phase 26 consumes `BookVerses` directly,
  so the container shape is an external contract, not an extraction implementation detail.

- **Verification seam at each of the three above.** `clean_verse_text` proves done with synthetic
  strings; the resolver with synthetic book rows; the dataclasses with construction/validation
  assertions. None of the three needs the other two to be green.

- **Parallelism seam across all three.** Zero `files_modified` overlap — `html_parsing_utils.py`,
  `book_resolver.py`, and `scripture_data.py` are three disjoint file sets with three disjoint test
  files. They are genuinely simultaneous work.

- **No seam inside extraction.** The query builder, the row→`ScriptureVerse` transform, and the
  grouping step share the `canonical_books` lookup and the row dict shape as internals, not as a
  nameable contract — and the 41,996 assertion can only be made once all three exist. One mental
  model: *read → clean → normalize → group.*

- **No seam between the extractor and its tests.** The 41,996 / no-tags-survive / no-word-ordinal
  assertions are the extractor's own proof of done, not a separable deliverable.

- **No seam between the `db/__init__.py` schema hardening and extraction.** Declaring
  `scripture` and the extra `book` columns in `EXPECTED_CORE_TABLES` is four lines whose only
  purpose is to make *this phase's* queries fail loudly on a DB version bump. It is a prerequisite
  task of the plan that issues those queries, not a plan.

## Cuts chosen

- **Plan 25-01** — `clean_verse_text` in `extractors/html_parsing_utils.py` + its synthetic unit
  tests. One mental model: *one pure decode-and-clean function with an unconditional no-tags
  post-condition* (D-01/D-02/D-03). Wave 1.

- **Plan 25-02** — `config/book_resolver.py` (`canonicalize` → `build_alias_index` → `resolve`) +
  `tests/test_book_resolver.py`. One mental model: *canonical book names and the alias lookup that
  maps every input form onto them* (D-04/D-05, EXT-04, RES-01). Wave 1.

- **Plan 25-03** — `models/scripture_data.py` (`ScriptureVerse`, `BookVerses`, `VARIANT_BY_FLAG`) +
  the scripture constants in `config/pipeline_config.py` + `tests/test_scripture_data.py`. One
  mental model: *the record contract the corpus is defined by, declared before anything produces
  it.* Wave 1.

- **Plan 25-04** — `extractors/scripture_extraction.py` + `tests/test_scripture_extraction.py` +
  the `db/__init__.py` schema declaration + the CLAUDE.md index update. One mental model:
  *read → clean → normalize → group, and prove exactly 41,996.* Consumes all three Wave-1
  contracts and nothing of their internals. Wave 2.

**Constants placement.** `WEAVIATE_SCRIPTURE_COLLECTION_NAMES` / `SCRIPTURE_WINDOW_RADIUS` /
`SCRIPTURE_BATCH_SIZE` have no consumer inside Phase 25 (Phases 26-27 consume them). They sit with
the model because both are *declarations of what the scripture corpus is*, and `config/pipeline_config.py`
is touched by no other plan in the phase.

**Third test file.** `25-VALIDATION.md` names two test files; this decomposition adds a third,
`tests/test_scripture_data.py`, so the Wave-1 plans keep disjoint file ownership and the repo's
one-test-file-per-module convention holds. Strict superset of the validation strategy — no
coverage is lost, and the phase quick-run command widens to three files.

## Alternatives rejected

- **Coarser (3 plans — fold the model into extraction).** Crosses the record-shape seam: `BookVerses`
  is Phase 26's input contract and deserves to be fixed before anything produces it, and the merged
  plan would carry two mental models (declare the shape / build the pipeline) across seven tasks.

- **Coarser (2 plans — one "pure building blocks" Wave-1 plan + extraction).** Merges text cleaning
  with data-shape declaration — a grab-bag, not a mental model — and drops three-way Wave-1
  parallelism to none. It also folds an edit to the shared talk-pipeline utility module into a plan
  full of brand-new scripture files, widening the revert surface for no gain.

- **Finer (split `canonicalize` from `resolve` into two plans).** No parallelism seam — both live in
  `config/book_resolver.py`, so the second would be forced into Wave 2 for a file conflict — and
  `resolve`'s only meaningful assertion is that its output equals what `canonicalize` stores, which
  is one proof, not two.

- **Finer (split extraction's tests into their own plan).** Separating a deliverable from its own
  proof of done is an anti-pattern; the 41,996 assertion *is* how the extractor proves done.

- **Finer (a plan for the `db/__init__.py` schema hardening).** Four lines with no independent
  proof of done — no verification seam.

## Granularity

Standard, honored. Plan 25-01 is a single task; that is the honest size of the seam, and padding it
with a second task would only restate the verify. The one place the bias was *not* pushed further is
inside 25-04, where the query/transform/group trio share internals and a single corpus-wide
assertion — no seam to cut.
