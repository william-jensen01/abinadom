# Hymns: research handoff

Research for the hymns goal, which starts after the scriptures goal is closed. It records what the Church music site exposes and how to get it. Nothing here is built yet.

- **Gathered:** 2026-11-08, by calling the live site and reading its JavaScript bundle. Every endpoint below returned the response described on that date unless marked otherwise.
- **Scope:** the three hymnbooks. The rest of the music library is listed only for context.
- **Samples:** `docs/hymns/samples/` (small, committed).
- **Raw capture:** `/srv/projects/lds-sci-mcp/data/hymns-research/` (git-ignored, about 22 MB). It holds every response, the JS bundles, the recovered app source, and the media files for one hymn.

## 1. The three hymnbooks

| Book | Slug | Songs (2026-11-08) | `songPublicationId` | Whole-book downloads |
|---|---|---|---|---|
| Hymns for Home and Church (new) | `hymns-for-home-and-church` | 90 | `0000018d-1b40-dff5-a3fd-3fe6c413000c` | yes: PDF, MP3 zips, Braille |
| Hymns (1985) | `hymns` | 341 | `00000184-1714-d3a5-ab95-17fe0b9b0012` | none |
| Children's Songbook | `childrens-songbook` | 268 | `00000184-1714-d3a5-ab95-17fe0b9b0002` | none |

The counts come from `api?type=songBookData` and `songsFilteredList`. Don't hard-code them in checks: *Hymns for Home and Church* is still being released in batches, so its count will grow. Read the count from the API when a check runs.

## 2. Endpoints

Base: `https://www.churchofjesuschrist.org/media/music`. No login, no API key, and plain `GET` with `Accept: application/json` works.

### 2.1 Content API: use this one

`GET /api?type=<type>&lang=<lang>&identifier=<id>[&batchSize=N]`

| `type` | `identifier` | Returns |
|---|---|---|
| `book` | book slug | title, `sortType` (`NUMBER_TITLE`), and a link to an "about" article for the new hymnbook |
| `songBookData` | book slug | `songList[]` of `{slug, songNumber}`, in book order |
| `song` | song slug | the full song record (§3.1) |
| `songLangs` | song slug (send no `lang`) | the song's language codes, e.g. 47 for "The Morning Breaks" |
| `collectionFilters` | JSON array of book slugs, URL-encoded | every filter option for those books, including topics (§4) |
| `songsFilteredList` | JSON filter object, URL-encoded | `{data[], limit, offset, total}`; each entry is a listing entry (§3.2) |
| `article` | article slug | article body |

- **`lang`:** takes 3-letter codes, e.g. `eng` or `spa`.
- **JSON parameters:** must be URL-encoded. The site's source notes that CloudFront rejects raw braces and brackets with a 400.
- **`songsFilteredList` filter keys:** `limit` (default 500), `offset`, and `orderByKey` (`songTitleSortKey` or `bookSongPosition`). Then `bookQueryList`, `textQueryValue`, `tagsQueryList`, `recordingAvailableQuery`, `sheetMusicAvailableQuery`, `videoAvailableQuery`, `difficultyQueryList`, `musicalFeatureQueryList`, `instrumentationQueryList`, `ensembleTypeQueryList`, `voicingQueryList`, `authorQueryList`, `arrangerQueryList`, `artistQueryList`, `composerQueryList`, `categoryQueryList`.
- **Whole book in one call:** `{"lang":"eng","limit":500,"offset":0,"orderByKey":["songTitleSortKey"],"bookQueryList":["hymns"]}` returned all 341 entries (1.3 MB).

### 2.2 Newer API (Brightspot): don't use it yet

`GET /api-bspservice/<endpoint>?collection=<slug>&lang=<lang>[&songFilters=<encoded JSON>]`, where `<endpoint>` is `book`, `song-book`, `song`, `song-lang`, `article`, `collection-filters` or `song-filtered-list`.

- **Switched off:** the site only calls it when the Harness feature flag `MusicContentEnableBSPService` is on, and on 2026-11-08 the flag was `false` for every visitor. The server-rendered pages match the old API (§2.1) exactly.
- **Broken:** `collection-filters` returned 404 and `song-filtered-list` returned 500.
- **Incomplete:** for "The Morning Breaks", `song` returned empty `scriptures`, a blank tune `$id`, lyric `data-aid` IDs that differ from §2.1, and a `url` pointing to `/media/music2/…`, which returns 403.
- **Watch:** re-check the flag before building. If it flips on, the site switches to this API.

