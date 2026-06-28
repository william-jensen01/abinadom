import os

import requests


class OllamaEmbedder:
    """
    HTTP-based embedder that calls the Ollama /api/embeddings endpoint.

    Accepts a list of strings and returns a list of float vectors.
    One HTTP request is made per text in the input list.
    """

    def __init__(self, base_url: str, model: str = "nomic-embed-text") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def __call__(self, texts: list[str]) -> list[list[float]]:
        """
        Embed each text via the Ollama /api/embeddings endpoint.

        Args:
            texts: List of strings to embed.

        Returns:
            List of float vectors, one per input text.
        """
        embeddings = []
        for text in texts:
            payload = {"model": self.model, "prompt": text}
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json=payload,
            )
            response.raise_for_status()
            embeddings.append(response.json()["embedding"])
        return embeddings


def resolve_ollama_url() -> str:
    """
    Return the Ollama base URL.
    Override: Set OLLAMA_URL env var (e.g. http://remote-host:11434).
    Default: http://localhost:11434
    """
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


def get_embedding_function(url: str | None = None) -> OllamaEmbedder:
    """
    Return an OllamaEmbedder configured for nomic-embed-text.

    url: Optional base URL override. Defaults to resolve_ollama_url().
    """
    base_url = url or resolve_ollama_url()
    return OllamaEmbedder(base_url=base_url, model="nomic-embed-text")
