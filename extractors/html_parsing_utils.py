# -*- coding: utf-8 -*-
"""
Shared HTML parsing utilities for the extraction pipeline.

Provides HTML parsing, body container detection, position anchor walking,
word boundary snapping, filtered paragraph building, context window extraction,
punctuation token rendering, and a lazy-parsed paragraph context wrapper —
used by all pipeline phases.
"""

import copy
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag

logger = logging.getLogger(__name__)


# =============================================================================
# HTML Parsing & Container Detection
# =============================================================================


def parse_html(html: str, parser: str = "html.parser") -> Optional[BeautifulSoup]:
    """
    Parse an HTML string into a BeautifulSoup object.

    Falls back to html.parser if lxml raises an exception.
    Returns None for empty input or when both parsers fail.
    """
    if not html or not html.strip():
        logger.warning("Empty HTML provided to parse_html")
        return None

    try:
        return BeautifulSoup(html, parser)
    except Exception as e:
        logger.error(f"HTML parsing failed with {parser}: {e}")
        if parser == "lxml":
            try:
                logger.info("Trying fallback parser: html.parser")
                return BeautifulSoup(html, "html.parser")
            except Exception as e2:
                logger.error(f"Fallback parser also failed: {e2}")
        return None


def find_body_container(soup: BeautifulSoup) -> Optional[Tag]:
    """
    Find the main body container using an era-specific fallback chain.

    Fallback order:
      1. div.body-block  (2010s–present)
      2. div#primary     (1990s–2000s)
      3. div.gcbody      (1950s–1970s)
      4. div.primary     (1980s)

    Returns the container Tag, or None if not found.
    """
    if not soup:
        return None

    selectors = [
        ("div", {"class": "body-block"}),
        ("div", {"id": "primary"}),
        ("div", {"class": "gcbody"}),
        ("div", {"class": "primary"}),
    ]

    for tag_name, attrs in selectors:
        container = soup.find(tag_name, attrs)
        if container:
            logger.debug(f"Found body container: {tag_name} with {attrs}")
            return container

    logger.warning("No body container found using fallback chain")
    return None


# =============================================================================
# Lazy-Parsed Paragraph Context
# =============================================================================


class ParagraphHTMLContext:
    """
    Wraps a paragraph's raw HTML and lazily parses it once.

    - ``soup``      — cached read-only parse for discovery (find_all, find)
    - ``fresh_soup()`` — new parse for mutating operations (decompose, replace_with)
    - ``find_citation_spans()`` / ``find_note_markers()`` — convenience finders
    """

    def __init__(self, text_raw: str, parser: str = "html.parser") -> None:
        self._text_raw = text_raw
        self._parser = parser
        self._soup: Optional[BeautifulSoup] = None

    @property
    def soup(self) -> BeautifulSoup:
        if self._soup is None:
            self._soup = BeautifulSoup(self._text_raw, self._parser)
        return self._soup

    def fresh_soup(self) -> BeautifulSoup:
        """Return a new independent parse suitable for mutation."""
        return BeautifulSoup(self._text_raw, self._parser)

    def find_citation_spans(self) -> List[Tag]:
        return self.soup.find_all("span", class_="citation")

    def find_note_markers(self) -> List[Tag]:
        return self.soup.find_all("sup", class_="noteMarker")


# Null-byte placeholder — substituted for the position anchor element so its
# location can be found in the filtered text.  Null bytes never appear in
# normal paragraph text.
ELEMENT_PLACEHOLDER = "\x00"


def _find_position_anchor(element: Tag) -> Tag:
    """
    Walk up from *element* to find the topmost Tag that is a direct child of
    the paragraph root (BeautifulSoup document or <p>).

    Returns the correct position anchor for all structures:
    - Direct <span class="citation">  → the citation span itself
    - <span class="ccontainer ...">   → the ccontainer span
    - <sup class="noteMarker">        → the noteMarker sup
    """
    anchor = element
    for parent in element.parents:
        if not isinstance(parent, Tag):
            break  # reached NavigableString root (shouldn't happen)
        if parent.name in ("p", "[document]"):
            break  # reached paragraph wrapper or BeautifulSoup document root
        anchor = parent
    return anchor


def _snap_to_word_boundaries(
    before: str,
    after: str,
    before_truncated: bool,
    after_truncated: bool,
) -> Tuple[str, str]:
    """
    Trim partial words introduced by hard character cuts.

    before_truncated: True when the slice didn't start at position 0 (i.e.,
        the left edge may have cut mid-word).
    after_truncated: True when the slice didn't reach the end of the text
        (i.e., the right edge may have cut mid-word).

    In each case the partial word is dropped so the window always starts and
    ends on a whole word boundary.
    """
    if before_truncated:
        space_idx = before.find(" ")
        if space_idx != -1:
            before = before[space_idx + 1 :]

    if after_truncated:
        space_idx = after.rfind(" ")
        if space_idx != -1:
            after = after[:space_idx]

    return before, after


def filter_paragraph_around_anchor(
    soup: BeautifulSoup,
    anchor: Tag,
    placeholder: str,
) -> str:
    """
    Replace *anchor* with *placeholder*, decompose remaining noteMarker sups,
    and return the filtered plain text.

    The anchor is replaced first so that if the anchor itself is a noteMarker,
    it won't be accidentally removed during the decompose step.
    """
    anchor.replace_with(placeholder)

    for marker in soup.find_all("sup", class_="noteMarker"):
        marker.decompose()

    return soup.get_text(strip=True)


