"""
Unit tests for server.py startup validation and MCP tool integration.

CORE-01: Weaviate client factory (env-var config, _validate_collections guard)
CORE-02: Embedding server health check (fails fast on connection error)
CORE-03: _validate_collections (all 4 collections present and non-empty)
CORE-05: _build_weaviate_filters — all 5 filter cases
TOOL-01/TOOL-02/TOOL-03: search tool integration
TOOL-04/TOOL-05: get_talk tool integration
TRANS-02: Health endpoint checks data["weaviate"]
OAUTH-01/OAUTH-02/OAUTH-03: dispatcher auth routing
"""
import asyncio
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# CORE-01: get_weaviate_client — env-var configuration
# ---------------------------------------------------------------------------


def test_weaviate_client_default_host(monkeypatch):
    """get_weaviate_client() uses localhost:8080:50051 when env vars are unset."""
    monkeypatch.delenv("WEAVIATE_HOST", raising=False)
    monkeypatch.delenv("WEAVIATE_PORT", raising=False)
    monkeypatch.delenv("WEAVIATE_GRPC_PORT", raising=False)

    with patch("weaviate.connect_to_local") as mock_connect:
        mock_connect.return_value = MagicMock()
        from config.weaviate_client import get_weaviate_client
        get_weaviate_client()
        mock_connect.assert_called_once_with(host="localhost", port=8080, grpc_port=50051)


def test_weaviate_client_env_override(monkeypatch):
    """get_weaviate_client() respects WEAVIATE_HOST, WEAVIATE_PORT, WEAVIATE_GRPC_PORT env vars."""
    monkeypatch.setenv("WEAVIATE_HOST", "weaviate.internal")
    monkeypatch.setenv("WEAVIATE_PORT", "9090")
    monkeypatch.setenv("WEAVIATE_GRPC_PORT", "50099")

    with patch("weaviate.connect_to_local") as mock_connect:
        mock_connect.return_value = MagicMock()
        from config.weaviate_client import get_weaviate_client
        get_weaviate_client()
        mock_connect.assert_called_once_with(host="weaviate.internal", port=9090, grpc_port=50099)


# ---------------------------------------------------------------------------
# CORE-03: _validate_collections
# ---------------------------------------------------------------------------


class TestValidateCollections:
    """Tests for _validate_collections(client) -> None."""

    def _make_client(self, exists_return=True, total_count=100):
        """Build a mock Weaviate client for _validate_collections."""
        mock_client = MagicMock()
        mock_client.collections.exists.return_value = exists_return
        # aggregate.over_all returns an object with total_count attribute
        agg_result = MagicMock()
        agg_result.total_count = total_count
        mock_client.collections.use.return_value.aggregate.over_all.return_value = agg_result
        return mock_client

    def test_missing_collection_exits(self):
        """_validate_collections() raises SystemExit(1) when a collection does not exist."""
        from server import _validate_collections

        mock_client = self._make_client(exists_return=False)

        with pytest.raises(SystemExit) as exc_info:
            _validate_collections(mock_client)

        assert exc_info.value.code == 1

    def test_zero_count_collection_exits(self):
        """_validate_collections() raises SystemExit(1) when a collection has 0 records."""
        from server import _validate_collections

        mock_client = self._make_client(exists_return=True, total_count=0)

        with pytest.raises(SystemExit) as exc_info:
            _validate_collections(mock_client)

        assert exc_info.value.code == 1

    def test_all_collections_valid_passes(self):
        """_validate_collections() completes without exception when all 4 collections are present and non-empty."""
        from server import _validate_collections

        mock_client = self._make_client(exists_return=True, total_count=100)

        # Should not raise
        _validate_collections(mock_client)

    def test_validates_exactly_4_collections(self):
        """_validate_collections() checks exactly 4 collection names."""
        from server import _validate_collections

        mock_client = self._make_client(exists_return=True, total_count=1)

        _validate_collections(mock_client)

        assert mock_client.collections.exists.call_count == 4


# ---------------------------------------------------------------------------
# CORE-02: _check_embedding
# ---------------------------------------------------------------------------


def test_embedding_failure_is_non_fatal():
    """_check_embedding() logs a warning but does not raise when the embedding server is unreachable."""
    from server import _check_embedding

    mock_ef = MagicMock(side_effect=Exception("connection refused"))
    mock_get_ef = MagicMock(return_value=mock_ef)

    with patch("server.get_embedding_function", mock_get_ef):
        # Should not raise — embedding server failure is non-fatal at startup
        _check_embedding()


# ---------------------------------------------------------------------------
# CORE-05: _build_weaviate_filters
# ---------------------------------------------------------------------------


