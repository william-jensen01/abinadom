# scriptures.byu.edu Routes

What's reachable on the Scripture Citation Index site and what each route is good for. Found by probing the site and reading its JavaScript (`/static/homepage/scripts/base.js`) on 2026-10-29. None of this is documented by BYU, so any of it can change without notice. Keep requests light.

## SCI releases: `/sci.N.zip`

The raw `core.N.db` and `content.N.db` come from `https://scriptures.byu.edu/sci.N.zip`. There's no index or "latest" link, so the only way to find releases is to probe version numbers. A `HEAD` request tells you whether a version exists and gives its date and size without downloading it:

```bash
curl -sI https://scriptures.byu.edu/sci.55.zip | grep -iE 'content-length|last-modified'
```

| Version | Status | Last-Modified | Size (bytes) |
|---|---|---|---|
| 55 | 200 | 2026-10-27 | 103,129,509 |
| 54 | **404** | — | — |
| 53 | 200 | 2026-05-18 | 102,808,816 |
| 52 | 200 | 2026-02-15 | 102,228,031 |
| 51 | 200 | 2025-05-26 | 101,773,341 |
| 50 | 200 | 2024-11-04 | 101,339,039 |
| 40–49 | 200 | | |
| 38–39 | **404** | | |
| 30–37 | 200 | | |
| 1–29, 56+ | 404 | | |

Version numbers get skipped, so when checking for a new release try a few numbers past the current one, not just N+1.

**Doesn't exist (404):** `sci.zip`, `sci.latest.zip`, other name variants like `sci54.zip` or `sci.55.0.zip`, bare `core.N.db`/`content.N.db`, and any checksum or manifest file (`version.json`, `sci.md5`, `sci.55.sha256`).

## Android app page: `/sci/`

Lists every Android APK the site has published (`ldssci-109.apk` through `ldssci-v2.9.25.apk`, plus `ldssci15-beta-115.apk`), each with a one-line note such as "4/2026 conference updates." The app downloads the citation database on first launch, which is almost certainly the `sci.N.zip` release.

**What it's good for:** a rough release history. It lags the zips: on 2026-10-29 its newest APK was still 2.9.25 (2026-05-19, matching `sci.53.zip`), two days after `sci.55.zip` went up.

## Website API

The site's web app loads everything through these routes. Most return HTML fragments; the two `sync_*` routes return JSON.

| Route | Returns | What it's good for |
|---|---|---|
| `/content/talks_ajax/<talkID>` | Full talk page as HTML, by SCI talk ID | Checking or backfilling a single talk's text without a new release. `/1` is Heber J. Grant, April 1942. |
| `/citation_index/sync_sci/<citationID>` | JSON: `{"book", "chap", "verses", "flag"}` | Looking up one citation (see below) |
| `/scriptures/sync_scrip/<citationID>` | JSON: `{"book", "chapter", "verses", "jst"}` | Same lookup, different key names |
| `/citation_index/citation_ajax/Any/1830/<year>/all/s/f` | Citation index view filtered by year range | Browsing citations by period |
| `/citation_index/filter_ajax` | Filter panel | List of the filter options |
| `/citation_index/gc_ajax` | General Conference listing | List of conferences |
| `/citation_index/jod_ajax/` | Journal of Discourses | JD browsing |
| `/citation_index/stpjs_ajax/` | Teachings of the Prophet Joseph Smith | TPJS browsing |
| `/citation_index/ti_ajax/` | Probably the topical index (guessed from the name) | |
| `/citation_index/speakers_ajax/` | A–Z speaker index | List of speakers |
| `/citation_index/search_ajax/` | Search form | |
| `/citation_index/search_results_ajax/<query>` | Search results | |
| `/citation_index/contents_ajax/` | Contents | |
| `/scriptures/scriptures_ajax` | Scripture text pane | `/1` returns 500, so it needs a different argument format |

### The `sync_*` routes

Both look up one row of the SCI `citation` table by its `ID`. The fields are `citation.BookID`, `Chapter`, `Verses` and `Flag`, where a flag of `"J"` means a Joseph Smith Translation (JST) citation. In the site, clicking a citation in a talk calls them to move the scripture pane (`sync_scrip`) or the citation-index pane (`sync_sci`) to the cited verse.

```
GET /citation_index/sync_sci/1   → {"book": 113, "chap": 16, "verses": "15", "flag": ""}
GET /scriptures/sync_scrip/1     → {"book": 113, "chapter": 16, "verses": "15", "jst": ""}
```

Citation 1 is book 113 (1 Chronicles) 16:15. IDs 1, 2, 3, 646 (JST), 1000, 50000 and 146235 all matched `core.53.db` exactly.

**What they're good for:**

- **Spot-checking a build.** Sample citation IDs and compare them to the live site.
- **Spotting a new release early.** The live site serves the newest data. On 2026-10-29, `core.53.db` stopped at citation ID 146235, but the live site answered up to 146826 (about 590 new citations). If the live maximum is above your build's, there's new data.

**Limits:**

- **No talk ID.** The response tells you which verse was cited but not which talk cited it, so it can't replace the zip.
- **One request per citation.** There's no bulk mode.
- **Errors are HTML.** An ID of 0, a non-numeric ID, or one past the end returns an HTML 500 page instead of JSON.
- **Gaps.** `core.53.db` has 126,100 citation rows spread across IDs 1–146235, so about 20k IDs are unused. Those probably return 500 too (not tested).

## Other paths

| Path | Status | Notes |
|---|---|---|
| `/server-status` | 403 | Apache's status page exists but is locked |
| `/citation_index/` | 500 | Bare route prefix, not a page |
| `/content/` | 200 | Shows a "performing maintenance" page; just a bare route prefix |
| `/static/homepage/...`, `/django_mako_plus/dmp-common.min.js` | 200 | Site assets; shows the site is a Django app |
| `robots.txt`, `sitemap.xml`, `.git/`, `.env`, `api/`, `admin/` | 404 | Nothing there |
