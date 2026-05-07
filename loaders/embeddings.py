"""
Ollama embedding helper for vector DB loaders.

Provides a synchronous embed() function that calls Ollama nomic-embed-text
and returns a 768-dimensional float vector (D-04, D-05).

Import and inject as embed_fn at loader constructor time:
    from loaders.embeddings import embed
    loader = ChromaDBLoader("localhost", 8000, embed_fn=embed)

For batch embedding (one Ollama round-trip for N texts):
    from loaders.embeddings import embed_batch
    loader = ChromaDBLoader("localhost", 8000, embed_fn=embed_batch)
"""
import atexit
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import ollama

OLLAMA_URL = "http://localhost:11434"

# Module-level singleton reused across all embed() calls.
# atexit closes the underlying httpx session to prevent ResourceWarning on exit.
_client = ollama.Client(host=OLLAMA_URL)
atexit.register(_client._client.close)


def embed(
    text: str,
    model: str = "nomic-embed-text",
) -> list[float]:
    """
    Return a 768-dim float vector from Ollama nomic-embed-text.

    Uses the module-level singleton _client (created from OLLAMA_URL at import time).
    To use a different Ollama endpoint, set the OLLAMA_URL environment variable before
    importing this module.

    Args:
        text:  Input text to embed.
        model: Ollama model name. Default "nomic-embed-text" (768 dims).

    Returns:
        list[float] of length 768.

    Raises:
        Exception: Propagates any Ollama connection or model errors.
                   Callers (loaders) handle exceptions at the batch level (D-07).
    """
    response = _client.embed(model=model, input=text)
    # EmbedResponse.embeddings: Sequence[Sequence[float]]
    # Single input -> embeddings[0] is the 768-element vector
    return list(response.embeddings[0])


def embed_batch(
    texts: list[str],
    model: str = "nomic-embed-text",
) -> list[list[float]]:
    """
    Return a list of 768-dim float vectors from Ollama nomic-embed-text.
    Sends all texts in a single HTTP round-trip via Ollama batch embed API.

    Uses the module-level singleton _client (created from OLLAMA_URL at import time).
    To use a different Ollama endpoint, set the OLLAMA_URL environment variable before
    importing this module.

    Args:
        texts: Input texts to embed (list of strings).
        model: Ollama model name. Default "nomic-embed-text" (768 dims).

    Returns:
        list[list[float]], one vector per input text, same order.

    Raises:
        Exception: Propagates any Ollama connection or model errors.
    """
    response = _client.embed(model=model, input=texts)
    return [list(v) for v in response.embeddings]
