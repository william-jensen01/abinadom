"""
Shared data transformation utilities for all vector DB loaders.

Contains flatten_metadata, rich_metadata, and all prepare_* functions.
Importable without installing chromadb, weaviate-client, or qdrant-client.
No DB-client dependencies — pure data transforms using stdlib and project models only.
"""

import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

sys.path.append(str(Path(__file__).parent.parent))

from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport

logger = logging.getLogger(__name__)


# Type alias — kept as tuple to match phase6 iteration pattern
TalkBundle = tuple[TalkMetadata, TalkParagraphs, TalkCitations, TalkFootnotes, ValidationReport]


# =============================================================================
# Metadata normalization helpers
# =============================================================================


def flatten_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a metadata dict for ChromaDB insertion.

    Public API in loaders.shared_transforms (moved from extractors/phase6_chromadb_loader.py
    where it was private as _flatten_metadata).

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


def rich_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a metadata dict for Weaviate and Qdrant native array support.

    Unlike flatten_metadata, this function preserves Python list types
    rather than joining them to strings. Rules applied:
      - None values: removed
      - Empty lists: removed (Weaviate rejects empty arrays for TEXT_ARRAY / INT_ARRAY)
      - Lists: kept as-is (no joining or flattening)
      - str / int / float / bool: kept as-is
    """
    return {k: v for k, v in meta.items() if v is not None and v != []}


# =============================================================================
# Transformation functions
# =============================================================================


def prepare_talk_record(
    metadata: TalkMetadata,
    annotation_texts: list[str],
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> tuple[str, dict[str, Any], str, list[float] | None]:
    """
    Transform a TalkMetadata into a (document, metadata, id, vector|None) tuple.

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
        embed_fn:         Optional callable (list[str]) -> list[list[float]]. When None, vector is None.

    Returns:
        (document, metadata_dict, doc_id, vector|None)
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
    flat_meta = flatten_metadata(raw_meta)

    # Fold annotation texts (D-08)
    if annotation_texts:
        flat_meta["annotations"] = "|".join(annotation_texts)

    doc_id = f"talk_{metadata.talk_id}"
    vector = embed_fn([document])[0] if embed_fn is not None else None
    return document, flat_meta, doc_id, vector


