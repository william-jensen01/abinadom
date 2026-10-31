"""
Full Pipeline Example: Run all five phases for one or more talks.

Usage examples:
    # Single talk
    pipenv run py examples/pipeline_example.py --talk-id 1234

    # Multiple talks
    pipenv run py examples/pipeline_example.py --talk-id 1234 5678 9012

    # All talks (optionally capped)
    pipenv run py examples/pipeline_example.py --all
    pipenv run py examples/pipeline_example.py --all --limit 50

    # Filter by conference
    pipenv run py examples/pipeline_example.py --conference-id 42

    # Verbose: show paragraphs, citations, footnotes per talk
    pipenv run py examples/pipeline_example.py --talk-id 1234 --verbose

    # Suppress clean talks, only print errors/warnings
    pipenv run py examples/pipeline_example.py --all --errors-only
"""

import argparse
import logging
import sys
import textwrap
from pathlib import Path
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str(Path(__file__).parent.parent))

from db import core_db, content_db
from config.schemas import PARAGRAPH_CONFIG
from extractors.talk_metadata import (
    fetch_all_talks,
    fetch_talk_by_id,
    fetch_talks_by_conference,
    extract_talk_metadata,
)
from extractors.citations import fetch_all_books
from extractors.validation import validate_talk
from extractors.pipeline import process_talk_pipeline


