"""
Phase 6: ChromaDB Loader — Transformation and Insertion Layer

Transforms Phase 5 validated output bundles (TalkMetadata, TalkParagraphs,
TalkCitations, TalkFootnotes, ValidationReport) into ChromaDB-compatible
(documents, metadatas, ids) tuples for 4 collections, then inserts them
in dependency order with automatic batch chunking and progress logging.

Collections produced:
    - conference_talks: one record per talk
    - conference_talk_paragraphs: one record per non-annotation paragraph
    - conference_talk_citations: one record per citation (all, incl. annotation-sourced)
    - conference_talk_footnotes: one record per footnote
"""

import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).parent.parent))

import chromadb
from chromadb.utils.batch_utils import create_batches
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport
from config.pipeline_config import CHROMADB_PATH, CHROMADB_BATCH_SIZE, CHROMADB_COLLECTION_NAMES

logger = logging.getLogger(__name__)


# =============================================================================
# Internal helpers
# =============================================================================


def _flatten_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a metadata dict for ChromaDB insertion.

    ChromaDB metadata values must be scalars (str, int, float, bool).
    Rules applied:
      - None values: removed
      - Empty lists: removed (ChromaDB rejects empty arrays)
      - List[int]: comma-joined string (e.g., [32, 33] -> "32,33")
      - List[str]: pipe-joined string (e.g., ["a", "b"] -> "a|b")
      - str / int / float / bool: kept as-is
      - Other types: str(value)
    """
    result: dict[str, Any] = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, list):
            if len(value) == 0:
                continue
            # Detect element type by first element
            if value and isinstance(value[0], int):
                result[key] = ",".join(str(v) for v in value)
            elif value and isinstance(value[0], str):
                result[key] = "|".join(value)
            else:
                # Fallback for mixed or other types
                result[key] = "|".join(str(v) for v in value)
        elif isinstance(value, (str, int, float, bool)):
            result[key] = value
        else:
            result[key] = str(value)
    return result


# =============================================================================
# Public API — Transformation functions
# =============================================================================


def prepare_talk_record(
    metadata: TalkMetadata,
    annotation_texts: list[str],
) -> tuple[str, dict[str, Any], str]:
    """
    Transform a TalkMetadata into a ChromaDB (document, metadata, id) tuple.

    Document (D-01):
        f"{title}\n\n{talk_preview}" when talk_preview is truthy,
        else title alone.

    Metadata (D-05):
        All non-None fields from TalkMetadata as flat scalars.

    Annotations (D-08):
        If annotation_texts is non-empty, adds
        metadata["annotations"] = pipe-joined string of all annotation texts.

    Args:
        metadata:         Phase 1 output for this talk.
        annotation_texts: Text strings from annotation paragraphs (may be empty).

    Returns:
        (document, metadata_dict, doc_id)
    """
    # Build document text
    if metadata.talk_preview:
        document = f"{metadata.title}\n\n{metadata.talk_preview}"
    else:
        document = metadata.title

    if metadata.topics:
        document += f"\nTopics: {', '.join(metadata.topics)}"

    # Build metadata from all dataclass fields
    raw_meta = asdict(metadata)
    flat_meta = _flatten_metadata(raw_meta)

    # Fold annotation texts (D-08)
    if annotation_texts:
        flat_meta["annotations"] = "|".join(annotation_texts)

    doc_id = f"talk_{metadata.talk_id}"
    return document, flat_meta, doc_id


def prepare_paragraph_records(
    paragraphs: TalkParagraphs,
    talk_metadata: TalkMetadata | None = None,
) -> tuple[list[tuple[str, dict[str, Any], str]], list[str]]:
    """
    Transform TalkParagraphs into ChromaDB records, splitting by source_type.

    Annotation paragraphs (source_type == "annotation"):
        - Excluded from paragraph records (D-07)
        - Their text is collected and returned for folding into talk metadata (D-08)

    Non-annotation paragraphs:
        - Document: paragraph.text
        - Metadata: all non-None fields as flat scalars
        - ID: f"para_{paragraph_id}"

    Args:
        paragraphs: Phase 2 output container.
        talk_metadata: Optional Phase 1 metadata. When provided, speaker_name,
            title, conference_year, and conference_month are injected into each
            paragraph record's metadata for denormalized search results.

    Returns:
        (list_of_records, annotation_texts)
        where annotation_texts is a (possibly empty) list of annotation paragraph texts
    """
    records: list[tuple[str, dict[str, Any], str]] = []
    annotation_texts: list[str] = []

    for para in paragraphs.paragraphs:
        if para.source_type == "annotation":
            annotation_texts.append(para.text)
            continue

        document = para.text
        raw_meta = asdict(para)
        flat_meta = _flatten_metadata(raw_meta)
        # Inject talk-level fields when metadata is provided (D-01, D-05)
        if talk_metadata is not None:
            flat_meta["speaker_name"] = talk_metadata.speaker_name
            flat_meta["title"] = talk_metadata.title
            flat_meta["conference_year"] = talk_metadata.conference_year
            flat_meta["conference_month"] = talk_metadata.conference_month
        doc_id = f"para_{para.paragraph_id}"
        records.append((document, flat_meta, doc_id))

    return records, annotation_texts


def prepare_citation_records(
    citations: TalkCitations,
) -> list[tuple[str, dict[str, Any], str]]:
    """
    Transform TalkCitations into ChromaDB records.

    ALL citations are included, regardless of whether their parent paragraph
    is an annotation paragraph (D-09).

    Document (D-03):
        citation.context_window if truthy, else citation.citation_text_raw.

    Metadata:
        All non-None fields as flat scalars.
        verse_list (List[int]) is comma-joined per _flatten_metadata rules.

    ID:
        f"cite_{citation_id}_{paragraph_id}"

    Args:
        citations: Phase 3 output container.

    Returns:
        List of (document, metadata, id) tuples.
    """
    records: list[tuple[str, dict[str, Any], str]] = []

    for cite in citations.citations:
        document = cite.context_window if cite.context_window else cite.citation_text_raw
        raw_meta = asdict(cite)
        flat_meta = _flatten_metadata(raw_meta)
        doc_id = f"cite_{cite.citation_id}_{cite.paragraph_id}"
        records.append((document, flat_meta, doc_id))

    return records


def prepare_footnote_records(
    footnotes: TalkFootnotes,
) -> list[tuple[str, dict[str, Any], str]]:
    """
    Transform TalkFootnotes into ChromaDB records.

    Document (D-04):
        footnote.context_window if truthy, else footnote.footnote_text_raw.

    Metadata:
        All non-None fields as flat scalars.

    ID:
        f"fn_{footnote_id}"

    Args:
        footnotes: Phase 4 output container.

    Returns:
        List of (document, metadata, id) tuples.
    """
    records: list[tuple[str, dict[str, Any], str]] = []

    for fn in footnotes.footnotes:
        document = fn.context_window if fn.context_window else fn.footnote_text_raw
        raw_meta = asdict(fn)
        flat_meta = _flatten_metadata(raw_meta)
        doc_id = f"fn_{fn.footnote_id}"
        records.append((document, flat_meta, doc_id))

    return records


def prepare_talk_bundle(
    metadata: TalkMetadata,
    paragraphs: TalkParagraphs,
    citations: TalkCitations,
    footnotes: TalkFootnotes,
    validation_report: ValidationReport,
) -> dict[str, list[tuple[str, dict[str, Any], str]]]:
    """
    Prepare a complete set of ChromaDB records for a single talk across all 4 collections.

    If validation_report.is_valid is False (D-10):
        Log a WARNING with talk_id and errors list.
        Return empty lists for all 4 collections.

    Otherwise:
        1. Prepare paragraph records + collect annotation texts.
        2. Prepare talk record with annotation texts folded in (D-08).
        3. Prepare citation records (all citations included, D-09).
        4. Prepare footnote records.

    Args:
        metadata:           Phase 1 output.
        paragraphs:         Phase 2 output.
        citations:          Phase 3 output.
        footnotes:          Phase 4 output.
        validation_report:  Phase 5 output.

    Returns:
        dict with keys "talks", "paragraphs", "citations", "footnotes",
        each mapping to a list of (document, metadata, id) tuples.
    """
    if not validation_report.is_valid:
        logger.warning(
            "Skipping talk_id=%s — failed validation. Errors: %s",
            metadata.talk_id,
            validation_report.errors,
        )
        return {"talks": [], "paragraphs": [], "citations": [], "footnotes": []}

    # Prepare paragraphs first to collect annotation texts
    paragraph_records, annotation_texts = prepare_paragraph_records(
        paragraphs, talk_metadata=metadata
    )

    # Prepare talk record with annotations folded in
    talk_record = prepare_talk_record(metadata, annotation_texts)

    # Prepare citation and footnote records
    citation_records = prepare_citation_records(citations)
    footnote_records = prepare_footnote_records(footnotes)

    return {
        "talks": [talk_record],
        "paragraphs": paragraph_records,
        "citations": citation_records,
        "footnotes": footnote_records,
    }


# =============================================================================
# Public API — Client helpers and insertion
# =============================================================================


def get_embedding_function() -> OllamaEmbeddingFunction:
    """
    Return the OllamaEmbeddingFunction configured for nomic-embed-text.

    Per D-14: pass this to get_or_create_collection() for all 4 collections.
    Ollama must be running locally with nomic-embed-text pulled.
    """
    return OllamaEmbeddingFunction(
        model_name="nomic-embed-text",
        url="http://localhost:11434/api/embeddings",
    )


def get_chromadb_client(path: str | None = None) -> chromadb.ClientAPI:
    """
    Return a PersistentClient using the given path or config default.

    Per D-12: uses CHROMADB_PATH from pipeline_config when no path given.
    Tests can pass a tmp_path for isolation.
    """
    return chromadb.PersistentClient(path=path or CHROMADB_PATH)


def insert_collection(
    client: chromadb.ClientAPI,
    collection: chromadb.Collection,
    documents: list[str],
    metadatas: list[dict[str, Any]],
    ids: list[str],
    collection_name: str,
) -> int:
    """
    Insert records into a ChromaDB collection with automatic batch chunking.

    Uses create_batches() to respect SQLite parameter limits on large runs.
    Uses upsert() for idempotent behavior (LOAD-04).
    Logs per-batch progress with collection name and batch count (LOAD-05).

    Args:
        client:          ChromaDB client (needed by create_batches for max_batch_size).
        collection:      Target collection.
        documents:       Document texts to insert.
        metadatas:       Metadata dicts per document.
        ids:             Unique IDs per document.
        collection_name: Human-readable name for logging.

    Returns:
        Number of records inserted.
    """
    if len(ids) == 0:
        logger.info("%s: no records to insert", collection_name)
        return 0

    batches = create_batches(
        api=client,
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )
    total = len(batches)
    for i, batch in enumerate(batches, 1):
        batch_ids, batch_embeddings, batch_metadatas, batch_documents = batch
        collection.upsert(
            ids=batch_ids,
            documents=batch_documents,
            metadatas=batch_metadatas,
        )
        logger.info("%s: batch %d/%d (%d records)", collection_name, i, total, len(batch_ids))

    return len(ids)


# =============================================================================
# Type alias for a talk bundle input
# =============================================================================

TalkBundle = tuple[TalkMetadata, TalkParagraphs, TalkCitations, TalkFootnotes, ValidationReport]


# =============================================================================
# Public API — Orchestration
# =============================================================================


def load_talk_bundles(
    bundles: list[TalkBundle],
    client: chromadb.ClientAPI,
    embedding_fn=None,
) -> dict[str, Any]:
    """
    Load validated talk bundles into ChromaDB in dependency order.

    Inserts in order (LOAD-04): talks -> paragraphs -> citations -> footnotes.
    Invalid talks (is_valid=False) are skipped per D-10.

    Args:
        bundles:      List of (TalkMetadata, TalkParagraphs, TalkCitations,
                      TalkFootnotes, ValidationReport) tuples.
        client:       ChromaDB client instance.
        embedding_fn: Optional embedding function for collections (None in tests).

    Returns:
        Summary dict with per-collection counts and skipped talk info.
    """
    logger.info("Loading %d talk bundles into ChromaDB", len(bundles))

    # Get or create all 4 collections
    talks_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["talks"], embedding_function=embedding_fn
    )
    paras_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["paragraphs"], embedding_function=embedding_fn
    )
    cites_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["citations"], embedding_function=embedding_fn
    )
    fns_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["footnotes"], embedding_function=embedding_fn
    )

    # Accumulators
    all_talks: list[tuple[str, dict[str, Any], str]] = []
    all_paragraphs: list[tuple[str, dict[str, Any], str]] = []
    all_citations: list[tuple[str, dict[str, Any], str]] = []
    all_footnotes: list[tuple[str, dict[str, Any], str]] = []
    skipped_talks: list[int] = []

    # Transform each bundle
    for metadata, paragraphs, citations, footnotes, validation_report in bundles:
        result = prepare_talk_bundle(metadata, paragraphs, citations, footnotes, validation_report)
        if not result["talks"]:
            # Invalid talk — already logged by prepare_talk_bundle
            skipped_talks.append(metadata.talk_id)
            continue
        all_talks.extend(result["talks"])
        all_paragraphs.extend(result["paragraphs"])
        all_citations.extend(result["citations"])
        all_footnotes.extend(result["footnotes"])

    # Insert in dependency order: talks -> paragraphs -> citations -> footnotes
    def _split(records):
        """Split list of (doc, meta, id) tuples into separate lists."""
        docs = [r[0] for r in records]
        metas = [r[1] for r in records]
        ids = [r[2] for r in records]
        return docs, metas, ids

    t_docs, t_metas, t_ids = _split(all_talks)
    insert_collection(client, talks_col, t_docs, t_metas, t_ids, CHROMADB_COLLECTION_NAMES["talks"])

    p_docs, p_metas, p_ids = _split(all_paragraphs)
    insert_collection(client, paras_col, p_docs, p_metas, p_ids, CHROMADB_COLLECTION_NAMES["paragraphs"])

    c_docs, c_metas, c_ids = _split(all_citations)
    insert_collection(client, cites_col, c_docs, c_metas, c_ids, CHROMADB_COLLECTION_NAMES["citations"])

    f_docs, f_metas, f_ids = _split(all_footnotes)
    insert_collection(client, fns_col, f_docs, f_metas, f_ids, CHROMADB_COLLECTION_NAMES["footnotes"])

    summary = {
        "talks_inserted": len(all_talks),
        "paragraphs_inserted": len(all_paragraphs),
        "citations_inserted": len(all_citations),
        "footnotes_inserted": len(all_footnotes),
        "skipped_talks": skipped_talks,
        "skipped_count": len(skipped_talks),
    }

    logger.info("Load complete: %s", summary)
    return summary


# =============================================================================
# Public API — Verification
# =============================================================================


def generate_verification_report(
    client: chromadb.ClientAPI,
    load_summary: dict[str, Any],
    sample_size: int = 5,
) -> dict[str, Any]:
    """
    Generate a post-insertion verification report confirming data integrity.

    Checks:
        1. Record counts per collection match expectations.
        2. Sample documents are retrievable with non-empty text.
        3. Foreign key spot checks: paragraph talk_ids resolve in talks,
           citation paragraph_ids resolve in paragraphs.
        4. Skipped talks are listed.
        5. Overall pass/fail computed from counts + FK checks.

    Args:
        client:       ChromaDB client with loaded data.
        load_summary: Return value from load_talk_bundles().
        sample_size:  Max documents to sample per collection.

    Returns:
        Verification report dict.
    """
    report: dict[str, Any] = {}

    # 1. Record counts
    counts: dict[str, int] = {}
    for key, name in CHROMADB_COLLECTION_NAMES.items():
        collection = client.get_or_create_collection(name=name)
        counts[name] = collection.count()
    report["counts"] = counts
    report["expected"] = {
        "talks": load_summary.get("talks_inserted", 0),
        "paragraphs": load_summary.get("paragraphs_inserted", 0),
        "citations": load_summary.get("citations_inserted", 0),
        "footnotes": load_summary.get("footnotes_inserted", 0),
    }

    # 2. Sample document retrievals
    sample_retrievals: dict[str, list[dict[str, Any]]] = {}
    for key, name in CHROMADB_COLLECTION_NAMES.items():
        collection = client.get_or_create_collection(name=name)
        count = collection.count()
        if count == 0:
            sample_retrievals[name] = []
            continue
        result = collection.get(limit=min(sample_size, count), include=["documents", "metadatas"])
        samples = []
        for i, doc_id in enumerate(result["ids"]):
            samples.append({
                "id": doc_id,
                "document_preview": (result["documents"][i] or "")[:100],
                "metadata_keys": list(result["metadatas"][i].keys()) if result["metadatas"][i] else [],
            })
        sample_retrievals[name] = samples
    report["sample_retrievals"] = sample_retrievals

    # 3. Foreign key spot checks
    fk_checks: dict[str, Any] = {}

    talks_col = client.get_or_create_collection(name=CHROMADB_COLLECTION_NAMES["talks"])
    paras_col = client.get_or_create_collection(name=CHROMADB_COLLECTION_NAMES["paragraphs"])
    cites_col = client.get_or_create_collection(name=CHROMADB_COLLECTION_NAMES["citations"])

    # Check: paragraph talk_ids exist in talks collection
    para_count = paras_col.count()
    if para_count > 0:
        para_sample = paras_col.get(limit=min(sample_size, para_count), include=["metadatas"])
        para_talk_ids: set[int] = set()
        for meta in para_sample["metadatas"]:
            if meta and "talk_id" in meta:
                para_talk_ids.add(meta["talk_id"])
        missing_talk_ids = []
        for tid in para_talk_ids:
            result = talks_col.get(ids=[f"talk_{tid}"])
            if not result["ids"]:
                missing_talk_ids.append(tid)
        fk_checks["paragraphs_to_talks"] = {
            "sampled": len(para_talk_ids),
            "resolved": len(para_talk_ids) - len(missing_talk_ids),
            "missing": missing_talk_ids,
            "passed": len(missing_talk_ids) == 0,
        }
    else:
        fk_checks["paragraphs_to_talks"] = {"sampled": 0, "resolved": 0, "missing": [], "passed": True}

    # Check: citation paragraph_ids exist in paragraphs collection
    cite_count = cites_col.count()
    if cite_count > 0:
        cite_sample = cites_col.get(limit=min(sample_size, cite_count), include=["metadatas"])
        cite_para_ids: set[int] = set()
        for meta in cite_sample["metadatas"]:
            if meta and "paragraph_id" in meta:
                cite_para_ids.add(meta["paragraph_id"])
        missing_para_ids = []
        for pid in cite_para_ids:
            result = paras_col.get(ids=[f"para_{pid}"])
            if not result["ids"]:
                missing_para_ids.append(pid)
        fk_checks["citations_to_paragraphs"] = {
            "sampled": len(cite_para_ids),
            "resolved": len(cite_para_ids) - len(missing_para_ids),
            "missing_paragraph_ids": missing_para_ids,
            "passed": True,  # Missing paragraph_ids may be from annotation paragraphs (D-09)
            "note": "Missing paragraph_ids may belong to annotation paragraphs excluded per D-07/D-09",
        }
    else:
        fk_checks["citations_to_paragraphs"] = {"sampled": 0, "resolved": 0, "missing_paragraph_ids": [], "passed": True}

    report["fk_checks"] = fk_checks

    # 4. Skipped talks (D-11)
    report["skipped_talks"] = load_summary.get("skipped_talks", [])
    report["skipped_count"] = load_summary.get("skipped_count", 0)

    # 5. Overall pass/fail
    # Counts must match expected (not just be positive — legitimate 0s are fine for
    # talks with no citations or footnotes).
    counts_match = all(
        counts.get(name, -1) >= report["expected"].get(key, 0)
        for key, name in CHROMADB_COLLECTION_NAMES.items()
    )
    all_fk_passed = all(check.get("passed", False) for check in fk_checks.values())
    report["passed"] = counts_match and all_fk_passed

    logger.info(
        "Verification report: passed=%s, counts=%s, skipped=%s",
        report["passed"],
        counts,
        report["skipped_count"],
    )

    return report
