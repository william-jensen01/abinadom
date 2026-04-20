"""
Unit tests for loaders/shared_transforms.py.

Tests flatten_metadata, rich_metadata, and prepare_talk_bundle.
Imports from loaders.shared_transforms (public API), not from extractors.phase6_chromadb_loader.
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
    flatten_metadata,
    rich_metadata,
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
# Tests: flatten_metadata
# =============================================================================


class TestFlattenMetadata:
    def test_removes_none_values(self):
        """None values are dropped from the output dict."""
        meta = {"a": 1, "b": None}
        result = flatten_metadata(meta)
        assert "b" not in result
        assert result["a"] == 1

    def test_removes_empty_lists(self):
        """Empty list values are dropped from the output dict."""
        meta = {"a": []}
        result = flatten_metadata(meta)
        assert "a" not in result

    def test_joins_int_list_with_comma(self):
        """A list of ints is joined with commas."""
        meta = {"b": [1, 2]}
        result = flatten_metadata(meta)
        assert result["b"] == "1,2"

    def test_joins_str_list_with_pipe(self):
        """A list of strings is joined with pipes."""
        meta = {"c": ["x", "y"]}
        result = flatten_metadata(meta)
        assert result["c"] == "x|y"

    def test_spec_acceptance_criterion(self):
        """SPEC Req 2 acceptance criterion: mixed dict flattened correctly."""
        meta = {"a": None, "b": [1, 2], "c": ["x", "y"]}
        result = flatten_metadata(meta)
        assert result == {"b": "1,2", "c": "x|y"}

    def test_preserves_scalar_values(self):
        """Scalar int, float, bool, str values are passed through unchanged."""
        meta = {"talk_id": 8820, "score": 0.95, "is_valid": True, "title": "Test"}
        result = flatten_metadata(meta)
        assert result["talk_id"] == 8820
        assert result["score"] == 0.95
        assert result["is_valid"] is True
        assert result["title"] == "Test"

    def test_empty_dict_returns_empty_dict(self):
        """Empty input produces empty output."""
        result = flatten_metadata({})
        assert result == {}


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
