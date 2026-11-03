# -*- coding: utf-8 -*-
"""
Full pipeline orchestrator script.

Runs every extraction stage (talk metadata → validation via process_talk_pipeline,
then loading via load_talk_bundles) over all General Conference talks in the database.

Features:
  - Resume from last successfully flushed talk (skip-if-processed via Weaviate)
  - --force flag to re-process already-loaded talks
  - Weaviate writes buffered across talks by default (--unbuffered to disable)
  - Talks whose Weaviate inserts fail are recorded in failed_talks.json
  - Extraction + validation run in parallel worker processes (--workers)
  - --talk-ids / --from-failed to redo specific talks (clean delete + reload)
  - tqdm progress bar (no per-talk INFO log lines)
  - Incremental failed_talks.json writes after each failure
  - Final summary with processed/skipped/failed/validation-failed counts

Usage:
    pipenv run py scripts/run_pipeline.py
    pipenv run py scripts/run_pipeline.py --force
    pipenv run py scripts/run_pipeline.py --unbuffered
    pipenv run py scripts/run_pipeline.py --workers 1
    pipenv run py scripts/run_pipeline.py --talk-ids 150 451
    pipenv run py scripts/run_pipeline.py --from-failed
"""

import argparse
import itertools
import json
import logging
import multiprocessing
import os
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Tuple

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from db import content_db, core_db
from config.schemas import PARAGRAPH_CONFIG
from config.embedding import get_embedding_function, resolve_embedding_url
from extractors.pipeline import process_talk_pipeline
from extractors.citations import fetch_all_books
from extractors.validation import validate_talk
from config.weaviate_client import get_weaviate_client
from loaders.weaviate_loader import WeaviateLoader

logger = logging.getLogger(__name__)

FAILED_TALKS_PATH = Path(__file__).parent.parent / "data" / "failed_talks.json"

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

# Extraction outcome sent back from a worker: (talk_id, (kind, payload)) where
# kind is "ok" (payload = TalkBundle), "validation" (payload = error list) or
# "error" (payload = message).
Outcome = Tuple[int, Tuple[str, Any]]

# Per-process book cache, filled by _init_worker()
_book_cache: Dict[int, Any] = {}


def _get_all_gc_talk_ids() -> List[int]:
    """
    Return all General Conference talk IDs from the database.

    Uses INNER JOIN conference_talk to get only GC talks (approx. 5,838),
    not all talks in the database (approx. 7,659).
    """
    rows = core_db.select(
        "SELECT t.ID FROM talk t INNER JOIN conference_talk ct ON ct.TalkID = t.ID ORDER BY t.ID"
    )
    return [row["ID"] for row in rows]


def _filter_gc_talk_ids(talk_ids: List[int]) -> List[int]:
    """
    Return the subset of talk_ids that are General Conference talks, in the
    order given, with duplicates removed.
    """
    unique_ids = list(dict.fromkeys(talk_ids))
    if not unique_ids:
        return []
    placeholders = ",".join("?" * len(unique_ids))
    rows = core_db.select(
        "SELECT t.ID FROM talk t INNER JOIN conference_talk ct ON ct.TalkID = t.ID "
        f"WHERE t.ID IN ({placeholders})",
        unique_ids,
    )
    found = {row["ID"] for row in rows}
    return [tid for tid in unique_ids if tid in found]


def _load_failed_talks() -> List[Dict[str, Any]]:
    """Read failed_talks.json, or return [] if it doesn't exist."""
    if not FAILED_TALKS_PATH.exists():
        return []
    with open(FAILED_TALKS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _write_failed_talks(failed_talks: List[Dict[str, Any]]) -> None:
    FAILED_TALKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FAILED_TALKS_PATH, "w", encoding="utf-8") as f:
        json.dump(failed_talks, f, indent=2, ensure_ascii=False)


def _init_worker() -> None:
    """Prepare a process for extraction: logging and the book cache."""
    global _book_cache
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING, format=LOG_FORMAT)
    _book_cache = fetch_all_books(core_db)


