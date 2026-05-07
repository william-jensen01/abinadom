"""
Integration tests for loaders/qdrant_loader.py.

Requires Qdrant running at localhost:6333.
Tests auto-skip when Docker is not running (D-08).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import os
import pytest

_QDRANT_HOST = os.environ.get("BENCHMARK_QDRANT_HOST", "10.0.0.231")
_QDRANT_PORT = int(os.environ.get("BENCHMARK_QDRANT_PORT", "6333"))


class TestQdrantLoader:
    def setup_method(self, method):
        self.loader = None

    def teardown_method(self, method):
        if self.loader is not None:
            self.loader.close()

    def test_round_trip_paragraph(self, qdrant_available, talk_bundle):
        """Insert a talk bundle then vector search paragraphs collection; expect the inserted point."""
        from loaders.qdrant_loader import QdrantLoader

        def _mock_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1] * 768 for _ in texts]

        self.loader = QdrantLoader(_QDRANT_HOST, _QDRANT_PORT, embed_fn=_mock_embed, batch_size=10)
        loader = self.loader
        loader.load(talk_bundle)

        results = loader._client.query_points(
            collection_name="paragraphs",
            query=[0.1] * 768,
            limit=1,
            with_payload=True,
        )
        assert len(results.points) >= 1
        payload = results.points[0].payload
        # Original string doc_id stored in payload["_doc_id"] (not the uint64 point ID)
        assert "_doc_id" in payload
        assert payload.get("talk_id") == 9999