class TestBuildWeaviateFilters:
    """Tests for _build_weaviate_filters(year, season, speaker) -> Filter | None."""

    def test_no_filters(self):
        """Returns None when all three params are None."""
        from server import _build_weaviate_filters

        assert _build_weaviate_filters(None, None, None) is None

    def test_year_only(self):
        """Returns a non-None filter when only year is provided."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(2020, None, None)
        assert result is not None

    def test_season_only(self):
        """Returns a non-None filter when only season is provided."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(None, "April", None)
        assert result is not None

    def test_speaker_only(self):
        """Returns a non-None filter when only speaker is provided."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(None, None, "Holland")
        assert result is not None

    def test_all_three(self):
        """Returns a non-None filter when all three params are provided."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(2020, "April", "Holland")
        assert result is not None

    # --- new keyword-only params ---

    def test_session_only(self):
        """Returns a non-None filter when only session is provided."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(None, None, None, session="Sun AM")
        assert result is not None

    def test_cites_scripture_true(self):
        """Returns a non-None filter when cites_scripture=True."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(None, None, None, cites_scripture=True)
        assert result is not None

    def test_cites_scripture_false(self):
        """Returns a non-None filter when cites_scripture=False (must use 'is not None' check)."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(None, None, None, cites_scripture=False)
        assert result is not None

    def test_year_from_only(self):
        """Returns a non-None filter when only year_from is provided."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(None, None, None, year_from=2010)
        assert result is not None

    def test_year_to_only(self):
        """Returns a non-None filter when only year_to is provided."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(None, None, None, year_to=2020)
        assert result is not None

    def test_year_range(self):
        """Returns a non-None filter when both year_from and year_to are provided."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(None, None, None, year_from=2010, year_to=2020)
        assert result is not None

    def test_all_new_params_combined(self):
        """Returns a non-None filter when all new keyword-only params are provided."""
        from server import _build_weaviate_filters

        result = _build_weaviate_filters(
            2020, "April", "Holland",
            session="Sun AM",
            cites_scripture=True,
            year_from=2015,
            year_to=2022,
        )
        assert result is not None

    def test_backward_compat_positional(self):
        """Positional 3-arg call with all None still returns None (backward compat)."""
        from server import _build_weaviate_filters

        assert _build_weaviate_filters(None, None, None) is None

    def test_no_new_params_defaults_to_none(self):
        """Calling with only old params and no new keyword args returns None when no conditions."""
        from server import _build_weaviate_filters

        assert _build_weaviate_filters(None, None, None) is None


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

    def test_relevance_and_score_type_added_when_passed(self):
        """relevance and score_type appear in result when passed; distance is absent."""
        from server import _format_search_result

        result = _format_search_result("text", self._FULL_META, relevance=0.9, score_type="bm25")
        assert result["relevance"] == 0.9
        assert result["score_type"] == "bm25"
        assert "distance" not in result

    def test_distance_added_when_passed(self):
        """distance appears in result only when explicitly passed."""
        from server import _format_search_result

        result = _format_search_result(
            "text", self._FULL_META,
            relevance=0.9, score_type="vector_certainty", distance=0.1,
        )
        assert "distance" in result
        assert result["distance"] == 0.1

    def test_no_optional_fields_without_args(self):
        """Without optional keyword args, result has exactly the 6 base fields."""
        from server import _format_search_result

        result = _format_search_result("text", self._FULL_META)
        assert "relevance" not in result
        assert "score_type" not in result
        assert "distance" not in result

    # --- snippet fallback ---

    def test_snippet_fallback_empty_document(self):
        """Empty string document falls back to meta title as snippet."""
        from server import _format_search_result

        result = _format_search_result("", self._FULL_META)
        assert result["snippet"] == self._FULL_META["title"]

    def test_snippet_fallback_whitespace_document(self):
        """Whitespace-only document falls back to meta title as snippet."""
        from server import _format_search_result

        result = _format_search_result("   ", self._FULL_META)
        assert result["snippet"] == self._FULL_META["title"]

    def test_snippet_not_overridden_when_document_present(self):
        """Non-empty document is used as snippet (title is NOT substituted)."""
        from server import _format_search_result

        result = _format_search_result("Some paragraph text", self._FULL_META)
        assert result["snippet"] == "Some paragraph text"

    # --- topics field ---

    def test_topics_included_when_present(self):
        """topics list is included in result when meta contains a non-empty list."""
        from server import _format_search_result

        meta = {**self._FULL_META, "topics": ["Grace", "Atonement"]}
        result = _format_search_result("text", meta)
        assert "topics" in result
        assert result["topics"] == ["Grace", "Atonement"]

    def test_topics_absent_when_missing_from_meta(self):
        """topics key is absent when meta does not contain 'topics'."""
        from server import _format_search_result

        result = _format_search_result("text", self._FULL_META)
        assert "topics" not in result

    def test_topics_absent_when_empty_list(self):
        """topics key is absent when meta['topics'] is an empty list."""
        from server import _format_search_result

        meta = {**self._FULL_META, "topics": []}
        result = _format_search_result("text", meta)
        assert "topics" not in result

    # --- citation_count field ---

    def test_citation_count_included_when_present(self):
        """citation_count is included as int when meta contains a non-None value."""
        from server import _format_search_result

        meta = {**self._FULL_META, "citation_count": 7}
        result = _format_search_result("text", meta)
        assert "citation_count" in result
        assert result["citation_count"] == 7

    def test_citation_count_absent_when_key_missing(self):
        """citation_count is absent when 'citation_count' key is not in meta."""
        from server import _format_search_result

        result = _format_search_result("text", self._FULL_META)
        assert "citation_count" not in result

    def test_citation_count_absent_when_none(self):
        """citation_count is absent when meta['citation_count'] is None."""
        from server import _format_search_result

        meta = {**self._FULL_META, "citation_count": None}
        result = _format_search_result("text", meta)
        assert "citation_count" not in result


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


# ---------------------------------------------------------------------------
# Test helpers for MCP tool integration tests
# ---------------------------------------------------------------------------


def _make_mock_ctx():
    """Build a mock Context whose lifespan_context is an AppContext with a mock Weaviate client."""
    from server import AppContext

    mock_client = MagicMock()
    app = AppContext(client=mock_client)
    ctx = MagicMock()
    ctx.lifespan_context = {"app": app}
    return ctx, mock_client


def _make_search_col(properties_list):
    """
    Build a mock Weaviate collection for search tool tests.

    Returns a mock collection where query.hybrid/bm25/near_vector/fetch_objects all
    return objects from properties_list, each with a .metadata stub carrying
    score=0.9, distance=0.1, and certainty=0.9 attributes.

    aggregate.over_all.return_value.total_count is set to len(properties_list) so
    total/has_more in the result envelope work correctly.
    """
    mock_col = MagicMock()
    mock_objects = []
    for props in properties_list:
        obj = MagicMock()
        obj.properties = props
        obj.metadata = MagicMock()
        obj.metadata.score = 0.9
        obj.metadata.distance = 0.1
        obj.metadata.certainty = 0.9
        mock_objects.append(obj)
    mock_col.query.hybrid.return_value.objects = mock_objects
    mock_col.query.bm25.return_value.objects = mock_objects
    mock_col.query.near_vector.return_value.objects = mock_objects
    mock_col.query.fetch_objects.return_value.objects = mock_objects
    mock_col.aggregate.over_all.return_value.total_count = len(properties_list)
    return mock_col


# ---------------------------------------------------------------------------
# TOOL-01/TOOL-02/TOOL-03: search tool
# ---------------------------------------------------------------------------


