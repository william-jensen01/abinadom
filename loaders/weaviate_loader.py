"""
Weaviate loader — production collection names, client injection.

Creates 4 Weaviate collections with fully typed property schemas and batch-loads
talk bundles using pre-computed embedding vectors.

Key implementation notes:
- Collection names come from WEAVIATE_COLLECTION_NAMES in config/pipeline_config.py
- Vectorizer is disabled (pre-computed vectors passed explicitly)
- UUIDs are derived deterministically from doc_id strings via generate_uuid5()
- Client must be closed via close() to release gRPC connections
"""
import logging
import sys
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).parent.parent))

import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import DataType, Property
from weaviate.classes.data import DataObject
from weaviate.util import generate_uuid5
from loaders import BaseLoader
from loaders.shared_transforms import TalkBundle, prepare_talk_bundle
from config.pipeline_config import WEAVIATE_COLLECTION_NAMES

logger = logging.getLogger(__name__)


class WeaviateLoader(BaseLoader):
    """
    Weaviate loader.

    Creates 4 Weaviate collections with fully typed schemas and batch-inserts records
    using pre-computed embedding vectors. Schema creation is idempotent.

    Usage:
        client = get_weaviate_client()
        with WeaviateLoader(client=client, embed_fn=my_embed) as loader:
            loader.load(talk_bundle)
    """

    def __init__(
        self,
        client: weaviate.WeaviateClient,
        embed_fn: Callable[[list[str]], list[list[float]]],
        batch_size: int = 1000,
        buffered: bool = False,
    ) -> None:
        super().__init__(embed_fn, batch_size)
        self._client = client
        self._buffered = buffered
        self._buffers: dict[str, list[DataObject]] = {
            key: [] for key in WEAVIATE_COLLECTION_NAMES
        }
        self._buffer_talk_count: int = 0
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create Weaviate collections if they don't exist (idempotent)."""
        props_map = {
            "talks": self._talk_properties(),
            "paragraphs": self._paragraph_properties(),
            "citations": self._citation_properties(),
            "footnotes": self._footnote_properties(),
        }
        for key, name in WEAVIATE_COLLECTION_NAMES.items():
            if not self._client.collections.exists(name):
                self._client.collections.create(
                    name=name,
                    vector_config=wvc.config.Configure.Vectors.self_provided(),
                    properties=props_map[key],
                )

    def _talk_properties(self) -> list:
        """Property schema for talks collection — covers all TalkMetadata fields."""
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
            Property(name="doc_id_str", data_type=DataType.TEXT),
        ]

    def _paragraph_properties(self) -> list:
        """Property schema for paragraphs collection — covers all ParagraphData fields."""
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
            Property(name="speaker_name", data_type=DataType.TEXT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="conference_year", data_type=DataType.INT),
            Property(name="conference_month", data_type=DataType.TEXT),
            Property(name="doc_id_str", data_type=DataType.TEXT),
        ]

    def _citation_properties(self) -> list:
        """Property schema for citations collection — covers all CitationData fields."""
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
            Property(name="doc_id_str", data_type=DataType.TEXT),
        ]

    def _footnote_properties(self) -> list:
        """Property schema for footnotes collection — covers all FootnoteData fields."""
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
            Property(name="doc_id_str", data_type=DataType.TEXT),
        ]

    def load(self, bundle: TalkBundle) -> None:
        """
        Load a single talk bundle into Weaviate across all 4 collections.

        Builds (doc, meta, id, vector) tuples via prepare_talk_bundle() and
        appends DataObjects to per-collection buffers. In buffered mode, buffers
        flush when any reaches batch_size (see _flush_if_needed); in unbuffered
        mode (default) each call flushes immediately, matching per-talk inserts.
        """
        records = prepare_talk_bundle(*bundle, embed_fn=self.embed_fn)

        any_buffered = False
        for key in WEAVIATE_COLLECTION_NAMES:
            objects = [
                DataObject(
                    properties={**meta, "doc_id_str": doc_id},
                    uuid=generate_uuid5(doc_id),
                    vector={"default": vector},
                )
                for doc, meta, doc_id, vector in records[key]
            ]
            if objects:
                self._buffers[key].extend(objects)
                any_buffered = True

        if any_buffered:
            self._buffer_talk_count += 1

        if self._buffered:
            self._flush_if_needed()
        else:
            self.flush()

    def _flush_if_needed(self) -> None:
        """Flush buffers if any collection buffer has reached batch_size."""
        if any(len(buf) >= self.batch_size for buf in self._buffers.values()):
            self.flush()

    def flush(self) -> None:
        """Flush all buffered objects to Weaviate, dependents first, talks last.

        Write order (paragraphs, citations, footnotes, talks) is a crash-safety
        measure: talk_exists() checks only the talks collection, so writing talks
        last guarantees a mid-flush crash leaves the talk looking un-processed,
        triggering safe reprocessing on resume (inserts are idempotent via
        deterministic UUIDs). Buffers are always cleared, even on error, to avoid
        infinite retry loops; any lost objects are safely reprocessed next run.
        """
        total = sum(len(buf) for buf in self._buffers.values())
        if total == 0:
            return

        logger.info(
            "Flushing %d buffered objects (%d talks) to Weaviate",
            total,
            self._buffer_talk_count,
        )

        flush_order = ["paragraphs", "citations", "footnotes", "talks"]
        for key in flush_order:
            objects = self._buffers[key]
            if not objects:
                continue
            class_name = WEAVIATE_COLLECTION_NAMES[key]
            col = self._client.collections.use(class_name)
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
                    "Weaviate insert_many error in %s (%d objects): %s",
                    class_name,
                    len(objects),
                    e,
                )

        self._buffers = {key: [] for key in WEAVIATE_COLLECTION_NAMES}
        self._buffer_talk_count = 0

    def talk_exists(self, talk_id: int) -> bool:
        col = self._client.collections.use(WEAVIATE_COLLECTION_NAMES["talks"])
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
            collection: snake_case key ("talks", "paragraphs", etc.) or the actual
                        collection name ("ConferenceTalks", etc.).
            query_text: Query string to embed and search.
            k:          Number of results to return.
            filter:     Optional filter dict (e.g. {"book": "John"}).
        """
        name_map = {
            **WEAVIATE_COLLECTION_NAMES,
            **{v: v for v in WEAVIATE_COLLECTION_NAMES.values()},
        }
        class_name = name_map.get(collection, collection)
        if class_name not in WEAVIATE_COLLECTION_NAMES.values():
            raise ValueError(
                f"Unknown collection: {collection!r}. "
                f"Must be one of: {list(WEAVIATE_COLLECTION_NAMES.keys())} or "
                f"{list(WEAVIATE_COLLECTION_NAMES.values())}"
            )
        col = self._client.collections.use(class_name)
        query_embedding = self.embed_fn([query_text])[0]

        from weaviate.classes.query import Filter

        kwargs: dict = {"near_vector": query_embedding, "limit": k, "target_vector": "default"}
        if filter is not None:
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
        """Flush remaining buffers and close the Weaviate gRPC connection."""
        try:
            self.flush()
        finally:
            self._client.close()

    @staticmethod
    def reset(host: str, port: int, grpc_port: int = 50051) -> None:
        """Delete all Weaviate collections defined in WEAVIATE_COLLECTION_NAMES.

        Swallows NotFound — safe to call on a fresh stack.
        Caller must instantiate a new WeaviateLoader after this returns.
        """
        client = weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port)
        try:
            for name in WEAVIATE_COLLECTION_NAMES.values():
                try:
                    client.collections.delete(name)
                    logger.info("Weaviate: deleted collection %r", name)
                except Exception as e:
                    logger.debug("Weaviate: delete(%r) skipped: %s", name, e)
        finally:
            try:
                client.close()
            except Exception:
                pass
