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
