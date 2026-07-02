"""
loaders package — BaseLoader ABC and DB-specific loader implementations.

BaseLoader enforces the uniform load(bundle) interface (D-03).
Phase 22 benchmark runner imports `BaseLoader` and iterates over a list[BaseLoader].
"""
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).parent.parent))

from loaders.shared_transforms import TalkBundle


class BaseLoader(ABC):
    """
    Abstract base class for all vector DB loaders.

    Constructor args:
        embed_fn:   Callable that accepts list[str] and returns list[list[float]].
                    Injected at constructor time; same function used for all .load() calls.
        batch_size: Number of records per write batch. Default 100.
    """

    def __init__(
        self,
        embed_fn: Callable[[list[str]], list[list[float]]],
        batch_size: int = 100,
    ) -> None:
        self.embed_fn = embed_fn
        self.batch_size = batch_size

    def close(self) -> None:
        """Release any held connections. Default is no-op. Override when needed."""
        pass

    def flush(self) -> None:
        """Flush any buffered records to the target DB. Default is no-op."""
        pass

    @abstractmethod
    def query(
        self,
        collection: str,
        query_text: str,
        k: int,
        filter: dict | None = None,
    ) -> list[str]:
        """Query the target DB and return top-k document IDs."""
        ...

    @abstractmethod
    def load(self, bundle: TalkBundle) -> None:
        """
        Load a single talk bundle into the target vector DB.

        Implementations must:
        - Accept a TalkBundle (5-tuple of Phase 1-5 outputs)
        - Call prepare_talk_bundle() from shared_transforms
        - Upsert all 4 collections (talks, paragraphs, citations, footnotes)
        - Skip-and-log bad records per D-07 (log WARNING, continue)
        - Be idempotent: re-loading same bundle must not create duplicates
        """
        ...
