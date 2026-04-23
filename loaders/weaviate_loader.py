"""
Weaviate loader for benchmark vector DB comparisons.

Creates 4 Weaviate classes (Talk, Paragraph, Citation, Footnote) with fully typed
property schemas and batch-loads talk bundles using pre-computed embedding vectors.

Key implementation notes:
- Collection names are PascalCase per Weaviate convention: Talk, Paragraph, Citation, Footnote
- Vectorizer is disabled (pre-computed vectors passed explicitly per benchmark design)
- UUIDs are derived deterministically from doc_id strings via generate_uuid5()
- Client connection requires both HTTP port (8080) and gRPC port (50051)
- Client must be closed via close() to release gRPC connections (Pitfall 1)
"""
import logging
import sys
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).parent.parent))

import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import DataType, Property, Configure
from weaviate.util import generate_uuid5
from loaders import BaseLoader
from loaders.shared_transforms import TalkBundle, prepare_talk_bundle_rich

logger = logging.getLogger(__name__)


class WeaviateLoader(BaseLoader):
    """
    Benchmark Weaviate loader.

    Creates 4 Weaviate classes with fully typed schemas and batch-inserts records
    using pre-computed embedding vectors. Schema creation is idempotent.

    Usage:
        loader = WeaviateLoader("localhost", 8080, embed_fn=my_embed)
        loader.load(talk_bundle)
        loader.close()  # REQUIRED — releases gRPC connection

    Or wrap in try/finally:
        loader = WeaviateLoader("localhost", 8080, embed_fn=my_embed)
        try:
            loader.load(bundle)
        finally:
            loader.close()
    """

    # Weaviate class names are PascalCase (per Weaviate naming convention)
    COLLECTIONS = ["Talk", "Paragraph", "Citation", "Footnote"]

    def __init__(
        self,
        host: str,
        port: int,
        embed_fn: Callable[[str], list[float]],
        batch_size: int = 100,
    ) -> None:
        super().__init__(host, port, embed_fn, batch_size)
        # MUST include grpc_port=50051 — Weaviate Docker exposes both 8080 and 50051 (Pitfall 3)
        self._client = weaviate.connect_to_local(
            host=host,
            port=port,
            grpc_port=50051,
        )
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create Weaviate classes if they don't exist (idempotent)."""
        if not self._client.collections.exists("Talk"):
            self._client.collections.create(
                name="Talk",
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=self._talk_properties(),
            )
        if not self._client.collections.exists("Paragraph"):
            self._client.collections.create(
                name="Paragraph",
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=self._paragraph_properties(),
            )
        if not self._client.collections.exists("Citation"):
            self._client.collections.create(
                name="Citation",
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=self._citation_properties(),
            )
        if not self._client.collections.exists("Footnote"):
            self._client.collections.create(
                name="Footnote",
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=self._footnote_properties(),
            )

    def _talk_properties(self) -> list:
        """Property schema for Talk class — covers all TalkMetadata fields."""
        return [
            Property(name="talk_id", data_type=DataType.INT),
            Property(name="speaker_id", data_type=DataType.INT),
            Property(name="conference_id", data_type=DataType.INT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="speaker_name", data_type=DataType.TEXT),
            Property(name="conference_year", data_type=DataType.INT),
            Property(name="conference_month", data_type=DataType.TEXT),
            Property(name="conference_description", data_type=DataType.TEXT),
            Property(name="talk_date", data_type=DataType.TEXT),
            Property(name="session_id", data_type=DataType.INT),
            Property(name="session_description", data_type=DataType.TEXT),
            Property(name="session_abbr", data_type=DataType.TEXT),
            Property(name="session_date", data_type=DataType.TEXT),
            Property(name="session_sequence", data_type=DataType.INT),
            Property(name="talk_sequence", data_type=DataType.INT),
            Property(name="url", data_type=DataType.TEXT),
            Property(name="uri_l", data_type=DataType.TEXT),
            Property(name="uri_gc", data_type=DataType.TEXT),
            Property(name="data_aid", data_type=DataType.TEXT),
            Property(name="audio_url", data_type=DataType.TEXT),
            Property(name="video_low_url", data_type=DataType.TEXT),
            Property(name="video_med_url", data_type=DataType.TEXT),
            Property(name="video_high_url", data_type=DataType.TEXT),
            Property(name="corpus", data_type=DataType.TEXT),
            Property(name="speaker_role_id", data_type=DataType.INT),
            Property(name="kicker", data_type=DataType.TEXT),
            Property(name="talk_preview", data_type=DataType.TEXT),
            Property(name="topics", data_type=DataType.TEXT_ARRAY),
            Property(name="start_page_num", data_type=DataType.INT),
            Property(name="end_page_num", data_type=DataType.INT),
            Property(name="extraction_timestamp", data_type=DataType.TEXT),
            Property(name="extraction_version", data_type=DataType.TEXT),
            Property(name="annotations", data_type=DataType.TEXT),
        ]

    def _paragraph_properties(self) -> list:
        """Property schema for Paragraph class — covers all ParagraphData fields."""
        return [
            Property(name="paragraph_id", data_type=DataType.INT),
            Property(name="talk_id", data_type=DataType.INT),
            Property(name="paragraph_number", data_type=DataType.INT),
            Property(name="text", data_type=DataType.TEXT),
            Property(name="text_raw", data_type=DataType.TEXT),
            Property(name="word_count", data_type=DataType.INT),
            Property(name="source_type", data_type=DataType.TEXT),
            Property(name="list_header", data_type=DataType.TEXT),
            Property(name="list_item_index", data_type=DataType.INT),
            Property(name="position_in_item", data_type=DataType.INT),
            Property(name="has_scripture_citation", data_type=DataType.BOOL),
            Property(name="has_footnote", data_type=DataType.BOOL),
            Property(name="citation_count", data_type=DataType.INT),
            Property(name="footnote_count", data_type=DataType.INT),
            # Injected by prepare_paragraph_records when talk_metadata is provided
            Property(name="speaker_name", data_type=DataType.TEXT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="conference_year", data_type=DataType.INT),
            Property(name="conference_month", data_type=DataType.TEXT),
        ]

    def _citation_properties(self) -> list:
        """Property schema for Citation class — covers all CitationData fields."""
        return [
            Property(name="citation_id", data_type=DataType.INT),
            Property(name="talk_id", data_type=DataType.INT),
            Property(name="paragraph_id", data_type=DataType.INT),
            Property(name="paragraph_number", data_type=DataType.INT),
            Property(name="citation_text_raw", data_type=DataType.TEXT),
            Property(name="char_position", data_type=DataType.INT),
            Property(name="char_end_position", data_type=DataType.INT),
            Property(name="scripture_ref", data_type=DataType.TEXT),
            Property(name="book", data_type=DataType.TEXT),
            Property(name="book_abbr", data_type=DataType.TEXT),
            Property(name="book_id", data_type=DataType.INT),
            Property(name="chapter", data_type=DataType.INT),
            Property(name="verses", data_type=DataType.TEXT),
            Property(name="verse_start", data_type=DataType.INT),
            Property(name="verse_end", data_type=DataType.INT),
            Property(name="verse_list", data_type=DataType.INT_ARRAY),
            Property(name="is_jst", data_type=DataType.BOOL),
            Property(name="citation_location", data_type=DataType.TEXT),
            Property(name="parse_success", data_type=DataType.BOOL),
            Property(name="parse_source", data_type=DataType.TEXT),
            Property(name="parse_pattern", data_type=DataType.TEXT),
            Property(name="parse_confidence", data_type=DataType.NUMBER),
            Property(name="context_before", data_type=DataType.TEXT),
            Property(name="context_after", data_type=DataType.TEXT),
            Property(name="context_window", data_type=DataType.TEXT),
        ]

    def _footnote_properties(self) -> list:
        """Property schema for Footnote class — covers all FootnoteData fields."""
        return [
            Property(name="footnote_id", data_type=DataType.INT),
            Property(name="talk_id", data_type=DataType.INT),
            Property(name="paragraph_id", data_type=DataType.INT),
            Property(name="paragraph_number", data_type=DataType.INT),
            Property(name="footnote_number", data_type=DataType.INT),
            Property(name="footnote_text_raw", data_type=DataType.TEXT),
            Property(name="char_position", data_type=DataType.INT),
            Property(name="context_before", data_type=DataType.TEXT),
            Property(name="context_after", data_type=DataType.TEXT),
            Property(name="context_window", data_type=DataType.TEXT),
            Property(name="parse_success", data_type=DataType.BOOL),
        ]

    def load(self, bundle: TalkBundle) -> None:
        """
        Load a single talk bundle into Weaviate across all 4 classes.

        Calls prepare_talk_bundle_rich() to get (doc, meta, id, vector) tuples,
        then batch-inserts using fixed_size batches. After each batch context exits,
        checks failed_objects and logs any errors as WARNING (D-07, Pitfall 5).

        The rich bundle uses rich_metadata() so list fields (topics, verse_list)
        are preserved as native Python lists for Weaviate's TEXT_ARRAY / INT_ARRAY.
        """
        # Map from shared_transforms dict key -> Weaviate class name
        collection_map = {
            "talks": "Talk",
            "paragraphs": "Paragraph",
            "citations": "Citation",
            "footnotes": "Footnote",
        }
        records = prepare_talk_bundle_rich(*bundle, embed_fn=self.embed_fn)

        for key, class_name in collection_map.items():
            col = self._client.collections.use(class_name)
            with col.batch.fixed_size(batch_size=self.batch_size) as batch_ctx:
                for doc, meta, doc_id, vector in records[key]:
                    try:
                        batch_ctx.add_object(
                            properties=meta,
                            uuid=generate_uuid5(doc_id),
                            vector=vector,
                        )
                    except Exception as e:
                        logger.warning("Weaviate skip %s: %s", doc_id, e)
            # Check failed_objects on the context manager object (batch_ctx), not col.batch.
            # In weaviate-client v4, failed_objects is a property of the batch context object.
            if batch_ctx.failed_objects:
                for err in batch_ctx.failed_objects:
                    logger.warning(
                        "Weaviate batch error in class %s: %s",
                        class_name,
                        err,
                    )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self) -> None:
        """Close the Weaviate client and release the gRPC connection (Pitfall 1)."""
        self._client.close()
