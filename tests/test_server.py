"""
Unit tests for server.py startup validation and MCP tool integration.

CORE-01: ChromaDB path resolution (absolute path, env override, missing collection guard)
CORE-02: Ollama health check (fails fast on connection error)
CORE-03: Collection warmup (all 4 collections loaded and counted)
TOOL-01/TOOL-02/TOOL-03: search tool integration
TOOL-04/TOOL-05: get_talk tool integration
"""
import asyncio
import json
import os
from unittest.mock import MagicMock, patch

import chromadb
import pytest
from starlette.testclient import TestClient


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


# ---------------------------------------------------------------------------
# Test helpers for MCP tool integration tests
# ---------------------------------------------------------------------------


def _make_mock_ctx(collections: dict):
    """Build a mock Context whose lifespan_context is an AppContext with given collections."""
    from server import AppContext

    app = AppContext(client=MagicMock(), collections=collections)
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app
    return ctx


# ---------------------------------------------------------------------------
# TOOL-01/TOOL-02/TOOL-03: search tool
# ---------------------------------------------------------------------------


class TestSearchTool:
    """Integration tests for the search MCP tool."""

    _SINGLE_META = {
        "speaker_name": "Jeffrey R. Holland",
        "title": "A Talk",
        "conference_year": 2020,
        "conference_month": "April",
        "talk_id": 8820,
        # Pipeline-internal fields — must NOT leak through
        "text": "raw",
        "paragraph_id": "p1",
    }

    def _make_col(self, docs=None, metas=None):
        """Build a mock ChromaDB collection returning the given query result."""
        if docs is None:
            docs = ["Some text"]
        if metas is None:
            metas = [self._SINGLE_META]
        col = MagicMock()
        col.query.return_value = {
            "ids": [[f"id{i}" for i in range(len(docs))]],
            "documents": [docs],
            "metadatas": [metas],
        }
        return col

    def test_search_basic_query(self):
        """search calls col.query with correct args and returns JSON with 6-field results."""
        from server import search

        col = self._make_col()
        ctx = _make_mock_ctx({"paragraphs": col})

        result = asyncio.run(search(query="test query", ctx=ctx))
        parsed = json.loads(result)

        assert len(parsed) == 1
        assert set(parsed[0].keys()) == {
            "snippet",
            "speaker_name",
            "title",
            "conference_year",
            "conference_month",
            "talk_id",
        }
        assert "paragraph_id" not in parsed[0]
        assert "text" not in parsed[0]

    def test_search_speaker_post_filter(self):
        """search with speaker param filters results in Python (not in where dict)."""
        from server import search

        docs = ["Holland text", "Oaks text"]
        metas = [
            {**self._SINGLE_META, "speaker_name": "Jeffrey R. Holland"},
            {**self._SINGLE_META, "speaker_name": "Dallin H. Oaks"},
        ]
        col = self._make_col(docs=docs, metas=metas)
        ctx = _make_mock_ctx({"paragraphs": col})

        result = asyncio.run(search(query="grace", speaker="Holland", ctx=ctx))
        parsed = json.loads(result)

        assert len(parsed) == 1
        assert "Holland" in parsed[0]["speaker_name"]
        # Confirm speaker was NOT included in the where filter passed to ChromaDB
        call_kwargs = col.query.call_args.kwargs
        where = call_kwargs.get("where")
        if where is not None:
            assert "speaker" not in str(where).lower()

    def test_search_invalid_collection(self):
        """search with unknown collection returns error message."""
        from server import search

        ctx = _make_mock_ctx({"paragraphs": MagicMock()})
        result = asyncio.run(search(query="test", collection="nonexistent", ctx=ctx))

        assert "Unknown collection" in result

    def test_search_year_season_filter(self):
        """search with year=2020 and season='April' passes $and where filter to col.query."""
        from server import search

        col = self._make_col()
        ctx = _make_mock_ctx({"paragraphs": col})

        asyncio.run(search(query="test", year=2020, season="April", ctx=ctx))

        call_kwargs = col.query.call_args.kwargs
        assert call_kwargs["where"] == {
            "$and": [
                {"conference_year": {"$eq": 2020}},
                {"conference_month": {"$eq": "April"}},
            ]
        }

    def test_search_empty_results(self):
        """search with no matching results returns 'No results found.'"""
        from server import search

        col = MagicMock()
        col.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]]}
        ctx = _make_mock_ctx({"paragraphs": col})

        result = asyncio.run(search(query="nothing matches", ctx=ctx))

        assert result == "No results found."

    def test_search_limit_clamped(self):
        """limit > 20 is clamped to 20 when calling col.query."""
        from server import search

        col = self._make_col()
        ctx = _make_mock_ctx({"paragraphs": col})

        asyncio.run(search(query="test", limit=50, ctx=ctx))

        call_kwargs = col.query.call_args.kwargs
        assert call_kwargs["n_results"] == 20


