# How Updates Work

A plain-language guide to keeping the database current. The details live in the code: `scripts/fetch.py`, `scripts/fetch_sci.py`, `scripts/build.py`, `scripts/setup_data.py` and the backfill scripts in `db/one-off-migration/`.

## The short version

The database is built from two sources:

- **The Scripture Citation Index (SCI)** from BYU. It has every talk's text, the scripture citations, speakers and sessions. BYU releases a new version one to two months after each conference, because linking every citation takes time. Each release is a zip at `https://scriptures.byu.edu/sci.N.zip` (there was never a release 54).
- **The Church's website API.** It has the Church's own data for each conference talk: the official title, the speaker's calling, a short preview, and the topics it's tagged with. It's available within days of a conference.

So the Church data normally comes first and SCI catches up later: the Church JSON committed in the repo is usually *ahead* of the newest SCI release, holding talks SCI doesn't have yet. Those talks simply wait for SCI. The case to watch is the reverse, an SCI release with talks the committed JSON doesn't know about (see "Reading the match report").

Three commands keep them in step:

| Command | What it does | Talks to the internet? |
|---|---|---|
| **`fetch`** | Downloads the Church's data and saves it as JSON files in the repo | Yes |
| **`fetch_sci`** | Downloads an SCI release (`--version N`, or `--version latest` for the newest) and installs it in `db/sci/` | Yes |
| **`build`** | Takes a raw SCI release plus those JSON files and produces the finished database | No, it runs entirely offline |

`setup_data.py talks --version N` (or `latest`) runs `fetch_sci` and then `build` for the release it got, and ends by printing the `SCI_DB_VERSION=N` line for `.env`. Its `--force` goes to `build` only.

## What to run when

| Situation | Run |
|---|---|
| **A new conference happened** | `fetch --conference YYYY-MM`, then commit the JSON |
| **BYU released a new SCI version** | `setup_data.py talks --version N` (or `--version latest`), then reload Weaviate |
| **You changed a correction or the JSON** | `build --version N --force`, then reload Weaviate |
| **Starting from nothing** | `fetch --all`, then `setup_data.py talks --version N` |

All commands run as `pipenv run python scripts/<name>.py ...`. In the Docker deployment the same scripts run as `docker compose run --rm tools scripts/<name>.py ...` (see [../DEPLOY.md](../DEPLOY.md)), except `fetch`, whose output a container does not keep.

A typical cycle looks like this:

1. **Conference weekend passes.** Run `fetch --conference 2026-10`. Look over the summary and the JSON diff, then commit. The Church data for the new talks is now saved, even though SCI doesn't have those talks yet.
2. **A few weeks later, re-run the same fetch.** The Church keeps adjusting topic tags for a while after a conference, and this picks up the settled tags.
3. **One to two months later, BYU releases the next SCI version** (e.g. `.55`). Run `setup_data.py talks --version 55` (or `--version latest`): it downloads the release into `db/sci/` and builds from it. Check the match report and the setup hint (see below). Point the app at it with `SCI_DB_VERSION`, as setup prints.
4. **Reload Weaviate** with `run_pipeline.py --force`, then run `verify_weaviate_pipeline.py`.

## How it fits together

```
 Church API ──fetch──▶ JSON files (committed) ─┐
                                               ├──build──▶ db/core.N.db
 BYU sci.N.zip ──fetch_sci──▶ db/sci/ (raw) ───┘           db/content.N.db
                core.N.db, content.N.db,                       │
                lucene.N/, sci.N.json          run_pipeline ──▶ Weaviate
```

`build` does these steps, in order:
1. Copies the raw release, so the original in `db/sci/` is never changed.
2. Extracts clean talk text.
3. Works out each talk's Church web address (its URI) from the SCI data, applying any hand corrections.
4. Prints a match report.
5. Fills in the Church data: titles, callings, previews and topics.
6. Fills gaps from the SCI's own HTML: missing callings and kickers.
7. Applies title corrections, then checks the result.

## Why it works this way

**Only the fetches touch the network.** `fetch` downloads the Church data and `fetch_sci` the SCI release; `build` never does. Building is repeatable and safe. You can rebuild as often as you like, with no internet, without bothering the Church's servers, and get the same result every time. If the Church's site is down or changes, existing builds aren't affected.

