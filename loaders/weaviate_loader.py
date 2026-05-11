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
from weaviate.classes.data import DataObject
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
        embed_fn: Callable[[list[str]], list[list[float]]],
        batch_size: int = 100,
        grpc_port: int = 50051,
    ) -> None:
        super().__init__(host, port, embed_fn, batch_size)
        # MUST include grpc_port — Weaviate Docker exposes both HTTP and gRPC ports (Pitfall 3)
        self._client = weaviate.connect_to_local(
            host=host,
            port=port,
            grpc_port=grpc_port,
        )
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create Weaviate classes if they don't exist (idempotent)."""
        if not self._client.collections.exists("Talk"):
            self._client.collections.create(
                name="Talk",
                vector_config=wvc.config.Configure.Vectors.self_provided(),
                properties=self._talk_properties(),
            )
        if not self._client.collections.exists("Paragraph"):
            self._client.collections.create(
                name="Paragraph",
                vector_config=wvc.config.Configure.Vectors.self_provided(),
                properties=self._paragraph_properties(),
            )
        if not self._client.collections.exists("Citation"):
            self._client.collections.create(
                name="Citation",
                vector_config=wvc.config.Configure.Vectors.self_provided(),
                properties=self._citation_properties(),
            )
        if not self._client.collections.exists("Footnote"):
            self._client.collections.create(
                name="Footnote",
                vector_config=wvc.config.Configure.Vectors.self_provided(),
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
            Property(name="doc_id_str",  data_type=DataType.TEXT),
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
            Property(name="doc_id_str",       data_type=DataType.TEXT),
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
            Property(name="doc_id_str",     data_type=DataType.TEXT),
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
            Property(name="doc_id_str",    data_type=DataType.TEXT),
        ]

    def load(self, bundle: TalkBundle) -> None:
        """
        Load a single talk bundle into Weaviate across all 4 classes.

        Calls prepare_talk_bundle_rich() to get (doc, meta, id, vector) tuples,
        then insert_many for each collection. Errors are logged as WARNING
        (D-03, D-04) and execution continues to the next collection.

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
            objects = [
                DataObject(
                    properties={**meta, "doc_id_str": doc_id},
                    uuid=generate_uuid5(doc_id),
                    vector={"default": vector},
                )
                for doc, meta, doc_id, vector in records[key]
            ]
            if not objects:
                continue
            try:
                result = col.data.insert_many(objects)
                if result.has_errors:
                    for obj_idx, err in result.errors.items():
                        logger.warning(
                            "Weaviate insert error in %s idx=%s: %s",
                            class_name,
                            obj_idx,
                            err,
                        )
            except Exception as e:
                logger.warning(
                    "Weaviate insert_many error in %s: %s",
                    class_name,
                    e,
                )
                # continue to next collection — never crash a talk load (D-04)

    def talk_exists(self, talk_id: int) -> bool:
        from weaviate.util import generate_uuid5
        col = self._client.collections.use("ConferenceTalks")
        obj = col.query.fetch_object_by_id(generate_uuid5(f"talk_{talk_id}"))
        return obj is not None

    def query(
        self,
        collection: str,
        query_text: str,
        k: int,
        filter: dict | None = None,
    ) -> list[str]:
        """
        Query a Weaviate collection and return the top-k document IDs.

        Args:
            collection: Collection name in snake_case (e.g. "paragraphs").
                        Mapped to PascalCase Weaviate class name internally.
            query_text: Query string to embed and search.
            k:          Number of results to return.
            filter:     Optional filter dict (e.g. {"book_name": "John"}).
                        Translated to a Weaviate Filter object.

        Returns:
            list[str] of document IDs (from the "doc_id_str" metadata field,
            falls back to UUID string if not present).
        """
        # Map snake_case collection name to PascalCase Weaviate class
        name_map = {
            "talks": "Talk",
            "paragraphs": "Paragraph",
            "citations": "Citation",
            "footnotes": "Footnote",
            # Accept PascalCase directly too
            "Talk": "Talk",
            "Paragraph": "Paragraph",
            "Citation": "Citation",
            "Footnote": "Footnote",
        }
        class_name = name_map.get(collection, collection)
        if class_name not in ["Talk", "Paragraph", "Citation", "Footnote"]:
            raise ValueError(
                f"Unknown collection: {collection!r}. "
                "Must be one of: talks, paragraphs, citations, footnotes, "
                "Talk, Paragraph, Citation, Footnote"
            )
        col = self._client.collections.use(class_name)
        query_embedding = self.embed_fn([query_text])[0]

        from weaviate.classes.query import Filter

        kwargs: dict = {"near_vector": query_embedding, "limit": k, "target_vector": "default"}
        if filter is not None:
            # Build a simple equality filter for each key-value pair
            conditions = [Filter.by_property(prop).equal(v) for prop, v in filter.items()]
            if len(conditions) == 1:
                kwargs["filters"] = conditions[0]
            else:
                combined = conditions[0]
                for cond in conditions[1:]:
                    combined = combined & cond
                kwargs["filters"] = combined

        result = col.query.near_vector(**kwargs)
        return [obj.properties.get("doc_id_str", str(obj.uuid)) for obj in result.objects]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self) -> None:
        """Close the Weaviate client and release the gRPC connection (Pitfall 1)."""
        self._client.close()

    @classmethod
    def reset(cls, host: str, port: int, grpc_port: int = 50051) -> None:
        """Delete all 4 Weaviate classes (Talk, Paragraph, Citation, Footnote) per D-02.

        Swallows NotFound — safe to call on a fresh stack.
        Caller must instantiate a new WeaviateLoader after this returns.
        """
        client = weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port)
        try:
            for class_name in cls.COLLECTIONS:
                try:
                    client.collections.delete(class_name)
                    logger.info("Weaviate: deleted collection %r", class_name)
                except Exception as e:
                    logger.debug("Weaviate: delete(%r) skipped: %s", class_name, e)
        finally:
            try:
                client.close()
            except Exception:
                pass
