"""
Unit and integration tests for Footnote Extraction.
"""

import pytest
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from models.footnote_data import FootnoteData, TalkFootnotes
from models.paragraph_data import ParagraphData
from extractors.footnotes import (
    extract_footnotes_from_paragraph,
    calculate_footnote_position,
    extract_footnote_context_window,
    validate_footnote,
    validate_talk_footnotes,
    process_talk_footnotes,
    _build_filtered_paragraph_for_footnote,
)
from extractors.html_parsing_utils import (
    _ccontainer_punctuation,
    render_span_text as _render_footnote_span,
)
from config.schemas import FOOTNOTE_CONFIG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_paragraph(
    text_raw: str, paragraph_number: int = 1, talk_id: int = 1
) -> ParagraphData:
    """Create a minimal ParagraphData for testing."""
    return ParagraphData(
        paragraph_id=talk_id * 10000 + paragraph_number,
        talk_id=talk_id,
        paragraph_number=paragraph_number,
        text=_strip_html(text_raw),
        text_raw=text_raw,
        word_count=5,
    )


def _strip_html(html: str) -> str:
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser").get_text(strip=True)


CONFIG = FOOTNOTE_CONFIG.copy()


# ===========================================================================
# TestFootnoteDetection
# ===========================================================================


class TestFootnoteDetection:
    """Tests for extract_footnotes_from_paragraph."""

    def test_single_footnote_span(self):
        html = (
            '<p>Some text<sup class="noteMarker">'
            '<a href="#footnote1">1</a>'
            '<span class="footnote">[John Ruskin, "Little Brass Nails."]</span>'
            "</sup> more text.</p>"
        )
        para = make_paragraph(html)
        footnotes, warnings = extract_footnotes_from_paragraph(para, CONFIG)
        assert len(footnotes) == 1
        assert footnotes[0]["footnote_number"] == 1
        assert (
            footnotes[0]["footnote_text_raw"] == '[John Ruskin, "Little Brass Nails."]'
        )
        assert footnotes[0]["element_index"] == 0
        assert warnings == []

    def test_citation_span_fallback(self):
        """noteMarker containing only a citation span (scripture-only footnote)."""
        html = (
            '<p>See this<sup class="noteMarker">'
            '<span class="citation" id="7">Mosiah 2:17</span>'
            "</sup>.</p>"
        )
        para = make_paragraph(html)
        footnotes, warnings = extract_footnotes_from_paragraph(para, CONFIG)
        assert len(footnotes) == 1
        assert footnotes[0]["footnote_text_raw"] == "Mosiah 2:17"

    def test_multiple_footnotes_in_paragraph(self):
        html = (
            '<p>DeMille said<sup class="noteMarker">'
            '<a href="#footnote4">4</a>'
            '<span class="footnote">[Cecil B. DeMille, BYU Address, 1957.]</span>'
            '</sup> and Aurelius said<sup class="noteMarker">'
            '<a href="#footnote5">5</a>'
            '<span class="footnote">[Marcus Aurelius, Meditations.]</span>'
            "</sup></p>"
        )
        para = make_paragraph(html)
        footnotes, warnings = extract_footnotes_from_paragraph(para, CONFIG)
        assert len(footnotes) == 2
        assert footnotes[0]["footnote_number"] == 4
        assert footnotes[1]["footnote_number"] == 5

    def test_no_footnotes_returns_empty(self):
        html = "<p>No footnotes here.</p>"
        para = make_paragraph(html)
        footnotes, warnings = extract_footnotes_from_paragraph(para, CONFIG)
        assert footnotes == []
        assert warnings == []

    def test_asterisk_marker_sequential_number_and_warning(self):
        html = (
            '<p>Old talk<sup class="noteMarker">'
            '<a href="#footnoteSTAR">*</a>'
            '<span class="footnote">[Fast day was regularly observed.]</span>'
            "</sup></p>"
        )
        para = make_paragraph(html)
        footnotes, warnings = extract_footnotes_from_paragraph(para, CONFIG)
        assert len(footnotes) == 1
        assert footnotes[0]["footnote_number"] == 1  # element_index 0 → 1
        assert any("Asterisk" in w for w in warnings)

    def test_footnote_text_with_emphasis_span(self):
        """Emphasis spans inside footnote text are included via get_text()."""
        html = (
            '<p>Quote<sup class="noteMarker">'
            '<a href="#footnote3">3</a>'
            '<span class="footnote">[Juvenal, <span class="emphasis">Satires, </span>xiii.]</span>'
            "</sup></p>"
        )
        para = make_paragraph(html)
        footnotes, warnings = extract_footnotes_from_paragraph(para, CONFIG)
        assert len(footnotes) == 1
        assert "Juvenal" in footnotes[0]["footnote_text_raw"]
        assert "Satires" in footnotes[0]["footnote_text_raw"]

    def test_no_text_raw_returns_empty(self):
        para = ParagraphData(
            paragraph_id=10001,
            talk_id=1,
            paragraph_number=1,
            text="Some text",
            text_raw=None,
            word_count=2,
        )
        footnotes, warnings = extract_footnotes_from_paragraph(para, CONFIG)
        assert footnotes == []

    def test_threshold_warning(self):
        """More footnotes than max_footnotes_per_paragraph_warning triggers a warning."""
        markers = "".join(
            f'<sup class="noteMarker"><a href="#footnote{i}">{i}</a>'
            f'<span class="footnote">[Note {i}]</span></sup>'
            for i in range(1, 22)
        )
        html = f"<p>Text{markers}</p>"
        para = make_paragraph(html)
        low_config = {**CONFIG, "max_footnotes_per_paragraph_warning": 5}
        footnotes, warnings = extract_footnotes_from_paragraph(para, low_config)
        assert len(footnotes) == 21
        assert any("threshold" in w for w in warnings)


