# Scripture corpus audit

## Real fetch (I2)

- Date: 2026-11-02
- Command: `scripts/fetch_scriptures.py --db db/scripture.db` (resumed once with `--only-missing`)
- Pages stored (`raw_latest` rows): 1812 (6 TOC pages + 1806 linked pages, 0 failed)
- File size: 77,152,256 bytes (74 MiB)
- Duration: about 17 min 12 s (570 s timed-out first chunk + 462 s resume chunk)

Audit date 2026-11-02, from the full raw store `db/scripture.db` (`raw_latest`, lang `eng`, status 200, 1812 pages,
47,201 footnote entries). All counts below were computed from that store.

## Q1: JST link coverage

Answered after I7 (it needs the JST import from `core.55.db`).

## Q2: footnote categories (`data-note-category`)

A footnote's `text` is HTML: one `<p>` holding one or more `<span data-note-category="…">` segments (a single
footnote often has several, e.g. `tg` then `cross-ref`). Counts are spans over all pages. `referenceUris` entries
all have `type: "scripture-ref"`, whatever the category. "With href" means the span holds at least one `<a href>`.

| Category | Spans | With href | No href | Pages | Label | How to parse |
|---|---|---|---|---|---|---|
| `cross-ref` | 27,452 | 27,449 | 3 | 1571 | none (68 spans contain `JST`, 11 start with it; 2 start `IE`) | Refs from the hrefs. Targets are `ot nt bofm dc-testament pgp` and 44 into `jst` (see **Numbers for the I6 JST-storage decision**). The 3 spans without href are kept as text only. |
| `tg` | 18,616 | 18,615 | 1 | 1471 | `TG` | Target is a Topical Guide entry, `/study/scriptures/tg/<slug>`. Store into `target_help`. Not fetched. |
| `trn` | 2,504 | 90 | 2,414 | 784 | `HEB` 1267, `GR` 1131, `IE` 12, `OR` 4 | Text is the translation note, kept as text. Hrefs in the body, when present, are inline refs (81 `ot`, 8 `nt`, 4 `bofm`, 1 `pgp`). |
| `or` | 1,300 | 77 | 1,223 | 566 | `OR` | Alternate-reading text, kept as text. Inline hrefs (83 `ot`, 1 `nt`) become refs. |
| `ie` | 928 | 101 | 827 | 507 | `IE` 856, none 69, `B.C.` 3 | Explanatory text, kept as text. Inline hrefs (84 `ot`, 23 `bofm`, 11 `dc-testament`, 5 `pgp`, 3 `nt`) become refs. |
| `jst` | 558 | 178 | 380 | 258 | `JST` | See **`jst` parse rule** below. 171 spans link to the JST appendix; 387 (380 without href, 7 with a non-JST href) do not. Of those 387, 380 name a JST verse in their text and 7 name none. |
| `bd` | 41 | 41 | 0 | 40 | `BD` | Bible Dictionary entry, `/study/scriptures/bd/<slug>`. Store into `target_help`. |
| `triple-index` | 5 | 5 | 0 | 4 | none (`See also …`) | Link into `/study/scriptures/triple-index/<slug>` (D&C only). Store into `target_help`. |

**`jst` parse rule**

Only an href under `/scriptures/jst/` replaces text parsing. Every other href inside a `jst` span is an
ordinary inline ref, and the span's JST target still comes from its text.

- 380 spans have no href. 375 of them name a JST verse in the text (`JST Gen. 8:13 And it repented…`), which is
  parsed: the one exception to "never parse the label". The other 5 are the `<h1>` book-title notes (below).
- 171 spans link to the JST appendix (`/study/scriptures/jst/jst-gen/9?lang=eng&id=p4-p6#p4`, text
  `JST Gen. 9:4–6 (Appendix)`). The target is the href range and focus, not the text.
- 7 spans have hrefs that do not point into `/scriptures/jst/`. Each href is an ordinary inline ref:
  - `nt/rev/2` `note1_a`, `nt/heb/9` `note15_c` and `note16_c`, `nt/1-cor/14` `note2_a`: same-chapter refs
    (`vv. 1, 8, 12, and 18`, and so on) inside a "(Note: JST uses … in every instance …)" remark. The text
    still names the JST verse (`JST Rev. 2:1`, `JST Heb. 9:15`, `JST Heb. 9:16`, `JST 1 Cor. 14:2`).
  - `nt/matt/5` `note22_b`: the href goes to `bofm/3-ne/12` (`3 Ne. 12:22`). The text names `JST Matt. 5:24`.
  - `nt/matt/24` `note3_b` and `nt/mark/13` `note1_a`: href into `pgp/js-m/1`; the text names no JST verse (below).

