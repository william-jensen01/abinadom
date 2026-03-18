"""
Phase 4: Footnote extraction from General Conference talk HTML.

Extracts footnotes as "see also" markers. No type-specific parsing —
the full footnote text is the data to be embedded.

3-layer architecture:
  Layer 2 — Extraction (no DB access needed — footnotes are entirely in HTML)
  Layer 3 — Validation
  Orchestration — process_talk_footnotes()
"""

from typing import Any, Dict, List, Optional, Tuple
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup

from extractors.html_parsing_utils import (
    ELEMENT_PLACEHOLDER,
    ParagraphHTMLContext,
    filter_paragraph_around_anchor,
    apply_context_window,
    render_span_text,
)
from models.footnote_data import FootnoteData, TalkFootnotes
from models.paragraph_data import ParagraphData, ValidationResult


# =============================================================================
# LAYER 2: Extraction
# =============================================================================


def extract_footnotes_from_paragraph(
    paragraph: ParagraphData,
    config: Dict[str, Any],
    ctx: Optional[ParagraphHTMLContext] = None,
) -> Tuple[List[Dict], List[str]]:
    """
    Detect and extract footnotes from a paragraph's HTML.

    When *ctx* is provided its cached soup is used for marker discovery (avoids
    a redundant re-parse).  Mutating operations always use a fresh parse.

    Returns a list of raw footnote dicts:
        {footnote_number, footnote_text_raw, element_index}
    and a list of warnings.
    """
    warnings: List[str] = []

    if not paragraph.text_raw:
        return [], warnings

    parser = config.get("html_parser", "html.parser")
    soup = ctx.soup if ctx is not None else BeautifulSoup(paragraph.text_raw, parser)
    markers = soup.find_all("sup", class_="noteMarker")

    if not markers:
        return [], warnings

    max_warn = config.get("max_footnotes_per_paragraph_warning", 20)
    if len(markers) > max_warn:
        warnings.append(
            f"Paragraph {paragraph.paragraph_number} has {len(markers)} footnotes "
            f"(threshold: {max_warn})"
        )

    footnotes = []
    for element_index, marker in enumerate(markers):
        fn_num, fn_warnings = _extract_footnote_number(marker, element_index)
        warnings.extend(fn_warnings)
        footnote_text = _extract_footnote_text(marker)
        footnotes.append(
            {
                "footnote_number": fn_num,
                "footnote_text_raw": footnote_text,
                "element_index": element_index,
            }
        )

    return footnotes, warnings


def _extract_footnote_number(marker, element_index: int) -> Tuple[int, List[str]]:
    """Extract the footnote number from a noteMarker element.

    Non-numeric markers (* or missing <a>) get a sequential number based on
    element position (element_index + 1) and generate a warning.
    """
    warnings = []
    a_tag = marker.find("a")
    if a_tag:
        text = a_tag.get_text(strip=True)
        if text == "*":
            fn_num = element_index + 1
            warnings.append(
                f"Asterisk footnote marker at element index {element_index}; "
                f"assigned sequential number {fn_num}"
            )
            return fn_num, warnings
        try:
            return int(text), warnings
        except ValueError:
            fn_num = element_index + 1
            warnings.append(
                f"Non-numeric footnote marker '{text}' at element index {element_index}; "
                f"assigned sequential number {fn_num}"
            )
            return fn_num, warnings
    # No <a> tag — assign by position
    fn_num = element_index + 1
    warnings.append(
        f"No <a> tag in noteMarker at element index {element_index}; "
        f"assigned sequential number {fn_num}"
    )
    return fn_num, warnings



def _extract_footnote_text(marker) -> str:
    """Extract footnote display text from a noteMarker element.

    Preference order:
      1. <span class="footnote"> (standard pattern)
      2. <span class="citation"> (scripture-only footnote)
      3. Full sup text (fallback)
    """
    fn_span = marker.find("span", class_=lambda c: c and "footnote" in c)
    if fn_span:
        return render_span_text(fn_span)
    cit_span = marker.find("span", class_="citation")
    if cit_span:
        return render_span_text(cit_span)
    return render_span_text(marker)


def _build_filtered_paragraph_for_footnote(
    text_raw: str,
    footnote_index: int,
    parser: str = "html.parser",
) -> Tuple[str, str]:
    """
    Replace the target noteMarker (by index) with ELEMENT_PLACEHOLDER and
    decompose all remaining noteMarkers. Returns (filtered_text, footnote_text).

    If footnote_index is out of range, all markers are decomposed and ("", "")
    is returned for the footnote text.
    """
    soup = BeautifulSoup(text_raw, parser)
    markers = soup.find_all("sup", class_="noteMarker")

    if footnote_index < 0 or footnote_index >= len(markers):
        for m in markers:
            m.decompose()
        return soup.get_text(strip=True), ""

    target = markers[footnote_index]
    # Extract text before modifying the tree
    footnote_text = _extract_footnote_text(target)
    # noteMarker IS the anchor — pass directly to shared utility
    filtered = filter_paragraph_around_anchor(soup, target, ELEMENT_PLACEHOLDER)
    return filtered, footnote_text


def calculate_footnote_position(
    text_raw: str,
    footnote_index: int,
    config: Dict[str, Any],
) -> int:
    """
    Calculate the char_position of a footnote marker in the clean paragraph text.

    Single position value (not start/end pair — markers are point insertions).
    Returns -1 if the marker cannot be located.
    """
    parser = config.get("html_parser", "html.parser")
    filtered, _ = _build_filtered_paragraph_for_footnote(
        text_raw, footnote_index, parser
    )
    return filtered.find(ELEMENT_PLACEHOLDER)  # -1 if not found


