"""
Unit tests for Phase 5: Validation Gate.
"""

import sys
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from models.talk_metadata import TalkMetadata
from models.paragraph_data import ParagraphData, TalkParagraphs
from models.citation_data import CitationData, TalkCitations
from models.footnote_data import FootnoteData, TalkFootnotes
from models.validation_report import ValidationReport
from extractors.phase5_validation import (
    validate_talk,
    _check_cross_collection,
    _check_paragraphs,
    _check_chromadb_readiness,
    _check_footnotes,
)


# =============================================================================
# Factories
# =============================================================================

TALK_ID = 10


def make_metadata(talk_id: int = TALK_ID) -> TalkMetadata:
    return TalkMetadata(
        talk_id=talk_id,
        speaker_id=1,
        conference_id=1,
        title="Test Talk",
        speaker_name="Test Speaker",
        conference_year=2020,
        conference_month="April",
        conference_description="April 2020 General Conference",
        talk_date="2020-04-05",
    )


def make_paragraph(
    number: int,
    talk_id: int = TALK_ID,
    text: str = "Some paragraph text.",
    citation_count: int = 0,
    footnote_count: int = 0,
    has_scripture_citation: bool = False,
    has_footnote: bool = False,
) -> ParagraphData:
    return ParagraphData(
        paragraph_id=talk_id * 10000 + number,
        talk_id=talk_id,
        paragraph_number=number,
        text=text,
        text_raw=None,
        word_count=3,
        citation_count=citation_count,
        footnote_count=footnote_count,
        has_scripture_citation=has_scripture_citation,
        has_footnote=has_footnote,
    )


def make_paragraphs(paras: List[ParagraphData], talk_id: int = TALK_ID) -> TalkParagraphs:
    return TalkParagraphs(
        talk_id=talk_id,
        paragraphs=paras,
        total_paragraphs=len(paras),
        total_words=sum(p.word_count for p in paras),
        extraction_success=True,
    )


def make_citation(
    citation_id: int,
    paragraph_number: int,
    talk_id: int = TALK_ID,
    paragraph_id: int = None,
) -> CitationData:
    if paragraph_id is None:
        paragraph_id = talk_id * 10000 + paragraph_number
    return CitationData(
        citation_id=citation_id,
        talk_id=talk_id,
        paragraph_id=paragraph_id,
        paragraph_number=paragraph_number,
        citation_text_raw="John 3:16",
        char_position=0,
        char_end_position=8,
        scripture_ref="John 3:16",
        book="John",
        book_abbr="John",
        book_id=1,
        chapter=3,
        verses="16",
        verse_start=16,
        verse_end=16,
        verse_list=[16],
    )


def make_citations(cites: List[CitationData], talk_id: int = TALK_ID) -> TalkCitations:
    return TalkCitations(
        talk_id=talk_id,
        citations=cites,
        total_citations=len(cites),
        extraction_success=True,
    )


def make_footnote(
    fn_num: int,
    paragraph_number: int,
    talk_id: int = TALK_ID,
    footnote_id: int = None,
    paragraph_id: int = None,
    text: str = "[Some note.]",
) -> FootnoteData:
    if footnote_id is None:
        footnote_id = talk_id * 100000 + paragraph_number * 100 + fn_num
    if paragraph_id is None:
        paragraph_id = talk_id * 10000 + paragraph_number
    return FootnoteData(
        footnote_id=footnote_id,
        talk_id=talk_id,
        paragraph_id=paragraph_id,
        paragraph_number=paragraph_number,
        footnote_number=fn_num,
        footnote_text_raw=text,
        char_position=5,
    )


def make_footnotes(fns: List[FootnoteData], talk_id: int = TALK_ID) -> TalkFootnotes:
    return TalkFootnotes(
        talk_id=talk_id,
        footnotes=fns,
        total_footnotes=len(fns),
        extraction_success=True,
    )


