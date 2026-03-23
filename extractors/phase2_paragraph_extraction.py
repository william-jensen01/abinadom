"""
Phase 2: Paragraph Segmentation

Extracts paragraphs from talk HTML and prepares structured data for ChromaDB insertion.

This module implements a layered architecture:
- Database Layer: Fetch HTML content from database
- Extraction Layer: Parse HTML, extract paragraphs, calculate metrics
- Validation Layer: Data quality assurance

All extraction functions are pure (no side effects) and composable.
"""

import copy
import logging
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from bs4 import BeautifulSoup, Tag, NavigableString

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from db import content_db, Database
from models.paragraph_data import (
    ParagraphData,
    TalkParagraphs,
    ValidationResult,
)
from config.schemas import PARAGRAPH_CONFIG
from extractors.html_parsing_utils import (
    parse_html,
    find_body_container,
    render_span_text,
)

logger = logging.getLogger(__name__)


def _element_clean_text(element: Tag) -> str:
    """Return element text with noteMarker sups removed and inline spans normalized.

    Uses separator="" so that adjacent inline spans (e.g. <span class="emphasis">Z</span>
    <span class="small">ION</span>) concatenate without an injected space — the HTML
    text nodes already carry all necessary whitespace.

    Each ccontainer span is rendered via render_span_text() (which applies punctuation
    from the span's CSS classes) and replaced with its plain-text equivalent in the
    tree before the final get_text() call.

    The &nbsp; from sx() anchors provides the spacing before citations (e.g. '."  (Moses
    7:18.)'); render_span_text strips it, so we restore it as a leading non-breaking
    space on the replacement text when an sx anchor was present.
    """
    elem_copy = copy.deepcopy(element)

    # Remove noteMarker sups
    for marker in elem_copy.find_all(class_="noteMarker"):
        marker.decompose()

    # Render each ccontainer span (applies lparen/rdotparen punctuation etc.)
    # and replace it with its plain-text equivalent so get_text() sees it correctly.
    for ccontainer in elem_copy.find_all("span", class_="ccontainer"):
        # Detect whether an sx() anchor (whose &nbsp; provides pre-citation spacing)
        # is present — render_span_text removes it, so we restore the space manually.
        sx = ccontainer.find("a", onclick=lambda v: v and "sx(" in v)
        rendered = render_span_text(ccontainer)
        if sx is not None:
            rendered = "\u00a0" + rendered  # restore &nbsp; spacing
        ccontainer.replace_with(NavigableString(rendered))

    # strip=False preserves whitespace within text nodes; final .strip() cleans edges.
    text = elem_copy.get_text(separator="", strip=False)
    text = text.replace("\u00a0", " ")  # &nbsp; → regular space
    return text.strip()


# =============================================================================
# DATABASE LAYER - Data Access
# =============================================================================


def fetch_talk_html(db: Database, talk_id: int) -> Optional[str]:
    """
    Fetch raw HTML content for a single talk.

    Args:
        db: Database instance
        talk_id: Talk identifier

    Returns:
        HTML string or None if not found
    """
    logger.debug(f"Fetching HTML for talk ID {talk_id}")

    # Try TextRaw first (raw HTML content)
    row = db.select_one("SELECT TextRaw FROM talkbody WHERE TalkID = ?", (talk_id,))

    if not row:
        logger.warning(f"No HTML found for talk ID {talk_id}")
        return None

    html = row.get("TextRaw")
    if html and html.strip():
        logger.debug(f"Retrieved {len(html)} chars of HTML for talk ID {talk_id}")
        return html

    # Fallback to TextSimple if TextRaw is empty
    row = db.select_one("SELECT TextSimple FROM talkbody WHERE TalkID = ?", (talk_id,))
    if row:
        text = row.get("TextSimple")
        if text and text.strip():
            # Wrap plain text in paragraph tags for consistent processing
            html = f"<div>{text}</div>"
            logger.debug(
                f"Using TextSimple (wrapped) for talk ID {talk_id}: {len(html)} chars"
            )
            return html

    logger.warning(f"No usable content found for talk ID {talk_id}")
    return None


def fetch_talks_html_batch(db: Database, talk_ids: List[int]) -> Dict[int, str]:
    """
    Fetch HTML for multiple talks efficiently.

    Args:
        db: Database instance
        talk_ids: List of talk identifiers

    Returns:
        Dict mapping talk_id -> HTML string
    """
    if not talk_ids:
        return {}

    logger.info(f"Fetching HTML for {len(talk_ids)} talks")

    # Build query with placeholders
    placeholders = ",".join("?" * len(talk_ids))
    query = f"SELECT TalkID, TextRaw FROM talkbody WHERE TalkID IN ({placeholders})"

    rows = db.select(query, talk_ids)

    result = {}
    for row in rows:
        talk_id = row["TalkID"]
        html = row.get("TextRaw")
        if html and html.strip():
            result[talk_id] = html

    logger.info(f"Retrieved HTML for {len(result)}/{len(talk_ids)} talks")
    return result


def fetch_all_talk_ids(db: Database) -> List[int]:
    """Get all talk IDs that have content."""
    logger.info("Fetching all talk IDs with content")

    rows = db.select(
        """
        SELECT TalkID
        FROM talkbody
        WHERE TextRaw IS NOT NULL OR TextSimple IS NOT NULL
        ORDER BY TalkID
        """
    )

    talk_ids = [row["TalkID"] for row in rows]
    logger.info(f"Found {len(talk_ids)} talks with content")
    return talk_ids


# =============================================================================
# EXTRACTION LAYER - Semantic Unit Extraction
# =============================================================================


