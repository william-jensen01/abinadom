"""
Scripture loader: ScriptureVerses, ScriptureChapters and ScriptureMeta in Weaviate (SPEC-v2 sections 6-8).

Collection names come from config/pipeline_config.py. The vectorizer is disabled: vectors are computed here
(embed_fn, the document-task embedder) and passed explicitly. UUIDs are deterministic (generate_uuid5 over the
doc_id string), so a re-load upserts, and "already loaded" is just "that UUID exists" (resume checks existence, not
content: after changing an embed string or the window radius, drop the objects with reset_collections()).

ScriptureMeta holds one object. `loading_build_id` is the build a run (full or --book) started loading, recorded by
mark_loading() before the first insert; `build_id` is written by write_build_id() only after a complete load. The
pipeline compares both with the scripture.db it is loading and reloads everything when either differs.
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).parent.parent))

import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import DataType, Property, Tokenization
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter
from weaviate.util import generate_uuid5

from config.pipeline_config import (
    SCRIPTURE_WINDOW_RADIUS,
    WEAVIATE_SCRIPTURE_COLLECTION_NAMES,
    WEAVIATE_SCRIPTURE_META_COLLECTION,
)
from loaders import BaseLoader
from loaders.shared_transforms import ScriptureBundle, prepare_chapter_records, prepare_verse_records

logger = logging.getLogger(__name__)

META_UUID_SEED = "scripture_meta"


def _text(name: str, exact: bool = False) -> Property:
    """A TEXT property; `exact` indexes the whole value as one token so filters match it exactly ("1 Nephi")."""
    return Property(name=name, data_type=DataType.TEXT, tokenization=Tokenization.FIELD if exact else Tokenization.WORD)


class ScriptureLoader(BaseLoader):
    """
    Loads scripture bundles (one book at a time) into the Scripture* collections.

    Usage:
        loader = ScriptureLoader(client=get_weaviate_client(), embed_fn=get_embedding_function())
        loader.load_existing()                 # resume: skip objects whose UUID is already stored
        loader.load(ScriptureBundle(verses, jst_verses, chapters))
        loader.write_build_id(build_id)        # only after a COMPLETE load
    """

    def __init__(
        self,
        client: weaviate.WeaviateClient,
        embed_fn: Callable[[list[str]], list[list[float]]],
        batch_size: int = 500,
        query_embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        window_radius: int = SCRIPTURE_WINDOW_RADIUS,
    ) -> None:
        super().__init__(embed_fn, batch_size, query_embed_fn)
        self._client = client
        self.window_radius = window_radius
        self._existing: dict[str, set[str]] = {key: set() for key in WEAVIATE_SCRIPTURE_COLLECTION_NAMES}
        self._failures: list[str] = []
        self._ensure_schema()

    # -- schema --------------------------------------------------------------
    def _verse_properties(self) -> list:
        return [
            _text("variant", exact=True), _text("book", exact=True), _text("book_uri", exact=True),
            _text("cite_abbr", exact=True), _text("volume", exact=True),
            Property(name="chapter", data_type=DataType.INT),
            Property(name="verse", data_type=DataType.INT),
            _text("reference", exact=True), _text("text"),
            Property(name="has_jst", data_type=DataType.BOOL),
            Property(name="jst_refs", data_type=DataType.TEXT_ARRAY, tokenization=Tokenization.FIELD),
            Property(name="kjv_refs", data_type=DataType.TEXT_ARRAY, tokenization=Tokenization.FIELD),
            _text("aid", exact=True),
            Property(name="footnote_count", data_type=DataType.INT),
            _text("context_window"), _text("doc_id_str", exact=True),
        ]

    def _chapter_properties(self) -> list:
        return [
            _text("book", exact=True), _text("volume", exact=True),
            Property(name="chapter", data_type=DataType.INT),
            _text("reference", exact=True), _text("title"), _text("summary"), _text("intro"),
            _text("kind", exact=True),
            Property(name="verse_count", data_type=DataType.INT),
            _text("uri", exact=True), _text("doc_id_str", exact=True),
        ]

    def _ensure_schema(self) -> None:
        """Create the three collections if they don't exist (idempotent)."""
        wanted = {
            WEAVIATE_SCRIPTURE_COLLECTION_NAMES["verses"]: self._verse_properties(),
            WEAVIATE_SCRIPTURE_COLLECTION_NAMES["chapters"]: self._chapter_properties(),
            WEAVIATE_SCRIPTURE_META_COLLECTION: [_text("build_id", exact=True), _text("loading_build_id", exact=True),
                                                 _text("loaded_at", exact=True)],
        }
        for name, props in wanted.items():
            if not self._client.collections.exists(name):
                self._client.collections.create(
                    name=name,
                    vector_config=wvc.config.Configure.Vectors.self_provided(),
                    properties=props,
                )

    def reset_collections(self) -> None:
        """Drop all three collections and recreate them empty (a forced or changed-build reload starts clean)."""
        for name in (*WEAVIATE_SCRIPTURE_COLLECTION_NAMES.values(), WEAVIATE_SCRIPTURE_META_COLLECTION):
            if self._client.collections.exists(name):
                self._client.collections.delete(name)
        self._existing = {key: set() for key in WEAVIATE_SCRIPTURE_COLLECTION_NAMES}
        self._ensure_schema()

    # -- existence (resume) --------------------------------------------------
    def load_existing(self) -> None:
        """Read every stored UUID once, so load() can skip objects that are already there."""
        for key, name in WEAVIATE_SCRIPTURE_COLLECTION_NAMES.items():
            col = self._client.collections.use(name)
            self._existing[key] = {str(o.uuid) for o in col.iterator(return_properties=["doc_id_str"])}

    def _skipper(self, key: str) -> Callable[[str], bool]:
        existing = self._existing[key]
        return lambda doc_id: str(generate_uuid5(doc_id)) in existing

    # -- loading -------------------------------------------------------------
    def load(self, bundle: ScriptureBundle) -> None:
        """Embed and upsert one bundle's verses (canonical + JST) and chapters, skipping objects already stored."""
        verses = prepare_verse_records(
            bundle.verses, bundle.jst_verses, embed_fn=self.embed_fn,
            radius=self.window_radius, skip=self._skipper("verses"),
        )
        chapters = prepare_chapter_records(bundle.chapters, embed_fn=self.embed_fn, skip=self._skipper("chapters"))
        for key, records in (("verses", verses), ("chapters", chapters)):
            self._insert(key, [
                DataObject(properties=meta, uuid=generate_uuid5(doc_id), vector={"default": vec})
                for _, meta, doc_id, vec in records
            ])

    def _insert(self, key: str, objects: list[DataObject]) -> None:
        name = WEAVIATE_SCRIPTURE_COLLECTION_NAMES[key]
        col = self._client.collections.use(name)
        for start in range(0, len(objects), self.batch_size):
            chunk = objects[start:start + self.batch_size]
            try:
                result = col.data.insert_many(chunk)
            except Exception as e:  # noqa: BLE001 - recorded; the pipeline fails the run and writes no build_id
                self._failures.append(f"{name}: {e}")
                logger.warning("Weaviate insert_many error in %s (%d objects): %s", name, len(chunk), e)
                continue
            errors = result.errors if result.has_errors else {}
            failed = set(errors)
            for idx, err in errors.items():
                message = getattr(err, "message", err)
                self._failures.append(f"{name} {chunk[idx].properties.get('doc_id_str')}: {message}")
                logger.warning("Weaviate insert error in %s idx=%s: %s", name, idx, message)
            self._existing[key].update(str(o.uuid) for i, o in enumerate(chunk) if i not in failed)

    def pop_insert_failures(self) -> list[str]:
        """Return (and clear) the insert errors since the last call. A run with any must not write the build_id."""
        failures, self._failures = self._failures, []
        return failures

    def delete_bundle(self, bundle: ScriptureBundle) -> None:
        """Delete the objects a bundle would write (a forced reload of one book)."""
        for key, ids in (
            ("verses", [f"verse_{v['book_uri']}_{v['chapter']}_{v['verse']}" for v in bundle.verses]
                       + [f"jst_{j['book_uri']}_{j['chapter']}_{j['verse']}" for j in bundle.jst_verses]),
            ("chapters", [f"chapter_{c['page_uri']}" for c in bundle.chapters]),
        ):
            uuids = [generate_uuid5(i) for i in ids]
            col = self._client.collections.use(WEAVIATE_SCRIPTURE_COLLECTION_NAMES[key])
            for start in range(0, len(uuids), 500):
                col.data.delete_many(where=Filter.by_id().contains_any(uuids[start:start + 500]))
            self._existing[key].difference_update(str(u) for u in uuids)

    # -- ScriptureMeta -------------------------------------------------------
    def _meta(self) -> dict:
        col = self._client.collections.use(WEAVIATE_SCRIPTURE_META_COLLECTION)
        for obj in col.iterator():
            return dict(obj.properties)
        return {}

    def _write_meta(self, **props) -> None:
        col = self._client.collections.use(WEAVIATE_SCRIPTURE_META_COLLECTION)
        col.data.delete_by_id(generate_uuid5(META_UUID_SEED))
        props = {k: v for k, v in props.items() if v is not None}
        col.data.insert(
            properties={**props, "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            uuid=generate_uuid5(META_UUID_SEED),
        )

    def get_build_id(self) -> str | None:
        """The build_id of the last complete load, or None when no complete load is recorded."""
        return self._meta().get("build_id") or None

    def get_loading_build_id(self) -> str | None:
        """The build_id of the db the last (full or --book) run started loading, or None."""
        return self._meta().get("loading_build_id") or None

    def has_objects(self) -> bool:
        """True when either scripture collection holds any object."""
        return any(
            len(self._client.collections.use(name).query.fetch_objects(limit=1).objects) > 0
            for name in WEAVIATE_SCRIPTURE_COLLECTION_NAMES.values()
        )

    def mark_loading(self, build_id: str) -> None:
        """Record the build about to be loaded (before the first insert), keeping a finished build_id as is."""
        self._write_meta(build_id=self.get_build_id(), loading_build_id=build_id)

    def write_build_id(self, build_id: str) -> None:
        """Replace the single ScriptureMeta object. Call only after every object of the build is loaded."""
        self._write_meta(build_id=build_id, loading_build_id=build_id)

    # -- BaseLoader ----------------------------------------------------------
    def query(self, collection: str, query_text: str, k: int, filter: dict | None = None) -> list[str]:
        """Top-k doc_id_str values from a scripture collection ("verses"/"chapters" or the collection name)."""
        names = {**WEAVIATE_SCRIPTURE_COLLECTION_NAMES, **{v: v for v in WEAVIATE_SCRIPTURE_COLLECTION_NAMES.values()}}
        if collection not in names:
            raise ValueError(f"Unknown collection: {collection!r}. Must be one of: {list(names)}")
        col = self._client.collections.use(names[collection])
        kwargs: dict = {"near_vector": self.query_embed_fn([query_text])[0], "limit": k, "target_vector": "default"}
        if filter:
            conditions = [Filter.by_property(p).equal(v) for p, v in filter.items()]
            kwargs["filters"] = conditions[0] if len(conditions) == 1 else Filter.all_of(conditions)
        return [o.properties.get("doc_id_str", str(o.uuid)) for o in col.query.near_vector(**kwargs).objects]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self) -> None:
        self._client.close()