class TestSearchTool:
    """Integration tests for the search MCP tool."""

    _SINGLE_PROPS = {
        "speaker_name": "Jeffrey R. Holland",
        "title": "A Talk",
        "conference_year": 2020,
        "conference_month": "April",
        "talk_id": 8820,
        "text": "Some text",
        # Pipeline-internal fields — must NOT leak through
        "paragraph_id": "p1",
    }

    def _make_ctx_with_col(self, col_name="ConferenceTalkParagraphs", properties_list=None):
        """Create a ctx where app.client.collections.use(col_name) returns a search mock col."""
        if properties_list is None:
            properties_list = [self._SINGLE_PROPS]
        ctx, mock_client = _make_mock_ctx()
        mock_col = _make_search_col(properties_list)
        mock_client.collections.use.return_value = mock_col
        return ctx, mock_col

    def test_search_basic_query(self):
        """search with default alpha=0.7 calls hybrid and returns JSON with search_mode + results."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            result = asyncio.run(search(query="test query", ctx=ctx))

        parsed = json.loads(result)

        # Default alpha=0.7 → hybrid mode
        assert parsed["search_mode"] == "hybrid"
        assert "results" in parsed
        assert len(parsed["results"]) == 1

        result_item = parsed["results"][0]
        assert "snippet" in result_item
        assert "speaker_name" in result_item
        assert "talk_id" in result_item
        assert "paragraph_id" not in result_item
        assert result_item["score_type"] == "hybrid_fusion"

        mock_col.query.hybrid.assert_called_once()
        call_kwargs = mock_col.query.hybrid.call_args.kwargs
        assert "alpha" in call_kwargs

    def test_search_empty_results(self):
        """search with no matching results returns 'No results found.'"""
        from server import search

        ctx, mock_client = _make_mock_ctx()
        mock_col = MagicMock()
        mock_col.query.hybrid.return_value.objects = []
        mock_col.query.bm25.return_value.objects = []
        mock_col.query.near_vector.return_value.objects = []
        mock_client.collections.use.return_value = mock_col

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            result = asyncio.run(search(query="nothing matches", ctx=ctx))

        assert result == "No results found."

    def test_search_limit_clamped(self):
        """limit > 20 is clamped to 20 when calling hybrid (default alpha=0.7)."""
        from server import search

        ctx, mock_col_mock = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(query="test", limit=50, ctx=ctx))

        call_kwargs = mock_col_mock.query.hybrid.call_args.kwargs
        assert call_kwargs["limit"] == 20

    def test_search_invalid_collection(self):
        """search with unknown collection returns error message."""
        from server import search

        ctx, _ = _make_mock_ctx()
        result = asyncio.run(search(query="test", collection="nonexistent", ctx=ctx))

        assert "Unknown collection" in result

    def test_search_year_season_filter(self):
        """search with year=2020 and season='April' passes non-None filters to hybrid."""
        from server import search

        ctx, mock_col_mock = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(query="test", year=2020, season="April", ctx=ctx))

        call_kwargs = mock_col_mock.query.hybrid.call_args.kwargs
        assert call_kwargs.get("filters") is not None

    def test_search_speaker_filter_not_none(self):
        """search with speaker param passes non-None filters to hybrid (native Weaviate filter)."""
        from server import search

        ctx, mock_col_mock = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(query="grace", speaker="Holland", ctx=ctx))

        call_kwargs = mock_col_mock.query.hybrid.call_args.kwargs
        assert call_kwargs.get("filters") is not None

    # ------------------------------------------------------------------
    # New tests — alpha paths, fallback, empty query, grouping
    # ------------------------------------------------------------------

    def test_search_alpha_1_uses_near_vector(self):
        """alpha=1.0 uses near_vector and result includes distance + score_type='vector_certainty'."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            result = asyncio.run(search(query="test", alpha=1.0, ctx=ctx))

        parsed = json.loads(result)
        assert parsed["search_mode"] == "vector"
        assert "results" in parsed
        result_item = parsed["results"][0]
        assert result_item["score_type"] == "vector_certainty"
        assert "distance" in result_item
        mock_col.query.near_vector.assert_called_once()

    def test_search_alpha_0_uses_bm25(self):
        """alpha=0.0 uses bm25 (no embedding needed) and search_mode is 'keyword'."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        # No embedding patches — bm25 path skips embedding entirely
        result = asyncio.run(search(query="test", alpha=0.0, ctx=ctx))

        parsed = json.loads(result)
        assert parsed["search_mode"] == "keyword"
        assert parsed["results"][0]["score_type"] == "bm25"
        mock_col.query.bm25.assert_called_once()

    def test_search_embedding_down_fallback(self):
        """When the embedding call raises, search falls back to bm25 with search_mode 'keyword_only_embedding_unavailable'."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            # Embedding function raises on call
            mock_gef.return_value = MagicMock(side_effect=Exception("embedding server down"))
            result = asyncio.run(search(query="test", ctx=ctx))  # default alpha=0.7 → needs embedding

        parsed = json.loads(result)
        assert parsed["search_mode"] == "keyword_only_embedding_unavailable"
        mock_col.query.bm25.assert_called_once()

    def test_search_embeds_query_with_task_query(self):
        """search embeds the query via get_embedding_function(task="query") (search_query: prefix)."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(query="test query", ctx=ctx))

        assert mock_gef.call_args.kwargs["task"] == "query"

    def test_search_empty_query_with_filter_browse(self):
        """Empty/whitespace query with at least one filter uses fetch_objects and returns browse_filtered."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        result = asyncio.run(search(query="   ", year=2020, ctx=ctx))

        parsed = json.loads(result)
        assert parsed["search_mode"] == "browse_filtered"
        assert "results" in parsed
        mock_col.query.fetch_objects.assert_called_once()

    def test_search_empty_query_no_filter_error(self):
        """Empty query with no filters returns error string (no embed, no query)."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        result = asyncio.run(search(query="", ctx=ctx))

        assert "Provide a query" in result

    def test_search_group_by_talk_paragraphs(self):
        """group_by_talk=True on paragraphs returns grouped output with 'groups' key."""
        from server import search

        ctx, mock_client = _make_mock_ctx()
        mock_col = MagicMock()

        mock_para = MagicMock()
        mock_para.properties = {
            "speaker_name": "A. Speaker",
            "title": "A Talk",
            "conference_year": 2020,
            "conference_month": "April",
            "talk_id": 1234,
            "text": "Para text",
        }
        mock_para.metadata = MagicMock()
        mock_para.metadata.certainty = 0.85
        mock_para.metadata.distance = 0.15

        mock_group = MagicMock()
        mock_group.name = 1234
        mock_group.objects = [mock_para]

        # Grouping is routed through near_vector; weaviate returns .groups as a
        # dict {group_value: GroupObject}, and the group value is read from .name.
        mock_col.query.near_vector.return_value.groups = {"1234": mock_group}
        mock_col.query.near_vector.return_value.objects = []
        mock_col.aggregate.over_all.return_value.total_count = 1
        mock_client.collections.use.return_value = mock_col

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            result = asyncio.run(search(query="test", group_by_talk=True, ctx=ctx))

        parsed = json.loads(result)
        assert parsed["search_mode"] == "vector_grouped"
        assert "groups" in parsed
        assert len(parsed["groups"]) == 1
        assert parsed["groups"][0]["talk_id"] == "talk_1234"
        assert "paragraphs" in parsed["groups"][0]
        assert len(parsed["groups"][0]["paragraphs"]) == 1

    def test_search_group_by_talk_wrong_collection(self):
        """group_by_talk=True on a non-paragraphs collection returns an error string."""
        from server import search

        ctx, _ = _make_mock_ctx()

        result = asyncio.run(search(query="test", collection="talks", group_by_talk=True, ctx=ctx))

        assert "group_by_talk is only supported for the paragraphs collection" in result

    # ------------------------------------------------------------------
    # New tests — total/has_more, sort_by, query_properties, results_per_talk
    # ------------------------------------------------------------------

    def test_search_returns_total_and_has_more(self):
        """Result envelope contains 'total' and 'has_more' fields."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()
        # _make_search_col sets total_count = 1 and returns 1 object,
        # so has_more should be False (0 + 1 < 1 is False)
        mock_col.aggregate.over_all.return_value.total_count = 10

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            result = asyncio.run(search(query="test query", ctx=ctx))

        parsed = json.loads(result)
        assert "total" in parsed
        assert "has_more" in parsed
        assert isinstance(parsed["total"], int)
        assert isinstance(parsed["has_more"], bool)

    def test_search_has_more_true_when_more_results_exist(self):
        """has_more is True when total > offset + len(results)."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()
        # 1 result returned but total is 100 → has_more = True
        mock_col.aggregate.over_all.return_value.total_count = 100

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            result = asyncio.run(search(query="test query", ctx=ctx))

        parsed = json.loads(result)
        assert parsed["has_more"] is True
        assert parsed["total"] == 100

    def test_sort_by_date_desc_passes_sort_to_fetch_objects(self):
        """sort_by='date_desc' on empty query passes a sort argument to fetch_objects."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        result = asyncio.run(search(query="", sort_by="date_desc", ctx=ctx))

        parsed = json.loads(result)
        assert parsed["search_mode"] == "browse_filtered"
        call_kwargs = mock_col.query.fetch_objects.call_args.kwargs
        assert "sort" in call_kwargs

    def test_sort_by_allows_browse_without_filter(self):
        """sort_by alone (no filter) is enough to allow browse path without error."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        result = asyncio.run(search(query="", sort_by="date_asc", ctx=ctx))

        # Should return JSON, not the guard error string
        parsed = json.loads(result)
        assert parsed["search_mode"] == "browse_filtered"

    def test_sort_by_invalid_value_ignored(self):
        """Invalid sort_by value without a filter still returns the guard error."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        result = asyncio.run(search(query="", sort_by="invalid_value", ctx=ctx))

        assert "Provide a query" in result

    def test_sort_by_unsupported_collection_returns_message(self):
        """sort_by on a collection with no chronological field (citations) is rejected clearly, not crashed."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col(col_name="ConferenceTalkCitations")

        result = asyncio.run(
            search(query="", collection="citations", sort_by="date_desc", ctx=ctx)
        )

        assert "not supported for the 'citations' collection" in result
        # Must NOT have attempted a sorted fetch against a field the collection lacks
        mock_col.query.fetch_objects.assert_not_called()

    def test_sort_by_paragraphs_uses_conference_year(self):
        """sort_by on paragraphs sorts by conference_year (paragraphs have no talk_date)."""
        import server

        ctx, mock_col = self._make_ctx_with_col()  # default: paragraphs

        with patch("server.Sort.by_property", wraps=server.Sort.by_property) as spy:
            asyncio.run(server.search(query="", sort_by="date_desc", ctx=ctx))

        # sort_by on paragraphs must target conference_year, not talk_date
        assert spy.call_args is not None
        assert spy.call_args.args[0] == "conference_year"
        assert "sort" in mock_col.query.fetch_objects.call_args.kwargs

    def test_query_properties_passed_to_hybrid(self):
        """query_properties is forwarded to hybrid query call."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(query="test", query_properties=["title", "text"], ctx=ctx))

        call_kwargs = mock_col.query.hybrid.call_args.kwargs
        assert call_kwargs.get("query_properties") == ["title", "text"]

    def test_query_properties_passed_to_bm25(self):
        """query_properties is forwarded to bm25 query call (alpha=0.0)."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        # alpha=0.0 forces bm25 path, no embedding needed
        asyncio.run(search(query="test", alpha=0.0, query_properties=["title"], ctx=ctx))

        call_kwargs = mock_col.query.bm25.call_args.kwargs
        assert call_kwargs.get("query_properties") == ["title"]

    def test_query_properties_not_passed_to_near_vector(self):
        """query_properties is NOT forwarded to near_vector query (pure vector path)."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(query="test", alpha=1.0, query_properties=["title"], ctx=ctx))

        call_kwargs = mock_col.query.near_vector.call_args.kwargs
        assert "query_properties" not in call_kwargs

    def test_results_per_talk_flows_into_group_by(self):
        """results_per_talk value flows into GroupBy.objects_per_group."""
        from server import search

        ctx, mock_client = _make_mock_ctx()
        mock_col = MagicMock()
        # Grouping routes through near_vector; empty groups so we just inspect the call
        mock_col.query.near_vector.return_value.groups = {}
        mock_col.query.near_vector.return_value.objects = []
        mock_col.aggregate.over_all.return_value.total_count = 0
        mock_client.collections.use.return_value = mock_col

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(query="test", group_by_talk=True, results_per_talk=5, ctx=ctx))

        call_kwargs = mock_col.query.near_vector.call_args.kwargs
        group_by = call_kwargs.get("group_by")
        assert group_by is not None
        assert group_by.objects_per_group == 5

    def test_group_by_talk_without_embedding_returns_message(self):
        """group_by_talk requires a vector; when the embedding server is down it returns a clear message."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        # Embedding server unavailable -> no query vector -> grouping cannot run
        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.side_effect = RuntimeError("embedding server down")
            result = asyncio.run(search(query="test", group_by_talk=True, ctx=ctx))

        assert "group_by_talk requires semantic search" in result
        mock_col.query.near_vector.assert_not_called()

    def test_offset_passed_to_hybrid(self):
        """offset is forwarded to hybrid query call."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(query="test", offset=10, ctx=ctx))

        call_kwargs = mock_col.query.hybrid.call_args.kwargs
        assert call_kwargs.get("offset") == 10

    def test_new_filter_params_produce_non_none_filter(self):
        """session, cites_scripture, year_from/year_to all produce a non-None filter for hybrid."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_embedding_url") as mock_url:
            mock_url.return_value = "http://localhost:8080"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(
                query="test",
                session="Sun AM",
                cites_scripture=True,
                year_from=2000,
                year_to=2020,
                ctx=ctx,
            ))

        call_kwargs = mock_col.query.hybrid.call_args.kwargs
        assert call_kwargs.get("filters") is not None


# ---------------------------------------------------------------------------
# TOOL-04/TOOL-05: get_talk tool
# ---------------------------------------------------------------------------


def _make_talks_col(talk_properties=None):
    """
    Build a mock Weaviate talks collection.

    talk_properties: dict for the returned talk object's .properties.
    Set to None to simulate talk not found (fetch_object_by_id returns None).
    """
    mock_col = MagicMock()
    if talk_properties is None:
        mock_col.query.fetch_object_by_id.return_value = None
    else:
        talk_obj = MagicMock()
        talk_obj.properties = talk_properties
        mock_col.query.fetch_object_by_id.return_value = talk_obj
    return mock_col


def _make_paras_col(para_list):
    """
    Build a mock Weaviate paragraphs collection.

    para_list: list of dicts with "text" and "paragraph_number" keys.
    """
    mock_col = MagicMock()
    mock_objects = []
    for para_props in para_list:
        obj = MagicMock()
        obj.properties = para_props
        mock_objects.append(obj)
    mock_col.query.fetch_objects.return_value.objects = mock_objects
    return mock_col


class TestGetTalkTool:
    """Integration tests for the get_talk MCP tool."""

    _TALK_PROPS = {
        "speaker_name": "Jeffrey R. Holland",
        "title": "A Talk",
        "conference_month": "April",
        "conference_year": 2020,
        "session_description": "Saturday Afternoon",
    }

    _DEFAULT_PARAS = [
        {"text": "First paragraph.", "paragraph_number": 1},
        {"text": "Second paragraph.", "paragraph_number": 2},
    ]

    def _make_ctx(self, talk_props=None, para_list=None):
        """
        Build a mock ctx where:
          - client.collections.use("ConferenceTalks") → talks_col
          - client.collections.use("ConferenceTalkParagraphs") → paras_col
        """
        ctx, mock_client = _make_mock_ctx()

        if talk_props is None:
            talk_props = self._TALK_PROPS
        if para_list is None:
            para_list = self._DEFAULT_PARAS

        talks_col = _make_talks_col(talk_props)
        paras_col = _make_paras_col(para_list)

        def use_side_effect(name):
            if name == "ConferenceTalks":
                return talks_col
            elif name == "ConferenceTalkParagraphs":
                return paras_col
            return MagicMock()

        mock_client.collections.use.side_effect = use_side_effect
        return ctx

    def test_get_talk_returns_formatted_output(self):
        """get_talk returns header + paragraphs in correct format."""
        from server import get_talk

        ctx = self._make_ctx()

        result = asyncio.run(get_talk(talk_id="talk_8820", ctx=ctx))

        assert result.startswith("Speaker: Jeffrey R. Holland")
        assert "Title: A Talk" in result
        assert "Conference: April 2020" in result
        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_get_talk_paragraph_order(self):
        """Paragraphs are returned in Weaviate's ascending order — get_talk must NOT re-sort client-side."""
        from server import get_talk

        # Weaviate is responsible for ordering; mock returns paragraphs already in ascending order.
        para_list = [
            {"text": "Para one.", "paragraph_number": 1},
            {"text": "Para two.", "paragraph_number": 2},
            {"text": "Para three.", "paragraph_number": 3},
        ]
        ctx = self._make_ctx(para_list=para_list)

        result = asyncio.run(get_talk(talk_id="8820", ctx=ctx))

        pos_one = result.index("Para one.")
        pos_two = result.index("Para two.")
        pos_three = result.index("Para three.")
        assert pos_one < pos_two < pos_three

        # Assert fetch_objects was called with sort= kwarg (ordering delegated to Weaviate)
        paras_col = ctx.lifespan_context["app"].client.collections.use("ConferenceTalkParagraphs")
        call_kwargs = paras_col.query.fetch_objects.call_args.kwargs
        assert "sort" in call_kwargs

    def test_get_talk_not_found(self):
        """get_talk with nonexistent ID returns 'No talk found' error message."""
        from server import get_talk

        ctx, mock_client = _make_mock_ctx()
        talks_col = _make_talks_col(talk_properties=None)  # None = not found
        paras_col = _make_paras_col([])

        def use_side_effect(name):
            if name == "ConferenceTalks":
                return talks_col
            return paras_col

        mock_client.collections.use.side_effect = use_side_effect

        result = asyncio.run(get_talk(talk_id="talk_9999", ctx=ctx))

        assert "No talk found" in result

    def test_get_talk_invalid_id(self):
        """get_talk with unparseable ID returns format error message."""
        from server import get_talk

        ctx, _ = _make_mock_ctx()

        result = asyncio.run(get_talk(talk_id="not_valid_at_all", ctx=ctx))

        assert "Invalid talk_id format" in result


