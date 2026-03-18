"""
Unit tests for shared HTML parsing utilities.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest
from bs4 import BeautifulSoup, Tag

from extractors.html_parsing_utils import (
    ELEMENT_PLACEHOLDER,
    _find_position_anchor,
    _snap_to_word_boundaries,
    filter_paragraph_around_anchor,
    apply_context_window,
)


# =============================================================================
# TestFindPositionAnchor
# =============================================================================


class TestFindPositionAnchor:
    """Walk up from a target element to find the topmost direct child of the paragraph root."""

    def test_direct_child_of_document(self):
        """A span directly under the document root is its own anchor."""
        html = '<span class="citation" id="1">D&amp;C 1:1</span> some text'
        soup = BeautifulSoup(html, "html.parser")
        span = soup.find("span", class_="citation")
        assert _find_position_anchor(span) is span

    def test_ccontainer_wrapped(self):
        """A citation inside a ccontainer returns the ccontainer."""
        html = '<span class="ccontainer"><span class="citation" id="2">Gen 1:1</span></span>'
        soup = BeautifulSoup(html, "html.parser")
        span = soup.find("span", class_="citation")
        anchor = _find_position_anchor(span)
        assert anchor.name == "span"
        assert "ccontainer" in anchor.get("class", [])

    def test_notemarker_wrapped(self):
        """A citation inside a noteMarker sup returns the noteMarker."""
        html = '<sup class="noteMarker"><span class="citation" id="3">Mosiah 2:17</span></sup>'
        soup = BeautifulSoup(html, "html.parser")
        span = soup.find("span", class_="citation")
        anchor = _find_position_anchor(span)
        assert anchor.name == "sup"
        assert "noteMarker" in anchor.get("class", [])

    def test_deeply_nested(self):
        """Deep nesting still returns the topmost child below root."""
        html = (
            '<div><span><em><span class="citation" id="4">Test</span></em></span></div>'
        )
        soup = BeautifulSoup(html, "html.parser")
        span = soup.find("span", class_="citation")
        anchor = _find_position_anchor(span)
        assert anchor.name == "div"

    def test_inside_p_tag(self):
        """When wrapped in <p>, returns direct child of <p>."""
        html = '<p>Before <sup class="noteMarker"><span class="citation" id="5">Ref</span></sup> after</p>'
        soup = BeautifulSoup(html, "html.parser")
        span = soup.find("span", class_="citation")
        anchor = _find_position_anchor(span)
        assert anchor.name == "sup"


# =============================================================================
# TestSnapToWordBoundaries
# =============================================================================


class TestSnapToWordBoundaries:
    """Trim partial words at context window edges."""

    def test_before_truncated(self):
        before, after = _snap_to_word_boundaries(
            "artial word before", "after text", True, False
        )
        assert before == "word before"

    def test_after_truncated(self):
        before, after = _snap_to_word_boundaries(
            "before text", "after tex", False, True
        )
        assert after == "after"

    def test_both_truncated(self):
        before, after = _snap_to_word_boundaries(
            "artial before", "after parti", True, True
        )
        assert before == "before"
        assert after == "after"

    def test_neither_truncated(self):
        before, after = _snap_to_word_boundaries(
            "full before", "full after", False, False
        )
        assert before == "full before"
        assert after == "full after"

    def test_no_spaces_in_before_slice(self):
        """If there's no space to snap to, keep the full slice."""
        before, after = _snap_to_word_boundaries(
            "nospaceshere", "after text", True, False
        )
        assert before == "nospaceshere"

    def test_no_spaces_in_after_slice(self):
        before, after = _snap_to_word_boundaries(
            "before text", "nospaceshere", False, True
        )
        assert after == "nospaceshere"


# =============================================================================
# TestFilterParagraphAroundAnchor
# =============================================================================


