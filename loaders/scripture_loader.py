"""
Scripture loader: ScriptureVerses, ScriptureChapters and ScriptureMeta in Weaviate (SPEC-v2 sections 6-8).

Vectors are computed here (embed_fn, the document-task embedder) and passed explicitly. UUIDs are deterministic
(generate_uuid5 over the doc_id string), so a re-load replaces an object, and "already loaded" means "that UUID is
stored" (existence, not content: after changing an embed string or the window radius, reload with --force).

ScriptureMeta holds one object: `loading_build_id` is the build a run started loading (written before its first
insert); `build_id` is written only after a complete load.
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).parent.parent))

import weaviate
from weaviate.classes.config import Configure, DataType, Property, Tokenization
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter
from weaviate.util import generate_uuid5

from config.pipeline_config import (
    SCRIPTURE_WINDOW_RADIUS,
    WEAVIATE_SCRIPTURE_COLLECTION_NAMES as NAMES,
    WEAVIATE_SCRIPTURE_META_COLLECTION as META,
)
from loaders import BaseLoader
from loaders.shared_transforms import ScriptureBundle, prepare_chapter_records, prepare_verse_records

logger = logging.getLogger(__name__)

META_UUID = generate_uuid5("scripture_meta")


def _text(name: str, exact: bool = True) -> Property:
    """A TEXT property; `exact` (FIELD tokenization) indexes the whole value as one token, so filters match it exactly.

    `context_window` is exact too: it is embedded, not keyword-searched (`text` is), and FIELD keeps
    `context_window == ""` filterable (SCR-05), which word tokenization makes Weaviate reject.
    """
    return Property(name=name, data_type=DataType.TEXT, tokenization=Tokenization.FIELD if exact else Tokenization.WORD)


def _int(name: str) -> Property:
    return Property(name=name, data_type=DataType.INT)


def _refs(name: str) -> Property:
    return Property(name=name, data_type=DataType.TEXT_ARRAY, tokenization=Tokenization.FIELD)


SCHEMA = {
    NAMES["verses"]: [
        _text("variant"), _text("book"), _text("book_uri"), _text("cite_abbr"), _text("volume"),
        _int("chapter"), _int("verse"), _text("reference"), _text("text", exact=False),
        Property(name="has_jst", data_type=DataType.BOOL), _refs("jst_refs"), _refs("kjv_refs"),
        _text("aid"), _int("footnote_count"), _text("context_window"), _text("doc_id_str"),
    ],
    NAMES["chapters"]: [
        _text("book"), _text("volume"), _int("chapter"), _text("reference"),
        _text("title", exact=False), _text("summary", exact=False), _text("intro", exact=False),
        _text("kind"), _int("verse_count"), _text("uri"), _text("doc_id_str"),
    ],
    META: [_text("build_id"), _text("loading_build_id"), _text("loaded_at")],
}


class ScriptureLoader(BaseLoader):
    """Loads scripture bundles (one book at a time) into the Scripture* collections."""

    def __init__(
        self,
        client: weaviate.WeaviateClient,
        embed_fn: Callable[[list[str]], list[list[float]]],
        batch_size: int = 500,
        query_embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> None:
        super().__init__(embed_fn, batch_size, query_embed_fn)
        self._client = client
        self._existing: dict[str, set[str]] = {key: set() for key in NAMES}
        self.failures: list[str] = []      # insert errors; a run with any must not write the build_id
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        for name, props in SCHEMA.items():
            if not self._client.collections.exists(name):
                self._client.collections.create(
                    name=name, vector_config=Configure.Vectors.self_provided(), properties=props)

    def reset_collections(self) -> None:
        """Drop all three collections and recreate them empty."""
        for name in SCHEMA:
            if self._client.collections.exists(name):
                self._client.collections.delete(name)
        self._existing = {key: set() for key in NAMES}
        self._ensure_schema()

    def has_objects(self) -> bool:
        return any(self._client.collections.use(n).query.fetch_objects(limit=1).objects for n in NAMES.values())

    def load_existing(self) -> None:
        """Read every stored UUID once, so load() skips objects already there (resume)."""
        for key, name in NAMES.items():
            self._existing[key] = {str(o.uuid) for o in self._client.collections.use(name).iterator()}

    def load(self, bundle: ScriptureBundle) -> None:
        """Embed and upsert one bundle's verses (canonical + JST) and chapters, skipping objects already stored."""
        for key, prepare, args in (
            ("verses", prepare_verse_records, dict(verses=bundle.verses, jst_verses=bundle.jst_verses,
                                                   radius=SCRIPTURE_WINDOW_RADIUS)),
            ("chapters", prepare_chapter_records, dict(chapters=bundle.chapters)),
        ):
            existing = self._existing[key]
            records = prepare(**args, embed_fn=self.embed_fn, skip=lambda d: str(generate_uuid5(d)) in existing)
            objects = [DataObject(properties=meta, uuid=generate_uuid5(doc_id), vector={"default": vec})
                       for _, meta, doc_id, vec in records]
            self._insert(key, objects)

    def _insert(self, key: str, objects: list[DataObject]) -> None:
        col = self._client.collections.use(NAMES[key])
        for start in range(0, len(objects), self.batch_size):
            chunk = objects[start:start + self.batch_size]
            try:
                errors = col.data.insert_many(chunk).errors
            except Exception as e:  # noqa: BLE001 - recorded; the pipeline fails the run and writes no build_id
                errors = {i: e for i in range(len(chunk))}
            for idx, err in errors.items():
                self.failures.append(f"{NAMES[key]} {chunk[idx].properties.get('doc_id_str')}: "
                                     f"{getattr(err, 'message', err)}")
            self._existing[key].update(str(o.uuid) for i, o in enumerate(chunk) if i not in errors)
        if self.failures:
            logger.warning("%d Weaviate insert errors so far (latest: %s)", len(self.failures), self.failures[-1])

    def meta(self) -> dict:
        """The ScriptureMeta object's properties ({} when there is none)."""
        for obj in self._client.collections.use(META).iterator():
            return {k: v for k, v in obj.properties.items() if v}
        return {}

    def write_meta(self, build_id: str | None, loading_build_id: str) -> None:
        """Replace the single ScriptureMeta object."""
        props = {"build_id": build_id, "loading_build_id": loading_build_id,
                 "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        col = self._client.collections.use(META)
        col.data.delete_by_id(META_UUID)
        col.data.insert(properties={k: v for k, v in props.items() if v is not None}, uuid=META_UUID)

    def query(self, collection: str, query_text: str, k: int, filter: dict | None = None) -> list[str]:
        """Top-k doc_id_str values from "verses" or "chapters" by vector similarity."""
        conditions = [Filter.by_property(p).equal(v) for p, v in (filter or {}).items()]
        result = self._client.collections.use(NAMES[collection]).query.near_vector(
            self.query_embed_fn([query_text])[0], limit=k, target_vector="default",
            filters=Filter.all_of(conditions) if conditions else None)
        return [o.properties.get("doc_id_str", str(o.uuid)) for o in result.objects]

    def close(self) -> None:
        self._client.close()