# ---------------------------------------------------------------------------
# INTG-03: Tool docstrings
# ---------------------------------------------------------------------------


def test_search_docstring_has_collection_hint():
    """search tool docstring contains collection hints for paragraphs, talks, citations."""
    from server import search

    doc = search.__doc__ or ""
    assert "paragraphs" in doc
    assert "talks" in doc
    assert "citations" in doc


def test_get_talk_docstring_has_workflow_hint():
    """get_talk tool docstring contains guidance to search first."""
    from server import get_talk

    doc = get_talk.__doc__ or ""
    assert "search" in doc.lower()


# ---------------------------------------------------------------------------
# EMBEDDING_URL consolidation: _check_embedding passes resolved URL to get_embedding_function
# ---------------------------------------------------------------------------


def test_check_embedding_passes_resolved_url(monkeypatch):
    """_check_embedding passes resolve_embedding_url() result to get_embedding_function(url=..., task="query")."""
    monkeypatch.setenv("EMBEDDING_URL", "http://custom-host:9999")
    captured_url = {}

    def mock_get_ef(url=None, task="document"):
        captured_url["url"] = url
        captured_url["task"] = task
        mock_ef = lambda texts: [[0.1] * 10]
        return mock_ef

    monkeypatch.setattr("server.get_embedding_function", mock_get_ef)
    from server import _check_embedding

    _check_embedding()
    assert captured_url["url"] == "http://custom-host:9999"
    assert captured_url["task"] == "query"


