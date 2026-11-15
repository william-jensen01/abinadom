# db.py
import os
import sqlite3
import threading
import time
from typing import Any, Sequence, List, Dict, Optional, Iterable
import logging

log = logging.getLogger("sci-db")

PARENT_DIR = os.path.dirname(os.path.dirname(__file__))  # sci/
CURRENT_DIR = os.path.join(PARENT_DIR, "db")
# Directory holding core.<N>.db and content.<N>.db. Set SCI_DB_DIR to read them from
# elsewhere (a mounted data directory); unset, they sit in this package's own folder.
DB_DIR = os.environ.get("SCI_DB_DIR") or CURRENT_DIR
# SCI release number: core.<N>.db and content.<N>.db. Override with SCI_DB_VERSION.
SCI_DB_VERSION = os.environ.get("SCI_DB_VERSION", "55")
CORE_DB_PATH = os.path.join(DB_DIR, f"core.{SCI_DB_VERSION}.db")
CONTENT_DB_PATH = os.path.join(DB_DIR, f"content.{SCI_DB_VERSION}.db")
# scripture.db, built by scripts/fetch_scriptures.py and scripts/build_scriptures.py, sits beside them.
SCRIPTURE_DB_PATH = os.path.join(DB_DIR, "scripture.db")

DEFAULT_TIMEOUT = 5  # seconds

Row = Dict[str, Any]


class SchemaError(Exception):
    """Raised when database schema does not match expected structure."""
    pass


# Tables and key columns that the pipeline JOINs on (core DB)
EXPECTED_CORE_TABLES = {
    "talk": ["ID", "Corpus", "URL", "Title", "Date", "SpeakerID"],
    "speaker": ["ID", "GivenNames", "LastNames"],
    "conference": ["ID", "Description", "Year", "Annual"],
    "conf_session": ["ID", "Description", "ConferenceID"],
    "conference_talk": ["TalkID", "SessionID", "Sequence"],
    "citation": ["ID", "TalkID", "BookID", "Chapter", "Verses"],
    "book": ["ID", "Abbr", "FullName"],
    "talk_metadata": ["talk_id", "speaker_role_id", "uri_l", "uri_gc", "kicker", "talk_preview", "data_aid"],
}

# Tables and key columns for the content DB
EXPECTED_CONTENT_TABLES = {
    "talkbody": ["TalkID", "Text", "TextRaw"],
}


def validate_schema(conn: sqlite3.Connection, expected_tables: Dict[str, List[str]], db_name: str) -> None:
    """
    Validate that expected tables and columns exist. Raises SchemaError on mismatch.

    Args:
        conn: SQLite connection to validate
        expected_tables: Dict mapping table names to lists of required column names
        db_name: Human-readable name of the database (used in error messages)

    Raises:
        SchemaError: If a required table or column is missing
    """
    for table, required_cols in expected_tables.items():
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if not cols:
            raise SchemaError(f"{db_name}: table '{table}' not found")
        missing = [c for c in required_cols if c not in cols]
        if missing:
            raise SchemaError(f"{db_name}: table '{table}' missing columns: {missing}")


def _install_timeout(conn: sqlite3.Connection, timeout_sec: int = DEFAULT_TIMEOUT):
    force = os.environ.get("SCI_FORCE_TIMEOUT") == "1"
    start = time.time()
    deadline = start + timeout_sec

    def handler():
        if force or time.time() > deadline:
            return 1  # abort query
        return 0

    conn.set_progress_handler(handler, 1000)