def prepare_paragraph_records(
    paragraphs: TalkParagraphs,
    talk_metadata: TalkMetadata | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> tuple[list[tuple[str, dict[str, Any], str, list[float] | None]], list[str]]:
    """
    Transform TalkParagraphs into records, splitting by source_type.

    Annotation paragraphs (source_type == "annotation"):
        - Excluded from paragraph records (D-07)
        - Their text is collected and returned for folding into talk metadata (D-08)

    Non-annotation paragraphs:
        - Document: paragraph.text
        - Metadata: all non-None fields as flat scalars
        - ID: f"para_{paragraph_id}"
        - Vector: embed_fn(document) if embed_fn is not None else None

    Args:
        paragraphs:    Phase 2 output container.
        talk_metadata: Optional Phase 1 metadata. When provided, speaker_name,
            title, conference_year, and conference_month are injected into each
            paragraph record's metadata for denormalized search results.
        embed_fn:      Optional callable (list[str]) -> list[list[float]]. When None, vector is None.

    Returns:
        (list_of_records, annotation_texts)
        where annotation_texts is a (possibly empty) list of annotation paragraph texts
    """
    records: list[tuple[str, dict[str, Any], str, list[float] | None]] = []
    annotation_texts: list[str] = []

    for para in paragraphs.paragraphs:
        if para.source_type == "annotation":
            annotation_texts.append(para.text)
            continue

        document = para.text
        raw_meta = asdict(para)
        flat_meta = flatten_metadata(raw_meta)
        # Inject talk-level fields when metadata is provided (D-01, D-05)
        if talk_metadata is not None:
            flat_meta["speaker_name"] = talk_metadata.speaker_name
            flat_meta["title"] = talk_metadata.title
            flat_meta["conference_year"] = talk_metadata.conference_year
            flat_meta["conference_month"] = talk_metadata.conference_month
        doc_id = f"para_{para.paragraph_id}"
        vector = embed_fn([document])[0] if embed_fn is not None else None
        records.append((document, flat_meta, doc_id, vector))

    return records, annotation_texts


def prepare_citation_records(
    citations: TalkCitations,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> list[tuple[str, dict[str, Any], str, list[float] | None]]:
    """
    Transform TalkCitations into records.

    ALL citations are included, regardless of whether their parent paragraph
    is an annotation paragraph (D-09).

    Document (D-03):
        citation.context_window if truthy, else citation.citation_text_raw.

    Metadata:
        All non-None fields as flat scalars.
        verse_list (List[int]) is comma-joined per flatten_metadata rules.

    ID:
        f"cite_{citation_id}_{paragraph_id}"

    Args:
        citations: Phase 3 output container.
        embed_fn:  Optional callable (list[str]) -> list[list[float]]. When None, vector is None.

    Returns:
        List of (document, metadata, id, vector|None) tuples.
    """
    records: list[tuple[str, dict[str, Any], str, list[float] | None]] = []

    for cite in citations.citations:
        document = cite.context_window if cite.context_window else cite.citation_text_raw
        raw_meta = asdict(cite)
        flat_meta = flatten_metadata(raw_meta)
        doc_id = f"cite_{cite.citation_id}_{cite.paragraph_id}"
        vector = embed_fn([document])[0] if embed_fn is not None else None
        records.append((document, flat_meta, doc_id, vector))

    return records


def prepare_footnote_records(
    footnotes: TalkFootnotes,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> list[tuple[str, dict[str, Any], str, list[float] | None]]:
    """
    Transform TalkFootnotes into records.

    Document (D-04):
        footnote.context_window if truthy, else footnote.footnote_text_raw.

    Metadata:
        All non-None fields as flat scalars.

    ID:
        f"fn_{footnote_id}"

    Args:
        footnotes: Phase 4 output container.
        embed_fn:  Optional callable (list[str]) -> list[list[float]]. When None, vector is None.

    Returns:
        List of (document, metadata, id, vector|None) tuples.
    """
    records: list[tuple[str, dict[str, Any], str, list[float] | None]] = []

    for fn in footnotes.footnotes:
        document = fn.context_window if fn.context_window else fn.footnote_text_raw
        raw_meta = asdict(fn)
        flat_meta = flatten_metadata(raw_meta)
        doc_id = f"fn_{fn.footnote_id}"
        vector = embed_fn([document])[0] if embed_fn is not None else None
        records.append((document, flat_meta, doc_id, vector))

    return records


# =============================================================================
# Rich (_rich) variant helpers — use rich_metadata() instead of flatten_metadata()
# =============================================================================


def _prepare_talk_record_rich(
    metadata: TalkMetadata,
    annotation_texts: list[str],
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> tuple[str, dict[str, Any], str, list[float] | None]:
    """Rich variant: uses rich_metadata() instead of flatten_metadata()."""
    if metadata.talk_preview:
        document = f"{metadata.title}\n\n{metadata.talk_preview}"
    else:
        document = metadata.title
    if metadata.topics:
        document += f"\nTopics: {', '.join(metadata.topics)}"
    raw_meta = asdict(metadata)
    meta = rich_metadata(raw_meta)
    if annotation_texts:
        meta["annotations"] = "|".join(annotation_texts)
    doc_id = f"talk_{metadata.talk_id}"
    vector = embed_fn([document])[0] if embed_fn is not None else None
    return document, meta, doc_id, vector


def _prepare_paragraph_records_rich(
    paragraphs: TalkParagraphs,
    talk_metadata: TalkMetadata | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> tuple[list[tuple[str, dict[str, Any], str, list[float] | None]], list[str]]:
    """Rich variant: uses rich_metadata() instead of flatten_metadata()."""
    records: list[tuple[str, dict[str, Any], str, list[float] | None]] = []
    annotation_texts: list[str] = []
    for para in paragraphs.paragraphs:
        if para.source_type == "annotation":
            annotation_texts.append(para.text)
            continue
        document = para.text
        raw_meta = asdict(para)
        meta = rich_metadata(raw_meta)
        if talk_metadata is not None:
            meta["speaker_name"] = talk_metadata.speaker_name
            meta["title"] = talk_metadata.title
            meta["conference_year"] = talk_metadata.conference_year
            meta["conference_month"] = talk_metadata.conference_month
        doc_id = f"para_{para.paragraph_id}"
        vector = embed_fn([document])[0] if embed_fn is not None else None
        records.append((document, meta, doc_id, vector))
    return records, annotation_texts


def _prepare_citation_records_rich(
    citations: TalkCitations,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> list[tuple[str, dict[str, Any], str, list[float] | None]]:
    """Rich variant: uses rich_metadata() instead of flatten_metadata()."""
    records: list[tuple[str, dict[str, Any], str, list[float] | None]] = []
    for cite in citations.citations:
        document = cite.context_window if cite.context_window else cite.citation_text_raw
        raw_meta = asdict(cite)
        meta = rich_metadata(raw_meta)
        doc_id = f"cite_{cite.citation_id}_{cite.paragraph_id}"
        vector = embed_fn([document])[0] if embed_fn is not None else None
        records.append((document, meta, doc_id, vector))
    return records


def _prepare_footnote_records_rich(
    footnotes: TalkFootnotes,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> list[tuple[str, dict[str, Any], str, list[float] | None]]:
    """Rich variant: uses rich_metadata() instead of flatten_metadata()."""
    records: list[tuple[str, dict[str, Any], str, list[float] | None]] = []
    for fn in footnotes.footnotes:
        document = fn.context_window if fn.context_window else fn.footnote_text_raw
        raw_meta = asdict(fn)
        meta = rich_metadata(raw_meta)
        doc_id = f"fn_{fn.footnote_id}"
        vector = embed_fn([document])[0] if embed_fn is not None else None
        records.append((document, meta, doc_id, vector))
    return records


# =============================================================================
# Bundle preparation — flat (ChromaDB) and rich (Weaviate/Qdrant) variants
# =============================================================================


def prepare_talk_bundle(
    metadata: TalkMetadata,
    paragraphs: TalkParagraphs,
    citations: TalkCitations,
    footnotes: TalkFootnotes,
    validation_report: ValidationReport,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> dict[str, list[tuple[str, dict[str, Any], str, list[float] | None]]]:
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
        embed_fn:           Optional callable (list[str]) -> list[list[float]]. When None, vector is None
                            (backward compatible with existing callers that pass no embed_fn).

    Returns:
        dict with keys "talks", "paragraphs", "citations", "footnotes",
        each mapping to a list of (document, metadata, id, vector|None) tuples.
    """
    if not validation_report.is_valid:
        logger.warning(
            "Skipping talk_id=%s — failed validation. Errors: %s",
            metadata.talk_id,
            validation_report.errors,
        )
        return {"talks": [], "paragraphs": [], "citations": [], "footnotes": []}

    # Phase 1: prepare all records WITHOUT embedding (embed_fn=None)
    paragraph_records, annotation_texts = prepare_paragraph_records(
        paragraphs, talk_metadata=metadata, embed_fn=None
    )
    talk_record = prepare_talk_record(metadata, annotation_texts, embed_fn=None)
    citation_records = prepare_citation_records(citations, embed_fn=None)
    footnote_records = prepare_footnote_records(footnotes, embed_fn=None)

    all_records = [talk_record] + paragraph_records + citation_records + footnote_records

    # Phase 2: batch-embed all documents in one call
    if embed_fn is not None:
        texts = [doc for doc, _meta, _id, _vec in all_records]
        vectors = embed_fn(texts)
        if len(vectors) != len(all_records):
            logger.error(
                "embed_fn returned %d vectors for %d records — skipping bundle talk_id=%s",
                len(vectors), len(all_records), metadata.talk_id,
            )
            return {"talks": [], "paragraphs": [], "citations": [], "footnotes": []}
        all_records = [
            (doc, meta, doc_id, vec)
            for (doc, meta, doc_id, _), vec in zip(all_records, vectors)
        ]

    # Phase 3: redistribute back into per-collection lists
    n_talk = 1
    n_para = len(paragraph_records)
    n_cite = len(citation_records)
    talk_recs = all_records[:n_talk]
    para_recs = all_records[n_talk : n_talk + n_para]
    cite_recs = all_records[n_talk + n_para : n_talk + n_para + n_cite]
    fn_recs   = all_records[n_talk + n_para + n_cite :]

    return {
        "talks": talk_recs,
        "paragraphs": para_recs,
        "citations": cite_recs,
        "footnotes": fn_recs,
    }


def prepare_talk_bundle_rich(
    metadata: TalkMetadata,
    paragraphs: TalkParagraphs,
    citations: TalkCitations,
    footnotes: TalkFootnotes,
    validation_report: ValidationReport,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> dict[str, list[tuple[str, dict[str, Any], str, list[float] | None]]]:
    """
    Prepare a complete set of records for Weaviate/Qdrant (rich metadata — native lists preserved).

    Same as prepare_talk_bundle() but uses rich_metadata() throughout instead of
    flatten_metadata(). List fields (topics, verse_list) are preserved as Python lists
    rather than joined strings.

    If validation_report.is_valid is False:
        Log a WARNING and return empty lists for all 4 collections.

    Args:
        metadata:           Phase 1 output.
        paragraphs:         Phase 2 output.
        citations:          Phase 3 output.
        footnotes:          Phase 4 output.
        validation_report:  Phase 5 output.
        embed_fn:           Optional callable (list[str]) -> list[list[float]]. When None, vector is None.

    Returns:
        dict with keys "talks", "paragraphs", "citations", "footnotes",
        each mapping to a list of (document, metadata, id, vector|None) tuples.
    """
    if not validation_report.is_valid:
        logger.warning(
            "Skipping talk_id=%s — failed validation. Errors: %s",
            metadata.talk_id,
            validation_report.errors,
        )
        return {"talks": [], "paragraphs": [], "citations": [], "footnotes": []}

    # Phase 1: prepare all records WITHOUT embedding (embed_fn=None)
    paragraph_records, annotation_texts = _prepare_paragraph_records_rich(
        paragraphs, talk_metadata=metadata, embed_fn=None
    )
    talk_record = _prepare_talk_record_rich(metadata, annotation_texts, embed_fn=None)
    citation_records = _prepare_citation_records_rich(citations, embed_fn=None)
    footnote_records = _prepare_footnote_records_rich(footnotes, embed_fn=None)

    all_records = [talk_record] + paragraph_records + citation_records + footnote_records

    # Phase 2: batch-embed all documents in one call
    if embed_fn is not None:
        texts = [doc for doc, _meta, _id, _vec in all_records]
        vectors = embed_fn(texts)
        if len(vectors) != len(all_records):
            logger.error(
                "embed_fn returned %d vectors for %d records — skipping bundle talk_id=%s",
                len(vectors), len(all_records), metadata.talk_id,
            )
            return {"talks": [], "paragraphs": [], "citations": [], "footnotes": []}
        all_records = [
            (doc, meta, doc_id, vec)
            for (doc, meta, doc_id, _), vec in zip(all_records, vectors)
        ]

    # Phase 3: redistribute back into per-collection lists
    n_talk = 1
    n_para = len(paragraph_records)
    n_cite = len(citation_records)
    talk_recs = all_records[:n_talk]
    para_recs = all_records[n_talk : n_talk + n_para]
    cite_recs = all_records[n_talk + n_para : n_talk + n_para + n_cite]
    fn_recs   = all_records[n_talk + n_para + n_cite :]

    return {
        "talks": talk_recs,
        "paragraphs": para_recs,
        "citations": cite_recs,
        "footnotes": fn_recs,
    }
