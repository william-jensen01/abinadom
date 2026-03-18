"""
Phase 5: Validation Gate

Read-only cross-collection integrity check between extraction (Phases 1-4)
and ChromaDB insertion (Phase 6).

No enrichment, no mutations, no auto-fixing, no skipping.
Produces a ValidationReport — that's it.
"""

import sys
from pathlib import Path
from typing import List, Optional

sys.path.append(str(Path(__file__).parent.parent))

from models.talk_metadata import TalkMetadata
from models.paragraph_data import TalkParagraphs
from models.citation_data import TalkCitations
from models.footnote_data import TalkFootnotes
from models.validation_report import ValidationReport


# =============================================================================
# Public API
# =============================================================================


def validate_talk(
    metadata: TalkMetadata,
    paragraphs: TalkParagraphs,
    citations: TalkCitations,
    footnotes: TalkFootnotes,
    db=None,  # Optional[Database] — core_db for citation/talk DB checks
) -> ValidationReport:
    """
    Run all Phase 5 checks against a single talk's extracted data bundle.

    Args:
        metadata:   Phase 1 output
        paragraphs: Phase 2 output
        citations:  Phase 3 output
        footnotes:  Phase 4 output
        db:         Optional Database instance (core_db) for citation DB checks.
                    If None, DB-dependent checks are skipped with a warning.

    Returns:
        ValidationReport with is_valid=False if any error is found.
    """
    errors: List[str] = []
    warnings: List[str] = []

    db_checks_passed = 0
    db_checks_failed = 0

    # --- Check 1: Cross-collection integrity ---
    cross_passed, cross_failed, cross_errors, cross_warnings = _check_cross_collection(
        metadata, paragraphs, citations, footnotes
    )
    errors.extend(cross_errors)
    warnings.extend(cross_warnings)

    # --- Check 2: Citation DB validation ---
    if db is not None:
        cp, cf, cerrs, cwarns = _check_citation_db(metadata, paragraphs, citations, db)
        errors.extend(cerrs)
        warnings.extend(cwarns)
        db_checks_passed += cp
        db_checks_failed += cf
    else:
        warnings.append("DB checks skipped: no database connection provided")

    # --- Check 3: Paragraph sanity ---
    _check_paragraphs(paragraphs, errors, warnings)

    # --- Check 4: ChromaDB readiness ---
    _check_chromadb_readiness(metadata, paragraphs, citations, footnotes, errors)

    # --- Check 5: Footnote sanity ---
    _check_footnotes(footnotes, errors, warnings)

    stats = {
        "paragraph_count": len(paragraphs.paragraphs),
        "citation_count": len(citations.citations),
        "footnote_count": len(footnotes.footnotes),
        "cross_collection_checks_passed": cross_passed,
        "cross_collection_checks_failed": cross_failed,
        "db_checks_passed": db_checks_passed,
        "db_checks_failed": db_checks_failed,
    }

    return ValidationReport(
        talk_id=metadata.talk_id,
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        stats=stats,
    )


# =============================================================================
# Check 1: Cross-collection integrity
# =============================================================================


