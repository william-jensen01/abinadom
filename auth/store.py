"""
Auth storage layer — KeyStore ABC and SqliteKeyStore implementation.

KeyStore defines the abstract interface for token validation and usage logging.
SqliteKeyStore implements it using a local SQLite file (auth.db).

Design decisions (from 14-CONTEXT.md):
  D-01: Provider pattern — middleware depends on KeyStore, not directly on SQLite.
  D-05: Separate auth.db (not the pipeline database).
  D-06: Tokens stored as SHA-256 hashes only — raw token shown once at creation.
  D-10: Tokens generated via secrets.token_urlsafe(32) (OS CSPRNG).
  D-11: hmac.compare_digest for constant-time comparison (prevents timing attacks).
  Pitfall 4: New connection per operation — sqlite3.Connection is not thread-safe.
  Pitfall 5: Path resolved from __file__ (not cwd) — matches _resolve_chromadb_path pattern.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
import sqlite3


# ---------------------------------------------------------------------------
# KeyStore — abstract interface (D-01: provider pattern)
# ---------------------------------------------------------------------------


class KeyStore(ABC):
    """Abstract interface for bearer token storage and usage logging.

    Middleware and CLI depend on this interface, not on SqliteKeyStore directly.
    This allows the storage backend to be swapped (e.g., to Supabase) without
    touching the middleware or CLI layers.
    """

    @abstractmethod
    def verify_token(self, raw_token: str) -> str | None:
        """Return the key name if the token is valid, or None if invalid/unknown.

        Implementations must use constant-time comparison (D-11).
        """
        ...

    @abstractmethod
    def log_request(self, key_name: str, tool_name: str, timestamp: str) -> None:
        """Insert a usage log row for an authenticated request.

        Args:
            key_name: The name of the API key used (from verify_token).
            tool_name: The MCP method/tool name (e.g. "search", "tools/list").
            timestamp: ISO 8601 UTC timestamp string.
        """
        ...


# ---------------------------------------------------------------------------
# SqliteKeyStore — SQLite-backed implementation (D-02, D-05)
# ---------------------------------------------------------------------------


class SqliteKeyStore(KeyStore):
    """SQLite-backed key store.

    Each key management or logging operation opens a fresh connection to avoid
    SQLite thread-safety issues in async/uvicorn contexts (Pitfall 4).

    Schema:
      keys(name TEXT PRIMARY KEY, token_hash TEXT NOT NULL, created_at TEXT NOT NULL)
      usage_log(id INTEGER PK AUTOINCREMENT, key_name TEXT, tool_name TEXT, timestamp TEXT)
    """

    def __init__(self, db_path: str) -> None:
        """Initialize the store and create tables if they do not exist.

        Args:
            db_path: Absolute path to the auth.db SQLite file.
        """
        self._db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Open a new SQLite connection (one per operation — Pitfall 4)."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create the keys and usage_log tables if they do not exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS keys (
                    name TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_name TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_key ON usage_log(key_name)"
            )

    def create_key(self, name: str) -> str:
        """Generate a new API key, store its hash, and return the raw token.

        The raw token is shown once and is not stored — only the SHA-256 hash
        is persisted (D-06, D-10). Raises sqlite3.IntegrityError if name
        already exists (name is PRIMARY KEY).

        Args:
            name: Human-readable label for the key (e.g. "alice").

        Returns:
            The raw bearer token string. Caller must present this to end-users
            immediately; it cannot be retrieved later.
        """
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO keys (name, token_hash, created_at) VALUES (?, ?, ?)",
                (name, token_hash, created_at),
            )
        return token

    def verify_token(self, raw_token: str) -> str | None:
        """Validate a bearer token and return the associated key name.

        Hashes the incoming token and looks it up by hash (not by name) to
        avoid full table scan timing leaks. Uses hmac.compare_digest for
        constant-time final comparison (D-11).

        Args:
            raw_token: The raw bearer token from the Authorization header.

        Returns:
            The key name (str) if valid, or None if the token is unknown or
            invalid.
        """
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, token_hash FROM keys WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        # Constant-time comparison as final defense against timing attacks (D-11)
        if hmac.compare_digest(row["token_hash"], token_hash):
            return row["name"]
        return None

    def log_request(self, key_name: str, tool_name: str, timestamp: str) -> None:
        """Insert a usage log row for a successfully authenticated request (D-08, D-09).

        Args:
            key_name: The name of the API key (from verify_token).
            tool_name: The MCP method/tool name (e.g. "search", "tools/list").
            timestamp: ISO 8601 UTC timestamp string.
        """
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO usage_log (key_name, tool_name, timestamp) VALUES (?, ?, ?)",
                (key_name, tool_name, timestamp),
            )

    def revoke_key(self, name: str) -> bool:
        """Remove a key by name.

        Args:
            name: The key name to revoke.

        Returns:
            True if the key was found and deleted, False if it did not exist.
        """
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM keys WHERE name = ?", (name,))
        return cur.rowcount > 0

    def list_keys(self) -> list[dict]:
        """Return all key names and creation dates, ordered by created_at.

        Returns:
            List of dicts with 'name' and 'created_at' keys. Never includes
            token_hash — raw tokens are not retrievable after creation (D-06).
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, created_at FROM keys ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]
