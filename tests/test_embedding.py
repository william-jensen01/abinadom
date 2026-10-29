"""
Unit tests for config/embedding.py (llama-server embedding client).

All HTTP is mocked except test_embed_live, which hits the real embedding
server and auto-skips when it is unreachable.
"""
from unittest.mock import MagicMock

import pytest
import requests

from config.embedding import (
    LlamaCppEmbedder,
    get_embedding_function,
    resolve_embedding_url,
)
from tests.conftest import EMBEDDING_URL


def _response(indices_and_vectors):
    resp = MagicMock()
    resp.json.return_value = {
        "data": [{"index": i, "embedding": vec} for i, vec in indices_and_vectors]
    }
    resp.raise_for_status.return_value = None
    return resp


def _embedder(task="document", batch_size=64, responses=None):
    ef = LlamaCppEmbedder("http://x:1", task=task, batch_size=batch_size)
    ef._session = MagicMock()
    if responses is not None:
        ef._session.post.side_effect = responses
    return ef


def _posted_inputs(ef):
    return [c.kwargs["json"]["input"] for c in ef._session.post.call_args_list]


def test_document_task_prefixes_input():
    ef = _embedder(responses=[_response([(0, [0.1]), (1, [0.2])])])
    out = ef(["a", "b"])
    assert out == [[0.1], [0.2]]
    assert ef._session.post.call_count == 1
    args, kwargs = ef._session.post.call_args
    assert args[0].endswith("/v1/embeddings")
    assert kwargs["json"]["input"] == ["search_document: a", "search_document: b"]


def test_query_task_prefixes_input():
    ef = _embedder(task="query", responses=[_response([(0, [0.3])])])
    ef(["q"])
    assert _posted_inputs(ef) == [["search_query: q"]]


def test_results_reordered_by_index():
    ef = _embedder(responses=[_response([(1, [2.0]), (0, [1.0])])])
    assert ef(["a", "b"]) == [[1.0], [2.0]]


def test_sub_batching():
    responses = [
        _response([(0, [1.0]), (1, [2.0])]),
        _response([(0, [3.0]), (1, [4.0])]),
        _response([(0, [5.0])]),
    ]
    ef = _embedder(batch_size=2, responses=responses)
    out = ef(["t1", "t2", "t3", "t4", "t5"])
    assert [len(i) for i in _posted_inputs(ef)] == [2, 2, 1]
    assert out == [[1.0], [2.0], [3.0], [4.0], [5.0]]


def test_empty_input_makes_no_request():
    ef = _embedder()
    assert ef([]) == []
    ef._session.post.assert_not_called()


def test_http_error_propagates():
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.HTTPError("500")
    ef = _embedder(responses=[resp])
    with pytest.raises(requests.HTTPError):
        ef(["a"])


def test_count_mismatch_raises():
    ef = _embedder(responses=[_response([(0, [1.0])])])
    with pytest.raises(ValueError):
        ef(["a", "b"])


def test_unknown_task_rejected():
    with pytest.raises(ValueError):
        LlamaCppEmbedder("http://x", task="bogus")


def test_resolve_embedding_url_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_URL", "http://h:9")
    assert resolve_embedding_url() == "http://h:9"
    monkeypatch.delenv("EMBEDDING_URL", raising=False)
    assert resolve_embedding_url() == "http://localhost:8080"


def test_get_embedding_function_trailing_slash():
    ef = get_embedding_function(url="http://h:9/", task="query")
    assert ef.base_url == "http://h:9"
    assert ef.prefix == "search_query: "


def test_embed_live(embedding_available):
    vectors = get_embedding_function(url=EMBEDDING_URL)(["hello"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 768
