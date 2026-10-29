# Fetch & Build Spec

Status: draft for review · 2026-10-29

## The idea

Two commands replace the current mix of `UPDATE.py`, `gc.db` and hand-run backfills:

- **`fetch`** gets Church data from the Church API and saves it to committed JSON files. It is the only thing that talks to the network.
- **`build`** takes a raw SCI release plus those JSON files and produces the finished database. It runs offline and never modifies the raw release.

| Situation | Run |
|---|---|
| New conference | `fetch --conference YYYY-MM`, then `build` |
| New SCI release | `build` |
| From scratch | `fetch --all`, then `build` |

Both commands are thin wrappers. They **call the existing scripts' functions**, in order; they don't copy the code. Each script stays runnable on its own, so anyone can recreate any JSON file from the script that made it.

## Sources

| Source | Provides | Used by |
|---|---|---|
| **SCI release** (`core.N.db`, `content.N.db`) | Every talk, including pre-1971 (Corpus `E`) and Journal of Discourses (`J`); text, citations, speakers, sessions | `build` |
| **Church API** | 1971+ conference talks: URI, title, `data_aid`, speaker role, preview, topics | `fetch` |
| **Corrections** (`talk_corrections.json`, by hand) | URI fixes for SCI talks whose URL doesn't map to a Church URI; title fixes | `build` |

`gc.db` is no longer a source. For Oct 2025, the API matched `gc.db` on every field (`data_aid`, title, speaker role, preview for 34/34 talks; the "Atonement" topic page listed the same 305 talks).

## Stored files

All are committed. Talk files are keyed by **Church URI**, not SCI talk ID, so `fetch` never needs an SCI database.

| File | Contents | Made by |
|---|---|---|
| `db/one-off-migration/talk_metadata.json` | uri, title, speaker_role, data_aid | `process_topic_talks/extract_talk_metadata.py` |
| `db/one-off-migration/talk_previews.json` | uri, preview | `api/fetch_talk_previews.py` |
| `topics.json` | Every topic: title, uri | new topics-index step |
| `db/one-off-migration/conference_topics.json` | topic → its talk entries | `scripts/process_topics.py` |
| `db/one-off-migration/talk_corrections.json` | TalkID, original uri, correct_uri, gc, optional title | by hand |

The normalize commit drops the old `talkID` field from every entry: `fetch` can't produce it (no SCI DB), nothing reads it once lookups go by URI, and it goes stale if SCI renumbers. `build` derives URI → talk ID on every run (step 4 saves it).

## `fetch`

`scripts/fetch.py --conference YYYY-MM` (or `--all` for 1971-04 through the latest conference)

| Step | API page | Script | Updates | Cache |
|---|---|---|---|---|
| 1 | Conference contents page | `api/fetch_talk_previews.py` (`fetch_conference_talk_uris`) | list of talk URIs for steps 2-3 | fresh for the named conference |
| 2 | Each talk page | `extract_talk_metadata.py` | `talk_metadata.json` | cached OK |
| 3 | Each talk page | `api/fetch_talk_previews.py` | `talk_previews.json` | cached OK |
| 4 | Topics index (`/general-conference/topics`) | new function | `topics.json` | **always fresh** |
| 5 | Every topic page (~335) | `scripts/process_topics.py` | `conference_topics.json` | **always fresh** |

- Steps 4-5 re-fetch every topic each run, which catches new topics, new talks in old topics, and re-tagging.
- Merges are by URI: new entries are added, existing entries are replaced, so the file mirrors the API exactly (a field the API drops shows up in the diff).
- A topic page that still fails after one retry stops `fetch` before it writes anything. Writing `"entries": []` would silently delete that topic from the committed file. Exception: a topic the index lists but whose page is 404 keeps its old entries and is named in the summary (`values` has been 404 upstream since at least 2026-10-29).
- A talk page that fails keeps its old entry (the failure is listed in the summary); it is never overwritten with empty fields.
- Ends with a summary: talks fetched, talks missing a title, role, `data_aid` or preview, and new topics.

### Caching rule

Today `fetch_talk_previews.py`, `extract_conference_sections.py` and `extract_talk_metadata.py` call `requests_cache.install_cache(...)` at import. That caches every request in the process permanently, so importing one of them would make topic pages come from a stale cache.

- `fetch` creates one `CachedSession` and passes it to the scripts. Topics and the named conference's contents page use a plain, uncached session.
- No script calls `install_cache` at import. Standalone runs create their own session in `main()`.

### Stable output rule

Running `fetch` twice in a row, with nothing changed upstream, must leave `git diff` empty. A real upstream change shows up as only the lines that changed.

Today's writers break this in several ways:
- `extract_talk_metadata.py` saves results in thread-completion order (`as_completed`), so record order changes every run.
- `ensure_ascii` is set differently per writer (`fetch_talk_previews.py` passes `False`, `extract_talk_metadata.py` uses the default). A writer that switches rewrites every accented name.
- `open(path, "w")` has no `encoding=`, so the bytes depend on the OS (cp1252 on Windows, UTF-8 on Linux).
- No trailing newline, so any editor that adds one creates a diff.

