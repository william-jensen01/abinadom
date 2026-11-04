-- scripture.db raw layer (SPEC-v2 §4.1). Written only by scripts/fetch_scriptures.py, append-only.
CREATE TABLE IF NOT EXISTS raw_page (
  uri           TEXT NOT NULL,        -- "/scriptures/bofm/alma/32"
  lang          TEXT NOT NULL,        -- "eng"
  fetched_at    TEXT NOT NULL,        -- ISO-8601 UTC
  content_hash  TEXT NOT NULL,        -- sha256 of the normalized response JSON
  status        INTEGER NOT NULL,     -- HTTP status
  json          TEXT NOT NULL,        -- the response, unmodified
  PRIMARY KEY (uri, lang, content_hash)
);

-- newest row per (uri, lang)
CREATE VIEW IF NOT EXISTS raw_latest AS
SELECT r.*
FROM raw_page r
WHERE r.rowid = (
  SELECT r2.rowid FROM raw_page r2
  WHERE r2.uri = r.uri AND r2.lang = r.lang
  ORDER BY r2.fetched_at DESC, r2.rowid DESC
  LIMIT 1
);

-- ==== normalized layer ====
-- scripture.db normalized layer (SPEC-v2 §4.2). Written only by scripts/build_scriptures.py, which
-- drops and recreates every table below in one transaction. scripts/fetch_scriptures.py reads only the
-- raw layer above (everything before the marker line).

CREATE TABLE volume (
  volume_id   INTEGER PRIMARY KEY,
  uri         TEXT NOT NULL UNIQUE,    -- "/scriptures/bofm"
  title       TEXT NOT NULL,
  abbr        TEXT,
  sort        INTEGER NOT NULL
);

CREATE TABLE book (
  book_id       INTEGER PRIMARY KEY,
  volume_id     INTEGER NOT NULL REFERENCES volume(volume_id),
  uri           TEXT NOT NULL UNIQUE,  -- "/scriptures/bofm/alma"
  name          TEXT NOT NULL,
  abbr          TEXT,
  cite_abbr     TEXT,                  -- "1 Ne."
  sort          INTEGER NOT NULL,
  num_chapters  INTEGER,               -- TOC-derived: the pages the book's _contents page lists (fac-N links
                                       -- count toward abr/fac); a book with no _contents page (one-chapter
                                       -- books): its chapter links in the volume TOC
  core_book_id  INTEGER                -- core.db book.ID
);

CREATE TABLE page (
  page_id  INTEGER PRIMARY KEY,
  uri      TEXT NOT NULL UNIQUE,
  book_id  INTEGER REFERENCES book(book_id),
  kind     TEXT NOT NULL,              -- chapter|section|front_matter|declaration|facsimile|jst_appendix|book_toc|volume_toc
  title    TEXT,
  sort     INTEGER NOT NULL
);

CREATE TABLE chapter (
  chapter_id    INTEGER PRIMARY KEY,
  page_id       INTEGER NOT NULL UNIQUE REFERENCES page(page_id),
  book_id       INTEGER REFERENCES book(book_id),
  number        INTEGER,
  title         TEXT,
  summary       TEXT,
  intro         TEXT,
  summary_html  TEXT,
  intro_html    TEXT
);

CREATE TABLE verse (
  verse_id     INTEGER PRIMARY KEY,
  chapter_id   INTEGER NOT NULL REFERENCES chapter(chapter_id),
  book_id      INTEGER REFERENCES book(book_id),
  chapter      INTEGER,                -- chapter number
  verse        INTEGER NOT NULL,
  aid          TEXT NOT NULL,          -- data-aid
  pid_html_id  TEXT NOT NULL,          -- html id, "p32"
  text         TEXT NOT NULL,
  text_html    TEXT NOT NULL,
  UNIQUE (chapter_id, verse)
);

CREATE TABLE jst_verse (               -- every core.db J/F row, in JST numbering (extractors/scripture_jst.py)
  jst_verse_id  INTEGER PRIMARY KEY,
  core_id       INTEGER,               -- core.db scripture.ID
  book_id       INTEGER,               -- the KJV book of the same name (book.core_book_id = core.db BookID);
                                       -- NULL when the build has no such book row
  chapter       INTEGER,               -- JST chapter
  verse         INTEGER,               -- JST verse
  source_flag   TEXT,                  -- F = in the Church edition, J = rest of the Inspired Version
  text          TEXT                   -- core.db text, decoded, unchanged
);