For all 171 appendix-linked spans, the range in the text (`JST 1 Cor. 7:29–33, 38`) equals the href's `id=` range,
so text and href agree wherever both exist.

**`jst` spans that name no JST verse**

7 `jst` spans name no JST chapter and verse, so they cannot resolve to a `jst_verse` row by reference:

| Page | Key | Href | Text (start) |
|---|---|---|---|
| `ot/song/1` | `note` | none | "The JST manuscript states that “the Songs of Solomon are not inspired writings.”" |
| `nt/matt/1` | `note` | none | "JST entitles this book “The Testimony of St. Matthew.”" |
| `nt/mark/1` | `note` | none | "JST entitles this book “The Testimony of St. Mark.”" |
| `nt/luke/1` | `note` | none | "JST entitles this book “The Testimony of St. Luke.”" |
| `nt/john/1` | `note` | none | "JST entitles this book “The Testimony of St. John.”" |
| `nt/matt/24` | `note3_b` | `pgp/js-m/1#p4` | "JS—M 1:4 adds “or the destruction of the wicked, which is the end of the world.”" |
| `nt/mark/13` | `note1_a` | `pgp/js-m/1` | "The text of JST Mark 13 is the same as JST Matthew 24. See Pearl of Great Price, JS—M." |

The first 5 are the `<h1>` book-title notes (see Contradicts spec, item 1). How these 7 are stored is decided at
I6, together with the open JST-storage question in PROGRESS.md Blockers.

**Numbers for the I6 JST-storage decision**

Method for all of these: footnote `text` split into `<span data-note-category>` segments over `raw_latest` (lang `eng`,
status 200); a "JST href" is an `<a href>` containing `/scriptures/jst/`. Counts include repeats unless "distinct" is given.

- (a) **JST verses named by `jst` spans: 941** (911 distinct). Via JST href: 171 spans, **532** verses (513 distinct).
  Via text: 380 spans (375 without href, 5 with a non-JST href), **409** verses (398 distinct; 26 of them are ranges). The 7 spans above add 0.
  Method: href spans expand the `id=` list (`p29-p33%2Cp38` gives 29..33, 38); text spans expand the leading
  `JST <book> <ch>:<verses>` (`–` ranges and `,` lists). The two sets do not overlap (911 = 513 + 398).
  A naive "first `\d+:\d+` in the text" count gives 942, because it also takes
  `JS—M 1:4` from `nt/matt/24` `note3_b`, which is a Pearl of Great Price verse, not a JST verse.