Every JSON file `fetch` writes goes through one shared helper:

```python
def write_json(path, records, key="uri"):
    records = sorted(records, key=lambda r: r[key])
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")
```

- Talk files and `topics.json` sort by `uri`. `conference_topics.json` sorts topics by `topic`, and each topic's `entries` by `uri` descending. That's the API's own order: the topic page groups talks into year sections, newest first, and within a conference by slug descending. All 333 saved topics follow it exactly, and so did live re-fetches. Sorting ourselves keeps it stable if the API ever reshuffles; whether the API sorts `210soares` as text or as a number is unchecked, and doesn't matter for stability.

Within a conference this is **not** speaking order:
- From 2019-04 on, slugs are `<slot><position><name>`. The slot is one digit per session type and can skip: 1 Saturday morning, 2 Saturday afternoon, 3 Saturday evening/priesthood (unused from 2026-04, which has only 4 sessions), 4 Sunday morning, 5 Sunday afternoon. Position starts at 1 and can reach two digits (`210soares` = slot 2, position 10). Sorting by (slot, position) as numbers is close to speaking order, but not exact: the `toc` sometimes lists talks out of slug order (2022-10 opens with `18oaks`; 2025-10 runs `19oaks`, `11eyring` … `15eyre`, `17johnson`, `16uchtdorf`), and some numbers are never used (2021-10 `45`, 2025-10 `18`). A text sort is further off (`210soares` < `21christofferson`).
- Before 2019-04, slugs are title words (`born-of-god`), so the order is reverse alphabetical.

Speaking order only comes from the conference contents page (`toc`) or SCI sessions. Never use a `toc` session's index as its slot. The helper only sorts the top level, so `process_topics.py` sorts each topic's `entries` (`sorted(entries, key=lambda e: e["uri"], reverse=True)`) before calling `write_json(path, results, key="topic")`.
- Merges happen in memory, keyed by URI. Sorting once when writing means an updated entry keeps its position.
- All API fields are kept, even ones `build` doesn't read, so the files show what data is available for later use.
- `talk_corrections.json` is edited by hand and isn't written by `fetch`.
- Commit the first run with the helper on its own ("normalize JSON formatting"), so the one-time reorder doesn't hide real data changes.

## `build`

`scripts/build.py --version 53`

Reads the raw release from `db/sci/core.53.db` and `db/sci/content.53.db`, copies it to `db/core.53.db` and `db/content.53.db`, then enriches the copy. It refuses to overwrite an existing build unless given `--force`. The app reads the built copy through `SCI_DB_VERSION`.

| # | Step | Script (`db/one-off-migration/`) | From | Writes |
|---|---|---|---|---|
| 0 | Copy raw release | `build.py` | `db/sci/` | `db/core.N.db`, `db/content.N.db` |
| 1 | Talk text | `backfill_talk_texts.py` | SCI | `talkbody.TextRaw/Simple/Minimal/Enhanced` |
| 2 | Metadata table | `create_talk_metadata_table.py` | | `talk_metadata` table |
| 3 | Match key | `backfill_talk_uri.py` | SCI URL + URI corrections | `talk_metadata.uri_l`, `uri_gc` |
| 4 | Match report | `build.py` | step 3 + JSON URIs | printed and saved report |
| 5 | Church metadata | `backfill_talk_metadata.py` | `talk_metadata.json` | `talk.Title`, speaker_role, data_aid |
| 6 | Missing roles | `backfill_talk_metadata_role_extraction.py` | SCI HTML | speaker_role where still empty |
| 7 | Kicker | `backfill_talk_kicker.py` | SCI HTML | kicker |
| 8 | Previews | `backfill_talk_preview.py` | `talk_previews.json` | `talk_metadata.talk_preview` |
| 9 | Topics | `backfill_topics.py` | `conference_topics.json` | `conference_topic`, `talk_topic` |
| 10 | Title corrections | `build.py` | `talk_corrections.json` | `talk.Title` (last, so corrections always win) |
| 11 | Check | `build.py` | | schema check (`db/__init__.py` expected tables) + summary |

**Talk lookup.** Steps 5, 8 and 9 find the SCI talk for a Church URI through one shared function that matches `talk_metadata.uri_gc` or `uri_l`. Today they key by talk ID (5, 8) or read the old `talk.URI_GC` column (9).

**Match report (step 4).** Based on `.53` vs the API cache: 98.5% of SCI conference talks match by URI and 0.4% through corrections. It lists:
- SCI `G` talks with no Church data. Expected: Ensign-only broadcasts, which are out of scope, and any conference not yet fetched.
- Church URIs with no SCI talk. Expected: reports, sustainings, welfare meetings, videos.
- Corrections whose original `uri` no longer matches the SCI talk with that ID. This guards against SCI renumbering talks; 26/26 checkable corrections were stable from `.52` to `.53`.
- Any Church URI claimed by two SCI talks.