def happy_path_bundle(n_paragraphs: int = 5):
    """Return a consistent, valid data bundle."""
    metadata = make_metadata()
    paras = [make_paragraph(i) for i in range(1, n_paragraphs + 1)]
    tp = make_paragraphs(paras)
    tc = make_citations([])
    tf = make_footnotes([])
    return metadata, tp, tc, tf


# =============================================================================
# TestValidationReport
# =============================================================================


class TestValidationReport:
    def test_repr(self):
        report = ValidationReport(
            talk_id=1, is_valid=True, errors=[], warnings=[], stats={}
        )
        assert "talk_id=1" in repr(report)
        assert "valid=True" in repr(report)


# =============================================================================
# TestHappyPath
# =============================================================================


class TestHappyPath:
    def test_valid_bundle_returns_no_errors(self):
        metadata, tp, tc, tf = happy_path_bundle()
        report = validate_talk(metadata, tp, tc, tf)
        assert report.is_valid
        assert report.errors == []

    def test_stats_populated(self):
        metadata, tp, tc, tf = happy_path_bundle(n_paragraphs=5)
        report = validate_talk(metadata, tp, tc, tf)
        assert report.stats["paragraph_count"] == 5
        assert report.stats["citation_count"] == 0
        assert report.stats["footnote_count"] == 0

    def test_no_db_produces_warning(self):
        metadata, tp, tc, tf = happy_path_bundle()
        report = validate_talk(metadata, tp, tc, tf, db=None)
        assert any("DB checks skipped" in w for w in report.warnings)


# =============================================================================
# TestCrossCollectionIntegrity
# =============================================================================


