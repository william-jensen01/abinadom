"""
Unit tests for server.py startup validation.

CORE-01: ChromaDB path resolution (absolute path, env override, missing collection guard)
CORE-02: Ollama health check (fails fast on connection error)
CORE-03: Collection warmup (all 4 collections loaded and counted)
"""
import os
from unittest.mock import MagicMock, patch

import chromadb
import pytest


# ---------------------------------------------------------------------------
# CORE-01: _resolve_chromadb_path
# ---------------------------------------------------------------------------


def test_chromadb_path_absolute():
    """_resolve_chromadb_path() returns an absolute path ending in data/chromadb."""
    from server import _resolve_chromadb_path

    result = _resolve_chromadb_path()
    assert os.path.isabs(result), f"Expected absolute path, got: {result}"
    assert result.endswith(os.path.join("data", "chromadb")), (
        f"Expected path ending in data/chromadb, got: {result}"
    )


def test_chromadb_path_env_override(monkeypatch, tmp_path):
    """_resolve_chromadb_path() respects CHROMADB_PATH env var."""
    monkeypatch.setenv("CHROMADB_PATH", str(tmp_path))

    from server import _resolve_chromadb_path

    result = _resolve_chromadb_path()
    assert result == str(tmp_path.resolve()), (
        f"Expected {str(tmp_path.resolve())}, got: {result}"
    )


# ---------------------------------------------------------------------------
# CORE-01: _load_collections — missing collection guard
# ---------------------------------------------------------------------------


def test_chromadb_missing_collection_exits(tmp_path):
    """_load_collections() raises SystemExit(1) when collections don't exist."""
    from server import _load_collections

    # Create an empty ChromaDB — no collections present
    client = chromadb.PersistentClient(path=str(tmp_path))

    with pytest.raises(SystemExit) as exc_info:
        _load_collections(client)

    assert exc_info.value.code == 1, f"Expected exit code 1, got: {exc_info.value.code}"


# ---------------------------------------------------------------------------
# CORE-02: _check_ollama
# ---------------------------------------------------------------------------


def test_ollama_failure_exits():
    """_check_ollama() raises SystemExit(1) when the embedding function throws."""
    from server import _check_ollama

    mock_ef = MagicMock(side_effect=Exception("connection refused"))
    mock_get_ef = MagicMock(return_value=mock_ef)

    with patch("server.get_embedding_function", mock_get_ef):
        with pytest.raises(SystemExit) as exc_info:
            _check_ollama()

    assert exc_info.value.code == 1, f"Expected exit code 1, got: {exc_info.value.code}"


# ---------------------------------------------------------------------------
# CORE-03: _load_collections — all 4 collections warmed
# ---------------------------------------------------------------------------


def test_all_collections_warmed():
    """_load_collections() returns a dict with exactly 4 collection keys."""
    from server import _load_collections

    mock_collection = MagicMock()
    mock_collection.count.return_value = 100

    mock_client = MagicMock(spec=chromadb.ClientAPI)
    mock_client.get_collection.return_value = mock_collection

    result = _load_collections(mock_client)

    assert set(result.keys()) == {"talks", "paragraphs", "citations", "footnotes"}, (
        f"Expected 4 collection keys, got: {set(result.keys())}"
    )
    assert len(result) == 4, f"Expected 4 collections, got {len(result)}"
    for key, col in result.items():
        assert col is mock_collection, f"Collection '{key}' should be the mock collection"