# ---------------------------------------------------------------------------
# TRANS-01: No stdio references
# ---------------------------------------------------------------------------


def test_no_stdio_references():
    import server, inspect
    source = inspect.getsource(server)
    assert "stdio" not in source.lower(), f"Found stdio reference in server.py source"


# ---------------------------------------------------------------------------
# TRANS-02: Health endpoint — checks data["weaviate"]
# ---------------------------------------------------------------------------


def test_health_returns_200():
    """GET /health returns 200 with ok status when both the embedding server and Weaviate are reachable."""
    mock_ef = MagicMock(return_value=[[0.1] * 10])
    mock_weaviate_resp = MagicMock()
    mock_weaviate_resp.ok = True

    with patch("server._startup", return_value=_mock_startup()), \
         patch("server.get_embedding_function", return_value=mock_ef), \
         patch("server.http_requests.get", return_value=mock_weaviate_resp):
        from server import mcp
        app = mcp.http_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["embedding"] == "reachable"
    assert data["weaviate"] == "reachable"


def test_health_embedding_down():
    """GET /health returns degraded when the embedding server is unreachable; weaviate is still reachable."""
    mock_ef = MagicMock(side_effect=Exception("connection refused"))
    mock_weaviate_resp = MagicMock()
    mock_weaviate_resp.ok = True

    with patch("server._startup", return_value=_mock_startup()), \
         patch("server.get_embedding_function", return_value=mock_ef), \
         patch("server.http_requests.get", return_value=mock_weaviate_resp):
        from server import mcp
        app = mcp.http_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")

    data = response.json()
    assert data["weaviate"] == "reachable"
    assert data["status"] == "degraded"


# ---------------------------------------------------------------------------
# Wave 0: Dispatcher behavior tests (Plan 02 — FastAPI dispatcher)
# ---------------------------------------------------------------------------


def _mock_startup():
    """Return a mock AppContext for dispatcher tests (avoids real Weaviate/embedding calls)."""
    from server import AppContext
    mock_client = MagicMock()
    return AppContext(client=mock_client)


# ---------------------------------------------------------------------------
# MCP PROTOCOL TESTS (/mcp endpoint)
# ---------------------------------------------------------------------------

@pytest.fixture
def mcp_headers():
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

def test_initialize_no_auth(mcp_headers):
    """OAUTH-01: initialize succeeds without Authorization header."""
    with patch("server._startup", return_value=_mock_startup()):
        from server import mcp
        with TestClient(mcp.http_app(), raise_server_exceptions=False) as client:
            resp = client.post("/mcp", json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
            }, headers=mcp_headers)
    assert resp.status_code == 200
    assert "MCP-Session-Id" in resp.headers


def test_tools_list_local_mode_no_auth_required(mcp_headers):
    """OAUTH-02 / D-01: tools/list succeeds with no token when AUTH0_DOMAIN is unset (local mode)."""
    with patch("server._startup", return_value=_mock_startup()):
        from server import mcp
        with TestClient(mcp.http_app(), raise_server_exceptions=False) as client:
            init_resp = client.post("/mcp", json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
            }, headers=mcp_headers)
            assert init_resp.status_code == 200
            session_id = init_resp.headers["MCP-Session-Id"]
            resp = client.post("/mcp", json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/list",
            }, headers={**mcp_headers, "MCP-Session-Id": session_id})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# FRAMEWORK ASSERTION
# ---------------------------------------------------------------------------

def test_fastmcp_present_fastapi_absent():
    import inspect, server
    source = inspect.getsource(server)
    assert "from fastmcp import FastMCP" in source
    assert "from fastapi" not in source
    assert "BaseHTTPMiddleware(" not in source

# ---------------------------------------------------------------------------
# ENV VALIDATION
# ---------------------------------------------------------------------------

def test_env_vars_no_hardcoded_values():
    import inspect, server
    source = inspect.getsource(server)
    assert ".auth0.com" not in source.lower()  # no hardcoded Auth0 domain URLs
    assert "scalekit.com" not in source.lower()