class Database:
    def __init__(
        self, path: str, timeout: int = DEFAULT_TIMEOUT, read_only: bool = True
    ):
        self.path = path
        self.timeout = timeout
        self.read_only = read_only
        self._schema_validated = False
        self._expected_schema = None
        self._expected_schema_db_name = None
        # Read-only connections are reused per (process, thread). SQLite
        # connections must not cross a fork or a thread, so the cache is
        # thread-local and tagged with the pid that opened it.
        self._local = threading.local()

    def set_expected_schema(self, expected_tables: Dict[str, List[str]], db_name: str) -> None:
        """
        Set the schema expectation for this Database instance.
        Validation will run lazily on the first _connect() call.

        Args:
            expected_tables: Dict mapping table names to lists of required column names
            db_name: Human-readable name of the database (used in error messages)
        """
        self._expected_schema = expected_tables
        self._expected_schema_db_name = db_name

    def _connect(self) -> sqlite3.Connection:
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Database not found: {self.path}")
        if self.read_only:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        else:
            conn = sqlite3.connect(self.path)

        _install_timeout(conn, self.timeout)

        # Lazy schema validation: run once on first connection
        if self._expected_schema is not None and not self._schema_validated:
            validate_schema(conn, self._expected_schema, self._expected_schema_db_name)
            self._schema_validated = True

        return conn

    def _read_conn(self) -> sqlite3.Connection:
        """Return a cached read connection, opening one if needed.

        Opening a connection per query dominated short lookups in the
        pipeline, so read-only databases keep one per process and thread.
        Writable databases still get a fresh connection per call.

        The cached connection is dropped when the file at self.path is
        replaced (scripts/build.py swaps in rebuilt databases with
        os.replace), so long-running processes such as the MCP server read
        the new file instead of the deleted one.
        """
        if not self.read_only:
            return self._connect()
        conn = getattr(self._local, "conn", None)
        try:
            st = os.stat(self.path)
            file_id = (st.st_dev, st.st_ino)
        except FileNotFoundError:
            file_id = None  # _connect() raises the usual error
        same_process = getattr(self._local, "pid", None) == os.getpid()
        if conn is None or not same_process or getattr(self._local, "file_id", None) != file_id:
            if conn is not None and same_process:
                conn.close()
            self._local.conn = None
            conn = self._connect()
            self._local.conn = conn
            self._local.pid = os.getpid()
            self._local.file_id = file_id
        return conn

    def close(self) -> None:
        """Close this thread's cached read connection, if any."""
        conn = getattr(self._local, "conn", None)
        if conn is not None and getattr(self._local, "pid", None) == os.getpid():
            conn.close()
        self._local.conn = None

    def select(self, query: str, params: Sequence[Any] = ()) -> List[Row]:
        conn = self._read_conn()
        try:
            # Restart the timeout clock for this query (the connection may be reused)
            _install_timeout(conn, self.timeout)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e).lower():
                log.warning(f"Query timed out after {self.timeout}s: {query[:100]}...")
                return []
            raise
        finally:
            if not self.read_only:
                conn.close()

    def select_one(self, query: str, params: Sequence[Any] = ()) -> Optional[Row]:
        rows = self.select(query, params)
        return rows[0] if rows else None

    def scalar(
        self, query: str, params: Sequence[Any] = (), default: Any = None
    ) -> Any:
        row = self.select_one(query, params)
        return next(iter(row.values())) if row else default

    def execute(self, query: str, params: Sequence[Any] = ()) -> int:
        """
        Execute a write query (INSERT, UPDATE, DELETE).
        Returns the number of rows affected.

        Raises:
            RuntimeError: If database is in read-only mode
        """
        if self.read_only:
            raise RuntimeError("Cannot execute write operations on read-only database")

        conn = self._connect()
        try:
            cur = conn.execute(query, params)
            conn.commit()
            return cur.rowcount
        except sqlite3.OperationalError as e:
            conn.rollback()
            if "interrupted" in str(e).lower():
                log.warning(f"Query timed out after {self.timeout}s: {query[:100]}...")
                return 0
            raise
        finally:
            conn.close()

    def execute_many(self, query: str, params_list: Iterable[Sequence[Any]]) -> int:
        """
        Execute a write query multiple times with different parameters.
        Returns the total number of rows affected.

        Raises:
            RuntimeError: If database is in read-only mode
        """
        if self.read_only:
            raise RuntimeError("Cannot execute write operations on read-only database")

        conn = self._connect()
        try:
            cur = conn.executemany(query, params_list)
            conn.commit()
            return cur.rowcount
        except sqlite3.OperationalError as e:
            conn.rollback()
            if "interrupted" in str(e).lower():
                log.warning(f"Query timed out after {self.timeout}s")
                return 0
            raise
        finally:
            conn.close()


# Global shared instances
core_db = Database(CORE_DB_PATH)
core_db.set_expected_schema(EXPECTED_CORE_TABLES, os.path.basename(CORE_DB_PATH))
content_db = Database(CONTENT_DB_PATH)
content_db.set_expected_schema(EXPECTED_CONTENT_TABLES, os.path.basename(CONTENT_DB_PATH))