class TestFilterParagraphAroundAnchor:
    """Replace anchor with placeholder, decompose remaining noteMarkers."""

    def test_basic_replacement(self):
        html = 'Before <span class="citation" id="1">D&amp;C 1:1</span> after'
        soup = BeautifulSoup(html, "html.parser")
        anchor = soup.find("span", class_="citation")
        result = filter_paragraph_around_anchor(soup, anchor, ELEMENT_PLACEHOLDER)
        assert ELEMENT_PLACEHOLDER in result
        assert "D&C 1:1" not in result
        assert "Before" in result
        assert "after" in result

    def test_other_notemarkers_decomposed(self):
        html = (
            'Text <sup class="noteMarker"><span class="citation" id="1">Ref1</span></sup>'
            " middle "
            '<sup class="noteMarker"><a href="#">2</a><span class="footnote">[note]</span></sup>'
            " end"
        )
        soup = BeautifulSoup(html, "html.parser")
        target_sup = soup.find("sup", class_="noteMarker")
        result = filter_paragraph_around_anchor(soup, target_sup, ELEMENT_PLACEHOLDER)
        assert ELEMENT_PLACEHOLDER in result
        assert "[note]" not in result  # other noteMarker content removed
        assert "middle" in result

    def test_anchor_is_notemarker(self):
        """When the anchor IS a noteMarker, it gets replaced not decomposed."""
        html = '<sup class="noteMarker"><a>1</a><span class="footnote">[Source]</span></sup> text'
        soup = BeautifulSoup(html, "html.parser")
        anchor = soup.find("sup", class_="noteMarker")
        result = filter_paragraph_around_anchor(soup, anchor, ELEMENT_PLACEHOLDER)
        assert ELEMENT_PLACEHOLDER in result
        assert "[Source]" not in result
        assert "text" in result


# =============================================================================
# TestApplyContextWindow
# =============================================================================


class TestApplyContextWindow:
    """Extract context window around placeholder position."""

    def _config(self, before=100, after=100, mode="char"):
        return {
            "context_before_chars": before,
            "context_after_chars": after,
            "context_window_mode": mode,
        }

    def test_normal(self):
        text = "The quick brown fox " + ELEMENT_PLACEHOLDER + " jumps over the lazy dog"
        cb, ca, cw = apply_context_window(
            text, ELEMENT_PLACEHOLDER, "LABEL", self._config()
        )
        assert cb == "The quick brown fox "
        assert ca == " jumps over the lazy dog"
        assert cw == "The quick brown fox LABEL jumps over the lazy dog"

    def test_placeholder_at_start(self):
        text = ELEMENT_PLACEHOLDER + " rest of text"
        cb, ca, cw = apply_context_window(
            text, ELEMENT_PLACEHOLDER, "X", self._config()
        )
        assert cb == ""
        assert "rest of text" in ca

    def test_placeholder_at_end(self):
        text = "beginning of text " + ELEMENT_PLACEHOLDER
        cb, ca, cw = apply_context_window(
            text, ELEMENT_PLACEHOLDER, "X", self._config()
        )
        assert "beginning of text" in cb
        assert ca == ""

    def test_not_found(self):
        result = apply_context_window(
            "no placeholder here", ELEMENT_PLACEHOLDER, "X", self._config()
        )
        assert result == ("", "", "")

    def test_word_mode(self):
        # 10 char before limit will cut mid-word in "beginning"
        text = "In the beginning " + ELEMENT_PLACEHOLDER + " there was something more"
        cb, ca, cw = apply_context_window(
            text,
            ELEMENT_PLACEHOLDER,
            "REF",
            self._config(before=10, after=15, mode="word"),
        )
        # "beginning " is 10 chars — before_start=8, cuts into "beginning"
        # With word snapping, partial word "beginning" at left edge should be kept
        # since before_start > 0 → snaps to first space
        assert "REF" in cw

    def test_char_mode_no_snapping(self):
        text = "abcdefghij" + ELEMENT_PLACEHOLDER + "klmnopqrst"
        cb, ca, cw = apply_context_window(
            text, ELEMENT_PLACEHOLDER, "|", self._config(before=5, after=5, mode="char")
        )
        assert cb == "fghij"
        assert ca == "klmno"
        assert cw == "fghij|klmno"