# ---------------------------------------------------------------------------
# AUTH-02 / OAUTH-01 / OAUTH-02: Two-mode auth tests
# ---------------------------------------------------------------------------

def test_initialize_no_auth_remote_mode(mcp_headers):
    """OAUTH-01: initialize succeeds with a valid token in remote mode (DebugTokenVerifier).

    Note: FastMCP's DebugTokenVerifier enforces auth on all endpoints including
    initialize. This test verifies the remote-mode auth path is operational.
    """
    from fastmcp.server.auth.providers.debug import DebugTokenVerifier
    with patch("server._startup", return_value=_mock_startup()):
        from server import mcp
        orig_auth = mcp.auth
        mcp.auth = DebugTokenVerifier()
        try:
            app = mcp.http_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/mcp", json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
                }, headers={**mcp_headers, "Authorization": "Bearer test-token"})
        finally:
            mcp.auth = orig_auth
    assert resp.status_code == 200


def test_tools_list_requires_auth_remote_mode(mcp_headers):
    """AUTH-02: tools/list without token returns 401 when auth is enabled."""
    from fastmcp.server.auth.providers.debug import DebugTokenVerifier
    with patch("server._startup", return_value=_mock_startup()):
        from server import mcp
        orig_auth = mcp.auth
        mcp.auth = DebugTokenVerifier()
        try:
            app = mcp.http_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                # Initialize with valid token to get session
                init_resp = client.post("/mcp", json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
                }, headers={**mcp_headers, "Authorization": "Bearer test-token"})
                session_id = init_resp.headers.get("MCP-Session-Id", "")
                # tools/list without Authorization header — must be rejected
                resp = client.post("/mcp", json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/list",
                }, headers={**mcp_headers, "MCP-Session-Id": session_id})
        finally:
            mcp.auth = orig_auth
    assert resp.status_code == 401


def test_tools_list_valid_token_remote_mode(mcp_headers):
    """OAUTH-02: tools/list succeeds with valid Bearer token via DebugTokenVerifier."""
    from fastmcp.server.auth.providers.debug import DebugTokenVerifier
    with patch("server._startup", return_value=_mock_startup()):
        from server import mcp
        orig_auth = mcp.auth
        mcp.auth = DebugTokenVerifier()
        try:
            app = mcp.http_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                init_resp = client.post("/mcp", json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
                }, headers={**mcp_headers, "Authorization": "Bearer test-token"})
                session_id = init_resp.headers.get("MCP-Session-Id", "")
                resp = client.post("/mcp", json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/list",
                }, headers={**mcp_headers, "MCP-Session-Id": session_id, "Authorization": "Bearer test-token-123"})
        finally:
            mcp.auth = orig_auth
    assert resp.status_code == 200


def test_oauth_module_deleted():
    """D-05: auth/oauth.py must not exist (JWKSVerifier replaced by ScalekitProvider)."""
    import os
    # Use __file__ to locate relative to the project root (tests/ is one level below root)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    oauth_path = os.path.join(project_root, "auth", "oauth.py")
    assert not os.path.exists(oauth_path), f"auth/oauth.py should be deleted per D-05 (checked: {oauth_path})"


def test_fastapi_import_absent():
    """D-09: server.py must not import fastapi."""
    import inspect, server
    source = inspect.getsource(server)
    assert "from fastapi" not in source, "FastAPI imports should be removed per D-09"


# ---------------------------------------------------------------------------
# Wave 2 Agent C: find_by_scripture tool
# ---------------------------------------------------------------------------


def _make_citation_col(citation_props_list):
    """
    Build a mock Weaviate citations collection for find_by_scripture tests.

    citation_props_list: list of property dicts for citation objects.
    """
    mock_col = MagicMock()
    mock_objects = []
    for props in citation_props_list:
        obj = MagicMock()
        obj.properties = props
        mock_objects.append(obj)
    mock_col.query.fetch_objects.return_value.objects = mock_objects
    return mock_col


def _make_talks_fetch_col(talk_props_list):
    """
    Build a mock talks collection whose fetch_objects returns the given talks list.

    Used by find_by_scripture's batched talk join (not fetch_object_by_id).
    """
    mock_col = MagicMock()
    mock_objects = []
    for props in talk_props_list:
        obj = MagicMock()
        obj.properties = props
        mock_objects.append(obj)
    mock_col.query.fetch_objects.return_value.objects = mock_objects
    return mock_col


class TestFindByScripture:
    """Integration tests for the find_by_scripture MCP tool."""

    _CITATION_PROPS = {
        "talk_id": 8820,
        "paragraph_number": 3,
        "scripture_ref": "Romans 8:16",
        "book": "Romans",
        "book_abbr": "Rom.",
        "chapter": 8,
        "verses": "16",
        "verse_start": 16,
        "verse_end": 16,
        "context_window": "The Spirit itself beareth witness...",
    }

    _TALK_PROPS = {
        "talk_id": 8820,
        "speaker_name": "Jeffrey R. Holland",
        "title": "A Sure Foundation",
        "conference_year": 2020,
        "conference_month": "April",
    }

    def _make_ctx(self, citation_props_list, talk_props_list):
        """
        Build a mock ctx where:
          - client.collections.use("ConferenceTalkCitations") -> citations_col
          - client.collections.use("ConferenceTalks") -> talks_col
        Uses side_effect keyed on collection name (same pattern as TestGetTalkTool).
        """
        ctx, mock_client = _make_mock_ctx()
        citations_col = _make_citation_col(citation_props_list)
        talks_col = _make_talks_fetch_col(talk_props_list)

        def use_side_effect(name):
            if name == "ConferenceTalkCitations":
                return citations_col
            elif name == "ConferenceTalks":
                return talks_col
            return MagicMock()

        mock_client.collections.use.side_effect = use_side_effect
        return ctx, citations_col, talks_col

    def test_book_only_returns_joined_metadata(self):
        """Book-only query returns JSON with joined speaker/title/year from talks collection."""
        from server import find_by_scripture

        ctx, _, _ = self._make_ctx(
            citation_props_list=[self._CITATION_PROPS],
            talk_props_list=[self._TALK_PROPS],
        )

        result = asyncio.run(find_by_scripture(book="romans", ctx=ctx))

        parsed = json.loads(result)
        assert len(parsed) == 1
        item = parsed[0]
        assert item["speaker_name"] == "Jeffrey R. Holland"
        assert item["title"] == "A Sure Foundation"
        assert item["conference_year"] == 2020
        assert item["talk_id"] == "talk_8820"
        assert item["scripture_ref"] == "Romans 8:16"
        assert item["context_window"] == "The Spirit itself beareth witness..."

    def test_book_and_chapter_filter_applied(self):
        """book+chapter: fetch_objects is called with a non-None filter object."""
        from server import find_by_scripture

        ctx, citations_col, _ = self._make_ctx(
            citation_props_list=[self._CITATION_PROPS],
            talk_props_list=[self._TALK_PROPS],
        )

        asyncio.run(find_by_scripture(book="Romans", chapter=8, ctx=ctx))

        call_kwargs = citations_col.query.fetch_objects.call_args.kwargs
        assert call_kwargs.get("filters") is not None

    def test_verse_overlap_filter_applied(self):
        """verse_start + verse_end: fetch_objects receives a filter (overlap conditions ANDed)."""
        from server import find_by_scripture

        ctx, citations_col, _ = self._make_ctx(
            citation_props_list=[self._CITATION_PROPS],
            talk_props_list=[self._TALK_PROPS],
        )

        asyncio.run(
            find_by_scripture(book="Romans", chapter=8, verse_start=14, verse_end=18, ctx=ctx)
        )

        call_kwargs = citations_col.query.fetch_objects.call_args.kwargs
        assert call_kwargs.get("filters") is not None

    def test_empty_result_returns_no_match_string(self):
        """When no citations match, returns the canonical no-match string."""
        from server import find_by_scripture

        ctx, _, _ = self._make_ctx(
            citation_props_list=[],   # empty — no hits
            talk_props_list=[],
        )

        result = asyncio.run(find_by_scripture(book="Obadiah", ctx=ctx))

        assert result == "No talks found citing that scripture."

    def test_embedding_never_called(self):
        """find_by_scripture must not call get_embedding_function (no embedding dependency)."""
        from server import find_by_scripture

        ctx, _, _ = self._make_ctx(
            citation_props_list=[self._CITATION_PROPS],
            talk_props_list=[self._TALK_PROPS],
        )

        with patch("server.get_embedding_function") as mock_gef:
            asyncio.run(find_by_scripture(book="Romans", ctx=ctx))
            mock_gef.assert_not_called()

    def test_book_normalization(self):
        """Lowercase input is normalized to title-case before filtering."""
        from server import _normalize_book

        assert _normalize_book("romans") == "Romans"
        assert _normalize_book("1 nephi") == "1 Nephi"
        assert _normalize_book("  john  ") == "John"

    def test_result_has_exactly_six_fields(self):
        """Each result item has exactly the 6 expected public fields."""
        from server import find_by_scripture

        ctx, _, _ = self._make_ctx(
            citation_props_list=[self._CITATION_PROPS],
            talk_props_list=[self._TALK_PROPS],
        )

        result = asyncio.run(find_by_scripture(book="Romans", ctx=ctx))
        parsed = json.loads(result)
        assert set(parsed[0].keys()) == {
            "speaker_name",
            "title",
            "conference_year",
            "talk_id",
            "scripture_ref",
            "context_window",
        }