# ===========================================================================
# TestFootnotePosition
# ===========================================================================


class TestFootnotePosition:
    """Tests for calculate_footnote_position."""

    def test_single_marker_position(self):
        html = (
            'Hello world<sup class="noteMarker">'
            '<a href="#fn1">1</a>'
            '<span class="footnote">[Note.]</span>'
            "</sup> end"
        )
        pos = calculate_footnote_position(html, 0, CONFIG)
        assert pos == len("Hello world")

    def test_first_of_multiple_markers_by_index(self):
        html = (
            'First<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[A]</span></sup>'
            ' second<sup class="noteMarker"><a href="#fn2">2</a>'
            '<span class="footnote">[B]</span></sup>'
        )
        pos0 = calculate_footnote_position(html, 0, CONFIG)
        pos1 = calculate_footnote_position(html, 1, CONFIG)
        assert pos0 == len("First")
        # BeautifulSoup get_text(strip=True) strips each text node individually,
        # so " second" → "second", giving "Firstsecond" (11 chars not 12).
        assert pos1 == len("Firstsecond")
        assert pos1 > pos0

    def test_index_out_of_range_returns_minus_one(self):
        html = (
            '<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[A]</span></sup>'
        )
        pos = calculate_footnote_position(html, 99, CONFIG)
        assert pos == -1

    def test_filtered_paragraph_removes_other_markers(self):
        """Filtered paragraph for index 0 should not contain marker 1's text."""
        html = (
            'A<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[Note1]</span></sup>'
            'B<sup class="noteMarker"><a href="#fn2">2</a>'
            '<span class="footnote">[Note2]</span></sup>C'
        )
        filtered, _ = _build_filtered_paragraph_for_footnote(html, 0)
        assert "Note2" not in filtered
        assert "\x00" in filtered


# ===========================================================================
# TestContextWindow
# ===========================================================================


