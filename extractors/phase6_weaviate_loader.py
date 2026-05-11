import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import weaviate.classes as wvc
from loaders.weaviate_loader import WeaviateLoader
from loaders.shared_transforms import TalkBundle
from weaviate.util import generate_uuid5


class ProductionWeaviateLoader(WeaviateLoader):
    """WeaviateLoader subclass using production PascalCase collection names.

    The benchmark WeaviateLoader uses short names (Talk, Paragraph, Citation, Footnote).
    This subclass overrides COLLECTIONS and _ensure_schema() to use production names:
    ConferenceTalks, ConferenceTalkParagraphs, ConferenceTalkCitations,
    ConferenceTalkFootnotes.

    loaders/weaviate_loader.py is left completely unchanged so the benchmark suite
    continues to work. Per Phase 24 review resolution.
    """

    COLLECTIONS = [
        "ConferenceTalks",
        "ConferenceTalkParagraphs",
        "ConferenceTalkCitations",
        "ConferenceTalkFootnotes",
    ]

    def _ensure_schema(self) -> None:
        """Create production PascalCase collections if they don't exist."""
        # Re-implemented from WeaviateLoader._ensure_schema() but with production names.
        # Preserves all property definitions from the parent — only collection name strings change.
        if not self._client.collections.exists("ConferenceTalks"):
            self._client.collections.create(
                name="ConferenceTalks",
                vector_config=wvc.config.Configure.Vectors.self_provided(),
                properties=self._talk_properties(),
            )
        if not self._client.collections.exists("ConferenceTalkParagraphs"):
            self._client.collections.create(
                name="ConferenceTalkParagraphs",
                vector_config=wvc.config.Configure.Vectors.self_provided(),
                properties=self._paragraph_properties(),
            )
        if not self._client.collections.exists("ConferenceTalkCitations"):
            self._client.collections.create(
                name="ConferenceTalkCitations",
                vector_config=wvc.config.Configure.Vectors.self_provided(),
                properties=self._citation_properties(),
            )
        if not self._client.collections.exists("ConferenceTalkFootnotes"):
            self._client.collections.create(
                name="ConferenceTalkFootnotes",
                vector_config=wvc.config.Configure.Vectors.self_provided(),
                properties=self._footnote_properties(),
            )

    @classmethod
    def reset(cls, host: str, port: int, grpc_port: int = 50051) -> None:
        """Delete all production collections (uses PascalCase names)."""
        import weaviate as _weaviate
        client = _weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port)
        try:
            for name in cls.COLLECTIONS:
                if client.collections.exists(name):
                    client.collections.delete(name)
        finally:
            client.close()


def load_talk_bundles(bundles: list[TalkBundle], loader: WeaviateLoader) -> dict:
    skipped_talks = []
    talks_inserted = 0
    paragraphs_inserted = 0
    citations_inserted = 0
    footnotes_inserted = 0

    for metadata, paragraphs, citations, footnotes, validation_report in bundles:
        if not validation_report.is_valid:
            skipped_talks.append(metadata.talk_id)
            continue
        loader.load((metadata, paragraphs, citations, footnotes, validation_report))
        talks_inserted += 1
        paragraphs_inserted += sum(
            1 for p in paragraphs.paragraphs if p.source_type != "annotation"
        )
        citations_inserted += len(citations.citations)
        footnotes_inserted += len(footnotes.footnotes)

    return {
        "talks_inserted": talks_inserted,
        "paragraphs_inserted": paragraphs_inserted,
        "citations_inserted": citations_inserted,
        "footnotes_inserted": footnotes_inserted,
        "skipped_talks": skipped_talks,
        "skipped_count": len(skipped_talks),
    }


def generate_verification_report(loader: WeaviateLoader, load_summary: dict) -> dict:
    """Manual-use verification helper (not called by run_pipeline.py — per D-12).

    Uses loader._client directly (internal attribute access) — acceptable because this
    function is for manual/diagnostic use only and WeaviateLoader does not expose a
    public client property. See D-12.
    """
    collection_names = {
        "talks": "ConferenceTalks",
        "paragraphs": "ConferenceTalkParagraphs",
        "citations": "ConferenceTalkCitations",
        "footnotes": "ConferenceTalkFootnotes",
    }

    counts = {}
    for key, name in collection_names.items():
        col = loader._client.collections.use(name)
        result = col.aggregate.over_all(total_count=True)
        counts[name] = result.total_count

    fk_checks = {}

    para_col = loader._client.collections.use("ConferenceTalkParagraphs")
    para_result = para_col.query.fetch_objects(limit=5)
    paras_to_talks_passed = True
    sampled = 0
    for obj in para_result.objects:
        talk_id = obj.properties.get("talk_id")
        if talk_id is not None:
            talk_uuid = generate_uuid5(f"talk_{talk_id}")
            talk_col = loader._client.collections.use("ConferenceTalks")
            found = talk_col.query.fetch_object_by_id(talk_uuid)
            if found is None:
                paras_to_talks_passed = False
            sampled += 1
    fk_checks["paragraphs_to_talks"] = {"passed": paras_to_talks_passed, "sampled": sampled}

    cite_col = loader._client.collections.use("ConferenceTalkCitations")
    cite_result = cite_col.query.fetch_objects(limit=5)
    cites_to_paras_passed = True
    cites_sampled = 0
    for obj in cite_result.objects:
        para_id = obj.properties.get("paragraph_id")
        if para_id is not None:
            para_uuid = generate_uuid5(f"para_{para_id}")
            found = para_col.query.fetch_object_by_id(para_uuid)
            if found is None:
                cites_to_paras_passed = False
            cites_sampled += 1
    fk_checks["citations_to_paragraphs"] = {"passed": cites_to_paras_passed, "sampled": cites_sampled}

    passed = (
        counts.get("ConferenceTalks", 0) >= load_summary.get("talks_inserted", 0)
        and fk_checks["paragraphs_to_talks"]["passed"]
        and fk_checks["citations_to_paragraphs"]["passed"]
    )

    return {
        "counts": counts,
        "fk_checks": fk_checks,
        "skipped_talks": load_summary.get("skipped_talks", []),
        "skipped_count": load_summary.get("skipped_count", 0),
        "passed": passed,
    }
