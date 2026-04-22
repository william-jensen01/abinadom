"""
Integration tests for loaders/weaviate_loader.py.

Requires Weaviate running at localhost:8080 (HTTP) and localhost:50051 (gRPC).
Tests auto-skip when Docker is not running (D-08).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import os
import pytest

_WEAVIATE_HOST = os.environ.get("BENCHMARK_WEAVIATE_HOST", "10.0.0.231")
_WEAVIATE_PORT = int(os.environ.get("BENCHMARK_WEAVIATE_PORT", "8051"))


class TestWeaviateLoader:
    def setup_method(self, method):
        self.loader = None

    def teardown_method(self, method):
        if self.loader is not None:
            self.loader.close()

    def test_round_trip_paragraph(self, weaviate_available, talk_bundle):
        """Insert a talk bundle then near-vector query Paragraph class; expect the inserted object."""
        from loaders.weaviate_loader import WeaviateLoader
        from weaviate.classes.query import MetadataQuery

        def _mock_embed(text: str) -> list[float]:
            return [0.1] * 768

        self.loader = WeaviateLoader(_WEAVIATE_HOST, _WEAVIATE_PORT, embed_fn=_mock_embed, batch_size=10)
        self.loader.load(talk_bundle)

        col = self.loader._client.collections.use("Paragraph")
        results = col.query.near_vector(
            near_vector=[0.1] * 768,
            limit=1,
            return_metadata=MetadataQuery(distance=True),
        )
        assert len(results.objects) >= 1
        props = results.objects[0].properties
        assert props.get("talk_id") == 9999