class TestCrossCollectionIntegrity:
    """Check 1: foreign-key relationships across collections."""

    def test_citation_bad_paragraph_id_is_error(self):
        metadata = make_metadata()
        paras = [make_paragraph(1), make_paragraph(2), make_paragraph(3)]
        tp = make_paragraphs(paras)
        bad_cite = make_citation(999, paragraph_number=1, paragraph_id=99999)
        tc = make_citations([bad_cite])
        tf = make_footnotes([])
        report = validate_talk(metadata, tp, tc, tf)
        assert not report.is_valid
        assert any("paragraph_id" in e and "99999" in e for e in report.errors)

    def test_citation_wrong_talk_id_is_error(self):
        metadata = make_metadata(talk_id=10)
        paras = [make_paragraph(1), make_paragraph(2), make_paragraph(3)]
        tp = make_paragraphs(paras)
        bad_cite = make_citation(1, paragraph_number=1, talk_id=99)
        # fix paragraph_id so it doesn't trigger that error
        bad_cite.paragraph_id = 10 * 10000 + 1
        tc = make_citations([bad_cite])
        tf = make_footnotes([])
        report = validate_talk(metadata, tp, tc, tf)
        assert not report.is_valid
        assert any("talk_id mismatch" in e for e in report.errors)

    def test_footnote_bad_paragraph_id_is_error(self):
        metadata = make_metadata()
        paras = [make_paragraph(1), make_paragraph(2), make_paragraph(3)]
        tp = make_paragraphs(paras)
        tc = make_citations([])
        bad_fn = make_footnote(1, paragraph_number=1, paragraph_id=88888)
        tf = make_footnotes([bad_fn])
        report = validate_talk(metadata, tp, tc, tf)
        assert not report.is_valid
        assert any("88888" in e for e in report.errors)

    def test_footnote_wrong_talk_id_is_error(self):
        metadata = make_metadata(talk_id=10)
        paras = [make_paragraph(1), make_paragraph(2), make_paragraph(3)]
        tp = make_paragraphs(paras)
        tc = make_citations([])
        bad_fn = make_footnote(1, paragraph_number=1, talk_id=77)
        bad_fn.paragraph_id = 10 * 10000 + 1
        tf = make_footnotes([bad_fn])
        report = validate_talk(metadata, tp, tc, tf)
        assert not report.is_valid
        assert any("talk_id mismatch" in e for e in report.errors)

    def test_citation_count_mismatch_is_warning(self):
        metadata = make_metadata()
        # paragraph says citation_count=2 but no citations exist
        para = make_paragraph(1, citation_count=2, has_scripture_citation=True)
        tp = make_paragraphs([para, make_paragraph(2), make_paragraph(3)])
        tc = make_citations([])
        tf = make_footnotes([])
        report = validate_talk(metadata, tp, tc, tf)
        assert report.is_valid  # warning, not error
        assert any("citation_count" in w for w in report.warnings)

    def test_footnote_count_mismatch_is_warning(self):
        metadata = make_metadata()
        para = make_paragraph(1, footnote_count=1, has_footnote=True)
        tp = make_paragraphs([para, make_paragraph(2), make_paragraph(3)])
        tc = make_citations([])
        tf = make_footnotes([])
        report = validate_talk(metadata, tp, tc, tf)
        assert report.is_valid
        assert any("footnote_count" in w for w in report.warnings)

    def test_has_scripture_citation_flag_mismatch_is_warning(self):
        metadata = make_metadata()
        # has_scripture_citation=True but no citations
        para = make_paragraph(1, has_scripture_citation=True)
        tp = make_paragraphs([para, make_paragraph(2), make_paragraph(3)])
        tc = make_citations([])
        tf = make_footnotes([])
        report = validate_talk(metadata, tp, tc, tf)
        assert report.is_valid
        assert any("has_scripture_citation" in w for w in report.warnings)

    def test_has_footnote_flag_mismatch_is_warning(self):
        metadata = make_metadata()
        para = make_paragraph(1, has_footnote=True)
        tp = make_paragraphs([para, make_paragraph(2), make_paragraph(3)])
        tc = make_citations([])
        tf = make_footnotes([])
        report = validate_talk(metadata, tp, tc, tf)
        assert report.is_valid
        assert any("has_footnote" in w for w in report.warnings)

    def test_consistent_flags_no_warning(self):
        metadata = make_metadata()
        cite = make_citation(1, paragraph_number=1)
        fn = make_footnote(1, paragraph_number=2)
        para1 = make_paragraph(1, citation_count=1, has_scripture_citation=True)
        para2 = make_paragraph(2, footnote_count=1, has_footnote=True)
        para3 = make_paragraph(3)
        tp = make_paragraphs([para1, para2, para3])
        tc = make_citations([cite])
        tf = make_footnotes([fn])
        report = validate_talk(metadata, tp, tc, tf)
        flag_warnings = [
            w for w in report.warnings
            if "has_scripture_citation" in w or "has_footnote" in w
            or "citation_count" in w or "footnote_count" in w
        ]
        assert flag_warnings == []


# =============================================================================
# TestParagraphSanity
# =============================================================================


