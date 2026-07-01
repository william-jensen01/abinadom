"""
Unit tests for server.py startup validation and MCP tool integration.

CORE-01: Weaviate client factory (env-var config, _validate_collections guard)
CORE-02: Ollama health check (fails fast on connection error)
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
# CORE-02: _check_ollama
# ---------------------------------------------------------------------------


def test_ollama_failure_is_non_fatal():
    """_check_ollama() logs a warning but does not raise when Ollama is unreachable."""
    from server import _check_ollama

    mock_ef = MagicMock(side_effect=Exception("connection refused"))
    mock_get_ef = MagicMock(return_value=mock_ef)

    with patch("server.get_embedding_function", mock_get_ef):
        # Should not raise — Ollama failure is non-fatal at startup
        _check_ollama()


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
             patch("server.resolve_ollama_url") as mock_url:
            mock_url.return_value = "http://localhost:11434"
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
             patch("server.resolve_ollama_url") as mock_url:
            mock_url.return_value = "http://localhost:11434"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            result = asyncio.run(search(query="nothing matches", ctx=ctx))

        assert result == "No results found."

    def test_search_limit_clamped(self):
        """limit > 20 is clamped to 20 when calling hybrid (default alpha=0.7)."""
        from server import search

        ctx, mock_col_mock = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_ollama_url") as mock_url:
            mock_url.return_value = "http://localhost:11434"
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
             patch("server.resolve_ollama_url") as mock_url:
            mock_url.return_value = "http://localhost:11434"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            asyncio.run(search(query="test", year=2020, season="April", ctx=ctx))

        call_kwargs = mock_col_mock.query.hybrid.call_args.kwargs
        assert call_kwargs.get("filters") is not None

    def test_search_speaker_filter_not_none(self):
        """search with speaker param passes non-None filters to hybrid (native Weaviate filter)."""
        from server import search

        ctx, mock_col_mock = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_ollama_url") as mock_url:
            mock_url.return_value = "http://localhost:11434"
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
             patch("server.resolve_ollama_url") as mock_url:
            mock_url.return_value = "http://localhost:11434"
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

    def test_search_ollama_down_fallback(self):
        """When Ollama embedding raises, search falls back to bm25 with search_mode 'keyword_only_ollama_unavailable'."""
        from server import search

        ctx, mock_col = self._make_ctx_with_col()

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_ollama_url") as mock_url:
            mock_url.return_value = "http://localhost:11434"
            # Embedding function raises on call
            mock_gef.return_value = MagicMock(side_effect=Exception("ollama down"))
            result = asyncio.run(search(query="test", ctx=ctx))  # default alpha=0.7 → needs embedding

        parsed = json.loads(result)
        assert parsed["search_mode"] == "keyword_only_ollama_unavailable"
        mock_col.query.bm25.assert_called_once()

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
        mock_para.metadata.score = 0.85

        mock_group = MagicMock()
        mock_group.belongs_to_group = 1234
        mock_group.objects = [mock_para]

        # Weaviate grouped results come from .groups (a list); .objects is empty
        mock_col.query.hybrid.return_value.groups = [mock_group]
        mock_col.query.hybrid.return_value.objects = []
        mock_client.collections.use.return_value = mock_col

        with patch("server.get_embedding_function") as mock_gef, \
             patch("server.resolve_ollama_url") as mock_url:
            mock_url.return_value = "http://localhost:11434"
            mock_gef.return_value = lambda texts: [[0.1] * 10]
            result = asyncio.run(search(query="test", group_by_talk=True, ctx=ctx))

        parsed = json.loads(result)
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
        """Paragraphs are sorted by paragraph_number ascending even when returned out of order."""
        from server import get_talk

        # Supply paragraphs in REVERSE order: 3, 1, 2
        para_list = [
            {"text": "Para three.", "paragraph_number": 3},
            {"text": "Para one.", "paragraph_number": 1},
            {"text": "Para two.", "paragraph_number": 2},
        ]
        ctx = self._make_ctx(para_list=para_list)

        result = asyncio.run(get_talk(talk_id="8820", ctx=ctx))

        pos_one = result.index("Para one.")
        pos_two = result.index("Para two.")
        pos_three = result.index("Para three.")
        assert pos_one < pos_two < pos_three

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
# OLLAMA_URL consolidation: _check_ollama passes resolved URL to get_embedding_function
# ---------------------------------------------------------------------------


def test_check_ollama_passes_resolved_url(monkeypatch):
    """_check_ollama passes resolve_ollama_url() result to get_embedding_function(url=...)."""
    monkeypatch.setenv("OLLAMA_URL", "http://custom-host:9999")
    captured_url = {}

    def mock_get_ef(url=None):
        captured_url["url"] = url
        mock_ef = lambda texts: [[0.1] * 10]
        return mock_ef

    monkeypatch.setattr("server.get_embedding_function", mock_get_ef)
    from server import _check_ollama

    _check_ollama()
    assert captured_url["url"] == "http://custom-host:9999"


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
    """GET /health returns 200 with ok status when both Ollama and Weaviate are reachable."""
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
    assert data["ollama"] == "reachable"
    assert data["weaviate"] == "reachable"


def test_health_ollama_down():
    """GET /health returns degraded when Ollama is unreachable; weaviate is still reachable."""
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
    """Return a mock AppContext for dispatcher tests (avoids real Weaviate/Ollama calls)."""
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
            })
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