class TestContextWindow:
    """Tests for extract_footnote_context_window."""

    def test_basic_before_after(self):
        html = (
            "Hello world"
            '<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[Note.]</span></sup>'
            " goodbye"
        )
        before, after, window = extract_footnote_context_window(
            html, 0, "[Note.]", CONFIG
        )
        assert "Hello world" in before
        assert "goodbye" in after
        assert "[Note.]" in window

    def test_word_boundary_snapping(self):
        """Word mode should not cut mid-word."""
        long_before = "word " * 30  # 150 chars of "word word word..."
        html = (
            long_before
            + '<sup class="noteMarker"><a href="#fn1">1</a>'
            + '<span class="footnote">[Note.]</span></sup>'
            + " "
            + "end " * 30
        )
        word_config = {
            **CONFIG,
            "context_window_mode": "word",
            "context_before_chars": 50,
        }
        before, after, window = extract_footnote_context_window(
            html, 0, "[Note.]", word_config
        )
        # Word mode: before should not start mid-word
        if before:
            assert before.startswith(" ") or before[0].isalpha()

    def test_marker_near_paragraph_start(self):
        html = (
            '<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[Note.]</span></sup>'
            " Some text follows."
        )
        before, after, window = extract_footnote_context_window(
            html, 0, "[Note.]", CONFIG
        )
        assert before == ""
        assert "Some text follows" in after

    def test_marker_near_paragraph_end(self):
        html = (
            "Some text precedes"
            '<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[Note.]</span></sup>'
        )
        before, after, window = extract_footnote_context_window(
            html, 0, "[Note.]", CONFIG
        )
        assert "Some text precedes" in before
        assert after == ""

    def test_context_window_assembles_correctly(self):
        html = (
            "Before text"
            '<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[The Note]</span></sup>'
            "After text"
        )
        before, after, window = extract_footnote_context_window(
            html, 0, "[The Note]", CONFIG
        )
        assert window == before + "[The Note]" + after


# ===========================================================================
# TestFootnoteData
# ===========================================================================


class TestFootnoteData:
    """Tests for the FootnoteData dataclass."""

    def _valid(self, **overrides):
        defaults = dict(
            footnote_id=100101,
            talk_id=1,
            paragraph_id=10001,
            paragraph_number=1,
            footnote_number=1,
            footnote_text_raw="[Some note text.]",
            char_position=10,
        )
        defaults.update(overrides)
        return FootnoteData(**defaults)

    def test_valid_creation(self):
        fn = self._valid()
        assert fn.footnote_id == 100101
        assert fn.footnote_text_raw == "[Some note text.]"

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="footnote_text_raw"):
            self._valid(footnote_text_raw="")

    def test_invalid_paragraph_number_raises(self):
        with pytest.raises(ValueError, match="paragraph_number"):
            self._valid(paragraph_number=0)

    def test_invalid_footnote_id_raises(self):
        with pytest.raises(ValueError, match="footnote_id"):
            self._valid(footnote_id=0)

    def test_invalid_footnote_number_raises(self):
        with pytest.raises(ValueError, match="footnote_number"):
            self._valid(footnote_number=0)

    def test_to_dict_round_trip(self):
        fn = self._valid(
            context_before="before",
            context_after="after",
            context_window="before[note]after",
        )
        d = fn.to_dict()
        assert d["footnote_id"] == fn.footnote_id
        assert d["footnote_text_raw"] == fn.footnote_text_raw
        assert d["context_before"] == "before"

    def test_to_db_record_uses_context_window(self):
        fn = self._valid(context_window="ctx window text")
        document, metadata, doc_id = fn.to_db_record()
        assert document == "ctx window text"
        assert doc_id == f"fn_{fn.footnote_id}"
        assert "context_window" not in metadata

    def test_to_db_record_falls_back_to_raw(self):
        fn = self._valid(context_window="")
        document, metadata, doc_id = fn.to_db_record()
        assert document == fn.footnote_text_raw


# ===========================================================================
# TestTalkFootnotes
# ===========================================================================


class TestTalkFootnotes:
    """Tests for the TalkFootnotes container."""

    def _make_fn(self, fn_num: int) -> FootnoteData:
        return FootnoteData(
            footnote_id=100000 + fn_num,
            talk_id=1,
            paragraph_id=10001,
            paragraph_number=1,
            footnote_number=fn_num,
            footnote_text_raw=f"[Note {fn_num}]",
            char_position=fn_num * 10,
        )

    def test_valid_container(self):
        footnotes = [self._make_fn(1), self._make_fn(2)]
        tf = TalkFootnotes(
            talk_id=1,
            footnotes=footnotes,
            total_footnotes=2,
            extraction_success=True,
        )
        assert tf.total_footnotes == 2

    def test_count_mismatch_raises(self):
        footnotes = [self._make_fn(1)]
        with pytest.raises(ValueError, match="does not match"):
            TalkFootnotes(
                talk_id=1,
                footnotes=footnotes,
                total_footnotes=5,
                extraction_success=True,
            )


# ===========================================================================
# TestValidation
# ===========================================================================


