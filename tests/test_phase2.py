"""
Unit tests for Phase 2: Paragraph Extraction

Tests all extraction functions with various edge cases.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

import pytest
from bs4 import BeautifulSoup

from extractors.phase2_paragraph_extraction import (
    parse_html,
    find_body_container,
    extract_stanza_text,
    extract_list_item_header,
    extract_list_item_paragraphs,
    extract_list,
    build_prefixed_text,
    extract_stanza_in_list,
    should_skip_element,
    is_container_element,
    extract_semantic_paragraphs,
    count_words,
    extract_paragraphs,
    validate_paragraph,
    validate_talk_paragraphs,
    detect_extraction_anomalies,
    fetch_talk_html,
)
from models.paragraph_data import ParagraphData, TalkParagraphs
from config.schemas import PARAGRAPH_CONFIG
from db import content_db


# =============================================================================
# Test HTML Parsing
# =============================================================================


class TestHTMLParsing:
    """Test HTML parsing functionality."""

    def test_parse_simple_html(self):
        """Test parsing simple HTML."""
        html = "<p>Hello world</p>"
        soup = parse_html(html)
        assert soup is not None
        assert soup.find("p") is not None

    def test_parse_empty_html(self):
        """Test parsing empty HTML."""
        soup = parse_html("")
        assert soup is None

    def test_parse_malformed_html(self):
        """Test parsing malformed HTML (should still work with BeautifulSoup)."""
        html = "<p>Unclosed tag"
        soup = parse_html(html)
        assert soup is not None

    def test_parse_with_lxml(self):
        """Test parsing with lxml parser."""
        html = "<p>Test</p>"
        soup = parse_html(html, parser="lxml")
        assert soup is not None

    def test_parse_with_html_parser(self):
        """Test parsing with html.parser."""
        html = "<p>Test</p>"
        soup = parse_html(html, parser="html.parser")
        assert soup is not None


# =============================================================================
# Test Text Extraction
# =============================================================================


class TestTextExtraction:
    """Test text extraction functionality."""

    def test_simple_paragraph(self):
        """Test extracting simple paragraph."""
        html = "<div class='body-block'><p>Hello world.</p></div>"
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)
        assert result.total_paragraphs == 1
        assert result.paragraphs[0].text == "Hello world."

    def test_multiple_paragraphs(self):
        """Test extracting multiple paragraphs."""
        html = "<div class='body-block'><p>First paragraph.</p><p>Second paragraph.</p></div>"
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)
        assert result.total_paragraphs == 2

    def test_nested_tags_stripped(self):
        """Test that nested tags are stripped.

        Regression: BUG-08 — test HTML text was below min_paragraph_length (9 < 10).
        """
        html = "<div class='body-block'><p><strong>Bold words</strong> appear in text.</p></div>"
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)
        assert result.paragraphs[0].text == "Bold words appear in text."

    def test_whitespace_normalization(self):
        """Test whitespace normalization."""
        html = "<div class='body-block'><p>Multiple    spaces\n\nand newlines</p></div>"
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)
        assert result.paragraphs[0].text == "Multiple spaces and newlines"

    def test_skip_tags(self):
        """Test that skip tags are removed.

        Regression: BUG-09 — first paragraph text was below min_paragraph_length (9 < 10).
        """
        html = "<div class='body-block'><p>Keep this paragraph.</p><script>Remove this</script><p>Keep this paragraph too.</p></div>"
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)
        assert result.total_paragraphs == 2
        assert result.paragraphs[0].text == "Keep this paragraph."


# =============================================================================
# Test Metrics Calculation
# =============================================================================


class TestMetrics:
    """Test metrics calculation functionality."""

    def test_word_count_simple(self):
        """Test simple word count."""
        assert count_words("Hello world") == 2

    def test_word_count_empty(self):
        """Test word count of empty string."""
        assert count_words("") == 0

    def test_word_count_contractions(self):
        """Test word count with contractions."""
        assert count_words("don't won't can't") == 3

    def test_word_count_hyphenated(self):
        """Test word count with hyphenated words."""
        # Hyphenated words count as one word
        assert count_words("well-known fact") == 2


# =============================================================================
# Test Paragraph Extraction
# =============================================================================


class TestParagraphExtraction:
    """Test complete paragraph extraction."""

    def test_extract_simple_talk(self):
        """Test extracting paragraphs from simple talk.

        Regression: BUG-02 — test HTML bare div lacked body-block container class.
        """
        html = """
        <div class="body-block">
            <p>Dear brothers and sisters, I am grateful.</p>
            <p>This is the body of the talk.</p>
            <p>In the name of Jesus Christ, amen.</p>
        </div>
        """
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)

        assert result.talk_id == 1
        assert result.total_paragraphs == 3
        assert result.extraction_success is True
        assert len(result.paragraphs) == 3

    def test_extract_with_multiple_paragraphs(self):
        """Test extraction with multiple paragraphs.

        Regression: BUG-03 — test HTML bare div lacked body-block container class.
        """
        html = """
        <div class="body-block">
            <p>Opening paragraph.</p>
            <p>Body paragraph one.</p>
            <p>Body paragraph two.</p>
            <p>Closing paragraph. In the name of Jesus Christ, amen.</p>
        </div>
        """
        result = extract_paragraphs(2, html, PARAGRAPH_CONFIG)

        assert result.total_paragraphs == 4

    def test_extract_empty_html(self):
        """Test extraction from empty HTML."""
        result = extract_paragraphs(3, "", PARAGRAPH_CONFIG)
        assert result.extraction_success is False
        assert result.total_paragraphs == 0

    def test_paragraph_ids_generated(self):
        """Test that paragraph IDs are generated correctly.

        Regression: BUG-10 — bare p without body-block container.
        """
        html = "<div class='body-block'><p>First paragraph text.</p><p>Second paragraph text.</p><p>Third paragraph text.</p></div>"
        result = extract_paragraphs(5, html, PARAGRAPH_CONFIG)

        # IDs should be: talk_id * 10000 + paragraph_number
        expected_ids = [50001, 50002, 50003]
        actual_ids = [p.paragraph_id for p in result.paragraphs]
        assert actual_ids == expected_ids


# =============================================================================
# Test Validation
# =============================================================================


class TestValidation:
    """Test validation functionality."""

    def test_validate_valid_paragraph(self):
        """Test validating a valid paragraph."""
        para = ParagraphData(
            paragraph_id=1,
            talk_id=1,
            paragraph_number=1,
            text="This is a test paragraph with some words.",
            text_raw="<p>This is a test paragraph with some words.</p>",
            word_count=8,
        )

        result = validate_paragraph(para, PARAGRAPH_CONFIG)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_empty_text(self):
        """Test validating paragraph with empty text."""
        with pytest.raises(ValueError):
            ParagraphData(
                paragraph_id=1,
                talk_id=1,
                paragraph_number=1,
                text="",  # Empty text should raise error in __post_init__
                text_raw="<p></p>",
                word_count=0,
            )

    def test_validate_talk_paragraphs_valid(self):
        """Test validating valid talk paragraphs."""
        paras = [
            ParagraphData(
                paragraph_id=1,
                talk_id=1,
                paragraph_number=1,
                text="First paragraph.",
                text_raw=None,
                word_count=2,
            ),
            ParagraphData(
                paragraph_id=2,
                talk_id=1,
                paragraph_number=2,
                text="Second paragraph.",
                text_raw=None,
                word_count=2,
            ),
        ]

        talk_paras = TalkParagraphs(
            talk_id=1,
            paragraphs=paras,
            total_paragraphs=2,
            total_words=4,
            extraction_success=True,
        )

        result = validate_talk_paragraphs(talk_paras, PARAGRAPH_CONFIG)
        assert result.is_valid is True

    def test_detect_anomaly_few_paragraphs(self):
        """Test detecting anomaly: very few paragraphs."""
        paras = [
            ParagraphData(
                paragraph_id=1,
                talk_id=1,
                paragraph_number=1,
                text="Only paragraph.",
                text_raw=None,
                word_count=2,
            )
        ]

        talk_paras = TalkParagraphs(
            talk_id=1,
            paragraphs=paras,
            total_paragraphs=1,
            total_words=2,
            extraction_success=True,
        )

        anomalies = detect_extraction_anomalies(talk_paras, PARAGRAPH_CONFIG)
        assert len(anomalies) > 0
        assert any("few paragraphs" in a.lower() for a in anomalies)


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_unicode_content(self):
        """Test handling Unicode characters."""
        html = "<div class='body-block'><p>Café résumé naïve</p></div>"
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)
        assert "Café" in result.paragraphs[0].text

    def test_very_long_paragraph(self):
        """Test handling very long paragraphs.

        Regression: BUG-04 — bare p was not wrapped in body-block container.
        """
        long_text = "word " * 5000  # 5000 words
        html = f"<div class='body-block'><p>{long_text}</p></div>"
        result = extract_paragraphs(99, html, PARAGRAPH_CONFIG)

        assert result.total_paragraphs == 1
        assert result.paragraphs[0].word_count == 5000

    def test_no_paragraphs(self):
        """Test HTML with no paragraph elements."""
        html = "<div>Just text without p tags</div>"
        result = extract_paragraphs(100, html, PARAGRAPH_CONFIG)

        # Should extract nothing since there are no <p> tags
        assert result.total_paragraphs == 0

    def test_multiple_paragraphs(self):
        """Test HTML with multiple paragraphs.

        Regression: BUG-11 — bare div without body-block container.
        """
        html = """
        <div class="body-block">
            <p>Paragraph 1 has enough text.</p>
            <p>Paragraph 2 has enough text.</p>
            <p>Paragraph 3 has enough text.</p>
        </div>
        """
        result = extract_paragraphs(101, html, PARAGRAPH_CONFIG)

        # Should extract 3 paragraphs
        assert result.total_paragraphs == 3


# =============================================================================
# Test Semantic Extraction
# =============================================================================


class TestSemanticExtraction:
    """Test semantic paragraph extraction functionality."""

    def test_find_body_container_modern(self):
        """Test finding body-block container (2010s+)."""
        html = '<div class="body-block"><p>Test</p></div>'
        soup = parse_html(html)
        container = find_body_container(soup)
        assert container is not None
        assert "body-block" in container.get("class", [])

    def test_find_body_container_fallback(self):
        """Test fallback to div#primary (1990s-2000s)."""
        html = '<div id="primary"><p>Test</p></div>'
        soup = parse_html(html)
        container = find_body_container(soup)
        assert container is not None
        assert container.get("id") == "primary"

    def test_find_body_container_gcbody(self):
        """Test fallback to div.gcbody (1950s-1970s)."""
        html = '<div class="gcbody"><p>Test</p></div>'
        soup = parse_html(html)
        container = find_body_container(soup)
        assert container is not None
        assert "gcbody" in container.get("class", [])

    def test_extract_stanza(self):
        """Test extracting stanza with citation."""
        html = """
        <div class="stanza">
            <div class="line">First line of poetry</div>
            <div class="line">Second line of poetry</div>
            <div class="citationInfo">Author Name</div>
        </div>
        """
        soup = parse_html(html)
        stanza = soup.find("div", class_="stanza")
        text = extract_stanza_text(stanza)

        assert "First line of poetry" in text
        assert "Second line of poetry" in text
        assert "— Author Name" in text

    def test_extract_list_item(self):
        """Test extracting list item with header."""
        html = '<li><strong>Header</strong><p>Content text here.</p></li>'
        soup = parse_html(html)
        li = soup.find("li")
        processed = set()

        # Extract header
        header = extract_list_item_header(li)
        assert header == "Header"

        # Extract paragraphs
        paragraphs = extract_list_item_paragraphs(li, header, 1, processed, PARAGRAPH_CONFIG)
        assert len(paragraphs) == 1
        assert "Header: Content text here" in paragraphs[0]["text"]

    def test_should_skip_empty_paragraph(self):
        """Test skipping empty paragraphs."""
        html = '<p></p>'
        soup = parse_html(html)
        p = soup.find("p")
        assert should_skip_element(p) is True

    def test_should_skip_header(self):
        """Test skipping header elements."""
        html = '<h1>Header</h1>'
        soup = parse_html(html)
        h1 = soup.find("h1")
        assert should_skip_element(h1) is True

    def test_is_container_figure(self):
        """Test identifying figure as container.

        Regression: BUG-05 — is_container_element returned False for div.figure
        despite docstring saying it should be True.
        """
        html = '<div class="figure"><p>Test</p></div>'
        soup = parse_html(html)
        div = soup.find("div")
        assert is_container_element(div) is True

    def test_is_not_container_stanza(self):
        """Test that stanza is NOT a container (it's a semantic unit)."""
        html = '<div class="stanza"><div class="line">Test</div></div>'
        soup = parse_html(html)
        div = soup.find("div", class_="stanza")
        assert is_container_element(div) is False

    def test_extract_semantic_paragraphs_mixed(self):
        """Test extracting mixed semantic units."""
        html = """
        <div class="body-block">
            <p>Standard paragraph</p>
            <div class="stanza">
                <div class="line">Poetry line</div>
            </div>
            <ol>
                <li>List item one</li>
                <li>List item two</li>
            </ol>
        </div>
        """
        soup = parse_html(html)
        container = find_body_container(soup)
        paragraphs = extract_semantic_paragraphs(container, PARAGRAPH_CONFIG)

        # Should extract: 1 standard p, 1 stanza, 2 list items = 4 total
        assert len(paragraphs) == 4

        # Check types (paragraphs are now dicts, not tuples)
        types = [p["source_type"] for p in paragraphs]
        assert "p" in types
        assert "stanza" in types
        assert types.count("list") == 2


