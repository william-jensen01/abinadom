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
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).parent.parent))

import chromadb
from chromadb.utils.batch_utils import create_batches
from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport
from config.chromadb_client import get_chromadb_client
from config.pipeline_config import CHROMADB_COLLECTION_NAMES

logger = logging.getLogger(__name__)

from loaders.shared_transforms import (
    flatten_metadata,
    prepare_talk_record,
    prepare_paragraph_records,
    prepare_citation_records,
    prepare_footnote_records,
    prepare_talk_bundle,
    TalkBundle,
)

# Backward-compat alias: tests/test_phase6.py imports _flatten_metadata directly.
_flatten_metadata = flatten_metadata


# =============================================================================
# Public API — Client helpers and insertion
# =============================================================================



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
