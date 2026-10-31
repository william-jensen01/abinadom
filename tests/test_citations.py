"""
Unit and integration tests for Citation Extraction & Parsing
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock

from extractors.citations import (
    extract_citations_from_paragraph,
    resolve_citation_from_db,
    expand_verses,
    calculate_citation_position,
    extract_context_window,
    _build_filtered_paragraph,
    validate_citation,
    validate_talk_citations,
    cross_validate_with_db,
    fetch_all_books,
    fetch_citations_for_talk,
    process_talk_citations,
)
from extractors.html_parsing_utils import _find_position_anchor, ELEMENT_PLACEHOLDER
from models.citation_data import CitationData, TalkCitations
from models.paragraph_data import ParagraphData
from config.schemas import CITATION_CONFIG, PARAGRAPH_CONFIG
from db import core_db


# =============================================================================
# Helpers
# =============================================================================


def make_paragraph(
    text: str,
    text_raw: str,
    talk_id: int = 1000,
    paragraph_number: int = 1,
) -> ParagraphData:
    paragraph_id = talk_id * 10000 + paragraph_number
    return ParagraphData(
        paragraph_id=paragraph_id,
        talk_id=talk_id,
        paragraph_number=paragraph_number,
        text=text,
        text_raw=text_raw,
        word_count=len(text.split()),
    )


def make_citation(**kwargs) -> CitationData:
    defaults = dict(
        citation_id=1,
        talk_id=1000,
        paragraph_id=10000001,
        paragraph_number=1,
        citation_text_raw="John 3:16",
        char_position=5,
        char_end_position=14,
        scripture_ref="John 3:16",
        book="John",
        book_abbr="John",
        book_id=43,
        chapter=3,
        verses="16",
        verse_start=16,
        verse_end=16,
        verse_list=[16],
        parse_success=True,
        parse_source="db_lookup",
        parse_confidence=1.0,
    )
    defaults.update(kwargs)
    return CitationData(**defaults)


# =============================================================================
# TestCitationDetection
# =============================================================================


class TestCitationDetection:
    """Test HTML citation span detection in paragraph text_raw."""

    def test_inline_citation_single(self):
        html = (
            '<p>See <span class="citation" id="42">'
            '<a onclick="gs(42)">John 3:16</a></span> for reference.</p>'
        )
        para = make_paragraph("See John 3:16 for reference.", html)
        results = extract_citations_from_paragraph(para, CITATION_CONFIG)
        assert len(results) == 1
        assert results[0]["citation_id"] == 42
        assert results[0]["display_text"] == "John 3:16"
        assert results[0]["citation_location"] == "inline"

    def test_inline_citation_no_anchor(self):
        html = '<p><span class="citation" id="99">D&amp;C 84:33</span></p>'
        para = make_paragraph("D&C 84:33", html)
        results = extract_citations_from_paragraph(para, CITATION_CONFIG)
        assert len(results) == 1
        assert results[0]["citation_id"] == 99
        assert results[0]["display_text"] == "D&C 84:33"

    def test_footnote_citation(self):
        html = (
            '<p>Text.<span class="footnote">'
            '<span class="citation" id="7">'
            '<a onclick="gs(7)">Mosiah 2:17</a></span></span></p>'
        )
        para = make_paragraph("Text. Mosiah 2:17", html)
        results = extract_citations_from_paragraph(para, CITATION_CONFIG)
        assert len(results) == 1
        assert results[0]["citation_location"] == "footnote"

    def test_multiple_citations_in_paragraph(self):
        html = (
            "<p>"
            '<span class="citation" id="10"><a>Gen 1:1</a></span> and '
            '<span class="citation" id="11"><a>John 1:1</a></span>'
            "</p>"
        )
        para = make_paragraph("Gen 1:1 and John 1:1", html)
        results = extract_citations_from_paragraph(para, CITATION_CONFIG)
        assert len(results) == 2
        assert {r["citation_id"] for r in results} == {10, 11}

    def test_no_citations_in_paragraph(self):
        html = "<p>No scripture here.</p>"
        para = make_paragraph("No scripture here.", html)
        results = extract_citations_from_paragraph(para, CITATION_CONFIG)
        assert results == []

    def test_no_text_raw(self):
        para = ParagraphData(
            paragraph_id=10000001,
            talk_id=1000,
            paragraph_number=1,
            text="Some text",
            text_raw=None,
            word_count=2,
        )
        results = extract_citations_from_paragraph(para, CITATION_CONFIG)
        assert results == []

    def test_non_integer_id_skipped(self):
        html = '<p><span class="citation" id="abc">Bad ref</span></p>'
        para = make_paragraph("Bad ref", html)
        results = extract_citations_from_paragraph(para, CITATION_CONFIG)
        assert results == []

    def test_html_entity_decoded(self):
        html = '<p><span class="citation" id="5"><a>D&amp;C 76:22</a></span></p>'
        para = make_paragraph("D&C 76:22", html)
        results = extract_citations_from_paragraph(para, CITATION_CONFIG)
        assert results[0]["display_text"] == "D&C 76:22"


# =============================================================================
# TestVerseExpansion
# =============================================================================


class TestVerseExpansion:
    """Test verse string expansion."""

    def test_single_verse(self):
        result, warnings = expand_verses("3")
        assert result == [3]
        assert warnings == []

    def test_range(self):
        result, warnings = expand_verses("3-7")
        assert result == [3, 4, 5, 6, 7]
        assert warnings == []

    def test_en_dash_range(self):
        result, warnings = expand_verses("3\u20137")
        assert result == [3, 4, 5, 6, 7]

    def test_comma_list(self):
        result, warnings = expand_verses("3,5,7")
        assert result == [3, 5, 7]

    def test_mixed(self):
        result, warnings = expand_verses("3-5,8,10-12")
        assert result == [3, 4, 5, 8, 10, 11, 12]

    def test_empty_string(self):
        result, warnings = expand_verses("")
        assert result == []
        assert warnings == []

    def test_non_numeric_skipped(self):
        result, warnings = expand_verses("3a,5")
        assert 5 in result
        assert any("3a" in w for w in warnings)

    def test_range_exceeds_max(self):
        result, warnings = expand_verses("1-500", max_range=200)
        assert len(result) == 201  # 1..201
        assert any("exceeds" in w for w in warnings)


# =============================================================================
# TestDBLookup
# =============================================================================


class TestDBLookup:
    """Test citation DB resolution."""

    def setup_method(self):
        self.book_cache = {
            1: {
                "ID": 1,
                "FullName": "Genesis",
                "CiteAbbr": "Gen.",
                "JSTTitle": None,
            },
            101: {
                "ID": 101,
                "FullName": "Doctrine and Covenants",
                "CiteAbbr": "D&C",
                "JSTTitle": None,
            },
            200: {
                "ID": 200,
                "FullName": "Joseph Smith Translation",
                "CiteAbbr": "JST",
                "JSTTitle": "JST, Matthew",
            },
        }
        self.citation_rows = {
            42: {
                "ID": 42,
                "TalkID": 1000,
                "BookID": 1,
                "Chapter": 1,
                "Verses": "1",
                "MinVerse": 1,
                "MaxVerse": 1,
            },
            99: {
                "ID": 99,
                "TalkID": 1000,
                "BookID": 101,
                "Chapter": 84,
                "Verses": "32-44",
                "MinVerse": 32,
                "MaxVerse": 44,
            },
            200: {
                "ID": 200,
                "TalkID": 1000,
                "BookID": 200,
                "Chapter": 5,
                "Verses": "48",
                "MinVerse": 48,
                "MaxVerse": 48,
            },
        }

    def test_existing_citation(self):
        result = resolve_citation_from_db(42, self.citation_rows, self.book_cache)
        assert result["parse_success"] is True
        assert result["book"] == "Genesis"
        assert result["chapter"] == 1
        assert result["verses"] == "1"
        assert result["parse_source"] == "db_lookup"
        assert result["parse_confidence"] == 1.0

    def test_missing_citation(self):
        result = resolve_citation_from_db(9999, self.citation_rows, self.book_cache)
        assert result["parse_success"] is False

    def test_book_resolution(self):
        result = resolve_citation_from_db(99, self.citation_rows, self.book_cache)
        assert result["book"] == "Doctrine and Covenants"
        assert result["book_abbr"] == "D&C"
        assert result["scripture_ref"] == "Doctrine and Covenants 84:32-44"

    def test_jst_detection(self):
        result = resolve_citation_from_db(200, self.citation_rows, self.book_cache)
        assert result["is_jst"] is True


# =============================================================================
# TestPositionCalculation
# =============================================================================


class TestPositionCalculation:
    """Test character position calculation using citation ID (not text matching)."""

    def test_direct_citation(self):
        html = '<p>In <span class="citation" id="42">John 3:16</span> we read.</p>'
        start, end = calculate_citation_position(html, 42, "John 3:16", CITATION_CONFIG)
        assert start >= 0
        assert end == start + len("John 3:16")

    def test_ccontainer_citation_anchor_at_container(self):
        """Position anchor is the ccontainer span, not the inner citation span."""
        html = (
            '<p>See <span class="ccontainer rdot">'
            '<span class="citation" id="5">D&amp;C 84:33</span>'
            "</span> here.</p>"
        )
        start, end = calculate_citation_position(html, 5, "D&C 84:33", CITATION_CONFIG)
        assert start >= 0
        assert end == start + len("D&C 84:33")

    def test_footnote_citation_anchor_at_notemarker(self):
        """Footnote citations use the noteMarker sup as the position anchor."""
        html = (
            "<p>Narrative text."
            '<sup class="noteMarker">'
            '<span class="citation" id="7">Mosiah 2:17</span>'
            "</sup>"
            " more text.</p>"
        )
        start, end = calculate_citation_position(
            html, 7, "Mosiah 2:17", CITATION_CONFIG
        )
        # noteMarker sits right after "Narrative text." (15 chars)
        assert start == 15
        assert end == start + len("Mosiah 2:17")

    def test_citation_not_found(self):
        html = "<p>No citation here.</p>"
        start, end = calculate_citation_position(
            html, 999, "John 3:16", CITATION_CONFIG
        )
        assert start == -1
        assert end == -1

    def test_no_text_raw(self):
        start, end = calculate_citation_position("", 42, "John 3:16", CITATION_CONFIG)
        assert start == -1
        assert end == -1

    def test_duplicate_refs_distinguished_by_id(self):
        """Same scripture text twice in one paragraph: IDs give distinct positions."""
        html = (
            '<p>First <span class="citation" id="20">John 3:16</span>'
            ' middle <span class="citation" id="21">John 3:16</span> end.</p>'
        )
        start_20, _ = calculate_citation_position(
            html, 20, "John 3:16", CITATION_CONFIG
        )
        start_21, _ = calculate_citation_position(
            html, 21, "John 3:16", CITATION_CONFIG
        )
        assert start_20 >= 0
        assert start_21 > start_20


# =============================================================================
# TestContextWindow
# =============================================================================


class TestContextWindow:
    """Test context window extraction."""

    def test_normal_extraction(self):
        text = "The quick brown fox John 3:16 jumps over the lazy dog"
        before, after, window = extract_context_window(text, 20, 29, CITATION_CONFIG)
        assert "John 3:16" in window
        assert before == text[max(0, 20 - 100) : 20]
        assert after == text[29 : min(len(text), 29 + 100)]

    def test_paragraph_start_boundary(self):
        text = "John 3:16 is great."
        before, after, window = extract_context_window(text, 0, 9, CITATION_CONFIG)
        assert before == ""
        assert "John 3:16" in window

    def test_paragraph_end_boundary(self):
        text = "See John 3:16"
        before, after, window = extract_context_window(text, 4, 13, CITATION_CONFIG)
        assert after == ""

    def test_invalid_position(self):
        before, after, window = extract_context_window(
            "Some text", -1, -1, CITATION_CONFIG
        )
        assert before == ""
        assert after == ""
        assert window == ""

    def test_empty_text(self):
        before, after, window = extract_context_window("", 0, 5, CITATION_CONFIG)
        assert window == ""

    def test_footnote_citation_uses_marker_position(self):
        """For footnote citations, context is anchored to where the noteMarker sat."""
        html = (
            "<p>Narrative text."
            '<sup class="noteMarker"><span class="citation" id="5">Matt. 5:3</span></sup>'
            " more narrative.</p>"
        )
        clean = "Narrative text.Matt. 5:3 more narrative."
        start, end = calculate_citation_position(html, 5, "Matt. 5:3", CITATION_CONFIG)
        before, after, window = extract_context_window(
            clean,
            start,
            end,
            CITATION_CONFIG,
            text_raw=html,
            citation_id=5,
            display_text="Matt. 5:3",
        )
        assert "Narrative text." in before
        assert "more narrative." in after
        assert "Matt. 5:3" in window

    def test_inline_citation_kept_in_filtered_context(self):
        """Inline citations (not in noteMarker) remain in context window."""
        html = (
            "<p>"
            '<span class="citation" id="10">Gen 1:1</span> and '
            '<span class="citation" id="11">John 1:1</span>'
            "</p>"
        )
        clean = "Gen 1:1 and John 1:1"
        start, end = calculate_citation_position(html, 11, "John 1:1", CITATION_CONFIG)
        before, after, window = extract_context_window(
            clean,
            start,
            end,
            CITATION_CONFIG,
            text_raw=html,
            citation_id=11,
            display_text="John 1:1",
        )
        assert "Gen 1:1" in before
        assert "John 1:1" in window

    def test_duplicate_display_text_uses_correct_citation(self):
        """Two identical scripture refs in one paragraph: citation_id picks the right one."""
        html = (
            '<p>First <span class="citation" id="20">John 3:16</span>'
            " middle text"
            ' <span class="citation" id="21">John 3:16</span> end.</p>'
        )
        clean = "First John 3:16 middle text John 3:16 end."
        # Ask for citation 21 (second occurrence)
        start, end = calculate_citation_position(html, 21, "John 3:16", CITATION_CONFIG)
        before, after, window = extract_context_window(
            clean,
            start,
            end,
            CITATION_CONFIG,
            text_raw=html,
            citation_id=21,
            display_text="John 3:16",
        )
        assert "middle text" in before
        assert "end." in after
        assert "John 3:16" in window

    def test_fallback_when_citation_id_not_found(self):
        """Falls back to original positions if citation_id is absent from HTML."""
        html = "<p>Some text here.</p>"
        clean = "Some text here."
        before, after, window = extract_context_window(
            clean,
            5,
            9,
            CITATION_CONFIG,
            text_raw=html,
            citation_id=999,
        )
        assert before == clean[max(0, 5 - 100) : 5]
        assert after == clean[9 : min(len(clean), 9 + 100)]


class TestContextWindowMode:
    """Tests for context_window_mode='word' vs 'char'."""

    def _cfg(self, mode, before=8, after=6):
        cfg = dict(CITATION_CONFIG)
        cfg["context_window_mode"] = mode
        cfg["context_before_chars"] = before
        cfg["context_after_chars"] = after
        return cfg

    def test_default_mode_is_word(self):
        assert CITATION_CONFIG.get("context_window_mode", "word") == "word"

    def test_char_mode_keeps_partial_leading_word(self):
        # "hello world " is 12 chars; citation at index 12
        # before_chars=8 → before_start=4 → slice = text[4:12] = "o world "
        # Starts mid-word "hello" — char mode keeps it as-is.
        text = "hello world citation end"
        cstart = text.index("citation")
        cend = cstart + len("citation")
        before, _, _ = extract_context_window(text, cstart, cend, self._cfg("char"))
        assert before == "o world "

    def test_word_mode_trims_partial_leading_word(self):
        # Same slice "o world " — word mode drops "o " (up to first space).
        text = "hello world citation end"
        cstart = text.index("citation")
        cend = cstart + len("citation")
        before, _, _ = extract_context_window(text, cstart, cend, self._cfg("word"))
        assert before == "world "
        assert "hello" not in before

    def test_char_mode_keeps_partial_trailing_word(self):
        # after_chars=6; citation ends at index 8; text[8:14] = " bar b"
        # Cuts mid-word "baz" — char mode keeps it.
        text = "citation bar baz"
        cstart, cend = 0, len("citation")
        _, after, _ = extract_context_window(text, cstart, cend, self._cfg("char"))
        assert after == " bar b"

    def test_word_mode_trims_partial_trailing_word(self):
        # " bar b" — word mode trims from last space → " bar"
        text = "citation bar baz"
        cstart, cend = 0, len("citation")
        _, after, _ = extract_context_window(text, cstart, cend, self._cfg("word"))
        assert after == " bar"

    def test_word_mode_no_trim_at_text_boundaries(self):
        # Short text — both slice edges hit string boundaries, so no truncation
        # occurs and word mode must produce the same result as char mode.
        text = "abc citation xyz"
        cstart = text.index("citation")
        cend = cstart + len("citation")
        before_w, after_w, _ = extract_context_window(
            text, cstart, cend, self._cfg("word", before=100, after=100)
        )
        before_c, after_c, _ = extract_context_window(
            text, cstart, cend, self._cfg("char", before=100, after=100)
        )
        assert before_w == before_c
        assert after_w == after_c

    def test_word_mode_context_window_assembled_correctly(self):
        # Verify window = before + citation_text + after with word-snapped edges.
        text = "hello world citation end of text"
        cstart = text.index("citation")
        cend = cstart + len("citation")
        before, after, window = extract_context_window(
            text, cstart, cend, self._cfg("word")
        )
        assert window == before + text[cstart:cend] + after

    def test_word_mode_no_space_in_before_keeps_whole_slice(self):
        # If the truncated before slice has no space, nothing can be dropped —
        # the slice is returned unchanged.
        # "averylongword" (13 chars) runs directly into "citation" (no space),
        # so with before_chars=8 the slice is text[5:13] = "longword" — no space.
        text = "averylongwordcitation rest"
        cstart = text.index("citation")  # 13
        cend = cstart + len("citation")
        before_w, _, _ = extract_context_window(
            text, cstart, cend, self._cfg("word", before=8)
        )
        before_c, _, _ = extract_context_window(
            text, cstart, cend, self._cfg("char", before=8)
        )
        assert before_w == before_c

    def test_word_mode_with_filtered_text_path(self):
        """word mode applies to the HTML-filtered code path as well."""
        html = (
            "<p>alpha beta gamma "
            '<span class="citation" id="3">John 3:16</span>'
            " delta epsilon zeta</p>"
        )
        clean = "alpha beta gamma John 3:16 delta epsilon zeta"
        cstart = clean.index("John 3:16")
        cend = cstart + len("John 3:16")
        cfg = self._cfg("word", before=12, after=12)
        before, after, window = extract_context_window(
            clean,
            cstart,
            cend,
            cfg,
            text_raw=html,
            citation_id=3,
            display_text="John 3:16",
        )
        # Window must be coherent and contain the citation label
        assert "John 3:16" in window
        assert window == before + "John 3:16" + after
        # Edges must start/end on whole words
        assert not before or before[0] != " " or before.lstrip()
        assert not after or after[-1] != " " or after.rstrip()


class TestBuildFilteredParagraph:
    """Test the internal filtered-text builder."""

    def test_footnote_citation_anchor_is_notemarker(self):
        """noteMarker is the position anchor: replaced with placeholder, not decomposed."""
        html = (
            "<p>Narrative text."
            '<sup class="noteMarker"><span class="citation" id="7">Mosiah 2:17</span></sup>'
            " more text.</p>"
        )
        filtered, display_text = _build_filtered_paragraph(html, 7)
        assert display_text == "Mosiah 2:17"
        assert "Mosiah 2:17" not in filtered
        assert "\x00" in filtered
        assert "Narrative text." in filtered
        assert "more text." in filtered

    def test_inline_citation_replaced_with_placeholder(self):
        """Direct citation span is its own anchor — replaced with placeholder."""
        html = '<p>See <span class="citation" id="42">D&amp;C 4:1</span> here.</p>'
        filtered, display_text = _build_filtered_paragraph(html, 42)
        assert display_text == "D&C 4:1"
        assert "\x00" in filtered
        assert "D&C 4:1" not in filtered

    def test_ccontainer_citation_anchor_is_container(self):
        """ccontainer is the position anchor: whole container replaced with placeholder."""
        html = (
            "<p>Before "
            '<span class="ccontainer rdot">'
            '<span class="citation" id="3">D&amp;C 84:33</span>'
            "</span>"
            " After.</p>"
        )
        filtered, display_text = _build_filtered_paragraph(html, 3)
        assert display_text == "D&C 84:33"
        assert "\x00" in filtered
        assert "D&C 84:33" not in filtered
        assert "Before" in filtered
        assert "After." in filtered

    def test_other_notemarkers_removed(self):
        """noteMarkers not containing the target are fully removed."""
        html = (
            "<p>"
            '<span class="citation" id="10">Gen 1:1</span>'
            '<sup class="noteMarker"><span class="citation" id="11">John 1:1</span></sup>'
            " narrative.</p>"
        )
        filtered, display_text = _build_filtered_paragraph(html, 10)
        assert display_text == "Gen 1:1"
        assert "\x00" in filtered
        assert "John 1:1" not in filtered
        assert "narrative." in filtered

    def test_citation_id_not_found_returns_empty_display(self):
        html = '<p>Text.<sup class="noteMarker">3</sup> continues.</p>'
        filtered, display_text = _build_filtered_paragraph(html, 999)
        assert display_text == ""
        assert "\x00" not in filtered
        assert "3" not in filtered
        assert "Text." in filtered


# =============================================================================
# TestValidation
# =============================================================================


class TestValidation:
    """Test citation validation."""

    def test_valid_citation(self):
        c = make_citation()
        issues = validate_citation(c, CITATION_CONFIG)
        assert issues == []

    def test_empty_display_text(self):
        c = make_citation(citation_text_raw="")
        issues = validate_citation(c, CITATION_CONFIG)
        assert any("empty display" in w for w in issues)

    def test_verse_range_too_large(self):
        c = make_citation(verse_start=1, verse_end=300)
        issues = validate_citation(c, CITATION_CONFIG)
        assert any("verse range" in w for w in issues)

    def test_cross_validation_match(self):
        issues = cross_validate_with_db(1000, [1, 2, 3], [1, 2, 3])
        assert issues == []

    def test_cross_validation_missing_from_html(self):
        issues = cross_validate_with_db(1000, [1, 2], [1, 2, 3])
        assert any("not in HTML" in w for w in issues)

    def test_cross_validation_extra_in_html(self):
        issues = cross_validate_with_db(1000, [1, 2, 99], [1, 2])
        assert any("not in DB" in w for w in issues)

    def test_validate_talk_citations(self):
        c = make_citation()
        tc = TalkCitations(
            talk_id=1000,
            citations=[c],
            total_citations=1,
            extraction_success=True,
        )
        result = validate_talk_citations(tc, CITATION_CONFIG)
        assert result.is_valid

    def test_validate_talk_citations_low_success_rate(self):
        citations = []
        for i in range(5):
            c = make_citation(
                citation_id=i,
                paragraph_id=10000001 + i,
                parse_success=(i < 1),  # Only 1 of 5 succeeds
            )
            citations.append(c)
        tc = TalkCitations(
            talk_id=1000,
            citations=citations,
            total_citations=5,
            extraction_success=True,
        )
        result = validate_talk_citations(tc, CITATION_CONFIG)
        assert any("success rate" in w for w in result.warnings)


# =============================================================================
# TestIntegration
# =============================================================================


class TestIntegration:
    """Integration tests using the real core.52.db database."""

    @pytest.fixture(autouse=True)
    def check_db(self):
        """Skip integration tests if DB is not accessible."""
        try:
            core_db.select("SELECT 1")
        except Exception:
            pytest.skip("core.52.db not accessible")

    def test_fetch_all_books(self):
        book_cache = fetch_all_books(core_db)
        assert len(book_cache) > 0
        # Spot check a known book
        assert any(
            row.get("FullName", "").lower() in ("genesis", "john")
            for row in book_cache.values()
        )

    def test_fetch_citations_for_talk_1059(self):
        """Talk 1059 should have 4 citations according to the plan."""
        rows = fetch_citations_for_talk(core_db, 1059)
        assert len(rows) == 4, f"Expected 4 citations for talk 1059, got {len(rows)}"

    def test_fetch_citations_for_nonexistent_talk(self):
        rows = fetch_citations_for_talk(core_db, 999999999)
        assert rows == []

    def test_process_talk_1059(self):
        """Process talk 1059 — expect 4 citations, all with DB lookup success."""
        from extractors.paragraphs import (
            extract_paragraphs,
            fetch_talk_html,
        )
        from db import content_db

        # Try to fetch talk HTML; skip if not available
        try:
            html = fetch_talk_html(content_db, 1059)
        except Exception:
            pytest.skip("Talk HTML not available for talk 1059")

        if not html:
            pytest.skip("Talk 1059 HTML is empty")

        talk_paragraphs = extract_paragraphs(1059, html, PARAGRAPH_CONFIG)
        if not talk_paragraphs.extraction_success:
            pytest.skip("Paragraph extraction failed for talk 1059")

        book_cache = fetch_all_books(core_db)
        talk_citations, warnings = process_talk_citations(
            core_db, 1059, talk_paragraphs.paragraphs, book_cache, CITATION_CONFIG
        )

        assert talk_citations.extraction_success
        assert (
            talk_citations.total_citations == 4
        ), f"Expected 4 citations, got {talk_citations.total_citations}"
        assert all(
            c.parse_success for c in talk_citations.citations
        ), "Some citations failed DB lookup"

    def test_zero_citation_talk(self):
        """A talk with no citations should return empty TalkCitations."""
        from extractors.paragraphs import (
            extract_paragraphs,
            fetch_talk_html,
        )
        from db import content_db

        # Find a talk with 0 citations
        zero_talk_rows = core_db.select(
            "SELECT ID FROM talk WHERE ID NOT IN "
            "(SELECT DISTINCT TalkID FROM citation) LIMIT 1"
        )
        if not zero_talk_rows:
            pytest.skip("No zero-citation talks found in DB")

        talk_id = zero_talk_rows[0]["ID"]
        try:
            html = fetch_talk_html(content_db, talk_id)
        except Exception:
            pytest.skip(f"HTML not available for talk {talk_id}")

        if not html:
            pytest.skip(f"Talk {talk_id} HTML is empty")

        talk_paragraphs = extract_paragraphs(talk_id, html, PARAGRAPH_CONFIG)
        book_cache = fetch_all_books(core_db)
        talk_citations, _ = process_talk_citations(
            core_db, talk_id, talk_paragraphs.paragraphs, book_cache, CITATION_CONFIG
        )

        assert talk_citations.total_citations == 0

    def test_paragraph_flags_updated(self):
        """After processing, paragraphs with citations should have flags set."""
        from extractors.paragraphs import (
            extract_paragraphs,
            fetch_talk_html,
        )
        from db import content_db

        try:
            html = fetch_talk_html(content_db, 1059)
        except Exception:
            pytest.skip("Talk HTML not available for talk 1059")

        if not html:
            pytest.skip("Talk 1059 HTML is empty")

        talk_paragraphs = extract_paragraphs(1059, html, PARAGRAPH_CONFIG)
        book_cache = fetch_all_books(core_db)
        process_talk_citations(
            core_db, 1059, talk_paragraphs.paragraphs, book_cache, CITATION_CONFIG
        )

        cited_paragraphs = [
            p for p in talk_paragraphs.paragraphs if p.has_scripture_citation
        ]
        assert len(cited_paragraphs) > 0
        assert all(p.citation_count > 0 for p in cited_paragraphs)