# =============================================================================
# Argument parsing
# =============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full extraction pipeline (phases 1–5) for LDS talks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Target selection (pick one):
              --talk-id ID [ID ...]   one or more talk IDs
              --all                   all talks in the database
              --conference-id ID      all talks in a specific conference

            Examples:
              %(prog)s --talk-id 1234
              %(prog)s --talk-id 1234 5678 --verbose
              %(prog)s --all --limit 100 --errors-only
              %(prog)s --conference-id 42
            """
        ),
    )

    # --- Target selection ---
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--talk-id",
        "-t",
        nargs="+",
        type=int,
        metavar="ID",
        help="One or more talk IDs to process",
    )
    target.add_argument(
        "--all",
        action="store_true",
        help="Process all talks in the database",
    )
    target.add_argument(
        "--conference-id",
        "-c",
        type=int,
        metavar="ID",
        help="Process all talks from a specific conference",
    )

    # --- Filters / limits ---
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max number of talks to process (useful with --all or --conference-id)",
    )

    # --- Output control ---
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed per-talk breakdown (paragraphs, citations, footnotes)",
    )
    parser.add_argument(
        "--errors-only",
        action="store_true",
        help="Only print talks that have errors or warnings",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING)",
    )

    return parser.parse_args()


# =============================================================================
# Talk row resolution
# =============================================================================


def resolve_rows(args: argparse.Namespace) -> list:
    """Return a list of raw DB rows based on the target selection args."""
    if args.talk_id:
        rows = []
        for tid in args.talk_id:
            row = fetch_talk_by_id(core_db, tid)
            if row is None:
                print(f"[WARN] talk_id={tid} not found in database — skipping")
            else:
                rows.append(row)
        return rows

    if args.conference_id:
        return fetch_talks_by_conference(core_db, args.conference_id, limit=args.limit)

    # --all
    return fetch_all_talks(core_db, limit=args.limit)


# =============================================================================
# Per-talk output helpers
# =============================================================================


def print_talk_header(i: int, total: int, talk_id: int, metadata) -> None:
    title = getattr(metadata, "title", "?")
    speaker = getattr(metadata, "speaker_name", "?")
    year = getattr(metadata, "conference_year", "?")
    print(f"\n[{i}/{total}] talk_id={talk_id}  ({year})  {speaker!r}  —  {title!r}")


def print_verbose_detail(result, report) -> None:
    """Print per-phase breakdown when --verbose is active."""
    metadata = result.metadata
    paras = result.paragraphs
    cites = result.citations
    fns = result.footnotes

    print(result)

    print(f"Metadata")
    print(f"  talk_id: {metadata.talk_id}")
    print(f"  title: {metadata.title}")
    print(f"  speaker_name: {metadata.speaker_name}")
    print(f"  speaker_role: {metadata.speaker_role_id}")

    print(
        f"  Paragraphs  : {paras.total_paragraphs}  "
        f"(words={paras.total_words}, ok={paras.extraction_success})"
    )
    # for p in paras.paragraphs[:3]:
    for p in paras.paragraphs:
        # snippet = (p.text or "")[:80].replace("\n", " ")
        snippet = p.text
        print(f"para #{p.paragraph_number}:")
        print(f"{snippet}\n")
    # if len(paras.paragraphs) > 3:
    #     print(f"    ... and {len(paras.paragraphs) - 3} more")

    print(f"  Citations   : {cites.total_citations}  (ok={cites.extraction_success})")
    for c in cites.citations[:3]:
        print(
            f"    cite #{c.citation_id}: para={c.paragraph_id}  ref={c.citation_text_raw!r}"
        )
        print(f"    Raw: `{c.citation_text_raw}`")
    if len(cites.citations) > 3:
        print(f"    ... and {len(cites.citations) - 3} more")

    print(f"  Footnotes   : {fns.total_footnotes}  (ok={fns.extraction_success})")
    for fn in fns.footnotes[:3]:
        snippet = (fn.footnote_text_raw or "")[:80]
        print(f"    fn #{fn.footnote_number}: {snippet!r}")
    if len(fns.footnotes) > 3:
        print(f"    ... and {len(fns.footnotes) - 3} more")

    print(
        f"  Validation  : {'VALID' if report.is_valid else 'INVALID'}  "
        f"checks_passed={report.stats.get('cross_collection_checks_passed', '?')}"
    )


def print_diagnostics(all_errors: list, all_warnings: list) -> None:
    for e in all_errors:
        print(f"    [ERROR] {e}")
    for w in all_warnings:
        print(f"    [WARN]  {w}")


# =============================================================================
# Main pipeline loop
# =============================================================================


def run_pipeline(args: argparse.Namespace) -> None:
    print("Loading book cache...")
    book_cache = fetch_all_books(core_db)

    print("Resolving target talks...")
    rows = resolve_rows(args)
    total = len(rows)

    if total == 0:
        print("No talks found. Check your arguments.")
        return

    print(f"Processing {total} talk(s)...\n")

    talk_errors: list[tuple[int, list[str]]] = []
    talk_warnings: list[tuple[int, list[str]]] = []
    talk_valid = 0
    talk_invalid = 0

    for i, row in enumerate(rows, 1):
        talk_id = row.get("talk_id", "?")

        # --- Talk metadata ---
        try:
            metadata = extract_talk_metadata(row)
        except Exception as e:
            talk_errors.append((talk_id, [f"Talk metadata failed: {e}"]))
            print(f"[{i}/{total}] talk_id={talk_id}  TALK METADATA ERROR: {e}")
            continue

        # --- Paragraphs, citations, footnotes ---
        try:
            result = process_talk_pipeline(
                content_db=content_db,
                core_db=core_db,
                talk_id=talk_id,
                book_cache=book_cache,
                config=PARAGRAPH_CONFIG,
            )
        except Exception as e:
            talk_errors.append((talk_id, [f"Pipeline (phases 2–4) crashed: {e}"]))
            print(f"[{i}/{total}] talk_id={talk_id}  PIPELINE CRASH: {e}")
            continue

        # --- Validation ---
        try:
            report = validate_talk(
                metadata,
                result.paragraphs,
                result.citations,
                result.footnotes,
                db=core_db,
            )
        except Exception as e:
            talk_errors.append((talk_id, [f"Validation failed: {e}"]))
            print(f"[{i}/{total}] talk_id={talk_id}  VALIDATION ERROR: {e}")
            continue

        # --- Collect diagnostics ---
        all_errors = result.errors + report.errors
        all_warnings = result.warnings + report.warnings
        is_valid = report.is_valid and not all_errors

        if all_errors:
            talk_errors.append((talk_id, all_errors))
            talk_invalid += 1
        else:
            talk_valid += 1

        if all_warnings:
            talk_warnings.append((talk_id, all_warnings))

        # --- Output ---
        has_issues = bool(all_errors or all_warnings)
        if not args.errors_only or has_issues:
            print_talk_header(i, total, talk_id, metadata)

            if args.verbose:
                print_verbose_detail(result, report)

            status = "VALID" if is_valid else "INVALID"
            print(
                f"  Status: {status}  "
                f"paras={result.paragraphs.total_paragraphs}  "
                f"cites={result.citations.total_citations}  "
                f"fns={result.footnotes.total_footnotes}  "
                f"errors={len(all_errors)}  warnings={len(all_warnings)}"
            )
            if has_issues:
                print_diagnostics(all_errors, all_warnings)

    # ==========================================================================
    # Summary
    # ==========================================================================
    print()
    print("=" * 60)
    print("Pipeline complete")
    print("=" * 60)
    print(f"  Total talks processed : {total}")
    print(f"  Valid                 : {talk_valid}")
    print(f"  Invalid               : {talk_invalid}")
    print(f"  Talks with errors     : {len(talk_errors)}")
    print(f"  Talks with warnings   : {len(talk_warnings)}")

    if talk_errors:
        print()
        print("Talks with errors:")
        for tid, errs in talk_errors:
            for e in errs:
                print(f"  talk_id={tid}: {e}")


# =============================================================================
# Entry point
# =============================================================================


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
    )

    run_pipeline(args)


if __name__ == "__main__":
    main()
