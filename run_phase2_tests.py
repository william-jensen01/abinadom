"""
Simple test runner for Phase 2 extraction (no pytest required).
"""

from extractors.phase2_paragraph_extraction import (
    parse_html,
    find_body_container,
    extract_stanza_text,
    extract_list_item_text,
    should_skip_element,
    is_container_element,
    extract_semantic_paragraphs,
    extract_paragraphs,
    detect_extraction_anomalies,
    fetch_talk_html,
)
from config.schemas import PARAGRAPH_CONFIG
from db import content_db


def test_body_container_detection():
    """Test body container detection with fallback chain."""
    print("\n1. Testing body container detection...")

    # Test modern (body-block)
    html = '<div class="body-block"><p>Test</p></div>'
    soup = parse_html(html)
    container = find_body_container(soup)
    assert container is not None
    assert "body-block" in container.get("class", [])
    print("   [OK] Modern container (body-block) detected")

    # Test fallback (primary)
    html = '<div id="primary"><p>Test</p></div>'
    soup = parse_html(html)
    container = find_body_container(soup)
    assert container is not None
    assert container.get("id") == "primary"
    print("   [OK] Fallback container (div#primary) detected")

    # Test old (gcbody)
    html = '<div class="gcbody"><p>Test</p></div>'
    soup = parse_html(html)
    container = find_body_container(soup)
    assert container is not None
    assert "gcbody" in container.get("class", [])
    print("   [OK] Old container (div.gcbody) detected")


def test_stanza_extraction():
    """Test stanza extraction."""
    print("\n2. Testing stanza extraction...")

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
    assert "Author Name" in text
    print("   [OK] Stanza with citation extracted correctly")


def test_list_extraction():
    """Test list item extraction."""
    print("\n3. Testing list item extraction...")

    html = '<li><strong>Header:</strong> Content text here.</li>'
    soup = parse_html(html)
    li = soup.find("li")
    text = extract_list_item_text(li)

    assert "Header:" in text
    assert "Content text here" in text
    print("   [OK] List item with header extracted correctly")


def test_semantic_paragraphs():
    """Test full semantic paragraph extraction."""
    print("\n4. Testing semantic paragraph extraction...")

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
    print(f"   [OK] Extracted {len(paragraphs)} semantic units")

    # Check types
    texts, types = zip(*paragraphs)
    assert "p" in types
    assert "stanza" in types
    assert types.count("list") == 2
    print(f"   [OK] Types: {dict(zip(range(1, len(types)+1), types))}")


def test_full_extraction():
    """Test full extraction pipeline."""
    print("\n5. Testing full extraction pipeline...")

    html = """
    <html>
    <body>
        <div class="body-block">
            <p>Opening paragraph.</p>
            <div class="stanza">
                <div class="line">First line</div>
                <div class="line">Second line</div>
            </div>
            <ol>
                <li>First item</li>
                <li>Second item</li>
            </ol>
            <p>Closing paragraph.</p>
        </div>
    </body>
    </html>
    """

    result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)

    assert result.extraction_success is True
    assert result.total_paragraphs == 5  # 2 p + 1 stanza + 2 li
    assert result.total_words > 0
    print(f"   [OK] Extracted {result.total_paragraphs} paragraphs")
    print(f"   [OK] Total words: {result.total_words}")


def test_real_talk():
    """Test extraction on real talk from database."""
    print("\n6. Testing extraction on real talk...")

    html = fetch_talk_html(content_db, 1)
    if not html:
        print("   [WARN] No HTML found for talk ID 1 (skipping)")
        return

    result = extract_paragraphs(1, html, PARAGRAPH_CONFIG)

    print(f"   [OK] Talk ID: {result.talk_id}")
    print(f"   [OK] Total paragraphs: {result.total_paragraphs}")
    print(f"   [OK] Total words: {result.total_words}")
    print(f"   [OK] Extraction success: {result.extraction_success}")

    if result.extraction_errors:
        print(f"   [WARN] Errors: {len(result.extraction_errors)}")
        for error in result.extraction_errors[:3]:
            print(f"     - {error}")

    # Check anomalies
    anomalies = detect_extraction_anomalies(result, PARAGRAPH_CONFIG)
    if anomalies:
        print(f"   [WARN] Anomalies: {len(anomalies)}")
        for anomaly in anomalies[:3]:
            print(f"     - {anomaly}")

    # Show sample paragraphs
    if result.paragraphs:
        print(f"\n   Sample paragraphs:")
        for para in result.paragraphs[:3]:
            print(f"   [{para.paragraph_number}] {para.text[:80]}...")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 2 Semantic Extraction Tests")
    print("=" * 60)

    try:
        test_body_container_detection()
        test_stanza_extraction()
        test_list_extraction()
        test_semantic_paragraphs()
        test_full_extraction()
        test_real_talk()

        print("\n" + "=" * 60)
        print("[OK] All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()
