"""Read-only access to scripture.db for the MCP server.

The same `db.Database` as core.db: a read-only connection, the 5s query timeout, and a slow query returns `[]`.
The file is `db.SCRIPTURE_DB_PATH` (scripture.db beside the talk dbs, in `SCI_DB_DIR`), looked up when
`open_scripture_db` is called (server startup).
"""
import logging
import os
from typing import Optional

import db
from db import DEFAULT_TIMEOUT, Database

log = logging.getLogger("sci-db")

# Tables and key columns the server reads (normalized layer)
EXPECTED_SCRIPTURE_TABLES = {
    "book": ["book_id", "uri", "name", "cite_abbr", "core_book_id", "num_chapters"],
    "chapter": ["chapter_id", "page_id", "book_id", "number", "title", "summary", "intro"],
    "verse": ["verse_id", "chapter_id", "book_id", "chapter", "verse", "text"],
    "footnote": ["footnote_id", "verse_id", "marker", "context", "text"],
    "footnote_ref": ["footnote_id", "seq", "category", "label", "target_uri"],
    "jst_verse": ["jst_verse_id", "book_id", "core_book_id", "chapter", "verse", "text"],
    "jst_passage_ref": ["passage_id", "rel", "target_book_id", "target_chapter"],
    "jst_passage_verse": ["passage_id", "jst_verse_id"],
    "build_meta": ["key", "value"],
}


def open_scripture_db(path: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> Optional[Database]:
    """A read-only Database on scripture.db (default: `db.SCRIPTURE_DB_PATH`), or None when it is missing, empty,
    or not a built store. Never raises: scripture is optional and the talk tools must not depend on it."""
    path = path or db.SCRIPTURE_DB_PATH
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        log.warning("scripture.db not found or empty at %s", path)
        return None
    database = Database(path, timeout=timeout)
    database.set_expected_schema(EXPECTED_SCRIPTURE_TABLES, os.path.basename(path))
    try:
        database.select("SELECT 1 FROM build_meta LIMIT 1")  # opens the connection and checks the schema
    except Exception as e:  # noqa: BLE001 — SchemaError, sqlite3.DatabaseError, ...
        log.warning("scripture.db at %s is not usable: %s", path, e)
        database.close()
        return None
    return database
