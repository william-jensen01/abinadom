"""
Shared data transformation utilities for all vector DB loaders.

Contains rich_metadata and all prepare_* functions (Weaviate/Qdrant native-list format).
Importable without installing weaviate-client or qdrant-client.
No DB-client dependencies — pure data transforms using stdlib and project models only.
"""

import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, NamedTuple

sys.path.append(str(Path(__file__).parent.parent))

from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport

logger = logging.getLogger(__name__)


# Type alias — kept as tuple to match the loader iteration pattern
TalkBundle = tuple[TalkMetadata, TalkParagraphs, TalkCitations, TalkFootnotes, ValidationReport]


# =============================================================================
# Metadata normalization helpers
# =============================================================================


def rich_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a metadata dict for Weaviate and Qdrant native array support.

    Rules applied:
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

    Uses rich_metadata() so list fields (topics) are preserved as native Python lists.

    Args:
        metadata:         Talk metadata output for this talk.
        annotation_texts: Text strings from annotation paragraphs (may be empty).
        embed_fn:         Optional callable (list[str]) -> list[list[float]]. When None, vector is None.

    Returns:
        (document, metadata_dict, doc_id, vector|None)
    """
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


def prepare_paragraph_records(
    paragraphs: TalkParagraphs,
    talk_metadata: TalkMetadata | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> tuple[list[tuple[str, dict[str, Any], str, list[float] | None]], list[str]]:
    """
    Transform TalkParagraphs into records, splitting by source_type.

    Uses rich_metadata() so list fields are preserved as native Python lists.
    Annotation paragraphs (source_type == "annotation") are excluded from records;
    their text is collected and returned for folding into talk metadata.

    Args:
        paragraphs:    Paragraph extraction output container.
        talk_metadata: Optional talk metadata. When provided, speaker_name,
            title, conference_year, and conference_month are injected into each
            paragraph record's metadata.
        embed_fn:      Optional callable (list[str]) -> list[list[float]]. When None, vector is None.

    Returns:
        (list_of_records, annotation_texts)
    """
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


def prepare_citation_records(
    citations: TalkCitations,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> list[tuple[str, dict[str, Any], str, list[float] | None]]:
    """
    Transform TalkCitations into records.

    Uses rich_metadata() so list fields (verse_list) are preserved as native Python lists.
    ALL citations are included regardless of whether their parent paragraph is an annotation.

    Args:
        citations: Citation extraction output container.
        embed_fn:  Optional callable (list[str]) -> list[list[float]]. When None, vector is None.

    Returns:
        List of (document, metadata, id, vector|None) tuples.
    """
    records: list[tuple[str, dict[str, Any], str, list[float] | None]] = []
    for cite in citations.citations:
        document = cite.context_window if cite.context_window else cite.citation_text_raw
        raw_meta = asdict(cite)
        meta = rich_metadata(raw_meta)
        doc_id = f"cite_{cite.citation_id}_{cite.paragraph_id}"
        vector = embed_fn([document])[0] if embed_fn is not None else None
        records.append((document, meta, doc_id, vector))
    return records


def prepare_footnote_records(
    footnotes: TalkFootnotes,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> list[tuple[str, dict[str, Any], str, list[float] | None]]:
    """
    Transform TalkFootnotes into records.

    Uses rich_metadata() so list fields are preserved as native Python lists.

    Args:
        footnotes: Footnote extraction output container.
        embed_fn:  Optional callable (list[str]) -> list[list[float]]. When None, vector is None.

    Returns:
        List of (document, metadata, id, vector|None) tuples.
    """
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
# Bundle preparation
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
    Prepare a complete set of Weaviate/Qdrant records for a single talk across all 4 collections.

    Uses rich_metadata() throughout — list fields (topics, verse_list) are preserved as
    native Python lists rather than joined strings.

    If validation_report.is_valid is False:
        Log a WARNING and return empty lists for all 4 collections.

    Raises:
        ValueError: If embed_fn returns a different number of vectors than records.

    Args:
        metadata:           Talk metadata output.
        paragraphs:         Paragraph extraction output.
        citations:          Citation extraction output.
        footnotes:          Footnote extraction output.
        validation_report:  Validation output.
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
            # Raise rather than skip: an empty result would let the caller count
            # the talk as loaded when nothing was written.
            raise ValueError(
                f"embed_fn returned {len(vectors)} vectors for {len(all_records)} "
                f"records (talk_id={metadata.talk_id})"
            )
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


def load_talk_bundles(bundles: list[TalkBundle], loader) -> dict:
    """Load a list of talk bundles into the given loader. Returns a summary dict."""
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

    # Drain any records the loader buffered internally (no-op for non-buffering loaders)
    loader.flush()

    return {
        "talks_inserted": talks_inserted,
        "paragraphs_inserted": paragraphs_inserted,
        "citations_inserted": citations_inserted,
        "footnotes_inserted": footnotes_inserted,
        "skipped_talks": skipped_talks,
        "skipped_count": len(skipped_talks),
    }


# =============================================================================
# Scriptures
# =============================================================================

class ScriptureBundle(NamedTuple):
    """One unit of a scripture load (a book, a JST-only book, or the front matter), read out of scripture.db.

    verses:     canonical verse rows, ordered by (chapter, verse). Keys: book, book_uri, cite_abbr, volume, chapter,
                verse, text, aid, footnote_count, jst_refs (list[str]), has_jst (bool)
    jst_verses: the `F` JST verse rows in JST numbering. Keys: book, book_uri, cite_abbr, volume, chapter, verse,
                text, kjv_refs (list[str])
    chapters:   chapter/section/document pages. Keys: page_uri, book (or None), volume, number (or None),
                cite_abbr (or None), title, summary, intro, kind, verse_count
    """
    verses: list
    jst_verses: list
    chapters: list


def _records(pending: list, skip, embed_fn) -> list[tuple[str, dict[str, Any], str, list[float] | None]]:
    """pending = [(embed string, metadata, doc_id)]: drop the skipped ones, then embed the rest in one call."""
    pending = [(text, rich_metadata(meta), doc_id) for text, meta, doc_id in pending if not (skip and skip(doc_id))]
    vectors = embed_fn([p[0] for p in pending]) if embed_fn is not None and pending else [None] * len(pending)
    return [(*p, vec) for p, vec in zip(pending, vectors)]


def prepare_verse_records(
    verses: list[dict],
    jst_verses: list[dict],
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    radius: int = 1,
    skip: Callable[[str], bool] | None = None,
) -> list[tuple[str, dict[str, Any], str, list[float] | None]]:
    """
    Transform scripture verse rows into (document, metadata, doc_id, vector|None) tuples for ScriptureVerses.

    Canonical verses embed "{book} {chapter}:{verse}\\n{prev}\\n{this}\\n{next}": the window holds `radius` neighbours
    each side, never crosses a chapter, and is stored as `context_window`. JST (`F`) verses embed alone as
    "JST {book} {chapter}:{verse}\\n{text}". `skip(doc_id)` drops a record already loaded before anything is embedded;
    windows are built from the whole chapter, so skipping never changes the rest.
    """
    pending = []
    chapters: dict[Any, list[dict]] = {}
    for v in verses:
        chapters.setdefault((v["book_uri"], v["chapter"]), []).append(v)
    for chapter in chapters.values():
        for i, v in enumerate(chapter):
            doc_id = f"verse_{v['book_uri']}_{v['chapter']}_{v['verse']}"
            near = chapter[max(0, i - radius): i + radius + 1]
            window = f"{v['book']} {v['chapter']}:{v['verse']}\n" + "\n".join(n["text"] for n in near)
            pending.append((window, {
                "variant": "standard", "book": v["book"], "book_uri": v["book_uri"], "cite_abbr": v["cite_abbr"],
                "volume": v["volume"], "chapter": v["chapter"], "verse": v["verse"],
                "reference": f"{v['cite_abbr']} {v['chapter']}:{v['verse']}", "text": v["text"],
                "has_jst": bool(v.get("has_jst")), "jst_refs": list(v.get("jst_refs") or []), "aid": v.get("aid"),
                "footnote_count": v.get("footnote_count", 0), "context_window": window, "doc_id_str": doc_id,
            }, doc_id))
    for j in jst_verses:
        doc_id = f"jst_{j['book_uri']}_{j['chapter']}_{j['verse']}"
        window = f"JST {j['book']} {j['chapter']}:{j['verse']}\n{j['text']}"
        pending.append((window, {
            "variant": "jst", "book": j["book"], "book_uri": j["book_uri"], "cite_abbr": j["cite_abbr"],
            "volume": j["volume"], "chapter": j["chapter"], "verse": j["verse"],
            "reference": f"JST {j['cite_abbr']} {j['chapter']}:{j['verse']}", "text": j["text"],
            "kjv_refs": list(j.get("kjv_refs") or []), "footnote_count": 0, "context_window": window,
            "doc_id_str": doc_id,
        }, doc_id))
    return _records(pending, skip, embed_fn)


def prepare_chapter_records(
    chapters: list[dict],
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    skip: Callable[[str], bool] | None = None,
) -> list[tuple[str, dict[str, Any], str, list[float] | None]]:
    """
    Transform chapter/section/document page rows into ScriptureChapters tuples.

    The reference is "{cite_abbr} {number}" ("Alma 32", "D&C 45"); a page with no book or number (front matter) is
    referenced by its title. The vector is over "{reference}: {title}\\n{intro}\\n{summary}".
    """
    pending = []
    for c in chapters:
        doc_id = f"chapter_{c['page_uri']}"
        has_number = c.get("cite_abbr") and c.get("number") is not None
        reference = f"{c['cite_abbr']} {c['number']}" if has_number else c["title"]
        text = f"{reference}: {c.get('title') or ''}\n{c.get('intro') or ''}\n{c.get('summary') or ''}"
        pending.append((text, {
            "book": c.get("book"), "volume": c.get("volume"), "chapter": c.get("number"), "reference": reference,
            "title": c.get("title"), "summary": c.get("summary"), "intro": c.get("intro"), "kind": c["kind"],
            "verse_count": c.get("verse_count", 0), "uri": c["page_uri"], "doc_id_str": doc_id,
        }, doc_id))
    return _records(pending, skip, embed_fn)