class TestParagraphSanity:
    """Check 3: sequential numbering, reasonable count, paragraph_id formula."""

    def test_sequential_numbering_ok(self):
        paras = [make_paragraph(i) for i in range(1, 6)]
        tp = make_paragraphs(paras)
        errors: List[str] = []
        warnings: List[str] = []
        _check_paragraphs(tp, errors, warnings)
        assert errors == []

    def test_gap_in_numbering_is_error(self):
        paras = [make_paragraph(1), make_paragraph(3)]  # gap: 2 missing
        tp = make_paragraphs(paras)
        errors: List[str] = []
        warnings: List[str] = []
        _check_paragraphs(tp, errors, warnings)
        assert any("Non-sequential" in e for e in errors)

    def test_duplicate_numbering_is_error(self):
        para_a = make_paragraph(1)
        para_b = make_paragraph(1)  # same number
        para_b.paragraph_id = TALK_ID * 10000 + 99  # avoid ParagraphData constraint
        tp = TalkParagraphs(
            talk_id=TALK_ID,
            paragraphs=[para_a, para_b],
            total_paragraphs=2,
            total_words=para_a.word_count + para_b.word_count,
            extraction_success=True,
        )
        errors: List[str] = []
        warnings: List[str] = []
        _check_paragraphs(tp, errors, warnings)
        assert any("Duplicate paragraph_number" in e for e in errors)

    def test_low_count_is_warning(self):
        paras = [make_paragraph(1), make_paragraph(2)]  # < 3
        tp = make_paragraphs(paras)
        errors: List[str] = []
        warnings: List[str] = []
        _check_paragraphs(tp, errors, warnings)
        assert any("Low paragraph count" in w for w in warnings)

    def test_high_count_is_warning(self):
        paras = [make_paragraph(i) for i in range(1, 152)]  # 151 > 150
        tp = make_paragraphs(paras)
        errors: List[str] = []
        warnings: List[str] = []
        _check_paragraphs(tp, errors, warnings)
        assert any("High paragraph count" in w for w in warnings)

    def test_paragraph_id_formula_violation_is_error(self):
        para = make_paragraph(1)
        para.paragraph_id = 99999  # wrong
        tp = TalkParagraphs(
            talk_id=TALK_ID,
            paragraphs=[para],
            total_paragraphs=1,
            total_words=para.word_count,
            extraction_success=True,
        )
        errors: List[str] = []
        warnings: List[str] = []
        _check_paragraphs(tp, errors, warnings)
        assert any("paragraph_id" in e for e in errors)


# =============================================================================
# TestChromaDBReadiness
# =============================================================================


class TestChromaDBReadiness:
    """Check 4: non-empty document text and unique IDs."""

    def test_empty_paragraph_text_is_error(self):
        metadata = make_metadata()
        # Create a paragraph that would produce empty text via to_chromadb_format.
        # ParagraphData enforces non-empty text, so we patch the method.
        para = make_paragraph(1)
        original_format = para.to_chromadb_format
        para.to_chromadb_format = lambda: ("", {}, "para_10001")
        tp = make_paragraphs([para, make_paragraph(2), make_paragraph(3)])
        tc = make_citations([])
        tf = make_footnotes([])
        errors: List[str] = []
        _check_chromadb_readiness(metadata, tp, tc, tf, errors)
        assert any("ParagraphData" in e and "empty" in e for e in errors)

    def test_duplicate_paragraph_ids_is_error(self):
        metadata = make_metadata()
        para1 = make_paragraph(1)
        para2 = make_paragraph(2)
        # Make them share the same ChromaDB ID
        para1.to_chromadb_format = lambda: ("text", {}, "para_SAME")
        para2.to_chromadb_format = lambda: ("text", {}, "para_SAME")
        tp = make_paragraphs([para1, para2, make_paragraph(3)])
        tc = make_citations([])
        tf = make_footnotes([])
        errors: List[str] = []
        _check_chromadb_readiness(metadata, tp, tc, tf, errors)
        assert any("Duplicate ID" in e and "paragraphs" in e for e in errors)

    def test_valid_bundle_no_errors(self):
        metadata, tp, tc, tf = happy_path_bundle()
        errors: List[str] = []
        _check_chromadb_readiness(metadata, tp, tc, tf, errors)
        assert errors == []


# =============================================================================
# TestFootnoteSanity
# =============================================================================