def extract_stanza_text(stanza_element: Tag) -> str:
    """
    Extract text from a stanza element (poetry/quotation).

    Combines all div.line children and any following div.citationInfo
    into a single text block.

    Args:
        stanza_element: div.stanza element

    Returns:
        Combined text with lines separated by newlines
    """
    if not stanza_element:
        return ""

    # Work on a cleaned copy so noteMarkers don't leak into stanza text
    stanza_copy = copy.deepcopy(stanza_element)
    for marker in stanza_copy.find_all(class_="noteMarker"):
        marker.decompose()

    text_parts = []

    # Extract all lines
    lines = stanza_copy.find_all(["p", "div"], class_="line")
    for line in lines:
        line_text = line.get_text(separator=" ", strip=True)
        if line_text:
            text_parts.append(line_text)

    # Extract citation info if present
    citation = stanza_copy.find("div", class_="citationInfo")
    if citation:
        citation_text = citation.get_text(separator=" ", strip=True)
        if citation_text:
            text_parts.append(f"— {citation_text}")

    return "\n".join(text_parts)


def extract_list_item_header(li_element: Tag) -> Optional[str]:
    """
    Extract header from list item using priority rules.

    Priority:
    1. h2 or h3 tags
    2. b or strong tags (if no heading)
    3. span.label (only if no text header)

    Args:
        li_element: li element

    Returns:
        Cleaned header text or None
    """
    if not li_element:
        return None

    # Priority 1: Check for h2 or h3
    for heading_tag in ["h2", "h3"]:
        heading = li_element.find(heading_tag)
        if heading:
            header_text = heading.get_text(separator=" ", strip=True)
            if header_text:
                # Clean: remove trailing punctuation
                header_text = header_text.rstrip(":.")
                return header_text

    # Priority 2: Check for b or strong
    for bold_tag in ["b", "strong"]:
        bold = li_element.find(bold_tag)
        if bold:
            header_text = bold.get_text(separator=" ", strip=True)
            if header_text:
                # Clean: remove trailing punctuation
                header_text = header_text.rstrip(":.")
                return header_text

    # Priority 3: Check for span.label (numeric fallback)
    label = li_element.find("span", class_="label")
    if label:
        label_text = label.get_text(separator=" ", strip=True)
        if label_text:
            # Clean: remove trailing punctuation
            label_text = label_text.rstrip(":.")
            return label_text

    return None


def build_prefixed_text(header: Optional[str], content: str) -> str:
    """
    Combine header and content with proper formatting.

    Args:
        header: Header text (None if no header)
        content: Paragraph content

    Returns:
        Formatted text with prefix if applicable
    """
    if not header:
        return content

    # Check if content already starts with the header to avoid duplication
    if content.startswith(f"{header}:"):
        return content

    return f"{header}: {content}"


def extract_stanza_in_list(stanza_element: Tag, processed_elements: set) -> str:
    """
    Extract stanza text when it appears inside a list item.
    Collapses lines with ' / ' delimiter.

    Args:
        stanza_element: div.stanza element
        processed_elements: Set to track processed elements

    Returns:
        Collapsed stanza text
    """
    if not stanza_element:
        return ""

    text_parts = []

    # Work on a cleaned copy for text extraction; track originals for processed set
    stanza_copy = copy.deepcopy(stanza_element)
    for marker in stanza_copy.find_all(class_="noteMarker"):
        marker.decompose()

    for line_copy in stanza_copy.find_all("div", class_="line"):
        line_text = line_copy.get_text(separator=" ", strip=True)
        if line_text:
            text_parts.append(line_text)

    # Mark original lines as processed
    for line in stanza_element.find_all("div", class_="line"):
        processed_elements.add(line)

    # Join with ' / ' delimiter
    stanza_text = " / ".join(text_parts)

    # Check for sibling citation
    next_sibling = stanza_element.find_next_sibling()
    if next_sibling and isinstance(next_sibling, Tag):
        if next_sibling.name == "div" and "citationInfo" in next_sibling.get(
            "class", []
        ):
            # Get citation text from nested <p> if present
            citation_p = next_sibling.find("p")
            if citation_p:
                citation_text = citation_p.get_text(separator=" ", strip=True)
            else:
                citation_text = next_sibling.get_text(separator=" ", strip=True)

            if citation_text:
                stanza_text = stanza_text + " / " + citation_text

            # Mark citation as processed
            processed_elements.add(next_sibling)
            for child in next_sibling.descendants:
                if isinstance(child, Tag):
                    processed_elements.add(child)

    # Mark stanza and all its children as processed
    processed_elements.add(stanza_element)
    for child in stanza_element.descendants:
        if isinstance(child, Tag):
            processed_elements.add(child)

    return stanza_text


