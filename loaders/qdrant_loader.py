"""
Qdrant loader for benchmark vector DB comparisons.

Creates 4 Qdrant collections (talks, paragraphs, citations, footnotes) with
COSINE distance, payload indexes for common filter fields, and batch-upserts
talk bundles using pre-computed embedding vectors.

Key implementation notes:
- Collection names are snake_case: talks, paragraphs, citations, footnotes
- Vector size is 768 (nomic-embed-text output dimension)
- Qdrant point IDs MUST be uint64 integers or UUID strings. Project doc_ids
  like "para_12345" are neither — they are hashed to uint64 via _str_to_uint64().
  The original string is preserved in payload["_doc_id"] for retrieval.
- Default (unnamed) vector field is used (simpler API for single-model benchmark)
"""
import hashlib
import logging
import struct
import sys
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
from loaders import BaseLoader
from loaders.shared_transforms import TalkBundle, prepare_talk_bundle_rich

logger = logging.getLogger(__name__)


def _str_to_uint64(s: str) -> int:
    """
    Hash a string to a stable uint64 for use as a Qdrant point ID.

    Qdrant point IDs must be unsigned 64-bit integers or UUID-format strings.
    Project doc_ids like "para_12345" are neither, so we derive a stable uint64
    from the SHA-256 digest (first 8 bytes, big-endian).

    The original string is stored in payload["_doc_id"] for retrieval.
    """
    digest = hashlib.sha256(s.encode()).digest()
    return struct.unpack(">Q", digest[:8])[0]


def _chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class QdrantLoader(BaseLoader):
    """
    Benchmark Qdrant loader.

    Creates 4 collections with COSINE distance and payload indexes, then
    batch-upserts records using pre-computed embedding vectors.
    """

    # Qdrant collection names are snake_case (per Claude's Discretion in CONTEXT.md)
    COLLECTIONS = ["talks", "paragraphs", "citations", "footnotes"]
    VECTOR_SIZE = 768  # nomic-embed-text output dimension

    def __init__(
        self,
        host: str,
        port: int,
        embed_fn: Callable[[str], list[float]],
        batch_size: int = 100,
    ) -> None:
        super().__init__(host, port, embed_fn, batch_size)
        self._client = QdrantClient(host=host, port=port)
        self._ensure_collections()

    def _ensure_collections(self) -> None:
        """Create Qdrant collections with payload indexes if they don't exist (idempotent)."""
        for name in self.COLLECTIONS:
            if not self._client.collection_exists(name):
                self._client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
            # Always ensure payload indexes exist — idempotent on pre-existing collections.
            # Indexes are required for Phase 22 filtered queries; without this guard they
            # would be absent when connecting to a collection created in a prior run.
            self._client.create_payload_index(
                name, "talk_id", PayloadSchemaType.INTEGER
            )
            self._client.create_payload_index(
                name, "conference_year", PayloadSchemaType.INTEGER
            )
            self._client.create_payload_index(
                name, "speaker_name", PayloadSchemaType.KEYWORD
            )

    def load(self, bundle: TalkBundle) -> None:
        """
        Load a single talk bundle into Qdrant across all 4 collections.

        Calls prepare_talk_bundle_rich() to get (doc, meta, id, vector) tuples.
        For each record, derives a uint64 point ID from the string doc_id and
        stores the original string in payload["_doc_id"]. Errors per record are
        logged as WARNING and the record is skipped (D-07).
        """
        records = prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)

        for coll_name in self.COLLECTIONS:
            for batch in _chunks(records[coll_name], self.batch_size):
                points: list[PointStruct] = []
                for doc, meta, doc_id, vector in batch:
                    try:
                        points.append(
                            PointStruct(
                                id=_str_to_uint64(doc_id),
                                vector=vector,
                                payload={
                                    **meta,
                                    "_doc_id": doc_id,   # original string for retrieval
                                    "_doc": doc,         # document text for retrieval
                                },
                            )
                        )
                    except Exception as e:
                        logger.warning("Qdrant skip %s: %s", doc_id, e)
                if points:
                    self._client.upsert(
                        collection_name=coll_name,
                        points=points,
                        wait=True,
                    )

    def query(
        self,
        collection: str,
        query_text: str,
        k: int,
        filter: dict | None = None,
    ) -> list[str]:
        """
        Query a Qdrant collection and return the top-k document IDs.

        Args:
            collection: Collection name (e.g. "paragraphs").
            query_text: Query string to embed and search.
            k:          Number of results to return.
            filter:     Optional filter dict (e.g. {"book_name": "John"}).
                        Translated to a Qdrant FieldCondition filter.

        Returns:
            list[str] of original document IDs (from payload["_doc_id"]).
        """
        from qdrant_client.models import Filter as QFilter, FieldCondition, MatchValue

        query_embedding = self.embed_fn(query_text)

        qdrant_filter = None
        if filter is not None:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter.items()
            ]
            qdrant_filter = QFilter(must=conditions)

        results = self._client.query_points(
            collection_name=collection,
            query=query_embedding,
            limit=k,
            query_filter=qdrant_filter,
            with_payload=["_doc_id"],
        )
        return [
            hit.payload.get("_doc_id", str(hit.id))
            for hit in results.points
        ]