### 2.3 Whole-book downloads

- **Endpoint:** `GET /fe-api/get-collection-content-meta?slug=<book>&lang=eng` returns an array of `{type, s3Url, fileSize, lastModified}`. Prefix `s3Url` with `https://www.churchofjesuschrist.org/`.
- **Only the new hymnbook has any:** PDF-Letter (9 MB), MP3-Vocal, MP3-Vocal-Choir, MP3-Accompaniment, MP3-Accompaniment-Guitar (zips up to 217 MB), and Braille as DOCX, HTML and TXT. `hymns` and `childrens-songbook` return `[]`.

### 2.4 Media files

- **Direct links:** `song.assets[].distributionUrl` points to `https://assets.churchofjesuschrist.org/…`, and all of them downloaded fine.
- **Proxy:** the site also serves them through `/media/music/proxyldscdn/<same path>`. That works for GET, but HEAD returns 403.
- **Images:** `/imgs/<assetID>/full/<size>/0/default` (standard IIIF image URLs).
- **Player fallback:** `/media/music/statics/asset/{JSON,MIDI}/<file>` returned 403 for the names I tried. Not needed.

### 2.5 Pages

Every page embeds its data as `window.renderData = {data, strings, envData, pageToRender}`.

| Route | `pageToRender` | Useful `data` |
|---|---|---|
| `/media/music` | `library` | `libraryData.entries`: the full library tree (`samples/library-tree.txt`) |
| `/media/music/<folder-slug>` | `subLibrary` | `subLibraryData` |
| `/media/music/collections/<book-slug>` | `collections` | `bookSlugList`, `bookData` |
| `/media/music/songs/<song-slug>?lang=eng` | `songs` | `songData` (identical to the `song` API), `songLangOptions` (code, English name, native name) |
| …`&crumbs=<book-slug>` | `songs` | also adds `bookData` (the book's song list) and `breadCrumbsPaths` |

`songNavigationList` came back empty even with `crumbs`; it needs a `songListFilters` query parameter.

## 3. Data model

### 3.1 Song record (`api?type=song`)

Sample: `samples/song.the-morning-breaks.json`.

- **`title`, `slug`, `url`, `description`**
- **`verses[]`:** `{verseNumber, verseType ("Verse", …), verseBody}`. `verseBody` is HTML with one `<p data-aid data-pid>` per line, separated by `<br><br>`.
- **`scriptures[]`:** `{linkText, linkUrl, $id}`, with `linkUrl` as a study path, e.g. `/scriptures/ot/isa/60?id=p1-p3#p1`. **This is where hymns join the scriptures corpus.**
- **`tunes[]`:** `{name, alternateTitles}`, e.g. "Hudson".
- **`fullCreditsText`:** HTML, e.g. "*Text:* Parley P. Pratt, 1807–1857 / *Music:* George Careless, 1839–1932".
- **`assets[]`:** `{assetType, distributionUrl, duration (ms), fileName, pianoMarvelUrl, thumbnail}`.
  - **Asset types seen:** `AUDIO_ACCOMPANIMENT`, `AUDIO_ACCOMPANIMENT_GUITAR`, `AUDIO_VOCAL_CONGREGATION`, `MIDI`, `MXL` (zipped MusicXML), `PDF`, `MOBILE_PDF`, `VIDEO`.
  - **`MXL.pianoMarvelUrl`:** a JSON file with the score's measure and line layout.
  - **File IDs:** `MIDI.fileName` and the file inside the MXL zip follow the pattern `2001-01-0010-the-morning-breaks-eng`. This looks like book `2001-01`, then hymn number × 10, then slug, then language. That's an inference from two examples, #1 and #30.

### 3.2 Listing entry (`songsFilteredList`)

Sample: `samples/listing-entry.the-morning-breaks.json`.

This is the only source of the hymn number, the section and the tags. The song record (§3.1) has none of them.

- **Book placement:** `songNumber` (a string, e.g. `"1"`), `bookSlug`, `bookSectionTitle` (e.g. "Restoration")
- **People:** `authors[]`, `composers[]`, `arrangers[]`, `artists[]`, each `{personName}`
- **Arrangement:** `voicings[]`, `instrumentations[]`, `musicalFeatures[]`, each `{name}`
- **Availability:** `recordingAvailable`, `sheetMusicAvailable`, `videoAvailable`
- **`tags[]`:** the topics (§4)
- **`assets[]`**

So a complete hymn record needs one `songsFilteredList` call per book, plus one `song` call per hymn.

### 3.3 Languages

- **`songLangs`** returns codes such as `eng`, `spa`, `zho`, `cmn-latn`, `yue`, `ase` (American Sign Language) and `fra-pf`.
- **Other languages:** the same `song` call with `lang=spa` returns the translated title ("Ya rompe el alba"), verses and the same asset types.
- **Coverage varies by song:** "The Morning Breaks" has 47 languages and "Amazing Grace" has 16.

## 4. Topics

There is no separate Topics index endpoint. Topics are **tags**.

- **Where they are:** `collectionFilters` for `["hymns"]` returns `tagsQueryList`, 119 entries of `{id, value}`. They match the union of every hymn's `tags[]` exactly, and every hymn has at least one tag (1 to 18).
- **Filter by ID, not name:** `tagsQueryList:["<id>"]` returned 28 hymns for "Restoration", matching the local count. `tagsQueryList:["Restoration"]` returned **500**.
- **Saved index:** topic → ID and hymn numbers, in `samples/topics.hymns.json`. The largest topics are Jesus Christ (156), praise (96), faith (77) and love (70).
- **Messy names:** capitalisation varies ("Restoration" vs "faith"), and there are near-duplicates ("Restoration" 28 vs "Restoration of the Church" 1).
- **Printed index:** the printed hymnbook has its own Topics index. The site's tags may not match it, and that hasn't been checked.

The same response also lists authors (218), composers (208), arrangers (13), voicings (7), ensemble types, difficulty, category and instrumentation for *Hymns* (1985).

## 5. Gotchas

- **Duplicate titles:** some hymns appear twice, e.g. "An Angel from on High" as #13 and #328. The 300s in *Hymns* (1985) are the men's and women's arrangements. Decide whether they are separate records.
- **Shared song pages:** a song slug can belong to several books or collections, so pass `crumbs=<book>` when the book matters.
- **Song numbers are strings.** Don't assume they're integers.
- **Lyrics are HTML:** `verseBody` can contain `<ruby>` markup in some languages (the site's helpers strip it), and the `data-aid` IDs differ between the two APIs.
- **Proxy HEAD:** `proxyldscdn` returns 403 for HEAD, so use GET with a byte range to probe.

## 6. Open questions for the goal

1. **Which books and languages?** All three books, or *Hymns* (1985) first? English only, or all languages?
2. **Store media or links?** MP3/PDF/MIDI/MXL can be stored as URLs or downloaded. Licensing hasn't been checked. Image assets carry an `ipCode` (e.g. "IRI owned. All uses permitted."), but songs don't show an equivalent field.
3. **How to model the scripture links?** `song.scriptures[].linkUrl` uses study paths. Map them to the scriptures corpus's verse IDs so hymn↔verse lookups work both ways.
4. **What about the duplicates?** Merge or keep #13 and #328 separately (§5)?
5. **Which API?** Re-check the Brightspot flag (§2.2) right before building.

## 7. Re-gathering

```bash
B=https://www.churchofjesuschrist.org/media/music
curl -s "$B/api?type=songBookData&lang=eng&identifier=hymns"
curl -s "$B/api?type=song&lang=eng&identifier=the-morning-breaks"
curl -s "$B/api?type=songLangs&identifier=the-morning-breaks"
curl -s "$B/api?type=collectionFilters&lang=eng&identifier=%5B%22hymns%22%5D"
F=$(python3 -c 'import json,urllib.parse;print(urllib.parse.quote(json.dumps({"lang":"eng","limit":500,"offset":0,"orderByKey":["songTitleSortKey"],"bookQueryList":["hymns"]},separators=(",",":"))))')
curl -s "$B/api?type=songsFilteredList&lang=eng&batchSize=20&identifier=$F"
```

- **Feature flags:** the site sends `POST https://config.ff.harness.io/api/1.0/client/auth` with the public key from `renderData.envData.HARNESS_SDK_TOKEN` and target `reactclientsdk`. It then reads `GET …/client/env/<env>/target/reactclientsdk/evaluations?cluster=<n>`, where `<env>` and `<n>` come from the returned token.
- **App source:** the bundle's source map is public at `/media/music/statics/build/lambda-react/<build>/client.js.map`. It contains the full TypeScript; read `services/CDAService`, `services/BSPService` and `services/MusicContentService`. The build ID is `envData.BUILD_FILE_PATH`, which was `701210730b` on 2026-11-08. A copy of the recovered source is in `data/hymns-research/src/`.