- (b) **`cross-ref` spans with a JST href: 44**, one JST href each. 43 carry an `id=` range and name **242** JST verses
  (153 distinct, all of them also named by a `jst` span's JST href); 1 (`dc/45` `note60_a`) links to
  `jst/introduction` with no range. Method: expand each JST href's `id=` as in (a).
- (c) **`cross-ref` spans that start with "JST" but have no JST href: 4**, naming 5 JST verses in text:
  `bofm/1-ne/21` `note24_a` (JST Isa. 49:25, no href), `dc/49` `note21_a` (JST Gen. 9:11, no href),
  `bofm/3-ne/13` `note12_a` (JST Matt. 6:14, href to KJV `matt/6#p13`), `dc/6` `note6_a` (JST Matt. 6:38 and
  JST Luke 12:34, hrefs to KJV `matt/6#p33` and `luke/12#p31`). Method: span text, left-trimmed, starts with `JST`
  (11 spans) minus those with a JST href (7). More broadly, 25 `cross-ref` spans mention `JST` somewhere without a JST
  href; most read "JST X (X note a)" and link to the KJV verse that carries the `jst` note.
- (d) **Appendix passages: 143** `<h2>` headings ("JST, Genesis 9:4–6. Compare …") on 108 of the 109 appendix pages
  (`jst/introduction` has none). 142 hold verse paragraphs, **518** in all (518 distinct). In every one the heading range
  equals the paragraph numbers. `jst-gen/1-8` has no verses (it points to Moses). All 513 distinct verses named by
  `jst` spans' JST hrefs are among the 518; 5 passage verses are named by no `jst` span.
  **"Compare" links: 165** `<a href>` after the word "Compare" in the 143 headings (128 headings have one, 15 have
  more): `nt` 117, `ot` 40, `dc-testament` 3, `jst` 3 ("see also JST, …"), `bofm` 2. 163 carry `id=` and name 501
  verses; 2 do not (`jst-gen/1-8`: `span=1%3A1-6%3A13`; `jst-matt/18`: `moro/8`, whole chapter). Method: split each
  appendix body at `<h2`; count `<p class="verse…" id="pN">` per chunk; take hrefs in the heading text after "Compare".

Other footnote notes:

- Not in the spec's list: `or`, `jst`, `bd`, `triple-index`. The spec (§2) named `cross-ref`, `tg`, `trn`, `ie`. No `gs`, `alt`,
  `hebrew` or `greek` category exists; Hebrew/Greek notes are `trn` with a `HEB`/`GR` label.
- One footnote has no `data-note-category` at all: `/scriptures/dc-testament/chron-order` `figure1_note_asterisk`
  (text "At or near place specified"), a table note on the chronology page. It is stored as a `footnote` row
  with no `footnote_ref` rows (it has no `referenceUris`) and `verse_id` NULL (see Contradicts spec below).
- Href shape for scripture refs: `/study/scriptures/<volume>/<book>/<chapter>?lang=eng&id=p2#p2`, where `id` can be
  a range (`p9-p11`) or a list (`p18%2Cp20-p21`). Same-chapter short refs (`v. 8`, `vv. 18, 20–21`) are hrefs too.

## Q3: page kinds, TOC `data-content-type`, `<p class>`

**TOC `data-content-type`**

The six TOC pages (`ot nt bofm dc-testament pgp jst`) hold 1,806 links (969 + 284 + 259 + 145 + 23 + 126), with no
duplicates. That equals the 1812 stored pages minus the 6 TOCs. Attribute counts over the TOCs:

| `data-content-type` | Count | Meaning |
|---|---|---|
| `chapter` | 1,736 | A page link (1,709 direct links) or a wrapper `<li>` around a sub-list (27, no link of its own). Covers verse chapters, D&C sections, front matter, Official Declarations, facsimiles and all JST appendix pages. |
| `book` | 92 | A book group heading (OT 38, NT 23, BoM 10, D&C 2, PGP 2, JST 17). No link. |
| `table-of-contents` | 92 | The link to the book's own chapter list, `<book>/_contents`. |
| `title-page` | 5 | The volume title page (`ot nt bofm dc-testament pgp`; the JST TOC has none). |

The spec says "five volume TOCs". There are six: the JST appendix TOC is the extra one (per GOAL.md it is fetched with the rest).

**Page kinds in the store**

`data-content-type` does not separate the document kinds, so the kind is derived from the URI and the body. Rule
order for the parser: 3-segment URI is a volume TOC; last segment `_contents` is a book TOC; volume `jst` is a JST appendix
page; `/od/` is a declaration; `/fac-` is a facsimile; last segment not numeric (or `title-page`) is front matter;
numeric under `dc-testament` is a section; the rest are chapters.

| Kind (`page.kind`) | Pages | `ScriptureChapters` object? | Notes |
|---|---|---|---|
| `chapter` | 1,444 (OT 929, NT 260, BoM 239, PGP 16) | **Yes** | Verses, `title-number`, `study-summary`, footnotes. 3 OT pages (`song/3`, `song/6`, `song/7`) have verses but no footnotes. |
| `section` | 138 | **Yes** | D&C sections 1 to 138. All carry `study-intro`; 136 carry `study-summary` (`dc/116` and `dc/120` do not). |
| `declaration` | 2 (`od/1`, `od/2`) | **Yes** | No verses; classes `office salutation signature closing study-intro title-number`. Neither has footnotes. |
| `facsimile` | 3 (`pgp/abr/fac-1..3`) | **Yes** | No verses, no footnotes; image plus explanation text (`title`, `subtitle`). |
| `front_matter` | 18 (OT 2, NT 1, BoM 10, D&C 3, PGP 2) | **Yes** | Title pages (5), OT dedication, BoM title/introduction/witnesses/Joseph Smith/explanation/illustrations/pronunciation/reference, D&C introduction and chronological order, PGP introduction. No verses. Only `dc-testament/chron-order` has a footnote (the uncategorised table note). |
| `jst_appendix` | 109 | **No** | `/scriptures/jst/jst-<book>/<chapter>`, `jst/introduction` and `jst/jst-gen/1-8` (a pointer to Moses, `study-intro` only). Parsed, not raw-only: each gets a `page` row (kind `jst_appendix`), and its passages and "Compare" links (passage to KJV range) go into the appendix-link table (e.g. `jst_passage`). 108 have verse-class paragraphs, but they are appendix passages used for JST links (Q1), not canonical text: no `chapter` rows, no `verse` rows. None has footnotes. |
| `book_toc` | 92 | **No** | `<book>/_contents`: a link list of chapters (OT 38, NT 23, BoM 10, D&C 2, PGP 2, JST 17). Parsed into a `page` row (kind `book_toc`) and used for TOC-derived `book.num_chapters` and to fail the build on missing pages. No `chapter` row. |
| `volume_toc` | 6 | **No** | The volume tables of contents the fetch started from. Parsed into a `page` row (kind `volume_toc`) and used for `volume`/`book` order and the missing-page check. No `chapter` row. |

`ScriptureChapters` objects: 1,444 + 138 + 2 + 3 + 18 = **1,605**, one per `chapter` row. The other 207 pages
(109 + 92 + 6) get `page` rows but no `chapter` row and no `ScriptureChapters` object, so SCR-02's
`>= COUNT(chapter)` stays exact. Total 1,812.
This reads spec §6 ("one object per chapter/section/document page", declarations and front matter included). It means
SCR-02's "`ScriptureChapters` count = chapter pages" must be checked against 1,605 (all non-JST document pages), not against the
1,444 chapters alone. Kinds beyond the spec's list (`chapter|section|front_matter|declaration|facsimile`): `jst_appendix`,
`book_toc`, `volume_toc`.

**`<p class>` values seen**

Exact `class` attribute of every `<p class="…">` in page bodies (TOC pages included), with counts. Paragraphs
inside footnotes carry no class.

| `<p class>` | Count | First seen | Where / use |
|---|---|---|---|
| `verse` | 42,514 | `ot/gen/1` | A verse. Has `data-aid`, `id="pN"` and `<span class="verse-number">`. |
| `title` | 3,601 | `ot` (TOC) | TOC item titles (1,928 in the six TOCs) and page headings in pages (1,673, e.g. `bofm/pronunciation`, `pgp/abr/fac-*`, JST appendix). |
| `description` | 3,272 | `ot` (TOC) | TOC item descriptions. |
| `title-number` | 1,584 | `ot/gen/1` | "Chapter 1" label in the page header; also on `od/1`, `od/2`. |
| `study-summary` | 1,577 | `ot/gen/1` | Chapter/section summary (1,441 chapters, 136 sections). |
| `study-intro` | 304 | `bofm/mosiah/9` | Header text: D&C 140, JST appendix 145, BoM 16, PGP 3 (section headings, book intros, `od/*`, `jst-gen/1-8`). |
| `label` | 249 | `dc-testament/chron-order` | Chronological-order table cells (all in that one page). |
| `entry` | 246 | `bofm/reference` | Reference-guide entries (all in that one page). |
| `intro` | 140 | `ot/dedication` | Intro paragraphs: OT 117, BoM 23. |
| `usx-cd` | 27 | `ot/ps/119` | Summary-style paragraph (OT 22, PGP 5) inside a chapter body, on `ot/ps/119` and `pgp/js-h/1`. |
| `subtitle` | 23 | `ot/dedication` | Subtitles on title pages, facsimiles, Moses/Abr/1 Ne./1-2 Sam./1-2 Kgs first chapters. |
| `usx-qa` | 22 | `ot/ps/119` | Psalm 119 Hebrew-letter headings (`Aleph`, ...). Only on that page. |
| `signature` | 20 | `bofm/three` | Signatures: BoM witnesses 11, D&C 8 (`dc/102`, `127`, `128`, `od/1`, `od/2`), PGP 1 (`a-of-f/1`). |
| `closing` | 19 | `ot/mal/4` | Closing line: NT 15 (epistle endings), BoM 2, OT 1, D&C 1 (`od/2`). |
| `verse contains-line digits-3` | 3 | `dc-testament/dc/84` | **A verse with extra classes** (D&C 84). Still a verse: match class tokens, not the exact string `verse`. |
| `office` | 3 | `dc-testament/dc/102` | Church office line (`dc/102`, `od/1`, `od/2`). |
| `salutation` | 3 | `dc-testament/od/1` | Salutation (`od/1` once, `od/2` twice). |
| `short-navigation` | 2 | `dc-testament` (TOC) | TOC book heading short label. |
| `wide-ellipse` | 2 | `pgp/js-h/1` | Typographic ellipsis separator paragraph. |
| `verse contains-line digits-2` | 1 | `dc-testament/dc/84` | Same as above, with a 2-digit verse number. |

Build consequence: a verse paragraph is any `<p>` whose class tokens include `verse`. An exact `class="verse"` match
would drop 4 verses in D&C 84 (3 `digits-3`, 1 `digits-2`).

**Chapter summary fallback**

Five pages with verses have no `study-summary` paragraph. `chapter.summary` comes from the first match, in this order:

1. `study-summary` (1,577 pages).
2. `study-intro`: `dc/116` and `dc/120` (the section heading is the only header text).
3. `usx-cd` paragraphs joined in order: `ot/ps/119` (22, one per Hebrew-letter stanza) and `pgp/js-h/1` (5, spread
   through the chapter). They are inline summaries, not verses.
4. Nothing: `pgp/a-of-f/1` has only `title-number`, `verse` and `signature`. Its summary is empty (NULL), so
   `get_verse` returns an empty `chapter_summary` and the `ScriptureChapters` vector uses the page title
   ("The Articles of Faith").

**Contradicts spec**

Three findings contradict the spec. All are logged under Blockers in PROGRESS.md; 1 and 2 have a planned resolution that does not stop the run, 3 is an open question.

1. **9 footnotes are not on a verse.** Spec §2 says footnotes are keyed `note{verse}_{letter}` with `pid` = the verse's
   `data-aid`, and §10 says every `footnote.verse_id` resolves. These 9 have other keys, and their `pid` is the
   `data-aid` of a heading, closing line or table paragraph. None has `referenceUris`.

   | Page | Key | Marker | Anchored on | Text (start) |
   |---|---|---|---|---|
   | `ot/song/1` | `note` | (empty) | `<h1>` book title | "Note: The JST manuscript states that “the Songs of Solomon are not inspired writ…" |
   | `nt/matt/1` | `note` | (empty) | `<h1>` book title | "Title: JST entitles this book “The Testimony of St. Matthew.”" |
   | `nt/mark/1` | `note` | (empty) | `<h1>` book title | "Title: JST entitles this book “The Testimony of St. Mark.”" |
   | `nt/luke/1` | `note` | (empty) | `<h1>` book title | "Title: JST entitles this book “The Testimony of St. Luke.”" |
   | `nt/john/1` | `note` | (empty) | `<h1>` book title | "Title: JST entitles this book “The Testimony of St. John.”" |
   | `ot/mal/4` | `note_asterisk` | `*` | `<p class="closing">` | "IE The end of the books of the prophets of the Old Testament." |
   | `nt/1-thes/5` | `note_asterisk` | `*` | `<p class="closing">` | "More recent scholarship concludes that 1 and 2 Thes. were most likely written fr…" |
   | `nt/2-thes/3` | `note_asterisk` | `*` | `<p class="closing">` | same opening as `1-thes/5` |
   | `dc-testament/chron-order` | `figure1_note_asterisk` | `*` | table `<p id="figure1_p24">` | "At or near place specified" (no category) |

   Planned resolution: store them as `footnote` rows with **`footnote.verse_id` NULL** (`note_key` as given, `letter`
   NULL), because GOAL.md says each page's footnotes equal its `content.footnotes`. The §10 "every `verse_id` resolves"
   check applies to footnotes whose `pid` is a verse `data-aid`. The locked check `test_build_full.py` already counts
   only `verse_id IS NOT NULL`.

2. **D&C 84 verse paragraphs with compound classes.** Spec §2 and §10 say verses are `<p class="verse">`. In
   `dc-testament/dc/84`, four verses carry extra classes:

   | Verse | `class` |
   |---|---|
   | 84:99 | `verse contains-line digits-2` |
   | 84:100 | `verse contains-line digits-3` |
   | 84:101 | `verse contains-line digits-3` |
   | 84:102 | `verse contains-line digits-3` |

   Planned resolution: a verse is any `<p>` whose class tokens include `verse`. An exact `class="verse"` match would
   leave D&C 84 as 1..98, 103..120 and break the 1..N check. The locked checks `test_build_full.py:55` and `:69`
   match the exact string; that is logged as a Blocker for the user.

3. **Where appendix passages go.** Spec §5.2.2 puts JST appendix passages into `footnote_ref` (`category='jst'`), but GOAL.md
   puts appendix "Compare" links in a separate table (e.g. `jst_passage`). See the PROGRESS.md Blockers question on JST link storage.

The rest extends the spec without disagreeing with it: the category list (§2) gains four (`or`, `jst`, `bd`,
`triple-index`); there are six TOCs, not five (the JST TOC, which GOAL.md adds); and 171 of 558 `jst` spans link to
the appendix instead of being hrefless (GOAL.md already records this).
