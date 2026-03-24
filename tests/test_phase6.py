"""
Unit tests for Phase 6: ChromaDB Loader (transformation functions only).

Tests all transformation functions that convert Phase 5 output bundles
into ChromaDB documents/metadatas/ids format.

No actual ChromaDB connections required -- these tests only verify the
data transformation logic.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest
from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport
from extractors.phase6_chromadb_loader import (
    _flatten_metadata,
    prepare_talk_record,
    prepare_paragraph_records,
    prepare_citation_records,
    prepare_footnote_records,
    prepare_talk_bundle,
)


# =============================================================================
# Fixtures
# =============================================================================


def make_talk_metadata(**kwargs) -> TalkMetadata:
    """Create a TalkMetadata with sensible defaults."""
    defaults = dict(
        talk_id=8820,
        speaker_id=100,
        conference_id=10,
        title="The Test Talk",
        speaker_name="Elder Tester",
        conference_year=2020,
        conference_month="April",
        conference_description="April 2020 General Conference",
        talk_date="2020-04-05",
        talk_preview="This is a preview of the talk.",
        corpus="E",
        extraction_timestamp="2026-01-01T00:00:00Z",
        extraction_version="1.0.0",
    )
    defaults.update(kwargs)
    return TalkMetadata(**defaults)


def make_paragraph(paragraph_id=1, paragraph_number=1, text="Hello world text.", source_type="p", **kwargs) -> ParagraphData:
    """Create a ParagraphData with sensible defaults."""
    defaults = dict(
        paragraph_id=paragraph_id,
        talk_id=8820,
        paragraph_number=paragraph_number,
        text=text,
        text_raw=None,
        word_count=3,
        source_type=source_type,
    )
    defaults.update(kwargs)
    return ParagraphData(**defaults)


def make_talk_paragraphs(paragraphs: list[ParagraphData]) -> TalkParagraphs:
    """Wrap paragraphs in a TalkParagraphs container."""
    total_words = sum(p.word_count for p in paragraphs)
    return TalkParagraphs(
        talk_id=8820,
        paragraphs=paragraphs,
        total_paragraphs=len(paragraphs),
        total_words=total_words,
        extraction_success=True,
    )


def make_citation(citation_id=1, paragraph_id=88200001, paragraph_number=1, **kwargs) -> CitationData:
    """Create a CitationData with sensible defaults."""
    defaults = dict(
        citation_id=citation_id,
        talk_id=8820,
        paragraph_id=paragraph_id,
        paragraph_number=paragraph_number,
        citation_text_raw="1 Ne. 3:7",
        char_position=10,
        char_end_position=18,
        scripture_ref="1 Nephi 3:7",
        book="1 Nephi",
        book_abbr="1 Ne.",
        book_id=1,
        chapter=3,
        verses="7",
        verse_start=7,
        verse_end=7,
        verse_list=[7],
        context_window="I will go and do the things 1 Ne. 3:7 which the Lord hath commanded",
    )
    defaults.update(kwargs)
    return CitationData(**defaults)


def make_talk_citations(citations: list[CitationData]) -> TalkCitations:
    """Wrap citations in a TalkCitations container."""
    return TalkCitations(
        talk_id=8820,
        citations=citations,
        total_citations=len(citations),
        extraction_success=True,
    )


def make_footnote(footnote_id=88200100, paragraph_id=88200001, paragraph_number=1, **kwargs) -> FootnoteData:
    """Create a FootnoteData with sensible defaults."""
    defaults = dict(
        footnote_id=footnote_id,
        talk_id=8820,
        paragraph_id=paragraph_id,
        paragraph_number=paragraph_number,
        footnote_number=1,
        footnote_text_raw="See John 3:16",
        char_position=20,
        context_window="surrounding text See John 3:16 more text",
    )
    defaults.update(kwargs)
    return FootnoteData(**defaults)


def make_talk_footnotes(footnotes: list[FootnoteData]) -> TalkFootnotes:
    """Wrap footnotes in a TalkFootnotes container."""
    return TalkFootnotes(
        talk_id=8820,
        footnotes=footnotes,
        total_footnotes=len(footnotes),
        extraction_success=True,
    )


def make_valid_report() -> ValidationReport:
    """Create a passing ValidationReport."""
    return ValidationReport(
        talk_id=8820,
        is_valid=True,
        errors=[],
        warnings=[],
        stats={},
    )


def make_invalid_report() -> ValidationReport:
    """Create a failing ValidationReport."""
    return ValidationReport(
        talk_id=8820,
        is_valid=False,
        errors=["Missing required metadata", "No paragraphs"],
        warnings=[],
        stats={},
    )


# =============================================================================
# Tests: _flatten_metadata
# =============================================================================


class TestFlattenMetadata:
    def test_flatten_metadata_removes_none_values(self):
        meta = {"a": 1, "b": None, "c": "hello"}
        result = _flatten_metadata(meta)
        assert "b" not in result
        assert result["a"] == 1
        assert result["c"] == "hello"

    def test_flatten_metadata_removes_empty_lists(self):
        meta = {"a": 1, "empty_list": [], "non_empty": [1, 2]}
        result = _flatten_metadata(meta)
        assert "empty_list" not in result
        assert "non_empty" in result

    def test_flatten_metadata_joins_int_list_with_comma(self):
        meta = {"verse_list": [32, 33, 44]}
        result = _flatten_metadata(meta)
        assert result["verse_list"] == "32,33,44"

    def test_flatten_metadata_joins_str_list_with_pipe(self):
        meta = {"extraction_warnings": ["warn a", "warn b"]}
        result = _flatten_metadata(meta)
        assert result["extraction_warnings"] == "warn a|warn b"

    def test_flatten_metadata_preserves_scalars(self):
        meta = {"talk_id": 8820, "score": 0.95, "is_valid": True, "title": "Test"}
        result = _flatten_metadata(meta)
        assert result["talk_id"] == 8820
        assert result["score"] == 0.95
        assert result["is_valid"] is True
        assert result["title"] == "Test"

    def test_flatten_metadata_empty_dict(self):
        result = _flatten_metadata({})
        assert result == {}

    def test_flatten_metadata_single_item_list(self):
        meta = {"verse_list": [7]}
        result = _flatten_metadata(meta)
        assert result["verse_list"] == "7"


# =============================================================================
# Tests: prepare_talk_record
# =============================================================================


class TestPrepareTalkRecord:
    def test_prepare_talk_record_with_preview(self):
        metadata = make_talk_metadata(title="The Test Talk", talk_preview="This is a preview.")
        doc, meta, doc_id = prepare_talk_record(metadata, annotation_texts=[])
        assert doc == "The Test Talk\n\nThis is a preview."
        assert doc_id == "talk_8820"

    def test_prepare_talk_record_no_preview(self):
        metadata = make_talk_metadata(title="The Test Talk", talk_preview=None)
        doc, meta, doc_id = prepare_talk_record(metadata, annotation_texts=[])
        assert doc == "The Test Talk"
        assert doc_id == "talk_8820"

    def test_prepare_talk_record_empty_preview_string(self):
        """Empty string talk_preview should fall back to title only."""
        metadata = make_talk_metadata(title="The Test Talk", talk_preview="")
        doc, meta, doc_id = prepare_talk_record(metadata, annotation_texts=[])
        assert doc == "The Test Talk"

    def test_prepare_talk_record_metadata_has_required_fields(self):
        metadata = make_talk_metadata()
        doc, meta, doc_id = prepare_talk_record(metadata, annotation_texts=[])
        assert meta["talk_id"] == 8820
        assert meta["speaker_name"] == "Elder Tester"
        assert meta["conference_year"] == 2020

    def test_prepare_talk_record_metadata_excludes_none_fields(self):
        metadata = make_talk_metadata(session_id=None, session_description=None)
        doc, meta, doc_id = prepare_talk_record(metadata, annotation_texts=[])
        assert "session_id" not in meta
        assert "session_description" not in meta

    def test_prepare_talk_record_with_annotations(self):
        metadata = make_talk_metadata()
        annotation_texts = ["Anno text 1", "Anno text 2"]
        doc, meta, doc_id = prepare_talk_record(metadata, annotation_texts=annotation_texts)
        assert meta["annotations"] == "Anno text 1|Anno text 2"

    def test_prepare_talk_record_no_annotations_field_absent(self):
        """When no annotations, the annotations key should not appear in metadata."""
        metadata = make_talk_metadata()
        doc, meta, doc_id = prepare_talk_record(metadata, annotation_texts=[])
        assert "annotations" not in meta

    def test_prepare_talk_record_id_format(self):
        metadata = make_talk_metadata(talk_id=12345)
        doc, meta, doc_id = prepare_talk_record(metadata, annotation_texts=[])
        assert doc_id == "talk_12345"


# =============================================================================
# Tests: prepare_paragraph_records
# =============================================================================


class TestPrepareParagraphRecords:
    def test_prepare_paragraph_records_basic(self):
        p1 = make_paragraph(paragraph_id=88200001, paragraph_number=1, text="First paragraph text.")
        p2 = make_paragraph(paragraph_id=88200002, paragraph_number=2, text="Second paragraph text.")
        talk_paras = make_talk_paragraphs([p1, p2])
        records, annotation_texts = prepare_paragraph_records(talk_paras)
        assert len(records) == 2
        assert annotation_texts == []

    def test_prepare_paragraph_records_document_is_text(self):
        p = make_paragraph(paragraph_id=88200001, text="The paragraph content.")
        talk_paras = make_talk_paragraphs([p])
        records, _ = prepare_paragraph_records(talk_paras)
        doc, meta, doc_id = records[0]
        assert doc == "The paragraph content."

    def test_prepare_paragraph_records_id_format(self):
        p = make_paragraph(paragraph_id=88200001)
        talk_paras = make_talk_paragraphs([p])
        records, _ = prepare_paragraph_records(talk_paras)
        doc, meta, doc_id = records[0]
        assert doc_id == "para_88200001"

    def test_annotation_exclusion(self):
        """Annotation paragraphs must not appear in paragraph records."""
        p_normal = make_paragraph(paragraph_id=88200001, paragraph_number=1, text="Normal text.", source_type="p", word_count=2)
        p_anno = make_paragraph(paragraph_id=88200002, paragraph_number=2, text="Annotation text.", source_type="annotation", word_count=2)
        talk_paras = make_talk_paragraphs([p_normal, p_anno])
        records, annotation_texts = prepare_paragraph_records(talk_paras)
        assert len(records) == 1
        doc, meta, doc_id = records[0]
        assert doc_id == "para_88200001"

    def test_annotation_folding(self):
        """Annotation paragraph texts are collected and returned separately."""
        p_normal = make_paragraph(paragraph_id=88200001, paragraph_number=1, text="Normal text.", source_type="p", word_count=2)
        p_anno1 = make_paragraph(paragraph_id=88200002, paragraph_number=2, text="Anno 1.", source_type="annotation", word_count=2)
        p_anno2 = make_paragraph(paragraph_id=88200003, paragraph_number=3, text="Anno 2.", source_type="annotation", word_count=2)
        talk_paras = make_talk_paragraphs([p_normal, p_anno1, p_anno2])
        records, annotation_texts = prepare_paragraph_records(talk_paras)
        assert len(records) == 1
        assert annotation_texts == ["Anno 1.", "Anno 2."]

    def test_prepare_paragraph_records_warnings_flattened(self):
        """extraction_warnings list must be pipe-joined in metadata."""
        p = make_paragraph(
            paragraph_id=88200001, text="Text with warnings.",
            extraction_warnings=["warn1", "warn2"],
        )
        talk_paras = make_talk_paragraphs([p])
        records, _ = prepare_paragraph_records(talk_paras)
        doc, meta, doc_id = records[0]
        assert meta["extraction_warnings"] == "warn1|warn2"

    def test_prepare_paragraph_records_empty_warnings_excluded(self):
        """Empty extraction_warnings list must not appear in metadata."""
        p = make_paragraph(paragraph_id=88200001, text="Clean text.", extraction_warnings=[])
        talk_paras = make_talk_paragraphs([p])
        records, _ = prepare_paragraph_records(talk_paras)
        doc, meta, doc_id = records[0]
        assert "extraction_warnings" not in meta


# =============================================================================
# Tests: prepare_citation_records
# =============================================================================


class TestPrepareCitationRecords:
    def test_prepare_citation_records_basic(self):
        c = make_citation(citation_id=1, paragraph_id=88200001)
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        assert len(records) == 1

    def test_prepare_citation_records_document_is_context_window(self):
        c = make_citation(context_window="the surrounding context window text")
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        doc, meta, doc_id = records[0]
        assert doc == "the surrounding context window text"

    def test_prepare_citation_records_fallback_to_raw(self):
        """When context_window is empty, fall back to citation_text_raw."""
        c = make_citation(context_window="", citation_text_raw="D&C 84:32-44")
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        doc, meta, doc_id = records[0]
        assert doc == "D&C 84:32-44"

    def test_prepare_citation_records_id_format(self):
        c = make_citation(citation_id=42, paragraph_id=88200003)
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        doc, meta, doc_id = records[0]
        assert doc_id == "cite_42_88200003"

    def test_prepare_citation_records_verse_list_flattened(self):
        """verse_list must be comma-joined in metadata."""
        c = make_citation(verse_list=[32, 33, 44])
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        doc, meta, doc_id = records[0]
        assert meta["verse_list"] == "32,33,44"

    def test_annotation_citation_included(self):
        """Citations from annotation paragraphs are included in citation records."""
        # paragraph_id 88200002 is an annotation paragraph (excluded from paragraphs)
        # but its citation must still be included
        c_normal = make_citation(citation_id=1, paragraph_id=88200001)
        c_from_anno = make_citation(citation_id=2, paragraph_id=88200002)
        talk_cites = make_talk_citations([c_normal, c_from_anno])
        records = prepare_citation_records(talk_cites)
        assert len(records) == 2
        ids = [r[2] for r in records]
        assert "cite_1_88200001" in ids
        assert "cite_2_88200002" in ids


# =============================================================================
# Tests: prepare_footnote_records
# =============================================================================


class TestPrepareFootnoteRecords:
    def test_prepare_footnote_records_basic(self):
        fn = make_footnote(footnote_id=88200100, paragraph_id=88200001)
        talk_fns = make_talk_footnotes([fn])
        records = prepare_footnote_records(talk_fns)
        assert len(records) == 1

    def test_prepare_footnote_records_document_is_context_window(self):
        fn = make_footnote(context_window="context around the footnote reference")
        talk_fns = make_talk_footnotes([fn])
        records = prepare_footnote_records(talk_fns)
        doc, meta, doc_id = records[0]
        assert doc == "context around the footnote reference"

    def test_prepare_footnote_records_fallback_to_raw(self):
        """When context_window is empty, fall back to footnote_text_raw."""
        fn = make_footnote(context_window="", footnote_text_raw="See John 3:16")
        talk_fns = make_talk_footnotes([fn])
        records = prepare_footnote_records(talk_fns)
        doc, meta, doc_id = records[0]
        assert doc == "See John 3:16"

    def test_prepare_footnote_records_id_format(self):
        fn = make_footnote(footnote_id=88200100)
        talk_fns = make_talk_footnotes([fn])
        records = prepare_footnote_records(talk_fns)
        doc, meta, doc_id = records[0]
        assert doc_id == "fn_88200100"

    def test_prepare_footnote_records_warnings_flattened(self):
        """extraction_warnings list must be pipe-joined in metadata."""
        fn = make_footnote(extraction_warnings=["w1", "w2"])
        talk_fns = make_talk_footnotes([fn])
        records = prepare_footnote_records(talk_fns)
        doc, meta, doc_id = records[0]
        assert meta["extraction_warnings"] == "w1|w2"


# =============================================================================
# Tests: prepare_talk_bundle
# =============================================================================


class TestPrepareTalkBundle:
    def _make_bundle(self, paragraphs=None, citations=None, footnotes=None, validation_report=None):
        """Helper to build a full bundle with defaults."""
        metadata = make_talk_metadata()

        if paragraphs is None:
            p = make_paragraph(paragraph_id=88200001)
            paragraphs = make_talk_paragraphs([p])

        if citations is None:
            c = make_citation(citation_id=1, paragraph_id=88200001)
            citations = make_talk_citations([c])

        if footnotes is None:
            fn = make_footnote(footnote_id=88200100, paragraph_id=88200001)
            footnotes = make_talk_footnotes([fn])

        if validation_report is None:
            validation_report = make_valid_report()

        return metadata, paragraphs, citations, footnotes, validation_report

    def test_prepare_talk_bundle_returns_correct_keys(self):
        bundle = self._make_bundle()
        result = prepare_talk_bundle(*bundle)
        assert set(result.keys()) == {"talks", "paragraphs", "citations", "footnotes"}

    def test_prepare_talk_bundle_talks_is_single_record(self):
        bundle = self._make_bundle()
        result = prepare_talk_bundle(*bundle)
        assert len(result["talks"]) == 1
        doc, meta, doc_id = result["talks"][0]
        assert doc_id == "talk_8820"

    def test_prepare_talk_bundle_paragraphs_list(self):
        bundle = self._make_bundle()
        result = prepare_talk_bundle(*bundle)
        assert len(result["paragraphs"]) == 1

    def test_prepare_talk_bundle_citations_list(self):
        bundle = self._make_bundle()
        result = prepare_talk_bundle(*bundle)
        assert len(result["citations"]) == 1

    def test_prepare_talk_bundle_footnotes_list(self):
        bundle = self._make_bundle()
        result = prepare_talk_bundle(*bundle)
        assert len(result["footnotes"]) == 1

    def test_invalid_talk_skipped(self):
        """When validation_report.is_valid is False, all 4 collections return empty lists."""
        bundle = self._make_bundle(validation_report=make_invalid_report())
        result = prepare_talk_bundle(*bundle)
        assert result["talks"] == []
        assert result["paragraphs"] == []
        assert result["citations"] == []
        assert result["footnotes"] == []

    def test_bundle_annotation_folding_end_to_end(self):
        """Annotations excluded from paragraphs but their text appears in talk metadata."""
        metadata = make_talk_metadata()
        p_normal = make_paragraph(paragraph_id=88200001, paragraph_number=1, text="Normal body text.", source_type="p", word_count=3)
        p_anno = make_paragraph(paragraph_id=88200002, paragraph_number=2, text="Annotation content.", source_type="annotation", word_count=2)
        paragraphs = make_talk_paragraphs([p_normal, p_anno])
        citations = make_talk_citations([])
        footnotes = make_talk_footnotes([])
        validation_report = make_valid_report()

        result = prepare_talk_bundle(metadata, paragraphs, citations, footnotes, validation_report)

        # Only 1 paragraph record (annotation excluded)
        assert len(result["paragraphs"]) == 1
        assert result["paragraphs"][0][2] == "para_88200001"

        # Talk metadata has annotations field
        doc, meta, doc_id = result["talks"][0]
        assert meta.get("annotations") == "Annotation content."