**The Church data is saved as JSON in the repo.** That gives three things a database file can't:
- **History.** Every change the Church makes, such as a corrected title, a re-tagged topic, or a new talk, shows up as a readable diff in git.
- **Review before it lands.** You see exactly what changed before it reaches the database.
- **Reproducibility.** Anyone can rebuild the same database from the same commit.

`fetch` writes the files in a fixed order and format, so running it twice with nothing new upstream changes nothing. When something does show up in the diff, it's a real change.

**Talks are matched by their Church web address, not SCI's talk number.** SCI talk numbers belong to SCI and can change between releases. The Church's address for a talk (e.g. `/general-conference/2026/10/12gong`) doesn't change. Matching on it means:
- `fetch` doesn't need the SCI database at all,
- Church data for a new conference can be saved before SCI has that conference,
- an SCI release that renumbers talks doesn't break anything.

**The raw SCI release is kept untouched in `db/sci/`.** `fetch_sci` installs `core.N.db` and `content.N.db` there, plus the release's search index as `lucene.N/` (kept, but nothing reads it) and a download record `sci.N.json`. Re-running it downloads nothing unless the release changed on the site (it asks with the ETag saved in the record; `--force` downloads again), and a release you put there by hand, without a record, is left alone. A failed download or a bad zip leaves `db/sci/` as it was. `latest` starts from the newest release it knows and tries the next three numbers, so it steps over the missing 54. `build` works on a copy and only replaces the finished database at the very end. A failed build leaves nothing half-done, and you can always start over from the original.

**SCI comes first; the Church data adds to it.** SCI is the backbone because it has what makes this project useful: the scripture citations. Church data adds official titles, callings, previews and topics. Where the Church has nothing, SCI's own data is kept. That covers pre-1971 talks and items the Church published only in the Ensign.

**Hand corrections live in one small file.** `db/one-off-migration/talk_corrections.json` lists the few talks whose SCI web address doesn't line up with the Church's: punctuation differences, and items published under `/ensign/` instead of `/general-conference/`. It also holds a few title fixes. `build` applies them last, so they always win.

**This replaces `UPDATE.py` and `gc.db`.** The old process copied Church data into a hand-maintained intermediate database (`gc.db`) and patched the main database from it. When we compared, the Church API gave exactly the same data as `gc.db`, so the middle step only added a file to keep in sync. `fetch` and `build` do the same job with fewer moving parts and a visible history.

## Reading the match report

Every build prints a match report and saves it to `db/build_report.N.json`. It answers one question: did every SCI conference talk find its Church data, and is anything left over?

Some items never match, and that's expected:
- **SCI talks with no Church data.** These are items SCI files under a conference but the Church published only in the Ensign, like the 1992 "A Worldwide Sisterhood" sessions.
- **Church items with no SCI talk.** These are procedural items SCI doesn't include: sustainings, statistical and audit reports, welfare-services addresses, videos, Music and the Spoken Word, and a few one-offs like the Family Proclamation.

The report counts expected items by kind, and lists only the **unexpected** ones in full. On a healthy build, every unexpected list is empty. If something shows up there, either it's a new kind of item that needs adding to the expected list at the top of `scripts/build.py`, or it's a real talk that failed to match and needs a correction.

**The setup hint.** After a successful build, `setup_data.py talks` reads this report. If `sci_talks_without_church_data` has `unexpected` items, it prints how many SCI talks are missing Church data. That almost always means the committed Church JSON is older than the SCI release, so the fix is to refresh the JSON (`fetch --conference YYYY-MM` and commit it; in a Docker deployment, `git pull` and `docker compose build tools`, since the JSON is baked into the image) and then run the same `setup_data.py talks --version N` command again, with `--force`. It is a warning: the build still succeeded. Church talks still waiting for SCI (`church_uris_without_sci_talk`) get no hint, since Church data normally comes first.

## Being polite to the Church's servers

`fetch` sends one request at a time, at most two per second, and names itself in its User-Agent. Talk pages are cached locally (`http_cache.sqlite` in the repo folder, or the file named by the `SCI_HTTP_CACHE` environment variable when it is set and not empty; its folder is created if missing), so a talk is downloaded once and then reused. Topic pages and conference contents are always downloaded fresh, because those are what change.

A run for one conference takes a few minutes, mostly for re-reading the ~335 topic pages. `fetch --all` takes longer the first time on a machine without the cache.

## Things to watch for