class TestFootnoteSanity:
    """Check 5: footnote_number, text, footnote_id formula."""

    def test_sequential_footnote_numbers_no_warning(self):
        fns = [make_footnote(i, paragraph_number=1) for i in range(1, 4)]
        tf = make_footnotes(fns)
        errors: List[str] = []
        warnings: List[str] = []
        _check_footnotes(tf, errors, warnings)
        assert errors == []
        assert not any("gap" in w.lower() for w in warnings)

    def test_non_sequential_footnote_numbers_warning(self):
        fn1 = make_footnote(1, paragraph_number=1)
        fn3 = make_footnote(3, paragraph_number=1)  # gap: 2 missing
        tf = make_footnotes([fn1, fn3])
        errors: List[str] = []
        warnings: List[str] = []
        _check_footnotes(tf, errors, warnings)
        assert any("gap" in w.lower() for w in warnings)

    def test_wrong_footnote_id_formula_is_error(self):
        fn = make_footnote(1, paragraph_number=2, footnote_id=9999)  # wrong
        tf = make_footnotes([fn])
        errors: List[str] = []
        warnings: List[str] = []
        _check_footnotes(tf, errors, warnings)
        assert any("footnote_id" in e for e in errors)

    def test_correct_footnote_id_formula_no_error(self):
        fn = make_footnote(1, paragraph_number=2)  # factory uses correct formula
        tf = make_footnotes([fn])
        errors: List[str] = []
        warnings: List[str] = []
        _check_footnotes(tf, errors, warnings)
        assert not any("footnote_id" in e for e in errors)

    def test_empty_text_is_error(self):
        fn = make_footnote(1, paragraph_number=1)
        fn.footnote_text_raw = ""  # bypass __post_init__ guard for belt-and-suspenders test
        tf = make_footnotes([fn])
        errors: List[str] = []
        warnings: List[str] = []
        _check_footnotes(tf, errors, warnings)
        assert any("empty footnote_text_raw" in e for e in errors)


# =============================================================================
# TestCitationDBValidation (mocked)
# =============================================================================


class TestCitationDBValidation:
    """Check 2: DB lookups using a mock database."""

    def _mock_db(self, has_talk: bool = True, has_citation: bool = True):
        db = MagicMock()

        def select_one(query, params):
            if "talk" in query.lower():
                return {"ID": params[0]} if has_talk else None
            if "citation" in query.lower():
                return {"ID": params[0]} if has_citation else None
            return None

        db.select_one.side_effect = select_one
        return db

    def test_valid_db_lookups_no_errors(self):
        metadata = make_metadata()
        cite = make_citation(100, paragraph_number=2)
        paras = [make_paragraph(i) for i in range(1, 4)]
        tp = make_paragraphs(paras)
        tc = make_citations([cite])
        tf = make_footnotes([])
        db = self._mock_db()
        report = validate_talk(metadata, tp, tc, tf, db=db)
        assert report.is_valid
        assert report.stats["db_checks_passed"] > 0

    def test_missing_talk_id_in_db_is_error(self):
        metadata = make_metadata()
        paras = [make_paragraph(i) for i in range(1, 4)]
        tp = make_paragraphs(paras)
        tc = make_citations([])
        tf = make_footnotes([])
        db = self._mock_db(has_talk=False)
        report = validate_talk(metadata, tp, tc, tf, db=db)
        assert not report.is_valid
        assert any("talk table" in e for e in report.errors)

    def test_missing_citation_id_in_db_is_error(self):
        metadata = make_metadata()
        cite = make_citation(999, paragraph_number=1)
        para = make_paragraph(1, citation_count=1, has_scripture_citation=True)
        tp = make_paragraphs([para, make_paragraph(2), make_paragraph(3)])
        tc = make_citations([cite])
        tf = make_footnotes([])
        db = self._mock_db(has_citation=False)
        report = validate_talk(metadata, tp, tc, tf, db=db)
        assert not report.is_valid
        assert any("citation table" in e for e in report.errors)

    def test_wrong_paragraph_id_formula_in_citation_is_error(self):
        metadata = make_metadata()
        cite = make_citation(1, paragraph_number=1)
        cite.paragraph_id = 99999  # breaks formula
        para = make_paragraph(1)
        tp = make_paragraphs([para, make_paragraph(2), make_paragraph(3)])
        tc = make_citations([cite])
        tf = make_footnotes([])
        db = self._mock_db()
        report = validate_talk(metadata, tp, tc, tf, db=db)
        assert not report.is_valid
        assert any("paragraph_id" in e for e in report.errors)
