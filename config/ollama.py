import os

from chromadb.utils.embedding_functions import OllamaEmbeddingFunction


def resolve_ollama_url() -> str:
    """
    Return the Ollama base URL.
    Override: Set OLLAMA_URL env var (e.g. http://remote-host:11434).
    Default: http://localhost:11434
    """
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


def get_embedding_function(url: str | None = None) -> OllamaEmbeddingFunction:
    """
    Return the OllamaEmbeddingFunction configured for nomic-embed-text.

    url: Optional base URL override. Defaults to resolve_ollama_url().
    """
    base_url = url or resolve_ollama_url()
    return OllamaEmbeddingFunction(
        model_name="nomic-embed-text",
        url=base_url + "/api/embeddings",
    )
