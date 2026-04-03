import os


def resolve_ollama_url() -> str:
    """
    Return the Ollama base URL.
    Override: Set OLLAMA_URL env var (e.g. http://remote-host:11434).
    Default: http://localhost:11434
    """
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")