# ---------------------------------------------------------------------------
# corpus_stats tool tests
# ---------------------------------------------------------------------------


class TestCorpusStats:
    """Integration tests for the corpus_stats MCP tool."""

    def test_unknown_collection_lists_all_six_and_description_explains_verse_count(self):
        """The unknown-collection message names every collection; the description explains the verse count."""
        from server import corpus_stats

        ctx, _ = _make_mock_ctx()
        result = asyncio.run(corpus_stats(collection="nope", ctx=ctx))
        for name in ("talks", "paragraphs", "citations", "footnotes", "scripture_verses", "scripture_chapters"):
            assert name in result
        doc = corpus_stats.__doc__ or corpus_stats.fn.__doc__
        assert "41,995" in doc and "1,359" in doc and 'variant' in doc

    def test_no_group_by_returns_total(self):
        """corpus_stats with no group_by returns JSON with collection and total count."""
        from server import corpus_stats

        ctx, mock_client = _make_mock_ctx()
        agg_result = MagicMock()
        agg_result.total_count = 5838
        mock_client.collections.use.return_value.aggregate.over_all.return_value = agg_result

        result = asyncio.run(corpus_stats(collection="talks", ctx=ctx))

        parsed = json.loads(result)
        assert parsed["collection"] == "talks"
        assert parsed["total"] == 5838
        assert "groups" not in parsed

    def test_group_by_returns_sorted_groups(self):
        """corpus_stats with group_by returns groups sorted by count descending."""
        from server import corpus_stats

        ctx, mock_client = _make_mock_ctx()

        # Build unsorted groups: Nelson=10, Hinckley=50, Monson=30
        group1 = MagicMock()
        group1.grouped_by.value = "Russell M. Nelson"
        group1.total_count = 10

        group2 = MagicMock()
        group2.grouped_by.value = "Gordon B. Hinckley"
        group2.total_count = 50

        group3 = MagicMock()
        group3.grouped_by.value = "Thomas S. Monson"
        group3.total_count = 30

        agg_result = MagicMock()
        agg_result.groups = [group1, group2, group3]  # unsorted
        mock_client.collections.use.return_value.aggregate.over_all.return_value = agg_result

        result = asyncio.run(corpus_stats(collection="talks", group_by="speaker_name", ctx=ctx))

        parsed = json.loads(result)
        assert parsed["collection"] == "talks"
        assert parsed["group_by"] == "speaker_name"
        groups = parsed["groups"]
        # Must be sorted descending by count
        assert groups[0] == {"value": "Gordon B. Hinckley", "count": 50}
        assert groups[1] == {"value": "Thomas S. Monson", "count": 30}
        assert groups[2] == {"value": "Russell M. Nelson", "count": 10}

    def test_group_by_limit_caps_results(self):
        """corpus_stats with group_by and limit caps the returned groups."""
        from server import corpus_stats

        ctx, mock_client = _make_mock_ctx()

        # 5 groups, but limit=2
        mock_groups = []
        for i in range(5):
            g = MagicMock()
            g.grouped_by.value = f"Speaker {i}"
            g.total_count = i * 10
            mock_groups.append(g)

        agg_result = MagicMock()
        agg_result.groups = mock_groups
        mock_client.collections.use.return_value.aggregate.over_all.return_value = agg_result

        result = asyncio.run(corpus_stats(collection="talks", group_by="speaker_name", limit=2, ctx=ctx))

        parsed = json.loads(result)
        assert len(parsed["groups"]) == 2
        # Top 2 should be the highest counts (40 and 30)
        assert parsed["groups"][0]["count"] == 40
        assert parsed["groups"][1]["count"] == 30

    def test_unknown_collection_returns_error(self):
        """corpus_stats with an unknown collection key returns the error string without querying Weaviate."""
        from server import corpus_stats

        ctx, mock_client = _make_mock_ctx()

        result = asyncio.run(corpus_stats(collection="nonexistent", ctx=ctx))

        assert result == "Unknown collection 'nonexistent'. Valid: talks, paragraphs, citations, footnotes, scripture_verses, scripture_chapters."
        # Weaviate must not have been called
        mock_client.collections.use.assert_not_called()

    def test_no_embedding_calls(self):
        """corpus_stats must never call get_embedding_function (no embedding needed)."""
        from server import corpus_stats

        ctx, mock_client = _make_mock_ctx()
        agg_result = MagicMock()
        agg_result.total_count = 100
        mock_client.collections.use.return_value.aggregate.over_all.return_value = agg_result

        with patch("server.get_embedding_function") as mock_gef:
            asyncio.run(corpus_stats(collection="paragraphs", ctx=ctx))
            mock_gef.assert_not_called()

    def test_scripture_collections(self):
        """The scripture collections aggregate their own Weaviate collections."""
        from server import corpus_stats

        ctx, mock_client = _make_mock_ctx()
        mock_client.collections.use.return_value.aggregate.over_all.return_value.total_count = 43354

        for collection, weaviate_name in (("scripture_verses", "ScriptureVerses"),
                                          ("scripture_chapters", "ScriptureChapters")):
            parsed = json.loads(asyncio.run(corpus_stats(collection=collection, ctx=ctx)))
            assert parsed == {"collection": collection, "total": 43354}
            mock_client.collections.use.assert_called_with(weaviate_name)

    def test_scripture_not_loaded(self):
        """Without the scripture collections, corpus_stats says so and does not query Weaviate."""
        from server import corpus_stats

        ctx, mock_client = _make_mock_ctx()
        ctx.lifespan_context["app"].scripture_loaded = False

        result = asyncio.run(corpus_stats(collection="scripture_verses", group_by="volume", ctx=ctx))

        assert "scripture corpus not available" in result
        mock_client.collections.use.assert_not_called()