def _check_cross_collection(
    metadata: TalkMetadata,
    paragraphs: TalkParagraphs,
    citations: TalkCitations,
    footnotes: TalkFootnotes,
):
    """Verify foreign-key relationships across all four collections."""
    errors: List[str] = []
    warnings: List[str] = []
    passed = 0
    failed = 0

    talk_id = metadata.talk_id
    paragraph_ids = {p.paragraph_id for p in paragraphs.paragraphs}
    para_by_id = {p.paragraph_id: p for p in paragraphs.paragraphs}

    # --- Citation foreign keys ---
    for cite in citations.citations:
        # paragraph_id exists in paragraph list
        if cite.paragraph_id in paragraph_ids:
            passed += 1
        else:
            errors.append(
                f"Citation {cite.citation_id}: paragraph_id {cite.paragraph_id} "
                f"not found in paragraph list"
            )
            failed += 1

        # talk_id matches metadata
        if cite.talk_id == talk_id:
            passed += 1
        else:
            errors.append(
                f"Citation {cite.citation_id}: talk_id mismatch "
                f"(expected {talk_id}, got {cite.talk_id})"
            )
            failed += 1

    # --- Footnote foreign keys ---
    for fn in footnotes.footnotes:
        # paragraph_id exists in paragraph list
        if fn.paragraph_id in paragraph_ids:
            passed += 1
        else:
            errors.append(
                f"Footnote {fn.footnote_id}: paragraph_id {fn.paragraph_id} "
                f"not found in paragraph list"
            )
            failed += 1

        # talk_id matches metadata
        if fn.talk_id == talk_id:
            passed += 1
        else:
            errors.append(
                f"Footnote {fn.footnote_id}: talk_id mismatch "
                f"(expected {talk_id}, got {fn.talk_id})"
            )
            failed += 1

    # --- Per-paragraph count vs. actual records ---
    from collections import Counter
    cite_counts = Counter(c.paragraph_id for c in citations.citations)
    fn_counts = Counter(f.paragraph_id for f in footnotes.footnotes)

    for para in paragraphs.paragraphs:
        actual_cites = cite_counts[para.paragraph_id]
        actual_fns = fn_counts[para.paragraph_id]

        # citation_count flag matches actual count
        if para.citation_count == actual_cites:
            passed += 1
        else:
            warnings.append(
                f"Paragraph {para.paragraph_id}: citation_count={para.citation_count} "
                f"but actual citations={actual_cites}"
            )
            failed += 1

        # footnote_count flag matches actual count
        if para.footnote_count == actual_fns:
            passed += 1
        else:
            warnings.append(
                f"Paragraph {para.paragraph_id}: footnote_count={para.footnote_count} "
                f"but actual footnotes={actual_fns}"
            )
            failed += 1

        # has_scripture_citation iff citation_count > 0
        expected_has_cite = actual_cites > 0
        if para.has_scripture_citation != expected_has_cite:
            warnings.append(
                f"Paragraph {para.paragraph_id}: has_scripture_citation="
                f"{para.has_scripture_citation} but citation_count={actual_cites}"
            )

        # has_footnote iff footnote_count > 0
        expected_has_fn = actual_fns > 0
        if para.has_footnote != expected_has_fn:
            warnings.append(
                f"Paragraph {para.paragraph_id}: has_footnote="
                f"{para.has_footnote} but footnote_count={actual_fns}"
            )

    return passed, failed, errors, warnings


# =============================================================================
# Check 2: Citation DB validation
# =============================================================================


def _check_citation_db(
    metadata: TalkMetadata,
    paragraphs: TalkParagraphs,
    citations: TalkCitations,
    db,
):
    """Verify citation IDs exist in core.52.db and ID formulas are correct."""
    errors: List[str] = []
    warnings: List[str] = []
    passed = 0
    failed = 0

    talk_id = metadata.talk_id

    # talk_id exists in source database
    row = db.select_one("SELECT ID FROM talk WHERE ID = ?", (talk_id,))
    if row is not None:
        passed += 1
    else:
        errors.append(f"talk_id {talk_id} not found in database talk table")
        failed += 1

    for cite in citations.citations:
        # citation_id exists in citation table
        row = db.select_one("SELECT ID FROM citation WHERE ID = ?", (cite.citation_id,))
        if row is not None:
            passed += 1
        else:
            errors.append(
                f"Citation {cite.citation_id}: ID not found in core.52.db citation table"
            )
            failed += 1

        # paragraph_id formula
        expected_pid = talk_id * 10000 + cite.paragraph_number
        if cite.paragraph_id == expected_pid:
            passed += 1
        else:
            errors.append(
                f"Citation {cite.citation_id}: paragraph_id={cite.paragraph_id} "
                f"expected {expected_pid} (talk_id*10000+paragraph_number)"
            )
            failed += 1

    return passed, failed, errors, warnings


# =============================================================================
# Check 3: Paragraph sanity
# =============================================================================