class TestValidation:
    """Tests for validate_footnote and validate_talk_footnotes."""

    def _make_fn(self, fn_num=1, text="[Valid note text.]", pos=10):
        return FootnoteData(
            footnote_id=100000 + fn_num,
            talk_id=1,
            paragraph_id=10001,
            paragraph_number=1,
            footnote_number=fn_num,
            footnote_text_raw=text,
            char_position=pos,
            context_window="ctx" if pos != -1 else "",
        )

    def test_happy_path_no_warnings(self):
        fn = self._make_fn()
        warnings = validate_footnote(fn, CONFIG)
        assert warnings == []

    def test_short_text_warning(self):
        fn = self._make_fn(text="Hi")
        warnings = validate_footnote(fn, CONFIG)
        assert any("short" in w for w in warnings)

    def test_position_not_found_warning(self):
        fn = self._make_fn(pos=-1)
        warnings = validate_footnote(fn, CONFIG)
        assert any("position not found" in w for w in warnings)

    def test_sequential_numbering_no_warning(self):
        tf = TalkFootnotes(
            talk_id=1,
            footnotes=[self._make_fn(1), self._make_fn(2), self._make_fn(3)],
            total_footnotes=3,
            extraction_success=True,
        )
        result = validate_talk_footnotes(tf, CONFIG)
        gap_warnings = [w for w in result.warnings if "Gap" in w]
        assert gap_warnings == []

    def test_gap_in_numbering_warning(self):
        tf = TalkFootnotes(
            talk_id=1,
            footnotes=[self._make_fn(1), self._make_fn(3)],  # gap: 1 → 3
            total_footnotes=2,
            extraction_success=True,
        )
        result = validate_talk_footnotes(tf, CONFIG)
        assert any("Gap" in w for w in result.warnings)

    def test_empty_talk_no_errors(self):
        tf = TalkFootnotes(
            talk_id=1,
            footnotes=[],
            total_footnotes=0,
            extraction_success=True,
        )
        result = validate_talk_footnotes(tf, CONFIG)
        assert result.is_valid
        assert result.stats["total"] == 0


# ===========================================================================
# TestFootnoteTextRendering
# ===========================================================================


