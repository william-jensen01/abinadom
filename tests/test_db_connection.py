"""Unit tests for Database connection reuse (db/__init__.py)."""
import sqlite3
import threading
from unittest.mock import patch

import pytest

import db as db_module
from db import Database


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?)", [(1,), (2,)])
    conn.commit()
    conn.close()
    return str(path)


def test_read_only_reuses_one_connection(db_path):
    d = Database(db_path)
    with patch.object(d, "_connect", wraps=d._connect) as spy:
        for _ in range(5):
            assert d.select("SELECT id FROM t ORDER BY id") == [{"id": 1}, {"id": 2}]
    assert spy.call_count == 1


def test_reconnects_after_pid_change(db_path):
    """A forked child must not reuse the parent's connection."""
    d = Database(db_path)
    with patch.object(d, "_connect", wraps=d._connect) as spy:
        d.select("SELECT 1")
        with patch.object(db_module.os, "getpid", return_value=-1):
            d.select("SELECT 1")
    assert spy.call_count == 2


def test_each_thread_gets_its_own_connection(db_path):
    d = Database(db_path)
    d.select("SELECT 1")
    errors = []

    def worker():
        try:
            d.select("SELECT 1")
        except Exception as e:  # sqlite3.ProgrammingError if a connection crossed threads
            errors.append(e)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert errors == []


def test_timeout_still_applies_on_reused_connection(db_path, monkeypatch):
    d = Database(db_path)
    d.select("SELECT 1")  # open and cache the connection
    monkeypatch.setenv("SCI_FORCE_TIMEOUT", "1")
    # A forced timeout aborts the query; select() reports it as an empty result
    big = (
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c LIMIT 100000) "
        "SELECT count(*) FROM c"
    )
    assert d.select(big) == []


def test_close_forces_new_connection(db_path):
    d = Database(db_path)
    with patch.object(d, "_connect", wraps=d._connect) as spy:
        d.select("SELECT 1")
        d.close()
        d.select("SELECT 1")
    assert spy.call_count == 2


def test_reconnects_when_file_is_replaced(db_path, tmp_path):
    """A rebuilt database swapped in with os.replace (scripts/build.py) is picked up."""
    d = Database(db_path)
    assert d.select("SELECT id FROM t ORDER BY id") == [{"id": 1}, {"id": 2}]

    new_path = tmp_path / "new.db"
    conn = sqlite3.connect(new_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.execute("INSERT INTO t VALUES (3)")
    conn.commit()
    conn.close()
    db_module.os.replace(new_path, db_path)

    with patch.object(d, "_connect", wraps=d._connect) as spy:
        assert d.select("SELECT id FROM t ORDER BY id") == [{"id": 3}]
        assert d.select("SELECT id FROM t ORDER BY id") == [{"id": 3}]
    assert spy.call_count == 1


def test_missing_file_after_caching_raises(db_path):
    d = Database(db_path)
    d.select("SELECT 1")
    db_module.os.remove(db_path)
    with pytest.raises(FileNotFoundError):
        d.select("SELECT 1")


def test_writable_database_does_not_cache(db_path):
    d = Database(db_path, read_only=False)
    with patch.object(d, "_connect", wraps=d._connect) as spy:
        d.select("SELECT 1")
        d.select("SELECT 1")
    assert spy.call_count == 2
