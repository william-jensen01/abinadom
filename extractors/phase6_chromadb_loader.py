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
    paragraph_records, annotation_texts = prepare_paragraph_records(paragraphs)

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