class TestFootnoteTextRendering:
    """Tests for _render_footnote_span and _ccontainer_punctuation.

    Covers whitespace preservation between inline elements and ccontainer
    punctuation injection.
    """

    def _span(self, html: str):
        from bs4 import BeautifulSoup

        return BeautifulSoup(html, "html.parser").find("span")

    # --- whitespace preservation ---

    def test_cite_tags_preserve_surrounding_spaces(self):
        """Spaces between <cite> elements must not be collapsed into nothing.

        Regression: BUG-13 — whitespace destroyed between inline elements;
        get_text(strip=True) dropped inter-element spaces.
        """
        html = (
            '<span class="footnote long">[<span class="note-p">'
            'Joseph&nbsp;B. Wirthlin, "The Great Commandment,"'
            " <cite>Ensign</cite> or <cite>Liahona</cite>, Nov. 2007,&nbsp;30."
            "</span>]</span>"
        )
        result = _render_footnote_span(self._span(html))
        assert "Ensign or Liahona" in result
        assert "EnsignorLiahona" not in result

    def test_nbsp_converted_to_regular_space(self):
        html = '<span class="footnote">[Joseph&nbsp;B. Smith, 1901.]</span>'
        result = _render_footnote_span(self._span(html))
        assert "Joseph B. Smith" in result
        assert "\u00a0" not in result

    def test_multiple_spaces_collapsed(self):
        html = '<span class="footnote">[Word   extra   spaces.]</span>'
        result = _render_footnote_span(self._span(html))
        assert "  " not in result

    # --- sx() anchor removal ---

    def test_sx_anchor_removed_no_extra_space(self):
        """The &nbsp;-only sx() anchor should not leave a leading space on the citation.

        Regression: BUG-14 — extra leading spaces from sx() anchors containing
        non-breaking space before citation text.
        """
        html = (
            '<span class="footnote">'
            '<span class="citation" id="1">'
            '<a href="javascript:void(0)" onclick="sx(this, 1)">\u00a0</a>'
            '<a href="javascript:void(0)" onclick="gs(1)">Mosiah 2:17</a>'
            "</span></span>"
        )
        result = _render_footnote_span(self._span(html))
        assert result == "Mosiah 2:17"
        assert result[0] != " "

    # --- _ccontainer_punctuation unit tests ---

    def test_rsemi_gives_semicolon_suffix(self):
        """Regression: BUG-15 — missing punctuation from CSS ccontainer
        pseudo-elements not present in HTML text content.
        """
        prefix, suffix = _ccontainer_punctuation(["ccontainer", "rsemi"])
        assert prefix == ""
        assert suffix == ";"

    def test_rdot_gives_dot_suffix(self):
        _, suffix = _ccontainer_punctuation(["ccontainer", "rdot"])
        assert suffix == "."

    def test_rbrackdotrdquo_gives_compound_suffix(self):
        """Regression: BUG-01 — cp1252 encoding of curly quotes in _PUNCT_TOKENS
        caused replacement chars on Windows. The fix uses ASCII-safe \\u201d escapes.
        Reverting the encoding fix would produce \\ufffd instead of \\u201d.
        """
        _, suffix = _ccontainer_punctuation(["ccontainer", "rbrackdotrdquo"])
        assert suffix == '].' + '\u201d'  # ]  .  " (right double curly quote)

    def test_lparen_gives_paren_prefix(self):
        prefix, suffix = _ccontainer_punctuation(["ccontainer", "lparen"])
        assert prefix == "("
        assert suffix == ""

    def test_rparen_gives_paren_suffix(self):
        prefix, suffix = _ccontainer_punctuation(["ccontainer", "rparen"])
        assert prefix == ""
        assert suffix == ")"

    def test_lparen_rparencomma_gives_both(self):
        prefix, suffix = _ccontainer_punctuation(
            ["ccontainer", "lparen", "rparencomma"]
        )
        assert prefix == "("
        assert suffix == "),"

    def test_unknown_class_ignored(self):
        prefix, suffix = _ccontainer_punctuation(["ccontainer", "xunknown"])
        assert prefix == ""
        assert suffix == ""

    # --- ccontainer injection in full span ---

    def test_rsemi_appended_after_citation(self):
        html = (
            '<span class="footnote long">[<span class="note-p">See '
            '<span class="ccontainer rsemi">'
            '<span class="citation" id="1">'
            '<a onclick="sx(this, 1)">\u00a0</a>'
            '<a onclick="gs(1)">Luke 19:1\u20134</a>'
            "</span></span>"
            " see also other text.</span>]</span>"
        )
        result = _render_footnote_span(self._span(html))
        assert "Luke 19:1\u20134;" in result
        assert "See Luke 19:1\u20134; see also other text." in result

    def test_bare_citation_no_punctuation_injected(self):
        """Citations not wrapped in ccontainer get no extra punctuation."""
        html = (
            '<span class="footnote">'
            '<span class="citation" id="2">'
            '<a onclick="sx(this, 2)">\u00a0</a>'
            '<a onclick="gs(2)">Jacob 4:13</a>'
            "</span></span>"
        )
        result = _render_footnote_span(self._span(html))
        assert result == "Jacob 4:13"

    # --- real-world examples ---

    def test_real_world_wirthlin_cite_tags(self):
        html = (
            '<sup class="noteMarker"><a href="#note2">2</a>'
            '<span class="footnote long">[<span class="note-p">'
            "Joseph\u00a0B. Wirthlin, \u201cThe Great Commandment,\u201d"
            " <cite>Ensign</cite> or <cite>Liahona</cite>, Nov. 2007,\u00a030."
            "</span>]</span></sup>"
        )
        from bs4 import BeautifulSoup
        from extractors.footnotes import _extract_footnote_text

        soup = BeautifulSoup(html, "html.parser")
        marker = soup.find("sup", class_="noteMarker")
        result = _extract_footnote_text(marker)
        assert "Ensign or Liahona" in result
        assert "Nov. 2007" in result

    def test_real_world_scripture_ccontainer_rsemi(self):
        html = (
            '<sup class="noteMarker"><a href="#note5">5</a>'
            '<span class="footnote long">[<span class="note-p">See '
            '<span class="ccontainer rsemi"><span class="citation" id="139288">'
            '<a href="javascript:void(0)" onclick="sx(this, 139288)">\u00a0</a>'
            '<a href="javascript:void(0)" onclick="gs(139288)">Luke 19:1\u20134</a>'
            "</span></span>"
            ' see also <span class="citation" id="139289">'
            '<a href="javascript:void(0)" onclick="sx(this, 139289)">\u00a0</a>'
            '<a href="javascript:void(0)" onclick="gs(139289)">Jacob 4:13</a>'
            "</span> (explaining that the Spirit \u201cspeaketh of things as they really are"
            ", and of things as they really will be\u201d) and "
            '<span class="citation" id="139290">'
            '<a href="javascript:void(0)" onclick="sx(this, 139290)">\u00a0</a>'
            '<a href="javascript:void(0)" onclick="gs(139290)">Doctrine and Covenants 93:24</a>'
            "</span> (defining truth as \u201cknowledge of things as they are, and as they were"
            ", and as they are to come\u201d).</span>]</span></sup>"
        )
        from bs4 import BeautifulSoup
        from extractors.footnotes import _extract_footnote_text

        soup = BeautifulSoup(html, "html.parser")
        marker = soup.find("sup", class_="noteMarker")
        result = _extract_footnote_text(marker)
        assert "Luke 19:1\u20134;" in result
        assert "see also Jacob 4:13" in result
        assert "Doctrine and Covenants 93:24" in result
        assert "  " not in result  # no double spaces


