"""
Unit tests for loaders/shared_transforms.py.

Tests rich_metadata, prepare_talk_record, prepare_paragraph_records,
prepare_citation_records, prepare_footnote_records, and prepare_talk_bundle.
Imports from loaders.shared_transforms (public API).
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
from loaders.shared_transforms import (
    rich_metadata,
    prepare_talk_record,
    prepare_paragraph_records,
    prepare_citation_records,
    prepare_footnote_records,
    prepare_talk_bundle,
)


# =============================================================================
# Factory functions
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


def make_paragraph(paragraph_id=88200001, paragraph_number=1, text="Hello world text.", **kwargs) -> ParagraphData:
    """Create a ParagraphData with sensible defaults."""
    defaults = dict(
        paragraph_id=paragraph_id,
        talk_id=8820,
        paragraph_number=paragraph_number,
        text=text,
        text_raw=None,
        word_count=3,
        source_type="p",
    )
    defaults.update(kwargs)
    return ParagraphData(**defaults)


def make_talk_paragraphs(paragraphs=None) -> TalkParagraphs:
    """Wrap paragraphs in a TalkParagraphs container."""
    if paragraphs is None:
        paragraphs = [make_paragraph()]
    total_words = sum(p.word_count for p in paragraphs)
    return TalkParagraphs(
        talk_id=8820,
        paragraphs=paragraphs,
        total_paragraphs=len(paragraphs),
        total_words=total_words,
        extraction_success=True,
    )


def make_talk_citations(citations=None) -> TalkCitations:
    """Wrap citations in a TalkCitations container."""
    if citations is None:
        citations = []
    return TalkCitations(
        talk_id=8820,
        citations=citations,
        total_citations=len(citations),
        extraction_success=True,
    )


def make_talk_footnotes(footnotes=None) -> TalkFootnotes:
    """Wrap footnotes in a TalkFootnotes container."""
    if footnotes is None:
        footnotes = []
    return TalkFootnotes(
        talk_id=8820,
        footnotes=footnotes,
        total_footnotes=len(footnotes),
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


def make_validation_report(is_valid=True) -> ValidationReport:
    """Create a ValidationReport."""
    return ValidationReport(
        talk_id=8820,
        is_valid=is_valid,
        errors=[],
        warnings=[],
        stats={},
    )


# =============================================================================
# Tests: rich_metadata
# =============================================================================


class TestRichMetadata:
    def test_removes_none_values(self):
        """None values are dropped; non-None values including lists are kept."""
        meta = {"a": None, "b": [1, 2]}
        result = rich_metadata(meta)
        assert "a" not in result
        assert result["b"] == [1, 2]

    def test_preserves_lists(self):
        """Lists are preserved as-is (not flattened to strings)."""
        meta = {"b": [1, 2], "c": ["x", "y"]}
        result = rich_metadata(meta)
        assert result["b"] == [1, 2]
        assert result["c"] == ["x", "y"]

    def test_spec_acceptance_criterion(self):
        """SPEC Req 3 acceptance criterion: None removed, lists preserved."""
        meta = {"a": None, "b": [1, 2], "c": ["x", "y"]}
        result = rich_metadata(meta)
        assert result == {"b": [1, 2], "c": ["x", "y"]}

    def test_empty_dict_returns_empty_dict(self):
        """Empty input produces empty output."""
        result = rich_metadata({})
        assert result == {}

    def test_preserves_all_scalar_types(self):
        """Scalar values (int, float, bool, str) pass through unchanged."""
        meta = {"x": 42, "y": 3.14, "z": True, "w": "hello"}
        result = rich_metadata(meta)
        assert result == meta


# =============================================================================
# Tests: prepare_talk_bundle
# =============================================================================


class TestPrepareTalkBundle:
    def test_returns_dict_with_four_keys(self):
        """Result dict has exactly the keys: talks, paragraphs, citations, footnotes."""
        metadata = make_talk_metadata()
        paragraphs = make_talk_paragraphs()
        citations = make_talk_citations()
        footnotes = make_talk_footnotes()
        report = make_validation_report()

        result = prepare_talk_bundle(metadata, paragraphs, citations, footnotes, report)

        assert set(result.keys()) == {"talks", "paragraphs", "citations", "footnotes"}

    def test_valid_bundle_produces_nonempty_talks(self):
        """A valid bundle produces non-empty lists for talks and paragraphs."""
        metadata = make_talk_metadata()
        paragraphs = make_talk_paragraphs()
        citations = make_talk_citations()
        footnotes = make_talk_footnotes()
        report = make_validation_report()

        result = prepare_talk_bundle(metadata, paragraphs, citations, footnotes, report)

        assert len(result["talks"]) > 0
        assert len(result["paragraphs"]) > 0


# =============================================================================
# Tests: prepare_talk_record
# =============================================================================


class TestPrepareTalkRecord:
    def test_with_preview(self):
        """Document includes title and talk_preview when preview is truthy."""
        metadata = make_talk_metadata(title="The Test Talk", talk_preview="This is a preview.")
        doc, meta, doc_id, vector = prepare_talk_record(metadata, annotation_texts=[])
        assert doc.startswith("The Test Talk\n\nThis is a preview.")
        assert doc_id == "talk_8820"
        assert vector is None

    def test_no_preview_fallback(self):
        """Document is title only when talk_preview is None."""
        metadata = make_talk_metadata(title="The Test Talk", talk_preview=None)
        doc, meta, doc_id, _ = prepare_talk_record(metadata, annotation_texts=[])
        assert doc == "The Test Talk"

    def test_empty_preview_string_fallback(self):
        """Empty string talk_preview falls back to title only."""
        metadata = make_talk_metadata(title="The Test Talk", talk_preview="")
        doc, meta, doc_id, _ = prepare_talk_record(metadata, annotation_texts=[])
        assert doc == "The Test Talk"

    def test_metadata_has_required_fields(self):
        """Returned metadata includes talk_id, speaker_name, conference_year."""
        metadata = make_talk_metadata()
        doc, meta, doc_id, _ = prepare_talk_record(metadata, annotation_texts=[])
        assert meta["talk_id"] == 8820
        assert meta["speaker_name"] == "Elder Tester"
        assert meta["conference_year"] == 2020

    def test_metadata_excludes_none_fields(self):
        """None-valued fields are excluded from metadata."""
        metadata = make_talk_metadata(session_id=None, session_description=None)
        doc, meta, doc_id, _ = prepare_talk_record(metadata, annotation_texts=[])
        assert "session_id" not in meta
        assert "session_description" not in meta

    def test_with_annotations(self):
        """Annotation texts are pipe-joined and stored in metadata['annotations']."""
        metadata = make_talk_metadata()
        doc, meta, doc_id, _ = prepare_talk_record(metadata, annotation_texts=["Anno 1", "Anno 2"])
        assert meta["annotations"] == "Anno 1|Anno 2"

    def test_no_annotations_key_absent(self):
        """When no annotations, 'annotations' key is absent from metadata."""
        metadata = make_talk_metadata()
        doc, meta, doc_id, _ = prepare_talk_record(metadata, annotation_texts=[])
        assert "annotations" not in meta

    def test_doc_id_format(self):
        """doc_id follows 'talk_{talk_id}' format."""
        metadata = make_talk_metadata(talk_id=12345)
        doc, meta, doc_id, _ = prepare_talk_record(metadata, annotation_texts=[])
        assert doc_id == "talk_12345"


# =============================================================================
# Tests: prepare_paragraph_records
# =============================================================================


class TestPrepareParagraphRecords:
    def test_basic_returns_records(self):
        """Two non-annotation paragraphs yield 2 records and empty annotation_texts."""
        p1 = make_paragraph(paragraph_id=88200001, paragraph_number=1, text="First paragraph text.")
        p2 = make_paragraph(paragraph_id=88200002, paragraph_number=2, text="Second paragraph text.")
        talk_paras = make_talk_paragraphs([p1, p2])
        records, annotation_texts = prepare_paragraph_records(talk_paras)
        assert len(records) == 2
        assert annotation_texts == []

    def test_document_is_paragraph_text(self):
        """Document in each record is the paragraph text."""
        p = make_paragraph(paragraph_id=88200001, text="The paragraph content.")
        talk_paras = make_talk_paragraphs([p])
        records, _ = prepare_paragraph_records(talk_paras)
        doc, meta, doc_id, _ = records[0]
        assert doc == "The paragraph content."

    def test_id_format(self):
        """doc_id follows 'para_{paragraph_id}' format."""
        p = make_paragraph(paragraph_id=88200001)
        talk_paras = make_talk_paragraphs([p])
        records, _ = prepare_paragraph_records(talk_paras)
        doc, meta, doc_id, _ = records[0]
        assert doc_id == "para_88200001"

    def test_annotation_exclusion(self):
        """Annotation paragraphs are excluded from records."""
        p_normal = make_paragraph(paragraph_id=88200001, source_type="p")
        p_anno = make_paragraph(paragraph_id=88200002, source_type="annotation")
        talk_paras = make_talk_paragraphs([p_normal, p_anno])
        records, annotation_texts = prepare_paragraph_records(talk_paras)
        assert len(records) == 1
        assert records[0][2] == "para_88200001"

    def test_annotation_folding(self):
        """Annotation paragraph texts are returned in annotation_texts list."""
        p_normal = make_paragraph(paragraph_id=88200001, source_type="p")
        p_anno1 = make_paragraph(paragraph_id=88200002, source_type="annotation", text="Anno 1.")
        p_anno2 = make_paragraph(paragraph_id=88200003, source_type="annotation", text="Anno 2.")
        talk_paras = make_talk_paragraphs([p_normal, p_anno1, p_anno2])
        records, annotation_texts = prepare_paragraph_records(talk_paras)
        assert len(records) == 1
        assert annotation_texts == ["Anno 1.", "Anno 2."]

    def test_enrichment_injects_four_fields(self):
        """When talk_metadata is provided, speaker_name, title, conference_year, conference_month are injected."""
        p = make_paragraph(paragraph_id=88200001)
        talk_paras = make_talk_paragraphs([p])
        meta = make_talk_metadata()
        records, _ = prepare_paragraph_records(talk_paras, talk_metadata=meta)
        _, flat_meta, _, _ = records[0]
        assert flat_meta["speaker_name"] == "Elder Tester"
        assert flat_meta["title"] == "The Test Talk"
        assert flat_meta["conference_year"] == 2020
        assert flat_meta["conference_month"] == "April"

    def test_enrichment_absent_when_no_talk_metadata(self):
        """When talk_metadata is None, no injected fields appear."""
        p = make_paragraph(paragraph_id=88200001)
        talk_paras = make_talk_paragraphs([p])
        records, _ = prepare_paragraph_records(talk_paras)
        _, flat_meta, _, _ = records[0]
        assert "speaker_name" not in flat_meta
        assert "title" not in flat_meta


# =============================================================================
# Tests: prepare_citation_records
# =============================================================================


class TestPrepareCitationRecords:
    def test_basic(self):
        """One citation yields one record."""
        c = make_citation(citation_id=1, paragraph_id=88200001)
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        assert len(records) == 1

    def test_document_is_context_window(self):
        """Document is the context_window when it is truthy."""
        c = make_citation(context_window="the surrounding context window text")
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        doc, meta, doc_id, _ = records[0]
        assert doc == "the surrounding context window text"

    def test_fallback_to_raw(self):
        """When context_window is empty, falls back to citation_text_raw."""
        c = make_citation(context_window="", citation_text_raw="D&C 84:32-44")
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        doc, meta, doc_id, _ = records[0]
        assert doc == "D&C 84:32-44"

    def test_id_format(self):
        """doc_id follows 'cite_{citation_id}_{paragraph_id}' format."""
        c = make_citation(citation_id=42, paragraph_id=88200003)
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        doc, meta, doc_id, _ = records[0]
        assert doc_id == "cite_42_88200003"

    def test_verse_list_preserved_as_list(self):
        """verse_list is preserved as a native list in metadata."""
        c = make_citation(verse_list=[32, 33, 44])
        talk_cites = make_talk_citations([c])
        records = prepare_citation_records(talk_cites)
        doc, meta, doc_id, _ = records[0]
        assert meta["verse_list"] == [32, 33, 44]


# =============================================================================
# Tests: prepare_footnote_records
# =============================================================================


class TestPrepareFootnoteRecords:
    def test_basic(self):
        """One footnote yields one record."""
        fn = make_footnote(footnote_id=88200100, paragraph_id=88200001)
        talk_fns = make_talk_footnotes([fn])
        records = prepare_footnote_records(talk_fns)
        assert len(records) == 1

    def test_document_is_context_window(self):
        """Document is context_window when truthy."""
        fn = make_footnote(context_window="context around the footnote reference")
        talk_fns = make_talk_footnotes([fn])
        records = prepare_footnote_records(talk_fns)
        doc, meta, doc_id, _ = records[0]
        assert doc == "context around the footnote reference"

    def test_fallback_to_raw(self):
        """When context_window is empty, falls back to footnote_text_raw."""
        fn = make_footnote(context_window="", footnote_text_raw="See John 3:16")
        talk_fns = make_talk_footnotes([fn])
        records = prepare_footnote_records(talk_fns)
        doc, meta, doc_id, _ = records[0]
        assert doc == "See John 3:16"

    def test_id_format(self):
        """doc_id follows 'fn_{footnote_id}' format."""
        fn = make_footnote(footnote_id=88200100)
        talk_fns = make_talk_footnotes([fn])
        records = prepare_footnote_records(talk_fns)
        doc, meta, doc_id, _ = records[0]
        assert doc_id == "fn_88200100"
