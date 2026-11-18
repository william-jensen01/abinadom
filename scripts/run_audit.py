# -*- coding: utf-8 -*-
"""
Bug audit driver script.

Reads talk_ids from config/audit_sample.json and runs each talk through
every stage of the extraction pipeline, reporting any errors per talk per stage.

Usage:
    pipenv run python scripts/run_audit.py

Runs on the host only. The tools image leaves config/audit_sample.json
out on purpose, so this script cannot run in the container.

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
from extractors.talk_metadata import fetch_talk_by_id, extract_talk_metadata
from extractors.paragraphs import fetch_talk_html, extract_paragraphs
from extractors.citations import extract_citations_from_paragraph
from extractors.footnotes import extract_footnotes_from_paragraph
from extractors.validation import validate_talk

logger = logging.getLogger(__name__)

AUDIT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "audit_sample.json"


def _run_talk(talk_id: int) -> Dict[str, Any]:
    """Run a single talk through every pipeline stage and return a result summary."""
    result: Dict[str, Any] = {
        "talk_id": talk_id,
        "errors": {},
        "warnings": [],
    }

    # Talk metadata
    try:
        row = fetch_talk_by_id(core_db, talk_id)
        if row is None:
            result["errors"]["talk_metadata"] = f"talk_id {talk_id} not found in database"
            return result
        metadata = extract_talk_metadata(row)
        logger.debug("Talk metadata OK — talk_id=%d title=%s", talk_id, metadata.title)
    except Exception as exc:
        result["errors"]["talk_metadata"] = str(exc)
        logger.error("Talk metadata error for talk_id=%d: %s", talk_id, exc)
        return result

    # Paragraph extraction
    try:
        html = fetch_talk_html(content_db, talk_id)
        if not html:
            result["errors"]["paragraphs"] = "no HTML content found"
            return result
        para_result = extract_paragraphs(talk_id, html, PARAGRAPH_CONFIG)
        if not para_result.extraction_success:
            result["errors"]["paragraphs"] = "; ".join(para_result.extraction_errors)
            logger.warning(
                "Paragraph extraction failed for talk_id=%d: %s",
                talk_id,
                para_result.extraction_errors,
            )
            return result
        logger.debug(
            "Paragraphs OK — talk_id=%d paragraphs=%d",
            talk_id,
            para_result.total_paragraphs,
        )
    except Exception as exc:
        result["errors"]["paragraphs"] = str(exc)
        logger.error("Paragraphs error for talk_id=%d: %s", talk_id, exc)
        return result

    # Citation extraction (per paragraph)
    all_citations = []
    citation_errors: List[str] = []
    try:
        for para in para_result.paragraphs:
            if not para.text_raw:
                continue
            try:
                citations = extract_citations_from_paragraph(para, CITATION_CONFIG)
                all_citations.extend(citations)
            except Exception as exc:
                citation_errors.append(f"para {para.paragraph_id}: {exc}")
        if citation_errors:
            result["errors"]["citations"] = "; ".join(citation_errors[:5])
            logger.warning(
                "Citations errors for talk_id=%d (%d errors): %s",
                talk_id,
                len(citation_errors),
                citation_errors[0],
            )
        else:
            logger.debug("Citations OK — talk_id=%d citations=%d", talk_id, len(all_citations))
    except Exception as exc:
        result["errors"]["citations"] = str(exc)
        logger.error("Citations error for talk_id=%d: %s", talk_id, exc)

    # Footnote extraction (per paragraph)
    all_footnotes = []
    footnote_errors: List[str] = []
    try:
        for para in para_result.paragraphs:
            if not para.text_raw:
                continue
            try:
                footnotes, _ = extract_footnotes_from_paragraph(para, FOOTNOTE_CONFIG)
                all_footnotes.extend(footnotes)
            except Exception as exc:
                footnote_errors.append(f"para {para.paragraph_id}: {exc}")
        if footnote_errors:
            result["errors"]["footnotes"] = "; ".join(footnote_errors[:5])
            logger.warning(
                "Footnotes errors for talk_id=%d (%d errors): %s",
                talk_id,
                len(footnote_errors),
                footnote_errors[0],
            )
        else:
            logger.debug("Footnotes OK — talk_id=%d footnotes=%d", talk_id, len(all_footnotes))
    except Exception as exc:
        result["errors"]["footnotes"] = str(exc)
        logger.error("Footnotes error for talk_id=%d: %s", talk_id, exc)

    # Validation
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
        logger.debug("Validation OK — talk_id=%d", talk_id)
    except Exception as exc:
        result["errors"]["validation"] = str(exc)
        logger.error("Validation error for talk_id=%d: %s", talk_id, exc)

    return result


def main() -> None:
    # Load talk_ids from config
    if not AUDIT_CONFIG_PATH.exists():
        print(
            f"Audit config not found: {AUDIT_CONFIG_PATH}\n"
            "run_audit.py runs on the host, where config/audit_sample.json lives: "
            "pipenv run python scripts/run_audit.py",
            file=sys.stderr,
        )
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
