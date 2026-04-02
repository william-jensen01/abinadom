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


# ---------------------------------------------------------------------------
# CORE-05: _build_where_filter
# ---------------------------------------------------------------------------


class TestBuildWhereFilter:
    """Tests for _build_where_filter(year, season) -> dict | None."""

    def test_no_filters(self):
        """Returns None when year and season are both None."""
        from server import _build_where_filter

        assert _build_where_filter(year=None, season=None) is None

    def test_year_only(self):
        """Returns a single year filter dict when only year is provided."""
        from server import _build_where_filter

        assert _build_where_filter(year=2020, season=None) == {
            "conference_year": {"$eq": 2020}
        }

    def test_season_only(self):
        """Returns a single season filter dict when only season is provided."""
        from server import _build_where_filter

        assert _build_where_filter(year=None, season="April") == {
            "conference_month": {"$eq": "April"}
        }

    def test_year_and_season(self):
        """Returns an $and filter when both year and season are provided."""
        from server import _build_where_filter

        assert _build_where_filter(year=2020, season="April") == {
            "$and": [
                {"conference_year": {"$eq": 2020}},
                {"conference_month": {"$eq": "April"}},
            ]
        }


# ---------------------------------------------------------------------------
# CORE-04: _matches_speaker
# ---------------------------------------------------------------------------


class TestMatchesSpeaker:
    """Tests for _matches_speaker(stored, query) -> bool."""

    def test_substring_match(self):
        """Partial surname match returns True."""
        from server import _matches_speaker

        assert _matches_speaker("Jeffrey R. Holland", "Holland") is True

    def test_case_insensitive(self):
        """Lowercase query matches stored name case-insensitively."""
        from server import _matches_speaker

        assert _matches_speaker("Jeffrey R. Holland", "holland") is True

    def test_no_match(self):
        """Non-matching query returns False."""
        from server import _matches_speaker

        assert _matches_speaker("Jeffrey R. Holland", "Oaks") is False

    def test_full_name_match(self):
        """Full name query matches stored full name."""
        from server import _matches_speaker

        assert _matches_speaker("Jeffrey R. Holland", "Jeffrey R. Holland") is True

    def test_whitespace_stripped(self):
        """Query with leading/trailing whitespace is stripped before matching."""
        from server import _matches_speaker

        assert _matches_speaker("Jeffrey R. Holland", " Holland ") is True


# ---------------------------------------------------------------------------
# TOOL-03: _format_search_result
# ---------------------------------------------------------------------------


class TestFormatSearchResult:
    """Tests for _format_search_result(document, meta) -> dict."""

    _FULL_META = {
        "speaker_name": "Jeffrey R. Holland",
        "title": "A Talk Title",
        "conference_year": 2020,
        "conference_month": "April",
        "talk_id": 8820,
        # Pipeline-internal fields that must NOT leak through
        "paragraph_id": "p_123",
        "word_count": 42,
        "text": "raw",
        "text_raw": "raw",
        "source_type": "p",
        "speaker_id": 5,
        "conference_id": 99,
    }

    def test_returns_exactly_6_fields(self):
        """Result contains exactly the 6 public fields and no others."""
        from server import _format_search_result

        result = _format_search_result("Some paragraph text", self._FULL_META)
        assert set(result.keys()) == {
            "snippet",
            "speaker_name",
            "title",
            "conference_year",
            "conference_month",
            "talk_id",
        }

    def test_snippet_from_document(self):
        """snippet comes from the document parameter, not meta['text']."""
        from server import _format_search_result

        result = _format_search_result("Some paragraph text", self._FULL_META)
        assert result["snippet"] == "Some paragraph text"

    def test_talk_id_prefixed(self):
        """talk_id is returned as 'talk_<int>' string."""
        from server import _format_search_result

        result = _format_search_result("Some paragraph text", self._FULL_META)
        assert result["talk_id"] == "talk_8820"


# ---------------------------------------------------------------------------
# TOOL-04: _parse_talk_id
# ---------------------------------------------------------------------------


class TestParseTalkId:
    """Tests for _parse_talk_id(talk_id) -> int | None."""

    def test_prefixed(self):
        """'talk_8820' format returns 8820."""
        from server import _parse_talk_id

        assert _parse_talk_id("talk_8820") == 8820

    def test_bare_int(self):
        """'8820' bare integer format returns 8820."""
        from server import _parse_talk_id

        assert _parse_talk_id("8820") == 8820

    def test_invalid(self):
        """Non-numeric string returns None."""
        from server import _parse_talk_id

        assert _parse_talk_id("not_a_number") is None

    def test_whitespace(self):
        """Leading/trailing whitespace is handled correctly."""
        from server import _parse_talk_id

        assert _parse_talk_id(" talk_8820 ") == 8820