def apply_context_window(
    filtered_text: str,
    placeholder_char: str,
    label: str,
    config: Dict[str, Any],
) -> Tuple[str, str, str]:
    """
    Find *placeholder_char* in *filtered_text*, extract before/after slices
    per config limits, apply word boundary snapping, and assemble the
    context_window string using *label* as the centre piece.

    Returns (context_before, context_after, context_window).
    Returns ("", "", "") if the placeholder is not found.
    """
    pos = filtered_text.find(placeholder_char)
    if pos == -1:
        return "", "", ""

    before_chars = config.get("context_before_chars", 100)
    after_chars = config.get("context_after_chars", 100)
    word_mode = config.get("context_window_mode", "char") == "word"

    before_start = max(0, pos - before_chars)
    after_end = min(len(filtered_text), pos + 1 + after_chars)

    context_before = filtered_text[before_start:pos]
    context_after = filtered_text[pos + 1 : after_end]

    if word_mode:
        context_before, context_after = _snap_to_word_boundaries(
            context_before,
            context_after,
            before_truncated=before_start > 0,
            after_truncated=after_end < len(filtered_text),
        )

    context_window = context_before + label + context_after
    return context_before, context_after, context_window


# =============================================================================
# Punctuation Token Rendering
# =============================================================================

# Atomic punctuation tokens.  Directional tokens use a dict keyed by "l"/"r";
# neutral tokens are a plain string (same char regardless of side).
# Class names are sequences of these tokens, each optionally preceded by "l" or "r".
_PUNCT_TOKENS: Dict[str, Any] = {
    "semi": ";",
    "dot": ".",
    "comma": ",",
    "paren": {"l": "(", "r": ")"},
    "brack": {"l": "[", "r": "]"},
    # "dquo": '"',
    "dquo": {"l": "\u201c", "r": "\u201d"},
    "squo": {"l": "‘", "r": "’"},
    "quote": '"',
    "mdash": "—",
    "quest": "?",
    "colon": ":",
    "bang": "!",
    "apos": "'",
}
# Sorted longest-first so greedy matching prefers longer tokens (e.g. "brack" over "b")
_TOKENS_BY_LENGTH = sorted(_PUNCT_TOKENS, key=len, reverse=True)


def _parse_punct_class(cls: str) -> Tuple[str, str]:
    """Parse a single ccontainer class name into (prefix, suffix).

    A class name is a concatenation of {l|r}{token} segments. Direction is
    sticky: tokens without an explicit l/r prefix inherit the most recent
    direction (defaulting to "r" when none has been seen yet).

    Examples:
      "rsemi"          → ("", ";")
      "lparen"         → ("(", "")
      "rparencomma"    → ("", "),")    r+paren, comma inherits r
      "rbrackdotrdquo" → ("", ']."')   r+brack, dot inherits r, r+dquo
    """
    prefix_parts: List[str] = []
    suffix_parts: List[str] = []
    direction = "r"  # sticky direction, defaults to right
    i = 0
    n = len(cls)

    while i < n:
        consumed = False

        # Try to consume an explicit direction prefix + token
        if cls[i] in ("l", "r"):
            candidate_dir = cls[i]
            for token in _TOKENS_BY_LENGTH:
                end = i + 1 + len(token)
                if cls[i + 1 : end] == token:
                    direction = candidate_dir
                    entry = _PUNCT_TOKENS[token]
                    char = entry[direction] if isinstance(entry, dict) else entry
                    (prefix_parts if direction == "l" else suffix_parts).append(char)
                    i = end
                    consumed = True
                    break

        # No direction prefix found — try bare token with sticky direction
        if not consumed:
            for token in _TOKENS_BY_LENGTH:
                end = i + len(token)
                if cls[i:end] == token:
                    entry = _PUNCT_TOKENS[token]
                    char = entry[direction] if isinstance(entry, dict) else entry
                    (prefix_parts if direction == "l" else suffix_parts).append(char)
                    i = end
                    consumed = True
                    break

        if not consumed:
            i += 1  # skip unrecognised character

    return "".join(prefix_parts), "".join(suffix_parts)


def _ccontainer_punctuation(classes: List[str]) -> Tuple[str, str]:
    """Parse ccontainer CSS classes into (prefix, suffix) punctuation strings."""
    prefix_parts: List[str] = []
    suffix_parts: List[str] = []
    for cls in classes:
        if not cls or cls[0] not in ("l", "r"):
            continue
        p, s = _parse_punct_class(cls)
        prefix_parts.append(p)
        suffix_parts.append(s)
    return "".join(prefix_parts), "".join(suffix_parts)


def render_span_text(span: Tag) -> str:
    """Convert a citation or footnote span to clean text.

    - Removes <a onclick="sx(...)"> anchors (display-only hooks with no text)
    - Injects punctuation around ccontainer spans via _ccontainer_punctuation()
    - Normalizes &nbsp; to regular space and collapses multiple spaces
    """
    span = copy.deepcopy(span)

    # Remove all sx() anchor tags — display-only hooks with no text content
    for a in span.find_all("a"):
        if "sx(" in a.get("onclick", ""):
            a.decompose()

    # Inject punctuation around ccontainer spans.
    # Include the root span itself if it carries ccontainer classes, since
    # find_all() only searches descendants, not the root.
    ccontainer_targets = span.find_all("span", class_="ccontainer")
    if "ccontainer" in (span.get("class") or []):
        ccontainer_targets = [span] + list(ccontainer_targets)
    for ccontainer in ccontainer_targets:
        prefix, suffix = _ccontainer_punctuation(ccontainer.get("class", []))
        if prefix:
            ccontainer.insert(0, NavigableString(prefix))
        if suffix:
            ccontainer.append(NavigableString(suffix))

    text = span.get_text()
    text = text.replace("\u00a0", " ")  # &nbsp; → regular space
    text = re.sub(r" {2,}", " ", text)  # collapse runs of spaces
    return text.strip()