Each unmatched list is split into **expected** (counted per category) and **unexpected** (listed in full), so a new surprise isn't buried in routine items:
- SCI talks: expected if a `gc: false` correction marks them as Ensign-only.
- Church URIs and topic entries with no SCI talk: expected by title (sustaining, solemn assembly, statistical report, audit/finance report, welfare services, video, Music and the Spoken Word) or by a short list of known one-off URIs (`EXPECTED_CHURCH_TITLES` / `EXPECTED_CHURCH_URIS` in `scripts/build.py`; categories from `docs/backfill/UNMATCHED_TALKS_ANALYSIS.md`).

## Changes to existing scripts

- [x] `db/__init__.py`: `SCI_DB_VERSION` setting (default `55` since 2026-10-29, env override).
- [x] `talk_corrections.json`: titles for the five 1992 "A Worldwide Sisterhood" splits.
- [x] `extract_talk_metadata.py`: take a list of URIs instead of reading the SCI DB; key output by URI; remove the "uncached → return None" gate; accept a session; no import-time cache.
- [x] `api/fetch_talk_previews.py`: expose talk-URI and preview functions that take a session; key output by URI; drop the SCI DB lookup; no import-time cache.
- [x] `scripts/process_topics.py`: accept a session, topics list and output path as arguments.
- [x] New topics-index function (in `process_topics.py`): fetch `/general-conference/topics` and write `topics.json`. Right now this adds `atonement-of-jesus-christ` and `callings`.
- [x] Shared `write_json()` helper (see Stable output rule); `extract_talk_metadata.py`, `api/fetch_talk_previews.py`, `scripts/process_topics.py` and the topics-index step write through it.
- [x] Shared `find_talk_by_uri()` helper (in `create_talk_metadata_table.py`, next to `upsert_talk_metadata`).
- [x] `backfill_talk_metadata.py`, `backfill_talk_preview.py`: look up talks by URI via the helper.
- [x] `backfill_topics.py`: use the helper instead of `talk.URI_GC`; default input stays `conference_topics.json`.
- [x] `backfill_talk_metadata_role_extraction.py`: "skip existing" reads `talk_metadata.speaker_role_id`. Since `97fed0e` it read `talk.speaker_role_id`, which nothing writes, so step 6 overwrote every Church role it could parse from HTML.
- [x] Stop adding the dead `talk` columns (`URI_L`, `URI_GC`, `speaker_role_id`, `data_aid`); since `97fed0e` all writes go to `talk_metadata`.
- [x] All backfills: accept `--core-db` / `--content-db` paths so `build` can point them at the copy.
- [x] New `scripts/fetch.py` and `scripts/build.py`.

## Retired

- `scripts/UPDATE.py` and `gc.db`. Their job is now `fetch` + `build`. `docs/update/Update_GC_PLAN.md` is superseded by this spec.
- `content.talkbody.TextPreview`: only `UPDATE.py` wrote it and nothing reads it.
- Dead and unused scripts (`_pg`/`_h1` variants, `fetch_talk_topics_*`, `process_entries.py`, `process_all.py`, `process_talkbody.py`, `migrate_topics.py`, `verify_uri.py`, and their outputs) are left for a later cleanup.

## Out of scope

- Ensign and other non-conference Church content. SCI talks published only in the Ensign keep their SCI data and get no Church data.
- Pre-1971 talks (Corpus `E`): the Church API doesn't have them.
- `api/sessions.json` stays as it is. `api/extract_conference_sections.py` made it (every conference's `toc` entries, sessions flattened); once `UPDATE.py` is retired nothing reads or updates it. It's the only saved copy of `toc` speaking order, except 2025-10, which has only the five session headers and no talks.
- Weaviate loading. `run_pipeline.py` and `verify_weaviate_pipeline.py` run after `build`, unchanged.

## Verification

- [ ] **Build reproduces `.52` contents.** Build `.53` from the current JSON and compare it field by field with what the `.52` backfills produced (talk_metadata, titles, roles, kickers, previews, topics). Every difference is explained by April 2026 being new or by a correction.
- [x] **Fetch reproduces the JSON.** `fetch --conference 2025-10` against the API produces the same Oct 2025 entries already in the JSON files (they came from `gc.db`).
- [x] **Fetch is stable.** After the normalize commit, run `fetch --conference 2025-10` twice; `git diff` on the JSON files is empty after both runs.
- [ ] **New conference.** `fetch --conference 2026-04` + `build` gives the 35 April 2026 talks full Church data.
- [x] **Match report.** Its unmatched lists contain only the expected categories above.
- [ ] Integration tests in `tests/test_pipeline_integration.py` and `tests/test_phase1.py` pass against the built `.53`.
- [ ] `run_pipeline.py` + `verify_weaviate_pipeline.py` pass.

## Decisions

- **Drop `talkID`, replace on merge** (decided 2026-10-29): see Stored files.
- **Raw vs built location** (decided 2026-10-29): raw releases in `db/sci/`, built copies in `db/` (what `SCI_DB_VERSION` points at).
