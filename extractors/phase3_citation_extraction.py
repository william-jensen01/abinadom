"""
Phase 3: Citation Extraction & Parsing

Detects scripture citations in talk HTML, resolves them via the core.52.db
citation/book tables, and produces structured CitationData objects with
context windows — ready for the conference_talk_citations ChromaDB collection.

3-Layer Architecture:
  Layer 1: Database Access  — fetch books cache + citation rows per talk
  Layer 2: Extraction       — HTML detection, DB resolution, verse expansion,
                               position calculation, context windows
  Layer 3: Validation       — single citation, talk level, cross-validation
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup, Tag

from db import Database, Row
from models.citation_data import CitationData, TalkCitations
from models.paragraph_data import ParagraphData, ValidationResult
from extractors.html_parsing_utils import (
    ELEMENT_PLACEHOLDER,
    ParagraphHTMLContext,
    _find_position_anchor,
    _snap_to_word_boundaries,
    filter_paragraph_around_anchor,
    apply_context_window,
    render_span_text,
)

logger = logging.getLogger(__name__)


# =============================================================================
# LAYER 1: Database Access
# =============================================================================


def fetch_all_books(db: Database) -> Dict[int, Row]:
    """
    Load all books from the book table into a cache keyed by book ID.
    Called once at startup — only 99 rows.
    Note: The book table uses 'ID' as the primary key column name.
    """
    rows = db.select("SELECT * FROM book")
    return {row["ID"]: row for row in rows}


def fetch_citations_for_talk(db: Database, talk_id: int) -> List[Row]:
    """
    Fetch all citation rows for a talk from core.52.db.
    Returns rows with ID, TalkID, BookID, Chapter, Verses, MinVerse, MaxVerse.
    """
    return db.select(
        "SELECT * FROM citation WHERE TalkID = ? ORDER BY ID",
        (talk_id,),
    )


# =============================================================================
# LAYER 2: Extraction
# =============================================================================

# --- 2a. HTML Citation Detection ---


def extract_citations_from_paragraph(
    paragraph: ParagraphData,
    config: Dict[str, Any],
    ctx: Optional[ParagraphHTMLContext] = None,
) -> List[Dict[str, Any]]:
    """
    Parse paragraph.text_raw (HTML) and find all <span class="citation" id="X">.

    When *ctx* is provided its cached soup is used for discovery (avoids a
    redundant re-parse).  Mutating operations always use a fresh parse.

    Returns a list of dicts with keys:
        citation_id, display_text, citation_location
    """
    if not paragraph.text_raw:
        return []

    soup = (
        ctx.soup
        if ctx is not None
        else BeautifulSoup(paragraph.text_raw, config.get("html_parser", "html.parser"))
    )
    results = []

    for span in soup.find_all("span", class_="citation"):
        raw_id = span.get("id", "")
        try:
            citation_id = int(raw_id)
        except (ValueError, TypeError):
            logger.warning(
                f"Non-integer citation id '{raw_id}' in paragraph "
                f"{paragraph.paragraph_id} — skipping"
            )
            continue

        # Extract display text with punctuation token rendering
        display_text = render_span_text(span)

        # Determine location: footnote if inside a <span class="footnote"> ancestor
        citation_location = "inline"
        for parent in span.parents:
            if not isinstance(parent, Tag):
                continue
            parent_classes = parent.get("class", [])
            if isinstance(parent_classes, list) and any(
                "footnote" in c for c in parent_classes
            ):
                citation_location = "footnote"
                break

        results.append(
            {
                "citation_id": citation_id,
                "display_text": display_text,
                "citation_location": citation_location,
            }
        )

    if len(results) > config.get("max_citations_per_paragraph_warning", 20):
        logger.warning(
            f"Paragraph {paragraph.paragraph_id} has {len(results)} citations — "
            "unusually high count"
        )

    return results


# --- 2b. DB Resolution ---


def resolve_citation_from_db(
    citation_id: int,
    citation_rows: Dict[int, Row],
    book_cache: Dict[int, Row],
) -> Dict[str, Any]:
    """
    Look up a citation_id in the pre-fetched citation rows and book cache.

    Returns a dict of parsed fields. parse_success=False if not found.
    """
    result: Dict[str, Any] = {
        "scripture_ref": "",
        "book": "",
        "book_abbr": "",
        "book_id": None,
        "chapter": None,
        "verses": "",
        "verse_start": None,
        "verse_end": None,
        "is_jst": False,
        "parse_success": False,
        "parse_source": "",
        "parse_confidence": 0.0,
    }

    citation_row = citation_rows.get(citation_id)
    if citation_row is None:
        logger.debug(f"Citation ID {citation_id} not found in DB rows for this talk")
        return result

    book_id = citation_row.get("BookID")
    chapter = citation_row.get("Chapter")
    verses = citation_row.get("Verses") or ""
    min_verse = citation_row.get("MinVerse")
    max_verse = citation_row.get("MaxVerse")

    book_row = book_cache.get(book_id) if book_id is not None else None
    if book_row is None:
        logger.warning(
            f"BookID {book_id} not found in book cache for citation {citation_id}"
        )
        full_name = ""
        cite_abbr = ""
        is_jst = False
    else:
        full_name = book_row.get("FullName") or ""
        cite_abbr = book_row.get("CiteAbbr") or ""
        is_jst = bool(book_row.get("JSTTitle"))

    # Build normalized scripture_ref
    parts = [full_name]
    if chapter is not None:
        parts.append(str(chapter))
        if verses:
            scripture_ref = f"{full_name} {chapter}:{verses}"
        else:
            scripture_ref = f"{full_name} {chapter}"
    else:
        scripture_ref = full_name

    result.update(
        {
            "scripture_ref": scripture_ref,
            "book": full_name,
            "book_abbr": cite_abbr,
            "book_id": book_id,
            "chapter": chapter,
            "verses": verses,
            "verse_start": min_verse,
            "verse_end": max_verse,
            "is_jst": is_jst,
            "parse_success": True,
            "parse_source": "db_lookup",
            "parse_confidence": 1.0,
        }
    )
    return result


# --- 2c. Verse Expansion ---


def expand_verses(verses_str: str, max_range: int = 200) -> Tuple[List[int], List[str]]:
    """
    Expand a verse string into a list of verse numbers.

    Supported formats:
        "3"          -> [3]
        "3-10"       -> [3,4,...,10]
        "3-10"       -> same (en-dash)
        "3,5,7"      -> [3,5,7]
        "3-5,8,10-12" -> [3,4,5,8,10,11,12]

    Non-numeric parts are skipped and reported in warnings.

    Returns:
        (verse_list, warnings)
    """
    if not verses_str or not verses_str.strip():
        return [], []

    # Normalize en-dash and em-dash to hyphen
    normalized = verses_str.replace("\u2013", "-").replace("\u2014", "-")

    verse_list: List[int] = []
    warnings: List[str] = []

    for part in normalized.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            sub_parts = part.split("-", 1)
            try:
                start = int(sub_parts[0].strip())
                end = int(sub_parts[1].strip())
            except ValueError:
                warnings.append(f"Non-numeric verse range '{part}' skipped")
                continue
            if end - start > max_range:
                warnings.append(
                    f"Verse range '{part}' exceeds max_range={max_range}, clamping"
                )
                end = start + max_range
            verse_list.extend(range(start, end + 1))
        else:
            try:
                verse_list.append(int(part))
            except ValueError:
                warnings.append(f"Non-numeric verse '{part}' skipped")

    return verse_list, warnings


# --- 2d. Position Calculation ---


def calculate_citation_position(
    text_raw: str,
    citation_id: int,
    display_text: str,
    config: Dict[str, Any],
) -> Tuple[int, int]:
    """
    Find the start char position of a citation in the paragraph using its
    HTML id attribute (not text matching).

    Locates the citation's position anchor — the topmost ancestor element
    below the paragraph root — replaces it with a placeholder, then finds the
    placeholder's offset in the resulting text.  This correctly handles all
    nesting patterns (direct, ccontainer, footnote noteMarker) and avoids
    false matches when the same scripture reference appears multiple times.

    Returns (char_start, char_end) where char_end is approximate
    (char_start + len(display_text)).  Returns (-1, -1) if not found.
    """
    if not text_raw:
        return -1, -1

    parser = config.get("html_parser", "html.parser")
    filtered, extracted_display = _build_filtered_paragraph(
        text_raw, citation_id, parser
    )

    pos = filtered.find(ELEMENT_PLACEHOLDER)
    if pos == -1:
        return -1, -1

    label = display_text or extracted_display
    return pos, pos + len(label)


# --- 2e. Context Windows ---


# ELEMENT_PLACEHOLDER, _find_position_anchor, _snap_to_word_boundaries
# are now imported from extractors.html_parsing_utils.


def _build_filtered_paragraph(
    text_raw: str,
    citation_id: int,
    parser: str = "html.parser",
) -> Tuple[str, str]:
    """
    Build paragraph text filtered for position and context extraction.

    Finds the target citation by its unique span id, walks up to its topmost
    ancestor below the paragraph root (the position anchor), replaces the
    anchor with a placeholder, then removes any remaining
    <sup class="noteMarker"> elements.

    Replacing the anchor (not just the citation span) ensures that footnote
    citations use the noteMarker's position, and that the placeholder is never
    accidentally removed when noteMarkers are decomposed.

    Returns (filtered_text, display_text) where display_text is the original
    text content of the target citation span (empty string if not found).
    """
    soup = BeautifulSoup(text_raw, parser)

    target_span = soup.find("span", class_="citation", id=str(citation_id))
    display_text = ""
    if target_span:
        display_text = target_span.get_text(strip=True)
        anchor = _find_position_anchor(target_span)
        filtered = filter_paragraph_around_anchor(soup, anchor, ELEMENT_PLACEHOLDER)
    else:
        for marker in soup.find_all("sup", class_="noteMarker"):
            marker.decompose()
        filtered = soup.get_text(strip=True)

    return filtered, display_text


def extract_context_window(
    clean_text: str,
    char_start: int,
    char_end: int,
    config: Dict[str, Any],
    text_raw: Optional[str] = None,
    citation_id: Optional[int] = None,
    display_text: str = "",
) -> Tuple[str, str, str]:
    """
    Extract context_before, context_after, and combined context_window.

    When text_raw and citation_id are provided, builds a filtered version of
    the paragraph text: the target citation is replaced with a placeholder,
    and all <sup class="noteMarker"> footnote references are removed.  The
    placeholder's position anchors the context window so footnote content
    never leaks into context_before or context_after.

    display_text is used only to assemble the final context_window string; it
    is not used for searching, so duplicate scripture references in the same
    paragraph are handled correctly.

    config["context_window_mode"] controls boundary behaviour:
        "char" (default) — hard character limit (original behaviour)
        "word"            — snap to nearest whole word within the char limit

    Returns ("", "", "") if position is invalid.
    """
    if char_start < 0 or char_end < 0 or not clean_text:
        return "", "", ""

    before_chars = config.get("context_before_chars", 100)
    after_chars = config.get("context_after_chars", 100)
    word_mode = config.get("context_window_mode", "char") == "word"

    # Use filtered text when available so footnote content is excluded.
    if text_raw and citation_id is not None:
        parser = config.get("html_parser", "html.parser")
        filtered, extracted_display = _build_filtered_paragraph(
            text_raw, citation_id, parser
        )
        citation_label = display_text or extracted_display
        result = apply_context_window(
            filtered, ELEMENT_PLACEHOLDER, citation_label, config
        )
        if result != ("", "", ""):
            return result

    # Fallback: use original clean text (no filtering)
    before_start = max(0, char_start - before_chars)
    after_end = min(len(clean_text), char_end + after_chars)

    context_before = clean_text[before_start:char_start]
    context_after = clean_text[char_end:after_end]
    citation_text = clean_text[char_start:char_end]
    if word_mode:
        context_before, context_after = _snap_to_word_boundaries(
            context_before,
            context_after,
            before_truncated=before_start > 0,
            after_truncated=after_end < len(clean_text),
        )
    context_window = context_before + citation_text + context_after

    return context_before, context_after, context_window


# =============================================================================
# LAYER 3: Validation
# =============================================================================


def validate_citation(citation: CitationData, config: Dict[str, Any]) -> List[str]:
    """
    Validate a single CitationData object.

    Returns a list of warning/error strings (empty = valid).
    """
    issues: List[str] = []

    if not citation.citation_text_raw:
        issues.append(f"Citation {citation.citation_id}: empty display text")

    if citation.char_position != -1:
        if citation.char_position < 0:
            issues.append(f"Citation {citation.citation_id}: invalid char_position")
        if citation.char_end_position <= citation.char_position:
            issues.append(f"Citation {citation.citation_id}: char_end <= char_start")

    max_range = config.get("max_verse_range", 200)
    if (
        citation.verse_start is not None
        and citation.verse_end is not None
        and citation.verse_end - citation.verse_start > max_range
    ):
        issues.append(
            f"Citation {citation.citation_id}: verse range "
            f"{citation.verse_start}-{citation.verse_end} exceeds max {max_range}"
        )

    return issues


def validate_talk_citations(
    talk_citations: TalkCitations, config: Dict[str, Any]
) -> ValidationResult:
    """
    Validate all citations for a talk.

    Returns a ValidationResult with errors, warnings, and stats.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Check for duplicate citation IDs (same span appearing multiple times is OK)
    id_counts: Dict[int, int] = {}
    for c in talk_citations.citations:
        id_counts[c.citation_id] = id_counts.get(c.citation_id, 0) + 1

    # Parse success rate
    if talk_citations.citations:
        success_count = sum(1 for c in talk_citations.citations if c.parse_success)
        success_rate = success_count / len(talk_citations.citations)
        if success_rate < 0.8:
            warnings.append(
                f"Low parse success rate: {success_rate:.1%} "
                f"({success_count}/{len(talk_citations.citations)})"
            )
    else:
        success_rate = 1.0

    # Individual citation validation
    for citation in talk_citations.citations:
        issues = validate_citation(citation, config)
        warnings.extend(issues)

    stats = {
        "total_citations": talk_citations.total_citations,
        "parse_success_rate": success_rate,
        "inline_count": sum(
            1 for c in talk_citations.citations if c.citation_location == "inline"
        ),
        "footnote_count": sum(
            1 for c in talk_citations.citations if c.citation_location == "footnote"
        ),
        "jst_count": sum(1 for c in talk_citations.citations if c.is_jst),
    }

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        stats=stats,
    )