- **Fetch failures in the summary.** An occasional timeout or server error is normal. The old entry is kept and the summary names the talk. Re-run the fetch.
- **Topics shift after a conference.** Expect the topic diffs for a new conference to keep changing for a few weeks.
- **The "values" topic** is listed by the Church but its page currently returns an error. `fetch` keeps its old entries and notes it in the summary.
- **Weaviate needs a reload after a build.** A plain `run_pipeline.py` only adds talks it hasn't seen. Use `--force` to refresh everything after a new build.

## Scriptures

The scriptures are a separate store, `db/scripture.db` (never committed). It is built from the Church's content API in two steps, then loaded into Weaviate:

| Command | What it does | Talks to the internet? |
|---|---|---|
| **`fetch_scriptures.py`** | Walks the tables of contents of the five standard works and the Joseph Smith Translation appendix, and stores every page's raw API response in `scripture.db`. A page is added only when its content changed, so a re-run that finds nothing new writes nothing. | Yes |
| **`build_scriptures.py`** | Parses the stored pages into chapters, verses, footnotes and cross-references, imports the JST rows from `core.N.db`, links them, and runs its checks in one transaction. Writes `build_meta.build_id`, a hash of the parsed content, which includes the JST rows imported from `core.N.db`. | No |
| **`run_scripture_pipeline.py`** | Loads `scripture.db` into the `ScriptureVerses`, `ScriptureChapters` and `ScriptureMeta` collections in Weaviate. | No (needs Weaviate and the embedder) |

```
 Church API ──fetch_scriptures──▶ scripture.db (raw pages)
                                      │   + db/core.N.db (JST rows)
                                build_scriptures
                                      ▼
                                scripture.db (parsed) ──run_scripture_pipeline──▶ Weaviate
```

| Situation | Run |
|---|---|
| **Starting from nothing** | `build` for `core.N.db` first, then `fetch_scriptures.py`, `build_scriptures.py`, `run_scripture_pipeline.py` |
| **The Church corrected scripture text or footnotes** | `fetch_scriptures.py`, `build_scriptures.py`, `run_scripture_pipeline.py` |
| **A new SCI release changed the JST rows** | `build_scriptures.py` again, then `run_scripture_pipeline.py` |
| **A fetch stopped partway** | `fetch_scriptures.py --only-missing` |

The same rules as for talks apply: only the fetch touches the network, and `build_scriptures.py` can be repeated at will, because the same raw pages and the same `core.N.db` (the JST rows come from it) always give the same `build_id`.

**The `build_id` ties the two stores together.** Search hits come from Weaviate, while footnotes, cross-references and JST text come from `scripture.db`, so both must be the same build. A complete load writes the file's `build_id` into `ScriptureMeta`. When that differs from the file's, the loader resets the three collections and reloads everything instead of resuming. The server compares the two once, at startup, and if they differ logs a warning and flags it in `/health`; it does not re-check while running. The fix is to run `run_scripture_pipeline.py` again and then recreate the server's container (`docker compose up -d --force-recreate mcp-server`), because the server compares them only at startup.

**On a deployed server** `scripture.db` is mounted read-only, so an update means replacing the file and recreating the container (`docker compose up -d --force-recreate mcp-server`): the server opens the file and compares build ids only at startup. See [../DEPLOY.md](../DEPLOY.md).

## Where things live

| What | Where |
|---|---|
| Raw SCI releases (never edited) | `db/sci/core.N.db`, `db/sci/content.N.db`, `db/sci/lucene.N/` (kept, unused), `db/sci/sci.N.json` (download record) |
| Finished databases (what the app reads) | `db/core.N.db`, `db/content.N.db` |
| Build report | `db/build_report.N.json` |
| Church data | `db/one-off-migration/talk_metadata.json`, `talk_previews.json`, `conference_topics.json`, and `topics.json` |
| Hand corrections | `db/one-off-migration/talk_corrections.json` |
| Which version the app uses | `SCI_DB_VERSION` in `.env` (default in `db/__init__.py`) |
| The commands | `scripts/fetch.py`, `scripts/fetch_sci.py`, `scripts/build.py`, `scripts/setup_data.py` |
| Scripture store | `db/scripture.db` (raw pages and parsed tables) |
| The scripture commands | `scripts/fetch_scriptures.py`, `scripts/build_scriptures.py`, `scripts/run_scripture_pipeline.py` |
