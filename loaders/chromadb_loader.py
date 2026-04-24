"""
Benchmark ChromaDB loader — accepts pre-computed embedding vectors.

Independent from the production loader (extractors/phase6_chromadb_loader.py).
Uses 4 collections with same names as production (CHROMADB_COLLECTION_NAMES)
against the benchmark Docker instance on port 8000.

Usage:
    from loaders.chromadb_loader import ChromaDBLoader
    from loaders.embeddings import embed
    loader = ChromaDBLoader("localhost", 8000, embed_fn=embed)
    loader.load(bundle)
"""
import logging
import sys
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).parent.parent))

import chromadb
from config.pipeline_config import CHROMADB_COLLECTION_NAMES
from loaders import BaseLoader
from loaders.shared_transforms import TalkBundle, prepare_talk_bundle

logger = logging.getLogger(__name__)


def _chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class ChromaDBLoader(BaseLoader):
    """
    Benchmark ChromaDB loader.

    Creates or gets 4 collections (talks, paragraphs, citations, footnotes)
    and upserts records using pre-computed embedding vectors (D-02).

    Collection names: same as production (CHROMADB_COLLECTION_NAMES) — benchmarking
    uses an isolated Docker instance on port 8000, so no naming conflict with production.
    """

    def __init__(
        self,
        host: str,
        port: int,
        embed_fn: Callable[[str], list[float]],
        batch_size: int = 100,
    ) -> None:
        super().__init__(host, port, embed_fn, batch_size)
        # Do NOT pass embedding_function= — collections use pre-computed vectors only (Pitfall 4)
        self._client = chromadb.HttpClient(host=host, port=port)

    def load(self, bundle: TalkBundle) -> None:
        """
        Load a single talk bundle into ChromaDB across all 4 collections.

        Calls prepare_talk_bundle() to get (doc, meta, id, vector) tuples,
        then upserts in batches of self.batch_size. Errors per batch are logged
        as WARNING and execution continues (D-07).
        """
        records = prepare_talk_bundle(*bundle, embed_fn=self.embed_fn)

        for key in ("talks", "paragraphs", "citations", "footnotes"):
            coll_name = CHROMADB_COLLECTION_NAMES[key]
            col = self._client.get_or_create_collection(name=coll_name)
            batch_records = records[key]

            for batch in _chunks(batch_records, self.batch_size):
                ids   = [r[2] for r in batch]
                docs  = [r[0] for r in batch]
                metas = [r[1] for r in batch]
                vecs  = [r[3] for r in batch]

                try:
                    col.upsert(
                        ids=ids,
                        documents=docs,
                        metadatas=metas,
                        embeddings=vecs,
                    )
                except Exception as e:
                    logger.warning(
                        "ChromaDB batch failed for collection %s: %s",
                        coll_name,
                        e,
                    )

    def query(
        self,
        collection: str,
        query_text: str,
        k: int,
        filter: dict | None = None,
    ) -> list[str]:
        """
        Query a ChromaDB collection and return the top-k document IDs.

        Args:
            collection: Collection name (e.g. "conference_talk_paragraphs").
            query_text: Query string to embed and search.
            k:          Number of results to return.
            filter:     Optional ChromaDB where-clause dict (e.g. {"book_name": "John"}).

        Returns:
            list[str] of document IDs (e.g. ["para_123", "para_456"]).
        """
        col = self._client.get_or_create_collection(name=collection)
        query_embedding = self.embed_fn(query_text)
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": k,
            "include": ["documents"],
        }
        if filter is not None:
            kwargs["where"] = filter
        result = col.query(**kwargs)
        ids = result.get("ids", [[]])[0]
        return list(ids)