CREATE TABLE jst_passage (             -- one JST appendix passage (a <section> with a "JST, Book C:V." heading)
  passage_id     INTEGER PRIMARY KEY,
  page_id        INTEGER NOT NULL REFERENCES page(page_id),   -- the /scriptures/jst/jst-gen/9 page
  seq            INTEGER NOT NULL,     -- order on the page
  section_id     TEXT,                 -- html id of the section, "sec_gen_9_4_6"
  anchor_aid     TEXT,                 -- data-aid of the heading
  title          TEXT,                 -- "JST, Genesis 9:4–6."
  verse_spec     TEXT,                 -- "9:4–6" / "4:1, 5–6, 8–9" as printed after the book name
  book_id        INTEGER,              -- the KJV book of the same name; NULL when the build has no such book row
  core_book_id   INTEGER,              -- core.db BookID (jst_verse.book_id's key)
  chapter_start  INTEGER,              -- first JST chapter:verse of the passage
  verse_start    INTEGER,
  chapter_end    INTEGER,              -- last JST chapter:verse
  verse_end      INTEGER,
  intro          TEXT,                 -- the heading's study-intro, when it has one
  UNIQUE (page_id, seq)
);

CREATE TABLE jst_passage_verse (       -- the jst_verse rows a passage's heading names (JST numbering)
  passage_id    INTEGER NOT NULL REFERENCES jst_passage(passage_id),
  jst_verse_id  INTEGER NOT NULL REFERENCES jst_verse(jst_verse_id),
  PRIMARY KEY (passage_id, jst_verse_id)
);

CREATE TABLE jst_passage_ref (         -- the links in a passage heading. Never footnote_ref rows.
  passage_id          INTEGER NOT NULL REFERENCES jst_passage(passage_id),
  seq                 INTEGER NOT NULL,
  rel                 TEXT NOT NULL,   -- compare (the KJV range, after "Compare") | similar | see-also
  href                TEXT,
  label               TEXT,
  target_uri          TEXT,
  target_book_id      INTEGER REFERENCES book(book_id),
  target_chapter      INTEGER,
  target_chapter_end  INTEGER,         -- only for a `span=` href crossing chapters
  target_verse_start  INTEGER,
  target_verse_end    INTEGER,
  PRIMARY KEY (passage_id, seq)
);

CREATE TABLE footnote (
  footnote_id  INTEGER PRIMARY KEY,
  verse_id     INTEGER REFERENCES verse(verse_id),  -- NULL for the 9 notes anchored on a heading, closing line or table
  note_key     TEXT NOT NULL,          -- "note2_a" (also "note", "note_asterisk")
  marker       TEXT,                   -- "2a"
  letter       TEXT,
  context      TEXT,
  text         TEXT,
  text_html    TEXT,
  page_id      INTEGER NOT NULL REFERENCES page(page_id),  -- extra column: gives verse-less notes a page
  anchor_aid   TEXT                    -- extra column: the API's `pid`, the data-aid of the verse, heading, line
                                       -- or table cell the note is attached to (= verse.aid for verse notes)
);

CREATE TABLE footnote_ref (
  footnote_id          INTEGER NOT NULL REFERENCES footnote(footnote_id),
  seq                  INTEGER NOT NULL,
  category             TEXT NOT NULL,  -- data-note-category of the span the ref sits in (cross-ref, tg, bd, …),
                                       -- except: 'jst' only for a JST verse named by a `jst` span (its
                                       -- /scriptures/jst/ link, one row per verse, or its text, ref_type
                                       -- 'jst-note'); a `jst` span naming no JST verse gets no 'jst' row; any
                                       -- other link in a `jst` span is 'cross-ref'; a /scriptures/jst/ link in a
                                       -- `cross-ref` span stays 'cross-ref'
  ref_type             TEXT,           -- scripture-ref (from an <a href>, study helps too) or jst-note (a jst span's text)
  href                 TEXT,
  label                TEXT,
  target_uri           TEXT,
  target_book_id       INTEGER REFERENCES book(book_id),
  target_chapter       INTEGER,
  target_verse_start   INTEGER,
  target_verse_end     INTEGER,
  target_help          TEXT,           -- "tg/poor"
  target_jst_verse_id  INTEGER REFERENCES jst_verse(jst_verse_id),
  PRIMARY KEY (footnote_id, seq)
);

CREATE INDEX footnote_verse_idx ON footnote(verse_id);
CREATE INDEX footnote_ref_book_idx ON footnote_ref(target_book_id, target_chapter, target_verse_start);
CREATE INDEX verse_chapter_idx ON verse(book_id, chapter, verse);
CREATE INDEX jst_verse_ref_idx ON jst_verse(book_id, chapter, verse);
CREATE UNIQUE INDEX jst_verse_core_idx ON jst_verse(core_id);
CREATE INDEX jst_passage_ref_book_idx ON jst_passage_ref(target_book_id, target_chapter, target_verse_start);

CREATE TABLE build_meta (
  key    TEXT PRIMARY KEY,
  value  TEXT
);
