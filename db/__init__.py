# db.py
import os
import sqlite3
import time
from typing import Any, Sequence, List, Dict, Optional, Iterable
import logging

log = logging.getLogger("sci-db")

PARENT_DIR = os.path.dirname(os.path.dirname(__file__))  # sci/
CURRENT_DIR = os.path.join(PARENT_DIR, "db")
print(f"CURRENT_DIR: {CURRENT_DIR}")
CORE_DB_PATH = os.path.join(CURRENT_DIR, "core.52.db")
CONTENT_DB_PATH = os.path.join(CURRENT_DIR, "content.52.db")

DEFAULT_TIMEOUT = 5  # seconds

Row = Dict[str, Any]


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

    def _connect(self) -> sqlite3.Connection:
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Database not found: {self.path}")
        if self.read_only:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        else:
            conn = sqlite3.connect(self.path)

        _install_timeout(conn, self.timeout)
        return conn

    def select(self, query: str, params: Sequence[Any] = ()) -> List[Row]:
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e).lower():
                log.warning(f"Query timed out after {self.timeout}s: {query[:100]}...")
                return []
            raise
        finally:
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
content_db = Database(CONTENT_DB_PATH)
