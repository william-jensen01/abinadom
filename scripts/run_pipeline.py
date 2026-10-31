# -*- coding: utf-8 -*-
"""
Full pipeline orchestrator script.

Runs every extraction stage (talk metadata → validation via process_talk_pipeline,
then loading via load_talk_bundles) over all General Conference talks in the database.

Features:
  - Resume from last successfully flushed talk (skip-if-processed via Weaviate)
  - --force flag to re-process already-loaded talks
  - tqdm progress bar (no per-talk INFO log lines)
  - Incremental failed_talks.json writes after each failure
  - Final summary with processed/skipped/failed/validation-failed counts

Usage:
    pipenv run py scripts/run_pipeline.py
    pipenv run py scripts/run_pipeline.py --force
    pipenv run py scripts/run_pipeline.py --buffered
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from db import content_db, core_db
from config.schemas import PARAGRAPH_CONFIG
from config.pipeline_config import WEAVIATE_BATCH_SIZE
from config.embedding import get_embedding_function, resolve_embedding_url
from extractors.pipeline import process_talk_pipeline
from extractors.citations import fetch_all_books
from extractors.validation import validate_talk
from config.weaviate_client import get_weaviate_client
from loaders.weaviate_loader import WeaviateLoader
from loaders.shared_transforms import load_talk_bundles, TalkBundle

logger = logging.getLogger(__name__)

FAILED_TALKS_PATH = Path(__file__).parent.parent / "data" / "failed_talks.json"


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
    FAILED_TALKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FAILED_TALKS_PATH, "w", encoding="utf-8") as f:
        json.dump(failed_talks, f, indent=2, ensure_ascii=False)


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
        "--buffered",
        action="store_true",
        help="Buffer records across talks and bulk-flush to Weaviate (fewer round trips)",
    )
    args = parser.parse_args()

    start_time = time.time()

    book_cache = fetch_all_books(core_db)
    embedding_url = resolve_embedding_url()
    embedding_fn = get_embedding_function(url=embedding_url)
    query_embedding_fn = get_embedding_function(url=embedding_url, task="query")

    client = get_weaviate_client()
    with WeaviateLoader(
        client=client,
        embed_fn=embedding_fn,
        buffered=args.buffered,
        query_embed_fn=query_embedding_fn,
    ) as loader:
        all_talk_ids = _get_all_gc_talk_ids()

        # --- Counters and buffers ---
        pending_bundles: List[TalkBundle] = []
        processed_since_flush: int = 0
        skipped_count: int = 0
        failed_count: int = 0
        validation_failed_count: int = 0
        processed_count: int = 0
        failed_talks: List[Dict[str, Any]] = []

        # --- Main per-talk loop ---
        for talk_id in tqdm(all_talk_ids, unit="talk", desc="Pipeline"):
            if not args.force and loader.talk_exists(talk_id):
                skipped_count += 1
                continue

            try:
                # Extraction: metadata, paragraphs, citations, footnotes
                result = process_talk_pipeline(
                    content_db, core_db, talk_id, book_cache, PARAGRAPH_CONFIG
                )

                if not result.success:
                    raise RuntimeError("; ".join(result.errors))

                # Validation
                validation = validate_talk(
                    result.metadata,
                    result.paragraphs,
                    result.citations,
                    result.footnotes,
                    db=core_db,
                )

                if not validation.is_valid:
                    tqdm.write(f"[WARN] talk_id={talk_id} validation failed")
                    _record_failure(
                        talk_id,
                        f"validation: {validation.errors}",
                        failed_talks,
                    )
                    validation_failed_count += 1
                    continue

                # Build bundle for loading
                bundle: TalkBundle = (
                    result.metadata,
                    result.paragraphs,
                    result.citations,
                    result.footnotes,
                    validation,
                )
                pending_bundles.append(bundle)
                processed_since_flush += 1
                processed_count += 1

                # Batch flush: load when buffer reaches WEAVIATE_BATCH_SIZE
                if processed_since_flush >= WEAVIATE_BATCH_SIZE:
                    load_talk_bundles(pending_bundles, loader)
                    pending_bundles.clear()
                    processed_since_flush = 0

            except Exception as exc:
                logger.error("talk_id=%d failed: %s", talk_id, exc)
                tqdm.write(f"[ERROR] talk_id={talk_id}: {exc}")
                _record_failure(talk_id, str(exc), failed_talks)
                failed_count += 1

        # --- Final flush: load any remaining buffered talks ---
        if pending_bundles:
            load_talk_bundles(pending_bundles, loader)

    # --- Final summary ---
    elapsed = time.time() - start_time
    print(f"\nRun complete in {elapsed:.1f}s")
    print(f"  Total GC talks:    {len(all_talk_ids)}")
    print(f"  Processed:         {processed_count}")
    print(f"  Skipped (cached):  {skipped_count}")
    print(f"  Failed:            {failed_count}")
    print(f"  Validation failed: {validation_failed_count}")
    if failed_talks:
        print(f"  Failed talks log:  {FAILED_TALKS_PATH}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    main()
