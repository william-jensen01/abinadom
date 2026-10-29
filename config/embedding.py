import os

import requests

# nomic-embed-text was trained with task prefixes; documents and queries must
# carry the matching prefix or retrieval quality degrades.
TASK_PREFIXES = {
    "document": "search_document: ",
    "query": "search_query: ",
}


class LlamaCppEmbedder:
    """
    HTTP-based embedder that calls llama-server's OpenAI-compatible /v1/embeddings endpoint.

    Accepts a list of strings and returns a list of float vectors, one per input,
    in input order. Texts are sent in sub-batches of `batch_size` per request.
    The task prefix is applied only to the text sent for embedding — callers keep
    (and store) the original text.
    """

    def __init__(
        self,
        base_url: str,
        task: str = "document",
        model: str = "nomic-embed-text",
        batch_size: int = 64,
        timeout: float = 60.0,
    ) -> None:
        if task not in TASK_PREFIXES:
            raise ValueError(f"Unknown task: {task!r}. Must be one of: {list(TASK_PREFIXES)}")
        self.base_url = base_url.rstrip("/")
        self.task = task
        self.prefix = TASK_PREFIXES[task]
        self.model = model
        self.batch_size = batch_size
        self.timeout = timeout
        self._session = requests.Session()

    def __call__(self, texts: list[str]) -> list[list[float]]:
        """
        Embed texts via llama-server /v1/embeddings.

        Args:
            texts: List of strings to embed.

        Returns:
            List of float vectors, one per input text, same order.

        Raises:
            requests.HTTPError: On a non-2xx response (llama-server returns 400/500
                when an input exceeds its physical batch size, -ub).
            ValueError: If the server returns a different number of vectors than inputs.
        """
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            chunk = texts[start : start + self.batch_size]
            response = self._session.post(
                f"{self.base_url}/v1/embeddings",
                json={"model": self.model, "input": [self.prefix + t for t in chunk]},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            if len(data) != len(chunk):
                raise ValueError(
                    f"Embedding server returned {len(data)} vectors for {len(chunk)} inputs"
                )
            embeddings.extend(item["embedding"] for item in data)
        return embeddings


def resolve_embedding_url() -> str:
    """
    Return the embedding server (llama-server) base URL.
    Override: Set EMBEDDING_URL env var (e.g. http://remote-host:8080).
    Default: http://localhost:8080
    """
    return os.environ.get("EMBEDDING_URL", "http://localhost:8080")


def get_embedding_function(url: str | None = None, task: str = "document") -> LlamaCppEmbedder:
    """
    Return a LlamaCppEmbedder configured for nomic-embed-text.

    url:  Optional base URL override. Defaults to resolve_embedding_url().
    task: "document" for indexing, "query" for search queries.
    """
    base_url = url or resolve_embedding_url()
    return LlamaCppEmbedder(base_url=base_url, task=task)