def _extract_talk(talk_id: int) -> Outcome:
    """
    Extract and validate one talk. Runs in a worker process.

    Never raises: any failure comes back as an "error" outcome so the main
    process can record it against the right talk.
    """
    try:
        result = process_talk_pipeline(
            content_db, core_db, talk_id, _book_cache, PARAGRAPH_CONFIG
        )
        if not result.success:
            return talk_id, ("error", "; ".join(result.errors))

        validation = validate_talk(
            result.metadata,
            result.paragraphs,
            result.citations,
            result.footnotes,
            db=core_db,
        )
        if not validation.is_valid:
            return talk_id, ("validation", validation.errors)

        bundle = (
            result.metadata,
            result.paragraphs,
            result.citations,
            result.footnotes,
            validation,
        )
        return talk_id, ("ok", bundle)
    except Exception as exc:
        logger.error("talk_id=%d failed: %s", talk_id, exc)
        return talk_id, ("error", str(exc))


def _iter_extractions(
    talk_ids: Iterable[int],
    workers: int,
    extract: Callable[[int], Outcome] = _extract_talk,
    initializer: Callable[[], None] = _init_worker,
) -> Iterator[Outcome]:
    """
    Yield extraction outcomes for talk_ids, in completion order.

    workers <= 1 runs in this process. Otherwise a spawn-based process pool
    does the work, with at most workers * 4 talks in flight so finished
    bundles can't pile up in memory faster than the loader drains them.
    """
    if workers <= 1:
        initializer()
        for talk_id in talk_ids:
            yield extract(talk_id)
        return

    remaining = iter(talk_ids)
    pool = ProcessPoolExecutor(
        max_workers=workers,
        # spawn, not fork: the parent holds gRPC/HTTP client threads
        mp_context=multiprocessing.get_context("spawn"),
        initializer=initializer,
    )
    in_flight: Dict[Any, int] = {}

    def submit(n: int) -> None:
        for talk_id in itertools.islice(remaining, n):
            in_flight[pool.submit(extract, talk_id)] = talk_id

    try:
        submit(workers * 4)
        while in_flight:
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                talk_id = in_flight.pop(future)
                submit(1)
                try:
                    yield future.result()
                except BrokenProcessPool:
                    raise
                except Exception as exc:
                    # e.g. the result couldn't be pickled back to this process
                    yield talk_id, ("error", f"worker: {exc}")
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _record_failure(talk_id: int, error: str, failed_talks: list) -> None:
    """
    Append a failure record to the failed_talks list and write it to disk.

    Writes incrementally after each failure so the file survives a mid-run kill.

    Args:
        talk_id:      The talk ID that failed.
        error:        Error message or description.
        failed_talks: The in-memory list of failure dicts (mutated in place).
    """
    failed_talks.append({"talk_id": talk_id, "error": error})
    _write_failed_talks(failed_talks)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full LDS pipeline over all General Conference talks."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process already-loaded talks (skip the Weaviate existence check)",
    )
    parser.add_argument(
        "--unbuffered",
        action="store_true",
        help="Write each talk to Weaviate as soon as it is extracted "
        "(default: buffer objects across talks and bulk-flush)",
    )
    # Buffering is now the default; --buffered is kept so old commands still work
    parser.add_argument("--buffered", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 1,
        metavar="N",
        help="Extraction worker processes (default: CPU count; 1 = no pool)",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--talk-ids",
        nargs="+",
        type=int,
        metavar="ID",
        help="Redo only these talks: delete their Weaviate objects and reload "
        "(always reprocesses; no --force needed)",
    )
    target.add_argument(
        "--from-failed",
        action="store_true",
        help=f"Redo the talks listed in {FAILED_TALKS_PATH.name} (same as --talk-ids)",
    )
    args = parser.parse_args()

    # --- Resolve targeted talk IDs (before any heavy setup) ---
    targeted = args.talk_ids is not None or args.from_failed
    failed_talks: List[Dict[str, Any]] = []
    if targeted:
        if args.from_failed:
            requested = [entry["talk_id"] for entry in _load_failed_talks()]
            if not requested:
                print(f"No talks in {FAILED_TALKS_PATH}; nothing to do.")
                return
        else:
            requested = args.talk_ids
        target_ids = _filter_gc_talk_ids(requested)
        unknown = [tid for tid in dict.fromkeys(requested) if tid not in set(target_ids)]
        if unknown:
            print(f"[WARN] Not General Conference talks, skipping: {unknown}")
        if not target_ids:
            print("No valid talk IDs to process.")
            return
        # Merge into the existing failure log: keep other talks' entries,
        # drop entries for the talks being redone (re-added if they fail again).
        target_set = set(target_ids)
        failed_talks = [
            entry for entry in _load_failed_talks() if entry["talk_id"] not in target_set
        ]

    start_time = time.time()

    embedding_url = resolve_embedding_url()
    embedding_fn = get_embedding_function(url=embedding_url)
    query_embedding_fn = get_embedding_function(url=embedding_url, task="query")

    client = get_weaviate_client()
    with WeaviateLoader(
        client=client,
        embed_fn=embedding_fn,
        buffered=not args.unbuffered,
        query_embed_fn=query_embedding_fn,
    ) as loader:
        all_talk_ids = target_ids if targeted else _get_all_gc_talk_ids()

        # --- Counters ---
        failed_count: int = 0
        validation_failed_count: int = 0
        load_failed_count: int = 0
        processed_count: int = 0

        def record_load_failures() -> None:
            """Record talks whose Weaviate inserts failed in the last flush."""
            nonlocal load_failed_count
            for failed_id, error in loader.pop_insert_failures().items():
                tqdm.write(f"[ERROR] talk_id={failed_id}: {error}")
                _record_failure(failed_id, error, failed_talks)
                load_failed_count += 1

        # One scan of loaded talk IDs instead of a talk_exists() call per talk
        if targeted or args.force:
            loaded_ids: set = set()
        else:
            loaded_ids = loader.existing_talk_ids()

        to_process = [tid for tid in all_talk_ids if tid not in loaded_ids]
        skipped_count = len(all_talk_ids) - len(to_process)

        # --- Main loop: workers extract + validate, this process loads ---
        outcomes = _iter_extractions(to_process, args.workers)
        for talk_id, (kind, payload) in tqdm(
            outcomes, total=len(to_process), unit="talk", desc="Pipeline"
        ):
            if kind == "error":
                tqdm.write(f"[ERROR] talk_id={talk_id}: {payload}")
                _record_failure(talk_id, payload, failed_talks)
                failed_count += 1
                continue

            if kind == "validation":
                tqdm.write(f"[WARN] talk_id={talk_id} validation failed")
                _record_failure(talk_id, f"validation: {payload}", failed_talks)
                validation_failed_count += 1
                continue

            try:
                # Targeted redo: clear old objects so nothing is left orphaned.
                # Done only after extraction + validation succeed, so a failed
                # redo leaves the previous version in place.
                if targeted:
                    loader.delete_talk(talk_id)

                # Embed and hand to the loader, which does the only buffering
                loader.load(payload)
                processed_count += 1

            except Exception as exc:
                logger.error("talk_id=%d failed: %s", talk_id, exc)
                tqdm.write(f"[ERROR] talk_id={talk_id}: {exc}")
                _record_failure(talk_id, str(exc), failed_talks)
                failed_count += 1

            record_load_failures()

        # --- Final flush: write whatever the loader still holds ---
        loader.flush()
        record_load_failures()

    # Targeted runs rewrite the merged log so talks that now succeed are removed
    if targeted:
        _write_failed_talks(failed_talks)

    # --- Final summary ---
    elapsed = time.time() - start_time
    print(f"\nRun complete in {elapsed:.1f}s")
    total_label = "Selected talks:   " if targeted else "Total GC talks:   "
    print(f"  {total_label} {len(all_talk_ids)}")
    print(f"  Processed:         {processed_count - load_failed_count}")
    print(f"  Skipped (cached):  {skipped_count}")
    print(f"  Failed:            {failed_count}")
    print(f"  Validation failed: {validation_failed_count}")
    print(f"  Load failed:       {load_failed_count}")
    if failed_talks:
        print(f"  Failed talks log:  {FAILED_TALKS_PATH}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format=LOG_FORMAT)
    main()