# =============================================================================
# Test List Extraction
# =============================================================================


class TestListExtraction:
    """Test list item extraction with semantic context preservation."""

    def test_header_extraction_h2(self):
        """Test h2 header extraction (priority 1)."""
        html = """
        <li>
            <span class="label">1.</span>
            <h2>Dating</h2>
            <p>Content here</p>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        header = extract_list_item_header(li)
        assert header == "Dating"

    def test_header_extraction_h3(self):
        """Test h3 header extraction (priority 1)."""
        html = """
        <li>
            <span class="label">2.</span>
            <h3>Repentance</h3>
            <p>Content here</p>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        header = extract_list_item_header(li)
        assert header == "Repentance"

    def test_header_extraction_bold(self):
        """Test bold header extraction (priority 2)."""
        html = """
        <li>
            <span class="label">3.</span>
            <b>Faith</b>
            <p>Content here</p>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        header = extract_list_item_header(li)
        assert header == "Faith"

    def test_header_extraction_strong(self):
        """Test strong header extraction (priority 2)."""
        html = """
        <li>
            <span class="label">4.</span>
            <strong>Prayer</strong>
            <p>Content here</p>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        header = extract_list_item_header(li)
        assert header == "Prayer"

    def test_header_extraction_numeric_fallback(self):
        """Test numeric label as fallback (priority 3)."""
        html = """
        <li>
            <span class="label"><span class="emphasis">5.</span></span>
            <p>Always be honest.</p>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        header = extract_list_item_header(li)
        assert header == "5"

    def test_header_cleanup_colon(self):
        """Test trailing colon removal."""
        html = """
        <li>
            <h2>Honesty:</h2>
            <p>Content here</p>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        header = extract_list_item_header(li)
        assert header == "Honesty"

    def test_header_cleanup_period(self):
        """Test trailing period removal."""
        html = """
        <li>
            <h2>Service.</h2>
            <p>Content here</p>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        header = extract_list_item_header(li)
        assert header == "Service"

    def test_text_prefixing(self):
        """Test text is properly prefixed with headers."""
        header = "Dating"
        content = "Don't date until you're 16."
        result = build_prefixed_text(header, content)
        expected = "Dating: Don't date until you're 16."
        assert result == expected

    def test_text_no_prefix_when_no_header(self):
        """Test no prefix when no header."""
        header = None
        content = "Always be honest."
        result = build_prefixed_text(header, content)
        assert result == "Always be honest."

    def test_text_avoid_duplication(self):
        """Test avoiding duplication when content already has prefix."""
        header = "Dating"
        content = "Dating: Don't date until you're 16."
        result = build_prefixed_text(header, content)
        assert result == "Dating: Don't date until you're 16."

    def test_list_extraction_basic(self):
        """Test basic list extraction with headers."""
        html = """
        <ol>
            <li>
                <span class="label">1.</span>
                <div>
                    <h2>Dating</h2>
                    <p>Don't date until you're 16.</p>
                    <p>Group dates are encouraged.</p>
                </div>
            </li>
            <li>
                <span class="label">2.</span>
                <div>
                    <h2>Repentance</h2>
                    <p>Repentance is always available.</p>
                </div>
            </li>
        </ol>
        """
        soup = parse_html(html)
        ol = soup.find("ol")
        processed = set()

        paragraphs = extract_list(ol, processed, PARAGRAPH_CONFIG)

        # Should have 3 paragraphs total
        assert len(paragraphs) == 3

        # Check first paragraph
        p1 = paragraphs[0]
        assert p1["text"] == "Dating: Don't date until you're 16."
        assert p1["list_header"] == "Dating"
        assert p1["list_item_index"] == 1
        assert p1["position_in_item"] == 1

        # Check second paragraph
        p2 = paragraphs[1]
        assert p2["text"] == "Dating: Group dates are encouraged."
        assert p2["list_header"] == "Dating"
        assert p2["list_item_index"] == 1
        assert p2["position_in_item"] == 2

        # Check third paragraph
        p3 = paragraphs[2]
        assert p3["text"] == "Repentance: Repentance is always available."
        assert p3["list_header"] == "Repentance"
        assert p3["list_item_index"] == 2
        assert p3["position_in_item"] == 1

    def test_nested_stanza_in_list(self):
        """Test stanza inside list item is collapsed with ' / ' delimiter."""
        html = """
        <li>
            <h2>Scripture</h2>
            <p>This teaches us hope.</p>
            <div class="stanza">
                <div class="line">Come unto Christ</div>
                <div class="line">And be perfected in him</div>
            </div>
            <div class="citationInfo">
                <p>(Moroni 10:32)</p>
            </div>
            <p>We must follow this counsel.</p>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        processed = set()

        paragraphs = extract_list_item_paragraphs(li, "Scripture", 1, processed, PARAGRAPH_CONFIG)

        # Should have 3 paragraphs
        assert len(paragraphs) == 3

        # First paragraph
        assert paragraphs[0]["text"] == "Scripture: This teaches us hope."
        assert paragraphs[0]["position_in_item"] == 1

        # Stanza paragraph (collapsed)
        stanza_text = paragraphs[1]["text"]
        expected = "Scripture: Come unto Christ / And be perfected in him / (Moroni 10:32)"
        assert stanza_text == expected
        assert paragraphs[1]["position_in_item"] == 2

        # Third paragraph
        assert paragraphs[2]["text"] == "Scripture: We must follow this counsel."
        assert paragraphs[2]["position_in_item"] == 3

    def test_list_no_header(self):
        """Test list item with no header, only numeric label."""
        html = """
        <li>
            <span class="label">3.</span>
            <div>
                <p>Always be honest.</p>
            </div>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        processed = set()

        paragraphs = extract_list_item_paragraphs(li, "3", 1, processed, PARAGRAPH_CONFIG)

        assert len(paragraphs) == 1
        assert paragraphs[0]["text"] == "3: Always be honest."
        assert paragraphs[0]["list_header"] == "3"

    def test_empty_paragraphs_skipped(self):
        """Test empty paragraphs are skipped."""
        html = """
        <li>
            <h2>Test</h2>
            <p></p>
            <p>Valid content.</p>
            <p>   </p>
        </li>
        """
        soup = parse_html(html)
        li = soup.find("li")
        processed = set()

        paragraphs = extract_list_item_paragraphs(li, "Test", 1, processed, PARAGRAPH_CONFIG)

        # Should only have 1 paragraph (empty ones skipped)
        assert len(paragraphs) == 1
        assert paragraphs[0]["text"] == "Test: Valid content."

    def test_full_example(self):
        """Test the full example from the specification."""
        html = """
        <ol>
            <li>
                <span class="label"><span class="emphasis">1.</span></span>
                <div>
                    <h2>Dating</h2>
                    <p>Don't date until you're 16.</p>
                    <p>Group dates are encouraged.</p>
                </div>
            </li>
            <li>
                <span class="label"><span class="emphasis">2.</span></span>
                <div>
                    <h2>Repentance</h2>
                    <p>Repentance is always available.</p>
                    <div class="stanza">
                        <div class="line">Come unto Christ</div>
                        <div class="line">And be perfected in him</div>
                    </div>
                    <div class="citationInfo">
                        <p>(Moroni 10:32)</p>
                    </div>
                    <p>This scripture teaches us hope.</p>
                </div>
            </li>
            <li>
                <span class="label"><span class="emphasis">3.</span></span>
                <div>
                    <p>Always be honest.</p>
                </div>
            </li>
        </ol>
        """
        soup = parse_html(html)
        ol = soup.find("ol")
        processed = set()

        paragraphs = extract_list(ol, processed, PARAGRAPH_CONFIG)

        # Expected outputs
        expected = [
            {"text": "Dating: Don't date until you're 16.", "list_header": "Dating", "list_item_index": 1, "position_in_item": 1},
            {"text": "Dating: Group dates are encouraged.", "list_header": "Dating", "list_item_index": 1, "position_in_item": 2},
            {"text": "Repentance: Repentance is always available.", "list_header": "Repentance", "list_item_index": 2, "position_in_item": 1},
            {"text": "Repentance: Come unto Christ / And be perfected in him / (Moroni 10:32)", "list_header": "Repentance", "list_item_index": 2, "position_in_item": 2},
            {"text": "Repentance: This scripture teaches us hope.", "list_header": "Repentance", "list_item_index": 2, "position_in_item": 3},
            {"text": "3: Always be honest.", "list_header": "3", "list_item_index": 3, "position_in_item": 1},
        ]

        assert len(paragraphs) == len(expected)

        for i, (actual, exp) in enumerate(zip(paragraphs, expected)):
            assert actual["text"] == exp["text"], f"Paragraph {i+1} text mismatch"
            assert actual["list_header"] == exp["list_header"], f"Paragraph {i+1} header mismatch"
            assert actual["list_item_index"] == exp["list_item_index"], f"Paragraph {i+1} item index mismatch"
            assert actual["position_in_item"] == exp["position_in_item"], f"Paragraph {i+1} position mismatch"


# =============================================================================
# Test Integration with Real Data
# =============================================================================


class TestRealDataIntegration:
    """Test extraction on real talk data."""

    def test_extract_real_talk(self):
        """Test extraction on a real talk from database.

        Regression: BUG-12 — no skip guard when database file absent in test environment.
        """
        import os
        if not os.path.exists(content_db.path):
            pytest.skip("Database not available in this environment")
        # Test on talk ID 1
        html = fetch_talk_html(content_db, 1)

        if html:  # Only test if we have data
            result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)

            # Basic sanity checks
            assert result.talk_id == 1
            assert result.total_paragraphs >= 0
            assert result.total_words >= 0

            # If extraction succeeded, verify structure
            if result.extraction_success:
                assert len(result.paragraphs) == result.total_paragraphs

                # Check paragraph numbering is sequential
                numbers = [p.paragraph_number for p in result.paragraphs]
                assert numbers == list(range(1, result.total_paragraphs + 1))


# =============================================================================
# Update Existing Tests for New Extraction
# =============================================================================


class TestNewExtractionApproach:
    """Test updated extraction approach."""

    def test_extract_with_body_block(self):
        """Test extraction finds body-block container."""
        html = """
        <html>
        <body>
            <div class="body-block">
                <p>First paragraph.</p>
                <p>Second paragraph.</p>
            </div>
        </body>
        </html>
        """
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)

        assert result.extraction_success is True
        assert result.total_paragraphs == 2

    def test_extract_no_container_fails(self):
        """Test extraction fails gracefully without body container."""
        html = "<div><p>No body container</p></div>"
        result = extract_paragraphs(2, html, PARAGRAPH_CONFIG)

        assert result.extraction_success is False
        assert "No body container found" in result.extraction_errors

    def test_extract_stanza_as_single_paragraph(self):
        """Test that stanzas are extracted as single paragraphs."""
        html = """
        <div class="body-block">
            <div class="stanza">
                <div class="line">Line one</div>
                <div class="line">Line two</div>
                <div class="line">Line three</div>
            </div>
        </div>
        """
        result = extract_paragraphs(3, html, PARAGRAPH_CONFIG)

        # Stanza should be ONE paragraph
        assert result.total_paragraphs == 1
        assert "Line one" in result.paragraphs[0].text
        assert "Line two" in result.paragraphs[0].text

    def test_extract_list_items_separately(self):
        """Test that list items are extracted as separate paragraphs."""
        html = """
        <div class="body-block">
            <ol>
                <li>First item with content</li>
                <li>Second item with content</li>
                <li>Third item with content</li>
            </ol>
        </div>
        """
        result = extract_paragraphs(4, html, PARAGRAPH_CONFIG)

        # Should have 3 paragraphs (one per list item)
        assert result.total_paragraphs == 3


# =============================================================================
# Regression Tests
# =============================================================================


class TestRegressionBugs:
    """Regression tests for bugs catalogued in BUGS.md.

    Each test reproduces the exact input that triggered the bug and asserts
    the correct (fixed) behavior. Reverting the fix would cause the test to fail.
    """

    def test_regression_bug_06_bare_li_text(self):
        """Regression: BUG-06 — extract_list_item_paragraphs silently drops bare
        li text without p wrapper.

        The fix added a fallback that extracts bare text content from <li> elements
        when no <p> children are found. Reverting the fallback would cause this test
        to return 0 paragraphs instead of 1.
        """
        html = """
        <div class="body-block">
            <ol>
                <li>Bare text content without p wrapper</li>
            </ol>
        </div>
        """
        result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)
        assert result.total_paragraphs >= 1
        texts = [p.text for p in result.paragraphs]
        assert any("Bare text content without p wrapper" in t for t in texts)

    def test_regression_bug_07_no_debug_prints(self, capsys):
        """Regression: BUG-07 — Debug print() statements left in
        extract_semantic_paragraphs violating logging convention.

        The fix removed print("Stanza Detected") calls. Re-adding them
        would cause this test to fail.
        """
        html = """
        <div class="body-block">
            <div class="stanza">
                <div class="line">First line of poetry here</div>
                <div class="line">Second line of poetry here</div>
            </div>
        </div>
        """
        soup = parse_html(html)
        container = find_body_container(soup)
        extract_semantic_paragraphs(container, PARAGRAPH_CONFIG)
        captured = capsys.readouterr()
        assert "Stanza Detected" not in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