# ---------------------------------------------------------------------------
# get_talk_citations tool tests
# ---------------------------------------------------------------------------


class TestGetTalkCitations:
    """Integration tests for the get_talk_citations MCP tool."""

    def _make_ctx(self, citation_props_list):
        """Build a mock ctx where collections.use returns a citations mock col."""
        ctx, mock_client = _make_mock_ctx()
        mock_col = MagicMock()
        mock_objects = []
        for props in citation_props_list:
            obj = MagicMock()
            obj.properties = props
            mock_objects.append(obj)
        mock_col.query.fetch_objects.return_value.objects = mock_objects
        mock_client.collections.use.return_value = mock_col
        return ctx, mock_client, mock_col

    def test_invalid_talk_id_returns_error(self):
        """An unparseable talk_id returns the canonical error string."""
        from server import get_talk_citations

        ctx, _, _ = self._make_ctx([])

        result = asyncio.run(get_talk_citations(talk_id="not_a_number", ctx=ctx))

        assert "Invalid talk_id format" in result
        assert "not_a_number" in result

    def test_no_citations_returns_not_found_string(self):
        """When no citations exist for a talk_id, returns 'No citations found' string."""
        from server import get_talk_citations

        ctx, _, _ = self._make_ctx([])

        result = asyncio.run(get_talk_citations(talk_id="talk_9999", ctx=ctx))

        assert result == "No citations found for talk_id 'talk_9999'."

    def test_happy_path_returns_ordered_citations(self):
        """3 citation objects given out of order are returned sorted by (paragraph_number, char_position)."""
        from server import get_talk_citations

        # Deliberately out of order to verify sorting
        citation_props_list = [
            {
                "talk_id": 8820,
                "paragraph_number": 5,
                "char_position": 10,
                "scripture_ref": "John 3:16",
                "book": "John",
                "chapter": 3,
                "verses": "16",
                "verse_start": 16,
                "verse_end": 16,
                "context_window": "For God so loved the world...",
            },
            {
                "talk_id": 8820,
                "paragraph_number": 2,
                "char_position": 50,
                "scripture_ref": "Moroni 10:4",
                "book": "Moroni",
                "chapter": 10,
                "verses": "4",
                "verse_start": 4,
                "verse_end": 4,
                "context_window": "...ask with a sincere heart...",
            },
            {
                "talk_id": 8820,
                "paragraph_number": 2,
                "char_position": 10,
                "scripture_ref": "1 Nephi 3:7",
                "book": "1 Nephi",
                "chapter": 3,
                "verses": "7",
                "verse_start": 7,
                "verse_end": 7,
                "context_window": "...I will go and do...",
            },
        ]

        ctx, _, _ = self._make_ctx(citation_props_list)

        result = asyncio.run(get_talk_citations(talk_id="8820", ctx=ctx))

        parsed = json.loads(result)
        assert len(parsed) == 3

        # Sorted by (paragraph_number, char_position): (2,10), (2,50), (5,10)
        assert parsed[0]["scripture_ref"] == "1 Nephi 3:7"
        assert parsed[1]["scripture_ref"] == "Moroni 10:4"
        assert parsed[2]["scripture_ref"] == "John 3:16"

    def test_output_fields_are_correct(self):
        """Each result has exactly the expected public fields; no pipeline-internal fields leak out."""
        from server import get_talk_citations

        citation_props_list = [
            {
                "talk_id": 8820,
                "paragraph_number": 1,
                "char_position": 0,
                "scripture_ref": "Alma 32:21",
                "book": "Alma",
                "chapter": 32,
                "verses": "21",
                "verse_start": 21,
                "verse_end": 21,
                "context_window": "...faith is not a perfect knowledge...",
            },
        ]

        ctx, _, _ = self._make_ctx(citation_props_list)

        result = asyncio.run(get_talk_citations(talk_id="talk_8820", ctx=ctx))

        parsed = json.loads(result)
        assert len(parsed) == 1
        item = parsed[0]

        expected_keys = {
            "scripture_ref",
            "book",
            "chapter",
            "verses",
            "verse_start",
            "verse_end",
            "context_window",
            "paragraph_number",
        }
        assert set(item.keys()) == expected_keys

        # Internal pipeline fields must NOT appear
        assert "talk_id" not in item
        assert "char_position" not in item
        assert "citation_id" not in item
        assert "paragraph_id" not in item

    def test_limit_is_clamped_to_min_1(self):
        """limit=0 is clamped up to 1 before the Weaviate call."""
        from server import get_talk_citations

        citation_props_list = [
            {
                "talk_id": 1234,
                "paragraph_number": 1,
                "char_position": 0,
                "scripture_ref": "Romans 8:16",
                "book": "Romans",
                "chapter": 8,
                "verses": "16",
                "verse_start": 16,
                "verse_end": 16,
                "context_window": "...",
            },
        ]

        ctx, _, mock_col = self._make_ctx(citation_props_list)

        asyncio.run(get_talk_citations(talk_id="1234", limit=0, ctx=ctx))

        call_kwargs = mock_col.query.fetch_objects.call_args.kwargs
        assert call_kwargs["limit"] == 1

    def test_limit_is_clamped_to_max_500(self):
        """limit=1000 is clamped down to 500 before the Weaviate call."""
        from server import get_talk_citations

        citation_props_list = [
            {
                "talk_id": 1234,
                "paragraph_number": 1,
                "char_position": 0,
                "scripture_ref": "Romans 8:16",
                "book": "Romans",
                "chapter": 8,
                "verses": "16",
                "verse_start": 16,
                "verse_end": 16,
                "context_window": "...",
            },
        ]

        ctx, _, mock_col = self._make_ctx(citation_props_list)

        asyncio.run(get_talk_citations(talk_id="1234", limit=1000, ctx=ctx))

        call_kwargs = mock_col.query.fetch_objects.call_args.kwargs
        assert call_kwargs["limit"] == 500

    def test_embedding_never_called(self):
        """get_talk_citations must not call get_embedding_function (no embedding needed)."""
        from server import get_talk_citations

        citation_props_list = [
            {
                "talk_id": 8820,
                "paragraph_number": 1,
                "char_position": 0,
                "scripture_ref": "Romans 8:16",
                "book": "Romans",
                "chapter": 8,
                "verses": "16",
                "verse_start": 16,
                "verse_end": 16,
                "context_window": "...",
            },
        ]

        ctx, _, _ = self._make_ctx(citation_props_list)

        with patch("server.get_embedding_function") as mock_gef:
            asyncio.run(get_talk_citations(talk_id="talk_8820", ctx=ctx))
            mock_gef.assert_not_called()
