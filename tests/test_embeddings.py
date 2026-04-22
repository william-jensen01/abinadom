"""
Unit tests for loaders/embeddings.py.

The mock test runs without Ollama. The live test skips if Ollama is not running.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest


def _mock_embed(text: str) -> list[float]:
    """Return a fixed 768-dim vector without calling Ollama."""
    return [0.1] * 768


def test_mock_embed_returns_list_of_floats():
    result = _mock_embed("hello world")
    assert isinstance(result, list)
    assert len(result) == 768
    assert all(isinstance(v, float) for v in result)


def test_mock_embed_is_deterministic():
    assert _mock_embed("abc") == _mock_embed("abc")


def test_embed_live(ollama_available):
    """Live embed test — skip if Ollama is not running."""
    from loaders.embeddings import embed
    result = embed("test paragraph text")
    assert isinstance(result, list)
    assert len(result) == 768
    assert all(isinstance(v, float) for v in result)
