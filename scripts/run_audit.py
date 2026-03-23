# -*- coding: utf-8 -*-
"""
Bug audit driver script.

Reads talk_ids from config/audit_sample.json and runs each talk through
Phases 1-5 of the extraction pipeline, reporting any errors per talk per phase.

Usage:
    pipenv run py scripts/run_audit.py

Before running, populate config/audit_sample.json with a list of talk_id
integers, e.g.: [1059, 2345, 3012]
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import content_db, core_db
from config.schemas import PARAGRAPH_CONFIG, CITATION_CONFIG, FOOTNOTE_CONFIG
from models.citation_data import TalkCitations
from models.footnote_data import TalkFootnotes
from extractors.phase1_talk_metadata import fetch_talk_by_id, extract_talk_metadata
from extractors.phase2_paragraph_extraction import fetch_talk_html, extract_paragraphs
from extractors.phase3_citation_extraction import extract_citations_from_paragraph
from extractors.phase4_footnote_extraction import extract_footnotes_from_paragraph
from extractors.phase5_validation import validate_talk

logger = logging.getLogger(__name__)

AUDIT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "audit_sample.json"


def _run_talk(talk_id: int) -> Dict[str, Any]:
    """Run a single talk through all 5 phases and return a result summary."""
    result: Dict[str, Any] = {
        "talk_id": talk_id,
        "errors": {},
        "warnings": [],
    }

    # Phase 1: Talk metadata
    try:
        row = fetch_talk_by_id(core_db, talk_id)
        if row is None:
            result["errors"]["phase1"] = f"talk_id {talk_id} not found in database"
            return result
        metadata = extract_talk_metadata(row)
        logger.debug("Phase 1 OK — talk_id=%d title=%s", talk_id, metadata.title)
    except Exception as exc:
        result["errors"]["phase1"] = str(exc)
        logger.error("Phase 1 error for talk_id=%d: %s", talk_id, exc)
        return result

    # Phase 2: Paragraph extraction
    try:
        html = fetch_talk_html(content_db, talk_id)
        if not html:
            result["errors"]["phase2"] = "no HTML content found"
            return result
        para_result = extract_paragraphs(talk_id, html, PARAGRAPH_CONFIG)
        if not para_result.extraction_success:
            result["errors"]["phase2"] = "; ".join(para_result.extraction_errors)
            logger.warning(
                "Phase 2 extraction failed for talk_id=%d: %s",
                talk_id,
                para_result.extraction_errors,
            )
            return result
        logger.debug(
            "Phase 2 OK — talk_id=%d paragraphs=%d",
            talk_id,
            para_result.total_paragraphs,
        )
    except Exception as exc:
        result["errors"]["phase2"] = str(exc)
        logger.error("Phase 2 error for talk_id=%d: %s", talk_id, exc)
        return result

    # Phase 3: Citation extraction (per paragraph)
    all_citations = []
    phase3_errors: List[str] = []
    try:
        for para in para_result.paragraphs:
            if not para.text_raw:
                continue
            try:
                citations = extract_citations_from_paragraph(para, CITATION_CONFIG)
                all_citations.extend(citations)
            except Exception as exc:
                phase3_errors.append(f"para {para.paragraph_id}: {exc}")
        if phase3_errors:
            result["errors"]["phase3"] = "; ".join(phase3_errors[:5])
            logger.warning(
                "Phase 3 errors for talk_id=%d (%d errors): %s",
                talk_id,
                len(phase3_errors),
                phase3_errors[0],
            )
        else:
            logger.debug("Phase 3 OK — talk_id=%d citations=%d", talk_id, len(all_citations))
    except Exception as exc:
        result["errors"]["phase3"] = str(exc)
        logger.error("Phase 3 error for talk_id=%d: %s", talk_id, exc)

    # Phase 4: Footnote extraction (per paragraph)
    all_footnotes = []
    phase4_errors: List[str] = []
    try:
        for para in para_result.paragraphs:
            if not para.text_raw:
                continue
            try:
                footnotes, _ = extract_footnotes_from_paragraph(para, FOOTNOTE_CONFIG)
                all_footnotes.extend(footnotes)
            except Exception as exc:
                phase4_errors.append(f"para {para.paragraph_id}: {exc}")
        if phase4_errors:
            result["errors"]["phase4"] = "; ".join(phase4_errors[:5])
            logger.warning(
                "Phase 4 errors for talk_id=%d (%d errors): %s",
                talk_id,
                len(phase4_errors),
                phase4_errors[0],
            )
        else:
            logger.debug("Phase 4 OK — talk_id=%d footnotes=%d", talk_id, len(all_footnotes))
    except Exception as exc:
        result["errors"]["phase4"] = str(exc)
        logger.error("Phase 4 error for talk_id=%d: %s", talk_id, exc)

    # Phase 5: Validation
    try:
        from models.citation_data import CitationData
        from models.footnote_data import FootnoteData

        talk_citations = TalkCitations(
            talk_id=talk_id,
            citations=[],
            total_citations=0,
            extraction_success=True,
        )
        talk_footnotes = TalkFootnotes(
            talk_id=talk_id,
            footnotes=[],
            total_footnotes=0,
            extraction_success=True,
        )
        validation = validate_talk(metadata, para_result, talk_citations, talk_footnotes)
        if validation.warnings:
            result["warnings"] = list(validation.warnings)
        logger.debug("Phase 5 OK — talk_id=%d", talk_id)
    except Exception as exc:
        result["errors"]["phase5"] = str(exc)
        logger.error("Phase 5 error for talk_id=%d: %s", talk_id, exc)

    return result


def main() -> None:
    # Load talk_ids from config
    if not AUDIT_CONFIG_PATH.exists():
        logger.error("Audit config not found: %s", AUDIT_CONFIG_PATH)
        sys.exit(1)

    with open(AUDIT_CONFIG_PATH, encoding="utf-8") as f:
        talk_ids = json.load(f)

    if not talk_ids:
        print(f"No talk_ids in {AUDIT_CONFIG_PATH}")
        print("Populate config/audit_sample.json with a list of talk_id integers before running.")
        sys.exit(0)

    print(f"Running audit on {len(talk_ids)} talk(s)...")
    print()

    results = []
    for talk_id in talk_ids:
        logger.info("Processing talk_id=%d", talk_id)
        result = _run_talk(talk_id)
        results.append(result)

    # Summary
    total = len(results)
    errored = [r for r in results if r["errors"]]
    clean = total - len(errored)

    print(f"Audit complete: {total} talks processed, {clean} clean, {len(errored)} with errors")
    print()

    if errored:
        print("Talks with errors:")
        for r in errored:
            error_phases = ", ".join(
                f"phase{p}={msg}" for p, msg in r["errors"].items()
            )
            print(f"  talk_id={r['talk_id']}: {error_phases}")
    else:
        print("No errors found.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    main()