def _check_paragraphs(
    paragraphs: TalkParagraphs,
    errors: List[str],
    warnings: List[str],
):
    """Sequential numbering, reasonable counts, paragraph_id formula."""
    paras = paragraphs.paragraphs
    talk_id = paragraphs.talk_id
    count = len(paras)

    # Reasonable count
    if count < 3:
        warnings.append(f"Low paragraph count: {count} (expected >= 3)")
    elif count > 150:
        warnings.append(f"High paragraph count: {count} (expected <= 150)")

    # Collect paragraph numbers for sequential check
    numbers = [p.paragraph_number for p in paras]

    # Duplicate check
    seen = set()
    for n in numbers:
        if n in seen:
            errors.append(f"Duplicate paragraph_number: {n}")
        seen.add(n)

    # Gap check: sorted numbers should be 1..N with no gaps
    sorted_nums = sorted(set(numbers))
    for i, n in enumerate(sorted_nums, start=1):
        if n != i:
            errors.append(
                f"Non-sequential paragraph numbering: expected {i}, got {n}"
            )
            break  # report first gap only to avoid noise

    # paragraph_id formula
    for para in paras:
        expected_pid = talk_id * 10000 + para.paragraph_number
        if para.paragraph_id != expected_pid:
            errors.append(
                f"Paragraph {para.paragraph_number}: paragraph_id={para.paragraph_id} "
                f"expected {expected_pid} (talk_id*10000+paragraph_number)"
            )


# =============================================================================
# Check 4: ChromaDB readiness
# =============================================================================


def _check_chromadb_readiness(
    metadata: TalkMetadata,
    paragraphs: TalkParagraphs,
    citations: TalkCitations,
    footnotes: TalkFootnotes,
    errors: List[str],
):
    """Document text not empty; IDs unique within each collection."""
    # Metadata document
    doc, _, meta_id = metadata.to_chromadb_format()
    if not doc or not doc.strip():
        errors.append(f"TalkMetadata talk_id={metadata.talk_id}: empty document text")

    # Paragraph documents + ID uniqueness
    para_ids = []
    for para in paragraphs.paragraphs:
        doc, _, doc_id = para.to_chromadb_format()
        if not doc or not doc.strip():
            errors.append(
                f"ParagraphData paragraph_id={para.paragraph_id}: empty document text"
            )
        para_ids.append(doc_id)
    _check_id_uniqueness("paragraphs", para_ids, errors)

    # Citation documents + ID uniqueness
    cite_ids = []
    for cite in citations.citations:
        doc, _, doc_id = cite.to_chromadb_format()
        if not doc or not doc.strip():
            errors.append(
                f"CitationData citation_id={cite.citation_id}: empty document text"
            )
        cite_ids.append(doc_id)
    _check_id_uniqueness("citations", cite_ids, errors)

    # Footnote documents + ID uniqueness
    fn_ids = []
    for fn in footnotes.footnotes:
        doc, _, doc_id = fn.to_chromadb_format()
        if not doc or not doc.strip():
            errors.append(
                f"FootnoteData footnote_id={fn.footnote_id}: empty document text"
            )
        fn_ids.append(doc_id)
    _check_id_uniqueness("footnotes", fn_ids, errors)


def _check_id_uniqueness(collection: str, ids: List[str], errors: List[str]):
    seen = set()
    for doc_id in ids:
        if doc_id in seen:
            errors.append(f"Duplicate ID in {collection} collection: {doc_id}")
        seen.add(doc_id)


# =============================================================================
# Check 5: Footnote sanity
# =============================================================================


def _check_footnotes(
    footnotes: TalkFootnotes,
    errors: List[str],
    warnings: List[str],
):
    """footnote_number >= 1, text not empty, footnote_id formula."""
    talk_id = footnotes.talk_id

    numbers = [fn.footnote_number for fn in footnotes.footnotes]

    # Non-sequential footnote numbering warning
    sorted_nums = sorted(numbers)
    for i, (a, b) in enumerate(zip(sorted_nums, sorted_nums[1:])):
        if b != a + 1:
            warnings.append(
                f"Non-sequential footnote numbering: gap between {a} and {b}"
            )

    for fn in footnotes.footnotes:
        # footnote_number >= 1 (belt-and-suspenders; __post_init__ enforces this)
        if fn.footnote_number < 1:
            errors.append(
                f"Footnote {fn.footnote_id}: invalid footnote_number={fn.footnote_number}"
            )

        # footnote_text_raw not empty (belt-and-suspenders)
        if not fn.footnote_text_raw:
            errors.append(
                f"Footnote {fn.footnote_id}: empty footnote_text_raw"
            )

        # footnote_id formula: talk_id * 100000 + paragraph_number * 100 + footnote_number
        expected_id = talk_id * 100000 + fn.paragraph_number * 100 + fn.footnote_number
        if fn.footnote_id != expected_id:
            errors.append(
                f"Footnote fn_num={fn.footnote_number} para={fn.paragraph_number}: "
                f"footnote_id={fn.footnote_id} expected {expected_id}"
            )