def cross_validate_with_db(
    talk_id: int,
    extracted_ids: List[int],
    db_ids: List[int],
) -> List[str]:
    """
    Compare HTML-extracted citation IDs vs DB expected citation IDs.

    Returns list of discrepancy messages.
    """
    issues: List[str] = []

    extracted_set = set(extracted_ids)
    db_set = set(db_ids)

    in_html_not_db = extracted_set - db_set
    in_db_not_html = db_set - extracted_set

    if in_html_not_db:
        issues.append(
            f"Talk {talk_id}: {len(in_html_not_db)} citation IDs in HTML but not in DB: "
            f"{sorted(in_html_not_db)[:10]}"
        )
    if in_db_not_html:
        issues.append(
            f"Talk {talk_id}: {len(in_db_not_html)} citation IDs in DB but not in HTML: "
            f"{sorted(in_db_not_html)[:10]}"
        )

    return issues


# =============================================================================
# ORCHESTRATION
# =============================================================================


def process_talk_citations(
    core_db_instance: Database,
    talk_id: int,
    paragraphs: List[ParagraphData],
    book_cache: Dict[int, Row],
    config: Dict[str, Any],
    contexts: Optional[Dict[int, ParagraphHTMLContext]] = None,
) -> Tuple[TalkCitations, List[str]]:
    """
    Full pipeline for a single talk.

    Pipeline:
    1. Fetch all citation DB rows for this talk
    2. For each ParagraphData: scan text_raw for <span class="citation"> tags
    3. For each citation: resolve via DB, calculate position, extract context
    4. Build CitationData objects
    5. Validate + cross-validate
    6. Update paragraph flags (has_scripture_citation, citation_count)

    Returns:
        (TalkCitations, cross_validation_warnings)
    """
    all_warnings: List[str] = []

    # Step 1: Fetch citation rows for this talk
    citation_rows_list = fetch_citations_for_talk(core_db_instance, talk_id)
    citation_rows: Dict[int, Row] = {row["ID"]: row for row in citation_rows_list}
    db_citation_ids = list(citation_rows.keys())

    # Step 2 & 3: Process each paragraph
    all_citations: List[CitationData] = []
    extracted_citation_ids: List[int] = []

    for paragraph in paragraphs:
        if not paragraph.text_raw:
            continue

        ctx = contexts.get(paragraph.paragraph_id) if contexts else None
        raw_citations = extract_citations_from_paragraph(paragraph, config, ctx=ctx)
        if not raw_citations:
            continue

        para_citation_count = 0

        for raw in raw_citations:
            citation_id = raw["citation_id"]
            display_text = raw["display_text"]
            citation_location = raw["citation_location"]
            extracted_citation_ids.append(citation_id)

            # Resolve via DB
            parsed = resolve_citation_from_db(citation_id, citation_rows, book_cache)

            # Expand verses
            verse_list: List[int] = []
            if parsed["verses"]:
                verse_list, verse_warnings = expand_verses(
                    parsed["verses"], config.get("max_verse_range", 200)
                )
                all_warnings.extend(verse_warnings)

            # Calculate position
            char_start, char_end = calculate_citation_position(
                paragraph.text_raw, citation_id, display_text, config
            )

            # Extract context window
            context_before, context_after, context_window = extract_context_window(
                paragraph.text,
                char_start,
                char_end,
                config,
                text_raw=paragraph.text_raw,
                citation_id=citation_id,
                display_text=display_text,
            )

            # Regex fallback if DB lookup failed
            parse_pattern = ""
            if not parsed["parse_success"]:
                fallback = _regex_fallback(display_text)
                if fallback:
                    parsed.update(fallback)
                    all_warnings.append(
                        f"Citation {citation_id}: used regex fallback for '{display_text}'"
                    )

            try:
                citation = CitationData(
                    citation_id=citation_id,
                    talk_id=talk_id,
                    paragraph_id=paragraph.paragraph_id,
                    paragraph_number=paragraph.paragraph_number,
                    citation_text_raw=display_text,
                    char_position=char_start,
                    char_end_position=char_end,
                    scripture_ref=parsed["scripture_ref"],
                    book=parsed["book"],
                    book_abbr=parsed["book_abbr"],
                    book_id=parsed["book_id"],
                    chapter=parsed["chapter"],
                    verses=parsed["verses"],
                    verse_start=parsed["verse_start"],
                    verse_end=parsed["verse_end"],
                    verse_list=verse_list,
                    is_jst=parsed["is_jst"],
                    citation_location=citation_location,
                    parse_success=parsed["parse_success"],
                    parse_source=parsed["parse_source"],
                    parse_pattern=parse_pattern,
                    parse_confidence=parsed["parse_confidence"],
                    context_before=context_before,
                    context_after=context_after,
                    context_window=context_window,
                )
                all_citations.append(citation)
                para_citation_count += 1
            except Exception as e:
                all_warnings.append(
                    f"Failed to create CitationData for ID {citation_id}: {e}"
                )

        # Step 6: Update paragraph flags
        if para_citation_count > 0:
            paragraph.has_scripture_citation = True
            paragraph.citation_count = para_citation_count

    # Step 5: Cross-validate
    cv_warnings = cross_validate_with_db(
        talk_id, extracted_citation_ids, db_citation_ids
    )
    all_warnings.extend(cv_warnings)

    talk_citations = TalkCitations(
        talk_id=talk_id,
        citations=all_citations,
        total_citations=len(all_citations),
        extraction_success=True,
        extraction_errors=[],
    )

    return talk_citations, all_warnings


def _regex_fallback(display_text: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to parse a citation reference using regex when DB lookup fails.

    Returns a partial parsed dict or None if regex also fails.
    """
    # Simple pattern: BookName Chapter:Verse
    pattern = re.compile(
        r"^(?P<book>.+?)\s+(?P<chapter>\d+)(?::(?P<verses>[\d,\-\u2013]+))?$"
    )
    m = pattern.match(display_text.strip())
    if not m:
        return None

    book = m.group("book").strip()
    chapter = int(m.group("chapter"))
    verses = m.group("verses") or ""
    scripture_ref = f"{book} {chapter}"
    if verses:
        scripture_ref += f":{verses}"

    return {
        "scripture_ref": scripture_ref,
        "book": book,
        "book_abbr": book,
        "book_id": None,
        "chapter": chapter,
        "verses": verses,
        "verse_start": None,
        "verse_end": None,
        "is_jst": False,
        "parse_success": True,
        "parse_source": "regex_fallback",
        "parse_confidence": 0.6,
    }