# ===========================================================================
# TestOrchestration (integration)
# ===========================================================================


class TestOrchestration:
    """Integration tests for process_talk_footnotes."""

    TALK_ID = 42

    def _make_para(self, html: str, para_num: int) -> ParagraphData:
        return make_paragraph(html, paragraph_number=para_num, talk_id=self.TALK_ID)

    def test_full_pipeline(self):
        html = (
            "Intro text"
            '<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[Ruskin, Brass Nails.]</span></sup>'
            " more text."
        )
        para = self._make_para(html, 1)
        talk_footnotes, warnings = process_talk_footnotes(self.TALK_ID, [para], CONFIG)
        assert talk_footnotes.total_footnotes == 1
        assert talk_footnotes.extraction_success
        fn = talk_footnotes.footnotes[0]
        assert fn.footnote_text_raw == "[Ruskin, Brass Nails.]"
        assert fn.footnote_number == 1
        assert fn.char_position == len("Intro text")

    def test_paragraph_flags_updated(self):
        html = (
            'Text<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[Note A]</span></sup>'
            ' more<sup class="noteMarker"><a href="#fn2">2</a>'
            '<span class="footnote">[Note B]</span></sup>'
        )
        para = self._make_para(html, 1)
        process_talk_footnotes(self.TALK_ID, [para], CONFIG)
        assert para.has_footnote is True
        assert para.footnote_count == 2

    def test_no_footnotes_returns_empty(self):
        para = self._make_para("<p>No footnotes here.</p>", 1)
        talk_footnotes, warnings = process_talk_footnotes(self.TALK_ID, [para], CONFIG)
        assert talk_footnotes.total_footnotes == 0
        assert talk_footnotes.extraction_success
        assert para.has_footnote is False
        assert para.footnote_count == 0

    def test_paragraph_without_text_raw_skipped(self):
        para = ParagraphData(
            paragraph_id=self.TALK_ID * 10000 + 1,
            talk_id=self.TALK_ID,
            paragraph_number=1,
            text="Some text",
            text_raw=None,
            word_count=2,
        )
        talk_footnotes, warnings = process_talk_footnotes(self.TALK_ID, [para], CONFIG)
        assert talk_footnotes.total_footnotes == 0

    def test_footnote_id_formula(self):
        """footnote_id = talk_id * 100000 + paragraph_number * 100 + footnote_number (global superscript)."""
        html = (
            'A<sup class="noteMarker"><a href="#fn1">1</a>'
            '<span class="footnote">[Note]</span></sup>'
        )
        para = self._make_para(html, 3)  # paragraph_number=3
        talk_footnotes, _ = process_talk_footnotes(self.TALK_ID, [para], CONFIG)
        fn = talk_footnotes.footnotes[0]
        expected_id = self.TALK_ID * 100000 + 3 * 100 + fn.footnote_number
        assert fn.footnote_id == expected_id