def extract_list_item_paragraphs(
    li_element: Tag,
    header: Optional[str],
    list_item_index: int,
    processed_elements: set,
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Extract all paragraphs from a single list item.
    Handles nested stanzas and multiple paragraphs.

    Args:
        li_element: li element
        header: Extracted header text (None if no header)
        list_item_index: Position of this li in parent list (1-indexed)
        processed_elements: Set to track processed elements
        config: Extraction configuration

    Returns:
        List of paragraph dicts with text, list_header, list_item_index, position_in_item
    """
    if not li_element:
        return []

    paragraphs = []
    position_in_item = 1

    # Find all paragraphs and stanzas in this list item
    # We need to traverse in document order
    for element in li_element.descendants:
        if element in processed_elements:
            continue

        if not isinstance(element, Tag):
            continue

        # Handle <p> elements
        if element.name == "p":
            # Skip if already processed
            if element in processed_elements:
                continue

            # Extract text (noteMarkers stripped via deepcopy)
            text = _element_clean_text(element)

            # Skip empty paragraphs
            if not text or len(text) < config.get("min_paragraph_length", 10):
                processed_elements.add(element)
                continue

            # Build prefixed text
            prefixed_text = build_prefixed_text(header, text)

            # Create paragraph dict
            paragraphs.append(
                {
                    "text": prefixed_text,
                    "text_raw": str(element),
                    "list_header": header,
                    "list_item_index": list_item_index,
                    "position_in_item": position_in_item,
                }
            )

            position_in_item += 1
            processed_elements.add(element)

        # Handle stanza elements
        elif element.name == "div" and "stanza" in element.get("class", []):
            # Skip if already processed
            if element in processed_elements:
                continue

            # Extract stanza (collapses lines with ' / ')
            stanza_text = extract_stanza_in_list(element, processed_elements)

            # Skip empty stanzas
            if not stanza_text or len(stanza_text) < config.get(
                "min_paragraph_length", 10
            ):
                continue

            # Build prefixed text
            prefixed_text = build_prefixed_text(header, stanza_text)

            # Create paragraph dict
            paragraphs.append(
                {
                    "text": prefixed_text,
                    "text_raw": str(element),
                    "list_header": header,
                    "list_item_index": list_item_index,
                    "position_in_item": position_in_item,
                }
            )

            position_in_item += 1

    # Fallback: if no paragraphs extracted, try bare text content of li directly.
    # Handles <li>text content</li> without a wrapping <p>.
    if not paragraphs:
        text = _element_clean_text(li_element)
        if text and len(text) >= config.get("min_paragraph_length", 10):
            prefixed_text = build_prefixed_text(header, text)
            paragraphs.append(
                {
                    "text": prefixed_text,
                    "text_raw": str(li_element),
                    "list_header": header,
                    "list_item_index": list_item_index,
                    "position_in_item": 1,
                }
            )

    return paragraphs


def extract_list(
    list_element: Tag, processed_elements: set, config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extract paragraphs from <ol> or <ul>.

    Each <p> inside a list item becomes its own paragraph with context.

    Args:
        list_element: BeautifulSoup Tag for the list (ol or ul)
        processed_elements: Set to track processed elements
        config: Extraction configuration

    Returns:
        List of paragraph dicts with text, list_header, list_item_index, position_in_item
    """
    if not list_element:
        return []

    paragraphs = []
    list_item_index = 1

    # Handle <p class="preamble"> as a direct non-li child of the list element
    for preamble in list_element.find_all("p", class_="preamble", recursive=False):
        preamble_text = _element_clean_text(preamble)
        if preamble_text and len(preamble_text) >= config.get("min_paragraph_length", 10):
            paragraphs.append(
                {
                    "text": preamble_text,
                    "text_raw": str(preamble),
                    "source_type": "p",
                    "list_header": None,
                    "list_item_index": None,
                    "position_in_item": None,
                }
            )
        processed_elements.add(preamble)

    # Find all direct <li> children
    for li in list_element.find_all("li", recursive=False):
        if li in processed_elements:
            continue

        # Extract header for this list item
        header = extract_list_item_header(li)

        # Extract all paragraphs from this list item
        li_paragraphs = extract_list_item_paragraphs(
            li, header, list_item_index, processed_elements, config
        )

        paragraphs.extend(li_paragraphs)

        # Mark list item as processed
        processed_elements.add(li)

        list_item_index += 1

    return paragraphs


def should_skip_element(element: Tag) -> bool:
    """
    Determine if an element should be skipped during extraction.

    Skip criteria:
    - Empty paragraphs
    - blockquote.intro
    - Headers (h1-h6)
    - Navigation elements

    Args:
        element: Element to check

    Returns:
        True if element should be skipped
    """
    if not element or not isinstance(element, Tag):
        return True

    # Skip reference-related divs
    if element.name == "div" and element.get("id") in (
        "showreferences",
        "hidereferences",
        "references",
    ):
        return True

    # Skip specific classes
    if element.get("class"):
        classes = element.get("class")
        if "intro" in classes and element.name == "blockquote":
            return True
        # Skip captions within figures
        if "caption" in classes and element.name == "div":
            parent = element.find_parent("div", class_="figure")
            if parent is not None:
                return True

    # Skip headers
    if element.name in ["h1", "h2", "h3", "h4", "h5", "h6", "header"]:
        return True

    # Skip if empty
    text = element.get_text(separator=" ", strip=True)
    if not text:
        return True

    return False


def is_container_element(element: Tag) -> bool:
    """
    Determine if element is a container (descend into it) vs semantic unit.

    Containers: div.figure, section, generic wrappers
    Semantic units: div.stanza, li, p

    Args:
        element: Element to check

    Returns:
        True if element is a container (should descend)
    """
    if not element or not isinstance(element, Tag):
        return False

    # Check for known containers
    if element.name == "section":
        return True

    if element.name == "div":
        classes = element.get("class", [])
        # stanza is a semantic unit handled separately
        if "stanza" in classes:
            return False
        if "figure" in classes:
            return True

    return False


def extract_semantic_paragraphs(
    container: Tag, config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extract semantic paragraph units from body container.

    Identifies and extracts:
    1. Stanzas (div.stanza) - collapsed with citation
    2. Lists (ol/ul) - each <p> becomes separate paragraph with context
    3. Standard paragraphs (p)
    4. Bare text (direct text nodes in container)

    Args:
        container: Body container element
        config: Extraction configuration

    Returns:
        List of paragraph dicts with keys:
        - text: paragraph text
        - source_type: 'stanza', 'list', 'p', or 'bare'
        - list_header: Optional[str] (only for list items)
        - list_item_index: Optional[int] (only for list items)
        - position_in_item: Optional[int] (only for list items)
    """
    if not container:
        return []

    paragraphs = []
    processed_elements = set()  # Track processed elements to avoid duplicates

    def process_element(element, depth=0):
        """Recursively process elements, tracking processed ones."""
        if element in processed_elements:
            return

        if not isinstance(element, Tag):
            return

        # Skip elements we shouldn't process
        if should_skip_element(element):
            processed_elements.add(element)
            return

        # Handle semantic units
        if element.name == "div" and "stanza" in element.get("class", []):
            # Stanza: collapse all lines + citation
            text = extract_stanza_text(element)
            # Check for sibling citation element
            next_sibling = element.find_next_sibling()
            if next_sibling and isinstance(next_sibling, Tag):
                if next_sibling.name == "div" and "citationInfo" in next_sibling.get(
                    "class", []
                ):
                    citation_text = next_sibling.get_text(separator=" ", strip=True)
                    if citation_text:
                        text = (
                            text + "\n" + f"— {citation_text}"
                            if text
                            else f"— {citation_text}"
                        )
                    # Mark citation as processed so it doesn't become a separate paragraph
                    processed_elements.add(next_sibling)

            if text and len(text) >= config.get("min_paragraph_length", 10):
                paragraphs.append(
                    {
                        "text": text,
                        "text_raw": str(element),
                        "source_type": "stanza",
                        "list_header": None,
                        "list_item_index": None,
                        "position_in_item": None,
                    }
                )
            processed_elements.add(element)
            # Mark all children as processed
            for child in element.descendants:
                if isinstance(child, Tag):
                    processed_elements.add(child)
            return

        elif element.name in ["ol", "ul"]:
            # List: extract each <p> as separate paragraph with context
            list_paragraphs = extract_list(element, processed_elements, config)
            for para_dict in list_paragraphs:
                # Add source_type to the dict
                para_dict["source_type"] = "list"
                paragraphs.append(para_dict)
            processed_elements.add(element)
            return

        elif element.name == "p":
            # Standard paragraph
            text = _element_clean_text(element)
            if text and len(text) >= config.get("min_paragraph_length", 10):
                paragraphs.append(
                    {
                        "text": text,
                        "text_raw": str(element),
                        "source_type": "p",
                        "list_header": None,
                        "list_item_index": None,
                        "position_in_item": None,
                    }
                )
            processed_elements.add(element)
            return

        elif element.name == "table" and element.find_parent("div", class_="figure"):
            # Table inside a figure: treat the whole table as one paragraph.
            # Rows are joined with newlines; cells within a row with " | ".
            rows = []
            for tr in element.find_all("tr"):
                cells = [
                    td.get_text(separator=" ", strip=True)
                    for td in tr.find_all(["td", "th"])
                ]
                row_text = " | ".join(c for c in cells if c)
                if row_text:
                    rows.append(row_text)
            text = "\n".join(rows)
            if text and len(text) >= config.get("min_paragraph_length", 10):
                paragraphs.append(
                    {
                        "text": text,
                        "text_raw": str(element),
                        "source_type": "table",
                        "list_header": None,
                        "list_item_index": None,
                        "position_in_item": None,
                    }
                )
            processed_elements.add(element)
            for child in element.descendants:
                if isinstance(child, Tag):
                    processed_elements.add(child)
            return

        elif element.name == "div" and "annotation" in element.get("class", []):
            # Annotation: publisher/editorial note attached to the talk.
            # Emitted as a paragraph so citations inside flow through Phase 3.
            # Phase 6 folds annotation paragraphs into talk-level metadata and
            # excludes them from conference_talk_paragraphs embeddings.
            text = _element_clean_text(element)
            if text and len(text) >= config.get("min_paragraph_length", 10):
                paragraphs.append(
                    {
                        "text": text,
                        "text_raw": str(element),
                        "source_type": "annotation",
                        "list_header": None,
                        "list_item_index": None,
                        "position_in_item": None,
                    }
                )
            processed_elements.add(element)
            for child in element.descendants:
                if isinstance(child, Tag):
                    processed_elements.add(child)
            return

        elif element.name == "div" and "figure" in element.get("class", []):
            # A figure with stanzas: join all stanzas into one paragraph so the
            # shared citationInfo is attached to the whole poem/hymn.
            # A figure without stanzas (e.g. a table figure): descend normally.
            stanza_elements = element.find_all("div", class_="stanza")
            if stanza_elements:
                text_parts = []
                # Prepend figure title if present
                title = element.find(["h2", "h3"])
                if title:
                    title_text = title.get_text(separator=" ", strip=True)
                    if title_text:
                        text_parts.append(title_text)
                for stanza in stanza_elements:
                    stanza_text = extract_stanza_text(stanza)
                    if stanza_text:
                        text_parts.append(stanza_text)
                # Attach shared citation found at the figure level
                citation = element.find("div", class_="citationInfo")
                if citation:
                    citation_text = citation.get_text(separator=" ", strip=True)
                    if citation_text:
                        text_parts.append(f"— {citation_text}")
                text = "\n".join(text_parts)
                if text and len(text) >= config.get("min_paragraph_length", 10):
                    paragraphs.append(
                        {
                            "text": text,
                            "text_raw": str(element),
                            "source_type": "stanza",
                            "list_header": None,
                            "list_item_index": None,
                            "position_in_item": None,
                        }
                    )
                processed_elements.add(element)
                for child in element.descendants:
                    if isinstance(child, Tag):
                        processed_elements.add(child)
            else:
                # No stanzas — check for any ol/ul inside the figure.
                list_element = element.find(["ol", "ul"])
                if list_element:
                    # Collect trailing text/elements that appear after the list
                    trailing_parts = []
                    found_list = False
                    for node in element.children:
                        if node is list_element:
                            found_list = True
                            continue
                        if not found_list:
                            continue
                        if isinstance(node, NavigableString):
                            t = re.sub(r"\s+", " ", str(node)).strip()
                            if t:
                                trailing_parts.append(t)
                        elif isinstance(node, Tag):
                            t = _element_clean_text(node)
                            if t:
                                trailing_parts.append(t)
                    trailing_text = " ".join(trailing_parts)

                    # Emit preamble siblings (elements before the list) as own paragraphs
                    for node in element.children:
                        if node is list_element:
                            break
                        if isinstance(node, Tag):
                            t = _element_clean_text(node)
                            if t and len(t) >= config.get("min_paragraph_length", 10):
                                paragraphs.append(
                                    {
                                        "text": t,
                                        "text_raw": str(node),
                                        "source_type": "p",
                                        "list_header": None,
                                        "list_item_index": None,
                                        "position_in_item": None,
                                    }
                                )

                    # Emit list items as own paragraphs; append trailing text to last item
                    list_paragraphs = extract_list(list_element, processed_elements, config)
                    for i, para_dict in enumerate(list_paragraphs):
                        para_dict["source_type"] = "list"
                        if trailing_text and i == len(list_paragraphs) - 1:
                            para_dict["text"] = para_dict["text"] + "\n" + trailing_text
                        paragraphs.append(para_dict)

                    processed_elements.add(element)
                    for child in element.descendants:
                        if isinstance(child, Tag):
                            processed_elements.add(child)
                else:
                    # No stanzas, no list — treat as container (e.g., figure with a table)
                    processed_elements.add(element)
                    for child in element.children:
                        process_element(child, depth + 1)
            return

        # Container elements - descend into them
        elif is_container_element(element):
            processed_elements.add(element)
            for child in element.children:
                process_element(child, depth + 1)
            return

        # For other elements, check if they have text and no semantic children
        else:
            # Check if this element contains any semantic units
            has_semantic_children = bool(
                element.find("div", class_="stanza")
                or element.find("ol")
                or element.find("ul")
                or element.find("p")
            )

            if not has_semantic_children:
                # No semantic children, treat as bare text if it has content
                text = _element_clean_text(element)
                if text and len(text) >= config.get("min_paragraph_length", 10):
                    paragraphs.append(
                        {
                            "text": text,
                            "text_raw": str(element),
                            "source_type": "bare",
                            "list_header": None,
                            "list_item_index": None,
                            "position_in_item": None,
                        }
                    )
                processed_elements.add(element)
            else:
                # Has semantic children, descend
                processed_elements.add(element)
                for child in element.children:
                    process_element(child, depth + 1)

    # Start processing from container
    for child in container.children:
        print(child)
        if isinstance(child, NavigableString):
            text = re.sub(r"\s+", " ", str(child)).strip()
            if text and len(text) >= config.get("min_paragraph_length", 10):
                paragraphs.append(
                    {
                        "text": text,
                        "text_raw": str(child),
                        "source_type": "bare",
                        "list_header": None,
                        "list_item_index": None,
                        "position_in_item": None,
                    }
                )
        else:
            process_element(child)

    logger.debug(
        f"Extracted {len(paragraphs)} semantic paragraphs: "
        f"{sum(1 for p in paragraphs if p['source_type'] == 'stanza')} stanzas, "
        f"{sum(1 for p in paragraphs if p['source_type'] == 'list')} list items, "
        f"{sum(1 for p in paragraphs if p['source_type'] == 'p')} standard, "
        f"{sum(1 for p in paragraphs if p['source_type'] == 'table')} tables, "
        f"{sum(1 for p in paragraphs if p['source_type'] == 'bare')} bare, "
        f"{sum(1 for p in paragraphs if p['source_type'] == 'annotation')} annotations"
    )

    return paragraphs


def element_to_text(element: Tag, config: Dict[str, Any]) -> str:
    """
    Extract clean text from a single HTML element.

    Handles:
    - Whitespace normalization
    - Entity decoding (handled by BeautifulSoup)
    - Nested tag handling

    Args:
        element: HTML element
        config: Extraction configuration

    Returns:
        Clean text string
    """
    if not element:
        return ""

    # Get text content
    text = element.get_text(separator=" ")

    # Normalize whitespace if configured
    if config.get("normalize_whitespace", True):
        # Collapse multiple spaces/newlines into single space
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

    return text


# =============================================================================
# EXTRACTION LAYER - Metrics Calculation (Pure Functions)
# =============================================================================


def count_words(text: str) -> int:
    """
    Count words in text (handles hyphenation, contractions).

    Args:
        text: Text to count

    Returns:
        Word count
    """
    if not text:
        return 0

    # Split on whitespace
    words = text.split()

    # Filter out empty strings
    words = [w for w in words if w.strip()]

    return len(words)


# =============================================================================
# EXTRACTION LAYER - Main Orchestration
# =============================================================================


def extract_paragraphs(
    talk_id: int, html: str, config: Dict[str, Any]
) -> TalkParagraphs:
    """
    Extract all paragraphs from a talk's HTML using semantic unit detection.

    Main orchestration function that:
    1. Parses HTML
    2. Finds body container (era-specific fallback)
    3. Extracts semantic paragraph units (stanzas, lists, standard paragraphs)
    4. Converts each to ParagraphData
    5. Returns TalkParagraphs container

    Args:
        talk_id: Talk identifier
        html: Raw HTML content
        config: Extraction configuration

    Returns:
        TalkParagraphs with all extracted paragraphs
    """
    logger.debug(f"Extracting paragraphs for talk ID {talk_id}")

    errors = []
    warnings = []

    # Step 1: Parse HTML
    soup = parse_html(html, config.get("html_parser", "html.parser"))
    if not soup:
        errors.append("Failed to parse HTML")
        return TalkParagraphs(
            talk_id=talk_id,
            paragraphs=[],
            total_paragraphs=0,
            total_words=0,
            extraction_success=False,
            extraction_errors=errors,
        )

    # Step 2: Find body container
    container = find_body_container(soup)
    if not container:
        errors.append("No body container found")
        return TalkParagraphs(
            talk_id=talk_id,
            paragraphs=[],
            total_paragraphs=0,
            total_words=0,
            extraction_success=False,
            extraction_errors=errors,
        )

    # Step 3: Extract semantic paragraph units
    semantic_paragraphs = extract_semantic_paragraphs(container, config)
    if not semantic_paragraphs:
        warnings.append("No semantic paragraphs found")

    # Step 4: Convert each to ParagraphData
    paragraphs = []
    total_words = 0

    for idx, para_dict in enumerate(semantic_paragraphs, 1):
        try:
            # Extract data from dict
            text = para_dict["text"]
            source_type = para_dict["source_type"]
            list_header = para_dict.get("list_header")
            list_item_index = para_dict.get("list_item_index")
            position_in_item = para_dict.get("position_in_item")

            # Clean and normalize text
            # Tables use "\n" as row separators — only normalize within each line
            if config.get("normalize_whitespace", True):
                if source_type == "table":
                    text = "\n".join(
                        re.sub(r"[ \t]+", " ", line).strip()
                        for line in text.splitlines()
                    )
                    text = text.strip()
                else:
                    text = re.sub(r"\s+", " ", text)
                    text = text.strip()

            # Calculate metrics
            word_count = count_words(text)

            # Generate paragraph ID: talk_id * 10000 + paragraph_number
            paragraph_id = talk_id * 10000 + idx

            # Create ParagraphData with list context
            para = ParagraphData(
                paragraph_id=paragraph_id,
                talk_id=talk_id,
                paragraph_number=idx,
                text=text,
                text_raw=para_dict.get("text_raw"),
                word_count=word_count,
                list_header=list_header,
                list_item_index=list_item_index,
                position_in_item=position_in_item,
                extraction_warnings=[],
            )

            paragraphs.append(para)
            total_words += word_count

        except Exception as e:
            error_msg = f"Failed to create paragraph {idx}: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)

    # Step 5: Create TalkParagraphs container
    success = len(paragraphs) > 0 and len(errors) == 0

    talk_paragraphs = TalkParagraphs(
        talk_id=talk_id,
        paragraphs=paragraphs,
        total_paragraphs=len(paragraphs),
        total_words=total_words,
        extraction_success=success,
        extraction_errors=errors if errors else [],
    )

    logger.debug(
        f"Extracted {len(paragraphs)} paragraphs for talk ID {talk_id} "
        f"({total_words} words)"
    )

    return talk_paragraphs


# =============================================================================
# VALIDATION LAYER - Data Quality Checks
# =============================================================================


def validate_paragraph(para: ParagraphData, config: Dict[str, Any]) -> ValidationResult:
    """
    Validate a single paragraph.

    Checks:
    - Text not empty
    - Counts match actual content
    - Length within bounds
    - No encoding issues

    Args:
        para: Paragraph to validate
        config: Validation configuration

    Returns:
        ValidationResult with errors/warnings
    """
    errors = []
    warnings = []
    stats = {}

    # Check text not empty
    if not para.text or not para.text.strip():
        errors.append(f"Paragraph {para.paragraph_id} has empty text")

    # Check counts are reasonable
    if para.word_count < 0:
        errors.append(f"Paragraph {para.paragraph_id} has negative word count")

    # Verify counts match actual content
    actual_words = count_words(para.text)
    if para.word_count != actual_words:
        warnings.append(
            f"Paragraph {para.paragraph_id} word count mismatch: "
            f"{para.word_count} vs {actual_words}"
        )

    # Check length bounds
    max_length = config.get("max_paragraph_length", 10000)
    if len(para.text) > max_length:
        warnings.append(
            f"Paragraph {para.paragraph_id} is unusually long: {len(para.text)} chars"
        )

    # Collect stats
    stats["word_count"] = para.word_count

    is_valid = len(errors) == 0

    return ValidationResult(
        is_valid=is_valid, errors=errors, warnings=warnings, stats=stats
    )


def validate_talk_paragraphs(
    talk_paras: TalkParagraphs, config: Dict[str, Any]
) -> ValidationResult:
    """
    Validate all paragraphs from a talk.

    Checks:
    - Paragraph numbers sequential (1, 2, 3...)
    - No duplicate paragraph_ids
    - Total counts match sum of individual
    - Paragraph count within expected range

    Args:
        talk_paras: Talk paragraphs to validate
        config: Validation configuration

    Returns:
        ValidationResult with errors/warnings
    """
    errors = []
    warnings = []
    stats = {}

    # Check sequential numbering
    expected_numbers = list(range(1, talk_paras.total_paragraphs + 1))
    actual_numbers = [p.paragraph_number for p in talk_paras.paragraphs]
    if actual_numbers != expected_numbers:
        errors.append(f"Talk {talk_paras.talk_id} has non-sequential paragraph numbers")

    # Check for duplicate IDs
    para_ids = [p.paragraph_id for p in talk_paras.paragraphs]
    if len(para_ids) != len(set(para_ids)):
        errors.append(f"Talk {talk_paras.talk_id} has duplicate paragraph IDs")

    # Check total counts match sum
    actual_words = sum(p.word_count for p in talk_paras.paragraphs)

    if talk_paras.total_words != actual_words:
        errors.append(
            f"Talk {talk_paras.talk_id} total words mismatch: "
            f"{talk_paras.total_words} vs {actual_words}"
        )

    # Collect stats
    stats["total_paragraphs"] = talk_paras.total_paragraphs
    stats["total_words"] = talk_paras.total_words

    is_valid = len(errors) == 0

    return ValidationResult(
        is_valid=is_valid, errors=errors, warnings=warnings, stats=stats
    )


def detect_extraction_anomalies(
    talk_paras: TalkParagraphs, config: Dict[str, Any]
) -> List[str]:
    """
    Flag unusual patterns that might indicate extraction issues.

    Thresholds from plan:
    - Total paragraphs = 0: ERROR
    - Total paragraphs < 3: WARNING
    - Total paragraphs > 150: WARNING
    - Word count < 5: INFO
    - Word count > 400: WARNING
    - Word count > 800: CRITICAL

    Args:
        talk_paras: Talk paragraphs to check
        config: Configuration with thresholds

    Returns:
        List of anomaly descriptions
    """
    anomalies = []

    # Check paragraph count (ERROR/WARNING level)
    if talk_paras.total_paragraphs == 0:
        anomalies.append("ERROR: No paragraphs extracted")
    elif talk_paras.total_paragraphs < 3:
        anomalies.append(f"WARNING: Very few paragraphs: {talk_paras.total_paragraphs}")
    elif talk_paras.total_paragraphs > 150:
        anomalies.append(
            f"WARNING: Very many paragraphs: {talk_paras.total_paragraphs}"
        )

    # Check individual paragraph word counts
    for para in talk_paras.paragraphs:
        if para.word_count < 5:
            anomalies.append(
                f"INFO: Very short paragraph {para.paragraph_number}: {para.word_count} words"
            )
        elif para.word_count > 800:
            anomalies.append(
                f"CRITICAL: Extremely long paragraph {para.paragraph_number}: {para.word_count} words"
            )
        elif para.word_count > 400:
            anomalies.append(
                f"WARNING: Long paragraph {para.paragraph_number}: {para.word_count} words"
            )

    return anomalies


# =============================================================================
# PROCESSING PIPELINE - Complete Workflow
# =============================================================================


def process_talk_paragraphs(
    db: Database, talk_id: int, config: Dict[str, Any], strict: bool = False
) -> Tuple[Optional[TalkParagraphs], List[str]]:
    """
    Full pipeline for single talk.

    Args:
        db: Database connection
        talk_id: Talk to process
        config: Extraction configuration
        strict: If True, fail on any validation error

    Returns:
        (TalkParagraphs or None, list of errors/warnings)
    """
    errors = []

    # Layer 1: Fetch
    html = fetch_talk_html(db, talk_id)
    if not html:
        return None, [f"No HTML found for talk {talk_id}"]

    # Layer 2: Extract
    try:
        talk_paras = extract_paragraphs(talk_id, html, config)
    except Exception as e:
        logger.error(f"Extraction failed for talk {talk_id}: {e}", exc_info=True)
        return None, [f"Extraction failed: {e}"]

    # Layer 3: Validate
    validation = validate_talk_paragraphs(talk_paras, config)

    if validation.errors:
        if strict:
            return None, validation.errors
        errors.extend(validation.errors)

    if validation.warnings:
        errors.extend([f"WARNING: {w}" for w in validation.warnings])

    # Check for anomalies
    anomalies = detect_extraction_anomalies(talk_paras, config)
    if anomalies:
        errors.extend([f"ANOMALY: {a}" for a in anomalies])

    return talk_paras, errors


def process_all_talks(
    db: Database, config: Dict[str, Any], batch_size: int = 100, strict: bool = False
) -> Tuple[List[TalkParagraphs], Dict[str, Any]]:
    """
    Process all talks with progress tracking.

    Args:
        db: Database connection
        config: Extraction configuration
        batch_size: Progress reporting interval
        strict: If True, fail on any validation error

    Returns:
        (list of TalkParagraphs, statistics dict)
    """
    logger.info("Starting batch processing of all talks")

    start_time = datetime.now()

    # Get all talk IDs
    talk_ids = fetch_all_talk_ids(db)
    total_talks = len(talk_ids)

    logger.info(f"Processing {total_talks} talks")

    # Process each talk
    results = []
    success_count = 0
    error_count = 0
    warnings_count = 0

    for idx, talk_id in enumerate(talk_ids, 1):
        try:
            talk_paras, errors = process_talk_paragraphs(db, talk_id, config, strict)

            if talk_paras:
                results.append(talk_paras)
                success_count += 1

                if errors:
                    warnings_count += 1
            else:
                error_count += 1
                logger.warning(f"Failed to process talk {talk_id}: {errors}")

            # Progress reporting
            if idx % batch_size == 0 or idx == total_talks:
                logger.info(
                    f"Progress: {idx}/{total_talks} talks processed "
                    f"({success_count} success, {error_count} errors)"
                )

        except Exception as e:
            logger.error(f"Unexpected error processing talk {talk_id}: {e}")
            error_count += 1

    elapsed = (datetime.now() - start_time).total_seconds()

    # Compile statistics
    stats = {
        "total_talks": total_talks,
        "successful": success_count,
        "errors": error_count,
        "warnings": warnings_count,
        "elapsed_seconds": elapsed,
        "total_paragraphs": sum(tp.total_paragraphs for tp in results),
        "total_words": sum(tp.total_words for tp in results),
    }

    logger.info(
        f"Batch processing complete: {success_count}/{total_talks} successful "
        f"in {elapsed:.2f}s"
    )

    return results, stats


# =============================================================================
# CHROMADB PREPARATION - Format Conversion
# =============================================================================


def paragraphs_to_chromadb_format(
    all_talk_paragraphs: List[TalkParagraphs],
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    """
    Convert extracted paragraphs to ChromaDB insertion format.

    Returns:
        documents: List of paragraph texts (for embedding)
        metadatas: List of metadata dicts
        ids: List of paragraph IDs as strings
    """
    logger.info(f"Converting {len(all_talk_paragraphs)} talks to ChromaDB format")

    documents = []
    metadatas = []
    ids = []

    for talk_paras in all_talk_paragraphs:
        for para in talk_paras.paragraphs:
            doc, meta, doc_id = para.to_chromadb_format()
            documents.append(doc)
            metadatas.append(meta)
            ids.append(doc_id)

    logger.info(f"Prepared {len(documents)} paragraphs for ChromaDB")

    return documents, metadatas, ids


# =============================================================================
# HIGH-LEVEL PIPELINE - Main Entry Point
# =============================================================================


def extract_paragraphs_for_chromadb(
    limit: Optional[int] = None, validate: bool = True
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    """
    Complete extraction pipeline from database to ChromaDB format.

    This is the main entry point for Phase 2 extraction. It:
    1. Fetches HTML from database
    2. Extracts paragraphs for each talk
    3. Validates (optional)
    4. Converts to ChromaDB format

    Args:
        limit: Optional limit on number of talks to extract
        validate: Whether to run strict validation (default True)

    Returns:
        Tuple of (documents, metadatas, ids) ready for ChromaDB

    Raises:
        ValueError: If validation fails in strict mode
    """
    logger.info(
        f"Starting Phase 2 extraction pipeline "
        f"(limit={limit or 'none'}, validate={validate})"
    )

    start_time = datetime.now()

    # Get talk IDs
    all_talk_ids = fetch_all_talk_ids(content_db)
    if limit:
        talk_ids = all_talk_ids[:limit]
    else:
        talk_ids = all_talk_ids

    logger.info(f"Processing {len(talk_ids)} talks")

    # Process each talk
    all_talk_paragraphs = []
    for idx, talk_id in enumerate(talk_ids, 1):
        talk_paras, errors = process_talk_paragraphs(
            content_db, talk_id, PARAGRAPH_CONFIG, strict=validate
        )

        if talk_paras:
            all_talk_paragraphs.append(talk_paras)

        if idx % 100 == 0:
            logger.info(f"Processed {idx}/{len(talk_ids)} talks")

    # Convert to ChromaDB format
    documents, metadatas, ids = paragraphs_to_chromadb_format(all_talk_paragraphs)

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(
        f"Phase 2 extraction complete: {len(documents)} paragraphs from "
        f"{len(all_talk_paragraphs)} talks in {elapsed:.2f}s"
    )

    return documents, metadatas, ids


# =============================================================================
# MAIN - Example Usage and CLI Interface
# =============================================================================


def main():
    """Main entry point for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 2: Extract paragraphs from talk HTML"
    )
    parser.add_argument(
        "--talk-id", type=int, default=None, help="Extract single talk by ID"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of talks to extract (default: all)",
    )
    parser.add_argument(
        "--no-validate", action="store_true", help="Skip validation checks"
    )
    parser.add_argument(
        "--stats", action="store_true", help="Print statistics only (no extraction)"
    )

    args = parser.parse_args()

    try:
        if args.talk_id:
            # Process single talk
            talk_paras, errors = process_talk_paragraphs(
                content_db, args.talk_id, PARAGRAPH_CONFIG, strict=not args.no_validate
            )

            if talk_paras:
                print(f"\n=== Talk {args.talk_id} ===")
                print(f"Total paragraphs: {talk_paras.total_paragraphs}")
                print(f"Total words: {talk_paras.total_words}")
                print(f"Extraction success: {talk_paras.extraction_success}")

                if errors:
                    print(f"\nErrors/Warnings ({len(errors)}):")
                    for error in errors[:10]:
                        print(f"  - {error}")

                print(f"\nFirst paragraph:")
                print(f"  {talk_paras.paragraphs[0]}")

                for para in talk_paras.paragraphs:
                    print("\n", para.to_dict())
                    # print(para)
                    # print(f"\n{para.text}")

        else:
            # Process multiple talks
            documents, metadatas, ids = extract_paragraphs_for_chromadb(
                limit=args.limit, validate=not args.no_validate
            )

            print(f"\n=== Extraction Complete ===")
            print(f"Total paragraphs: {len(documents)}")
            print(f"Sample paragraph (first):")
            print(f"  ID: {ids[0]}")
            print(f"  Text: {documents[0][:200]}...")
            print(f"  Metadata keys: {list(metadatas[0].keys())}")

    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