# ---------------------------------------------------------------------------
# TOOL-04/TOOL-05: get_talk tool
# ---------------------------------------------------------------------------


class TestGetTalkTool:
    """Integration tests for the get_talk MCP tool."""

    _TALK_META = {
        "speaker_name": "Jeffrey R. Holland",
        "title": "A Talk",
        "conference_month": "April",
        "conference_year": 2020,
        "session_description": "Saturday Afternoon",
    }

    def _make_talks_col(self, metas=None):
        """Build a mock talks collection."""
        if metas is None:
            metas = [self._TALK_META]
        col = MagicMock()
        col.get.return_value = {
            "ids": [f"talk_{i}" for i in range(len(metas))],
            "metadatas": metas,
        }
        return col

    def _make_paras_col(self, docs=None, metas=None):
        """Build a mock paragraphs collection."""
        if docs is None:
            docs = ["First paragraph.", "Second paragraph."]
        if metas is None:
            metas = [{"paragraph_number": 1}, {"paragraph_number": 2}]
        col = MagicMock()
        col.get.return_value = {
            "ids": [f"p{i}" for i in range(len(docs))],
            "documents": docs,
            "metadatas": metas,
        }
        return col

    def test_get_talk_returns_formatted_output(self):
        """get_talk returns header + paragraphs in correct format."""
        from server import get_talk

        talks_col = self._make_talks_col()
        paras_col = self._make_paras_col()
        ctx = _make_mock_ctx({"talks": talks_col, "paragraphs": paras_col})

        result = asyncio.run(get_talk(talk_id="talk_8820", ctx=ctx))

        assert result.startswith("Speaker: Jeffrey R. Holland")
        assert "Title: A Talk" in result
        assert "Conference: April 2020" in result
        assert "First paragraph.\n\nSecond paragraph." in result

    def test_get_talk_paragraph_order(self):
        """Paragraphs are sorted by paragraph_number ascending even when returned out of order."""
        from server import get_talk

        # Return paragraphs in REVERSE order: 3, 1, 2
        docs = ["Para three.", "Para one.", "Para two."]
        metas = [
            {"paragraph_number": 3},
            {"paragraph_number": 1},
            {"paragraph_number": 2},
        ]
        talks_col = self._make_talks_col()
        paras_col = self._make_paras_col(docs=docs, metas=metas)
        ctx = _make_mock_ctx({"talks": talks_col, "paragraphs": paras_col})

        result = asyncio.run(get_talk(talk_id="8820", ctx=ctx))

        # Para one should come before Para two, which should come before Para three
        pos_one = result.index("Para one.")
        pos_two = result.index("Para two.")
        pos_three = result.index("Para three.")
        assert pos_one < pos_two < pos_three

    def test_get_talk_not_found(self):
        """get_talk with nonexistent ID returns 'No talk found' error message."""
        from server import get_talk

        talks_col = MagicMock()
        talks_col.get.return_value = {"ids": [], "metadatas": []}
        ctx = _make_mock_ctx({"talks": talks_col, "paragraphs": MagicMock()})

        result = asyncio.run(get_talk(talk_id="talk_9999", ctx=ctx))

        assert "No talk found" in result

    def test_get_talk_invalid_id(self):
        """get_talk with unparseable ID returns format error message."""
        from server import get_talk

        ctx = _make_mock_ctx({"talks": MagicMock(), "paragraphs": MagicMock()})

        result = asyncio.run(get_talk(talk_id="not_valid_at_all", ctx=ctx))

        assert "Invalid talk_id format" in result


# ---------------------------------------------------------------------------
# INTG-02: OLLAMA_URL env var support
# ---------------------------------------------------------------------------