def extract_footnote_context_window(
    text_raw: str,
    footnote_index: int,
    footnote_text_raw: str,
    config: Dict[str, Any],
) -> Tuple[str, str, str]:
    """
    Extract context_before, context_after, context_window for a footnote marker.

    Returns ("", "", "") if the marker position cannot be found.
    """
    parser = config.get("html_parser", "html.parser")
    filtered, _ = _build_filtered_paragraph_for_footnote(
        text_raw, footnote_index, parser
    )
    return apply_context_window(
        filtered, ELEMENT_PLACEHOLDER, footnote_text_raw, config
    )


# =============================================================================
# LAYER 3: Validation
# =============================================================================


def validate_footnote(
    footnote: FootnoteData,
    config: Dict[str, Any],
) -> List[str]:
    """Validate a single FootnoteData. Returns a list of warnings."""
    warnings = []
    if len(footnote.footnote_text_raw) < 3:
        warnings.append(
            f"Footnote {footnote.footnote_number} has very short text: "
            f"'{footnote.footnote_text_raw}'"
        )
    if footnote.char_position == -1:
        warnings.append(
            f"Footnote {footnote.footnote_number} position not found in paragraph text"
        )
    if footnote.char_position != -1 and not footnote.context_window:
        warnings.append(
            f"Footnote {footnote.footnote_number} has valid position but empty context_window"
        )
    return warnings


def validate_talk_footnotes(
    talk_footnotes: TalkFootnotes,
    config: Dict[str, Any],
) -> ValidationResult:
    """Validate all footnotes for a talk. Returns a ValidationResult."""
    errors: List[str] = []
    warnings: List[str] = []

    if not talk_footnotes.footnotes:
        return ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
            stats={"total": 0, "position_found_rate": 0.0},
        )

    # Per-footnote validation
    for fn in talk_footnotes.footnotes:
        warnings.extend(validate_footnote(fn, config))

    # Check sequential numbering across the talk
    _check_sequential_numbering(talk_footnotes.footnotes, warnings)

    # Stats
    total = len(talk_footnotes.footnotes)
    positioned = sum(1 for fn in talk_footnotes.footnotes if fn.char_position != -1)
    position_found_rate = positioned / total if total > 0 else 0.0

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        stats={"total": total, "position_found_rate": position_found_rate},
    )


def _check_sequential_numbering(
    footnotes: List[FootnoteData],
    warnings: List[str],
) -> None:
    """Warn if footnote numbers contain gaps."""
    numbers = [fn.footnote_number for fn in footnotes]
    for i in range(1, len(numbers)):
        if numbers[i] != numbers[i - 1] + 1:
            warnings.append(
                f"Gap in footnote numbering: {numbers[i - 1]} → {numbers[i]}"
            )


# =============================================================================
# Orchestration
# =============================================================================


def process_talk_footnotes(
    talk_id: int,
    paragraphs: List[ParagraphData],
    config: Dict[str, Any],
    contexts: Optional[Dict[int, ParagraphHTMLContext]] = None,
) -> Tuple[TalkFootnotes, List[str]]:
    """
    Full Phase 4 pipeline for a single talk.

    For each paragraph:
      1. Detect footnotes from HTML
      2. Calculate char positions
      3. Extract context windows
      4. Build FootnoteData objects
      5. Update paragraph flags (has_footnote, footnote_count)

    Returns (TalkFootnotes, warnings).
    """
    all_footnotes: List[FootnoteData] = []
    all_warnings: List[str] = []
    errors: List[str] = []

    for paragraph in paragraphs:
        if not paragraph.text_raw:
            continue

        ctx = contexts.get(paragraph.paragraph_id) if contexts else None
        raw_footnotes, fn_warnings = extract_footnotes_from_paragraph(paragraph, config, ctx=ctx)
        all_warnings.extend(fn_warnings)

        if not raw_footnotes:
            continue

        # Update paragraph flags (same pattern as Phase 3)
        paragraph.has_footnote = True
        paragraph.footnote_count = len(raw_footnotes)

        for fn_dict in raw_footnotes:
            element_index = fn_dict["element_index"]
            footnote_number = fn_dict["footnote_number"]
            footnote_text_raw = fn_dict["footnote_text_raw"]

            footnote_id = (
                talk_id * 100000 + paragraph.paragraph_number * 100 + footnote_number
            )
            paragraph_id = talk_id * 10000 + paragraph.paragraph_number

            char_position = calculate_footnote_position(
                paragraph.text_raw, element_index, config
            )
            context_before, context_after, context_window = (
                extract_footnote_context_window(
                    paragraph.text_raw, element_index, footnote_text_raw, config
                )
            )

            try:
                fn_data = FootnoteData(
                    footnote_id=footnote_id,
                    talk_id=talk_id,
                    paragraph_id=paragraph_id,
                    paragraph_number=paragraph.paragraph_number,
                    footnote_number=footnote_number,
                    footnote_text_raw=footnote_text_raw,
                    char_position=char_position,
                    context_before=context_before,
                    context_after=context_after,
                    context_window=context_window,
                )
                all_footnotes.append(fn_data)
            except ValueError as e:
                errors.append(
                    f"Para {paragraph.paragraph_number}, fn {footnote_number}: {e}"
                )

    talk_footnotes = TalkFootnotes(
        talk_id=talk_id,
        footnotes=all_footnotes,
        total_footnotes=len(all_footnotes),
        extraction_success=len(errors) == 0,
        extraction_errors=errors,
    )

    validation_result = validate_talk_footnotes(talk_footnotes, config)
    all_warnings.extend(validation_result.warnings)

    return talk_footnotes, all_warnings