def test_ollama_url_env_override(monkeypatch):
    """get_embedding_function() uses OLLAMA_URL env var when set."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("OLLAMA_URL", "http://custom:11434")

    with patch(
        "extractors.phase6_chromadb_loader.OllamaEmbeddingFunction"
    ) as mock_ef_cls:
        mock_ef_cls.return_value = MagicMock()
        from extractors.phase6_chromadb_loader import get_embedding_function

        get_embedding_function()

    mock_ef_cls.assert_called_once_with(
        model_name="nomic-embed-text",
        url="http://custom:11434/api/embeddings",
    )


def test_get_embedding_function_url_param():
    """get_embedding_function(url=...) uses the explicit url parameter."""
    from unittest.mock import MagicMock, patch

    with patch(
        "extractors.phase6_chromadb_loader.OllamaEmbeddingFunction"
    ) as mock_ef_cls:
        mock_ef_cls.return_value = MagicMock()
        from extractors.phase6_chromadb_loader import get_embedding_function

        get_embedding_function(url="http://explicit:11434")

    mock_ef_cls.assert_called_once_with(
        model_name="nomic-embed-text",
        url="http://explicit:11434/api/embeddings",
    )


def test_get_embedding_function_default_url(monkeypatch):
    """get_embedding_function() defaults to localhost when OLLAMA_URL not set."""
    from unittest.mock import MagicMock, patch

    monkeypatch.delenv("OLLAMA_URL", raising=False)

    with patch(
        "extractors.phase6_chromadb_loader.OllamaEmbeddingFunction"
    ) as mock_ef_cls:
        mock_ef_cls.return_value = MagicMock()
        from extractors.phase6_chromadb_loader import get_embedding_function

        get_embedding_function()

    mock_ef_cls.assert_called_once_with(
        model_name="nomic-embed-text",
        url="http://localhost:11434/api/embeddings",
    )


# ---------------------------------------------------------------------------
# INTG-03: Tool docstrings
# ---------------------------------------------------------------------------


def test_search_docstring_has_collection_hint():
    """search tool docstring contains collection hints for paragraphs, talks, citations."""
    from server import search

    doc = search.__doc__
    assert "paragraphs" in doc
    assert "talks" in doc
    assert "citations" in doc


def test_get_talk_docstring_has_workflow_hint():
    """get_talk tool docstring contains guidance to search first."""
    from server import get_talk

    doc = get_talk.__doc__
    assert "search" in doc.lower()


# ---------------------------------------------------------------------------
# OLLAMA_URL consolidation: _check_ollama passes resolved URL to get_embedding_function
# ---------------------------------------------------------------------------


def test_check_ollama_passes_resolved_url(monkeypatch):
    """_check_ollama passes resolve_ollama_url() result to get_embedding_function(url=...)."""
    monkeypatch.setenv("OLLAMA_URL", "http://custom-host:9999")
    captured_url = {}

    from extractors.phase6_chromadb_loader import get_embedding_function as original_get_ef

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
# TRANS-02: Health endpoint
# ---------------------------------------------------------------------------


def test_health_returns_200():
    """GET /health returns 200 with ok status when both deps are reachable."""
    mock_ef = MagicMock(return_value=[[0.1] * 10])
    mock_ef_cls = MagicMock(return_value=mock_ef)
    mock_client = MagicMock()
    mock_client.get_collection.return_value = MagicMock()

    with patch("server.get_embedding_function", mock_ef_cls), \
         patch("server.chromadb.PersistentClient", return_value=mock_client):
        from server import build_app
        app = build_app()
        client = TestClient(app)
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ollama"] == "reachable"
    assert data["chromadb"] == "reachable"


def test_health_ollama_down():
    """GET /health returns 503 when Ollama is unreachable."""
    mock_ef = MagicMock(side_effect=Exception("connection refused"))
    mock_ef_cls = MagicMock(return_value=mock_ef)
    mock_client = MagicMock()
    mock_client.get_collection.return_value = MagicMock()

    with patch("server.get_embedding_function", mock_ef_cls), \
         patch("server.chromadb.PersistentClient", return_value=mock_client):
        from server import build_app
        app = build_app()
        client = TestClient(app)
        response = client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data["ollama"] == "unreachable"
    assert data["status"] == "degraded"


def test_health_chromadb_down():
    """GET /health returns 503 when ChromaDB is unreachable."""
    mock_ef = MagicMock(return_value=[[0.1] * 10])
    mock_ef_cls = MagicMock(return_value=mock_ef)

    with patch("server.get_embedding_function", mock_ef_cls), \
         patch("server.chromadb.PersistentClient", side_effect=Exception("path not found")):
        from server import build_app
        app = build_app()
        client = TestClient(app)
        response = client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data["chromadb"] == "unreachable"
    assert data["status"] == "degraded"


# ---------------------------------------------------------------------------
# Wave 0: Dispatcher behavior tests (Plan 02 will make these pass)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_initialize_no_auth():
    """OAUTH-01: initialize succeeds without Authorization header."""
    from server import build_app
    with TestClient(build_app(), raise_server_exceptions=False) as client:
        resp = client.post("/", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
        })
    assert resp.status_code == 200
    assert "mcp-session-id" in resp.headers
    data = resp.json()
    assert data["result"]["protocolVersion"] == "2025-06-18"
    assert data["result"]["serverInfo"]["name"] == "lds-scripture-index"


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_tools_list_requires_auth():
    """OAUTH-01: tools/list without token returns 401."""
    from server import build_app
    with TestClient(build_app(), raise_server_exceptions=False) as client:
        # First initialize to get session
        init_resp = client.post("/", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
        })
        session_id = init_resp.headers["mcp-session-id"]
        # Then try tools/list without auth
        resp = client.post("/", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        }, headers={"mcp-session-id": session_id})
    assert resp.status_code == 401


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_tools_list_401_has_www_authenticate():
    """OAUTH-01: 401 response includes WWW-Authenticate header with resource_metadata."""
    from server import build_app
    with TestClient(build_app(), raise_server_exceptions=False) as client:
        init_resp = client.post("/", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
        })
        session_id = init_resp.headers["mcp-session-id"]
        resp = client.post("/", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        }, headers={"mcp-session-id": session_id})
    assert "www-authenticate" in resp.headers
    assert "resource_metadata" in resp.headers["www-authenticate"]


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_tools_list_valid_rs256():
    """OAUTH-02: tools/list succeeds with valid RS256 token (kid present)."""
    pass  # Plan 02: mock JWKSVerifier.verify_token to return payload


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_tools_list_valid_hs256():
    """OAUTH-02: tools/list succeeds with valid HS256 token (no kid, /userinfo)."""
    pass  # Plan 02: mock JWKSVerifier.verify_token to return payload


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_tools_list_static_fallback():
    """OAUTH-02: Static fallback validates SqliteKeyStore token when AUTH0_DOMAIN unset."""
    pass  # Plan 02: mock SqliteKeyStore.verify_token


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_protected_resource_metadata():
    """OAUTH-03: /.well-known/oauth-protected-resource returns RFC 9728 JSON."""
    from server import build_app
    with TestClient(build_app(), raise_server_exceptions=False) as client:
        resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    data = resp.json()
    assert "resource" in data
    assert "authorization_servers" in data
    assert "bearer_methods_supported" in data


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_fastmcp_removed():
    """SC-4: FastMCP and BaseHTTPMiddleware are absent from server.py."""
    import inspect
    import server
    source = inspect.getsource(server)
    assert "FastMCP" not in source
    assert "BaseHTTPMiddleware" not in source
    assert "streamable_http_app" not in source


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_head_returns_protocol_version():
    """HEAD / returns MCP-Protocol-Version header."""
    from server import build_app
    with TestClient(build_app(), raise_server_exceptions=False) as client:
        resp = client.head("/")
    assert resp.status_code == 200
    assert "mcp-protocol-version" in resp.headers


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_get_root_returns_405():
    """GET / returns 405 Method Not Allowed."""
    from server import build_app
    with TestClient(build_app(), raise_server_exceptions=False) as client:
        resp = client.get("/")
    assert resp.status_code == 405


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_delete_session_cleanup():
    """DELETE / with valid session ID removes the session."""
    from server import build_app
    with TestClient(build_app(), raise_server_exceptions=False) as client:
        init_resp = client.post("/", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
        })
        session_id = init_resp.headers["mcp-session-id"]
        resp = client.delete("/", headers={"mcp-session-id": session_id})
    assert resp.status_code == 200


@pytest.mark.skip(reason="Wave 0: requires Plan 02 dispatcher implementation")
def test_missing_session_returns_400():
    """POST tools/list without MCP-Session-Id returns 400."""
    from server import build_app
    with TestClient(build_app(), raise_server_exceptions=False) as client:
        resp = client.post("/", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        })
    assert resp.status_code == 400
