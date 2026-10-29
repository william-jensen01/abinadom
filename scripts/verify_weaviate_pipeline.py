# -*- coding: utf-8 -*-
"""
Post-pipeline verification script (Weaviate).

Runs VER-01 through VER-05 against Weaviate collections and writes
a structured JSON report.

Checks:
  VER-01: Record count verification (talk count must match SQLite INNER JOIN)
  VER-02: Semantic search spot-check (5 queries; manual review — requires --embedding)
  VER-03: Metadata filter verification (speaker, year, session, compound)
  VER-04: Foreign key integrity spot-check (paragraphs and citations -> talks)
  VER-05: Topics metadata verification (topics list, title, speaker_name coverage)

Usage:
    pipenv run py scripts/verify_weaviate_pipeline.py
    pipenv run py scripts/verify_weaviate_pipeline.py --output data/my_report.json
    pipenv run py scripts/verify_weaviate_pipeline.py --embedding
"""

import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

import weaviate
from weaviate.classes.query import Filter
from tqdm import tqdm

from db import core_db
from config.pipeline_config import WEAVIATE_COLLECTION_NAMES
from config.embedding import get_embedding_function

logger = logging.getLogger(__name__)

FAILED_TALKS_PATH = Path(__file__).parent.parent / "data" / "failed_talks.json"
DEFAULT_REPORT_PATH = Path(__file__).parent.parent / "data" / "weaviate_verification_report.json"


# =============================================================================
# VER-01: Count verification
# =============================================================================


def check_counts(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    VER-01: Verify record counts across all 4 Weaviate collections.

    The expected talk count is derived from SQLite at runtime via INNER JOIN
    conference_talk (GC-only talks, approx. 5,838).

    Returns:
        Dict with keys: passed, counts, failed_talks_file
    """
    print("VER-01: Count verification ...")

    # Derive expected talk count from SQLite at runtime
    talk_rows = core_db.select(
        "SELECT COUNT(*) as cnt FROM talk t INNER JOIN conference_talk ct ON ct.TalkID = t.ID"
    )
    expected_talk_count = talk_rows[0]["cnt"]

    # Get SQLite citation baseline (informational only)
    citation_rows = core_db.select("SELECT COUNT(*) as cnt FROM citation")
    sqlite_citation_count = citation_rows[0]["cnt"]

    # Fetch Weaviate collection counts
    talks_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["talks"])
    paras_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["paragraphs"])
    citations_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["citations"])
    footnotes_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["footnotes"])

    weaviate_talk_count = talks_col.aggregate.over_all(total_count=True).total_count
    weaviate_para_count = paras_col.aggregate.over_all(total_count=True).total_count
    weaviate_citation_count = citations_col.aggregate.over_all(total_count=True).total_count
    weaviate_footnote_count = footnotes_col.aggregate.over_all(total_count=True).total_count

    # Hard pass/fail: talks must match exactly
    talks_pass = weaviate_talk_count == expected_talk_count
    paras_pass = weaviate_para_count > 0
    citations_pass = weaviate_citation_count > 0
    footnotes_pass = weaviate_footnote_count > 0
    overall_passed = talks_pass and paras_pass and citations_pass and footnotes_pass

    citation_delta = weaviate_citation_count - sqlite_citation_count

    # Check for failed_talks.json
    failed_talks_info: Optional[Dict[str, Any]] = None
    if FAILED_TALKS_PATH.exists():
        try:
            with open(FAILED_TALKS_PATH, encoding="utf-8") as f:
                failed_list = json.load(f)
            failed_talks_info = {
                "path": str(FAILED_TALKS_PATH),
                "count": len(failed_list),
                "talks": failed_list[:10],  # truncate for report
            }
        except Exception as exc:
            failed_talks_info = {"path": str(FAILED_TALKS_PATH), "error": str(exc)}

    status = "PASS" if overall_passed else "FAIL"
    print(f"VER-01: Count verification ... {status}")
    print(f"  {WEAVIATE_COLLECTION_NAMES['talks']}:            {weaviate_talk_count:>8} (expected {expected_talk_count}) {'OK' if talks_pass else 'MISMATCH'}")
    print(f"  {WEAVIATE_COLLECTION_NAMES['paragraphs']}:  {weaviate_para_count:>8} {'OK' if paras_pass else 'EMPTY'}")
    print(f"  {WEAVIATE_COLLECTION_NAMES['citations']}:   {weaviate_citation_count:>8} (SQLite baseline {sqlite_citation_count}, delta {citation_delta:+}) {'OK' if citations_pass else 'EMPTY'}")
    print(f"  {WEAVIATE_COLLECTION_NAMES['footnotes']}:   {weaviate_footnote_count:>8} {'OK' if footnotes_pass else 'EMPTY'}")
    if failed_talks_info:
        print(f"  failed_talks.json:           {failed_talks_info.get('count', '?')} entries")

    return {
        "passed": overall_passed,
        "counts": {
            WEAVIATE_COLLECTION_NAMES["talks"]: {
                "weaviate": weaviate_talk_count,
                "sqlite_expected": expected_talk_count,
                "match": talks_pass,
            },
            WEAVIATE_COLLECTION_NAMES["paragraphs"]: {
                "weaviate": weaviate_para_count,
                "has_records": paras_pass,
            },
            WEAVIATE_COLLECTION_NAMES["citations"]: {
                "weaviate": weaviate_citation_count,
                "sqlite_baseline": sqlite_citation_count,
                "delta": citation_delta,
                "has_records": citations_pass,
            },
            WEAVIATE_COLLECTION_NAMES["footnotes"]: {
                "weaviate": weaviate_footnote_count,
                "has_records": footnotes_pass,
            },
        },
        "failed_talks_file": failed_talks_info,
    }


# =============================================================================
# VER-02: Semantic search spot-check
# =============================================================================


def check_semantic_search(client: weaviate.WeaviateClient, ef: Any) -> Dict[str, Any]:
    """
    VER-02: Run 5 semantic queries (3 topical + 2 scriptural) against
    ConferenceTalkParagraphs and print top 5 results each.

    Results are for manual review only. VER-02 is skipped (not failed) if
    no embedding function is provided (--embedding flag not set).

    Returns:
        Dict with keys: skipped, reason (if skipped), or queries (list of result dicts)
    """
    print("VER-02: Semantic search ...")

    if ef is None:
        reason = "embedding server required — run with --embedding to enable"
        print(f"VER-02: Semantic search ... SKIPPED ({reason})")
        return {"skipped": True, "reason": reason, "queries": []}

    queries = [
        "the Atonement of Jesus Christ forgiveness of sins",
        "eternal family temple covenants",
        "faith and repentance turning to God",
        "Mosiah 3:19 natural man enemy to God",
        "John 3:16 God so loved the world",
    ]

    try:
        paras_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["paragraphs"])

        query_results: List[Dict[str, Any]] = []

        for query in queries:
            print(f"\n  Query: \"{query}\"")

            # Get embedding vector for the query
            embedding = ef([query])[0]

            results = paras_col.query.near_vector(
                near_vector=embedding,
                limit=5,
                return_properties=["text", "talk_id", "speaker_name", "conference_year", "title"],
            )

            hits: List[Dict[str, Any]] = []
            for i, obj in enumerate(results.objects, start=1):
                props = obj.properties
                talk_id = props.get("talk_id")
                speaker_name = props.get("speaker_name", "")
                conference_year = props.get("conference_year", "")
                title = props.get("title", "")
                para_text = (props.get("text") or "")[:150]

                print(f"  {i}. talk_id={talk_id} | {speaker_name} | {conference_year} | {title}")
                print(f"     Para: {para_text}")

                hits.append({
                    "rank": i,
                    "uuid": str(obj.uuid),
                    "talk_id": talk_id,
                    "speaker_name": speaker_name,
                    "conference_year": conference_year,
                    "title": title,
                    "para_text_preview": para_text,
                })

            query_results.append({"query": query, "hits": hits})

        print("\nVER-02: Semantic search ... (manual review required)")
        return {"skipped": False, "queries": query_results}

    except Exception as exc:
        reason = f"embedding server unavailable or query error: {exc}"
        print(f"VER-02: Semantic search ... SKIPPED ({reason})")
        return {"skipped": True, "reason": reason, "queries": []}


# =============================================================================
# VER-03: Metadata filter verification
# =============================================================================


def check_metadata_filters(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    VER-03: Verify metadata filtering on ConferenceTalkParagraphs collection.

    Runs 4 filter tests (speaker, year, session, compound) using Weaviate v4
    Filter API and verifies that matching objects satisfy the filter criteria.

    Returns:
        Dict with keys: passed, filters (list of filter results)
    """
    print("VER-03: Metadata filter ...")

    paras_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["paragraphs"])

    filter_results: List[Dict[str, Any]] = []
    all_pass = True

    # Filter 1: speaker_name LIKE *Holland*
    try:
        r1 = paras_col.query.fetch_objects(
            filters=Filter.by_property("speaker_name").like("*Holland*"),
            limit=5,
            return_properties=["speaker_name", "talk_id"],
        )
        count1 = len(r1.objects)
        # Verify objects actually match
        mismatch1 = sum(1 for o in r1.objects if "Holland" not in (o.properties.get("speaker_name") or ""))
        pass1 = count1 > 0 and mismatch1 == 0
        print(f"  Filter 1 — speaker_name LIKE '*Holland*': {count1} results {'PASS' if pass1 else 'FAIL'}")
        filter_results.append({
            "filter": "speaker_name LIKE '*Holland*'",
            "collection": WEAVIATE_COLLECTION_NAMES["paragraphs"],
            "count": count1,
            "mismatches": mismatch1,
            "passed": pass1,
        })
        if not pass1:
            all_pass = False
    except Exception as exc:
        logger.warning("Filter 1 error: %s", exc)
        filter_results.append({"filter": "speaker_name", "error": str(exc), "passed": False})
        all_pass = False

    # Filter 2: conference_year = 2020
    try:
        r2 = paras_col.query.fetch_objects(
            filters=Filter.by_property("conference_year").equal(2020),
            limit=5,
            return_properties=["conference_year", "talk_id"],
        )
        count2 = len(r2.objects)
        mismatch2 = sum(1 for o in r2.objects if o.properties.get("conference_year") != 2020)
        pass2 = count2 > 0 and mismatch2 == 0
        print(f"  Filter 2 — conference_year=2020: {count2} results {'PASS' if pass2 else 'FAIL'}")
        filter_results.append({
            "filter": "conference_year = 2020",
            "collection": WEAVIATE_COLLECTION_NAMES["paragraphs"],
            "count": count2,
            "mismatches": mismatch2,
            "passed": pass2,
        })
        if not pass2:
            all_pass = False
    except Exception as exc:
        logger.warning("Filter 2 error: %s", exc)
        filter_results.append({"filter": "conference_year", "error": str(exc), "passed": False})
        all_pass = False

    # Filter 3: conference_month = "April"
    try:
        r3 = paras_col.query.fetch_objects(
            filters=Filter.by_property("conference_month").equal("April"),
            limit=5,
            return_properties=["conference_month", "talk_id"],
        )
        count3 = len(r3.objects)
        mismatch3 = sum(1 for o in r3.objects if o.properties.get("conference_month") != "April")
        pass3 = count3 > 0 and mismatch3 == 0
        print(f"  Filter 3 — conference_month='April': {count3} results {'PASS' if pass3 else 'FAIL'}")
        filter_results.append({
            "filter": "conference_month = 'April'",
            "collection": WEAVIATE_COLLECTION_NAMES["paragraphs"],
            "count": count3,
            "mismatches": mismatch3,
            "passed": pass3,
        })
        if not pass3:
            all_pass = False
    except Exception as exc:
        logger.warning("Filter 3 error: %s", exc)
        filter_results.append({"filter": "conference_month", "error": str(exc), "passed": False})
        all_pass = False

    # Filter 4: compound — conference_year = 2020 AND conference_month = "April"
    try:
        compound_filter = (
            Filter.by_property("conference_year").equal(2020)
            & Filter.by_property("conference_month").equal("April")
        )
        r4 = paras_col.query.fetch_objects(
            filters=compound_filter,
            limit=5,
            return_properties=["conference_year", "conference_month", "talk_id"],
        )
        count4 = len(r4.objects)
        mismatch4 = sum(
            1 for o in r4.objects
            if o.properties.get("conference_year") != 2020 or o.properties.get("conference_month") != "April"
        )
        pass4 = count4 > 0 and mismatch4 == 0
        print(f"  Filter 4 — compound (year=2020 AND month=April): {count4} results {'PASS' if pass4 else 'FAIL'}")
        filter_results.append({
            "filter": "conference_year=2020 AND conference_month='April'",
            "collection": WEAVIATE_COLLECTION_NAMES["paragraphs"],
            "count": count4,
            "mismatches": mismatch4,
            "passed": pass4,
        })
        if not pass4:
            all_pass = False
    except Exception as exc:
        logger.warning("Filter 4 error: %s", exc)
        filter_results.append({"filter": "compound year+month", "error": str(exc), "passed": False})
        all_pass = False

    status = "PASS" if all_pass else "FAIL"
    print(f"VER-03: Metadata filter ... {status}")

    return {
        "passed": all_pass,
        "filters": filter_results,
    }


# =============================================================================
# VER-04: FK integrity spot-check
# =============================================================================


def _check_fk_sample(
    sample_col,
    target_col,
    id_prop: str,
    id_prefix: str,
    limit: int,
) -> dict:
    """Sample objects from sample_col and verify their id_prop resolves in target_col."""
    from weaviate.util import generate_uuid5
    sample = sample_col.query.fetch_objects(limit=limit, return_properties=[id_prop])
    hits, misses, miss_ids = 0, 0, []
    for obj in sample.objects:
        val = obj.properties.get(id_prop)
        if val is None:
            misses += 1
            continue
        uuid = generate_uuid5(f"{id_prefix}{int(val)}")
        result = target_col.query.fetch_object_by_id(uuid)
        if result is not None:
            hits += 1
        else:
            misses += 1
            miss_ids.append(val)
    return {"sampled": hits + misses, "hits": hits, "misses": misses, "miss_ids": miss_ids, "passed": misses == 0}


def check_fk_integrity(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    VER-04: FK spot-check across Weaviate collections.

    Samples 10 paragraph records and 5 citation records and verifies that
    their talk_id values resolve to an object in the talks collection via UUID.

    Returns:
        Dict with keys: passed, scans (dict of scan results)
    """
    print("VER-04: FK integrity ...")

    talks_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["talks"])
    paras_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["paragraphs"])
    citations_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["citations"])

    print("  Scanning paragraphs -> talks FK (spot-check, 10 records) ...")
    try:
        para_result = _check_fk_sample(paras_col, talks_col, "talk_id", "talk_", 10)
    except Exception as exc:
        logger.warning("Paragraph FK scan error: %s", exc)
        print(f"  Paragraphs -> talks scan error: {exc}")
        return {
            "passed": False,
            "scans": {
                "paragraphs_to_talks": {"error": str(exc), "passed": False},
                "citations_to_talks": {"sampled": 0, "hits": 0, "misses": 0, "passed": False},
            },
        }
    print(f"  Paragraphs spot-check: {para_result['hits']} hits, {para_result['misses']} misses {'PASS' if para_result['passed'] else 'FAIL'}")

    print("  Scanning citations -> talks FK (spot-check, 5 records) ...")
    try:
        cit_result = _check_fk_sample(citations_col, talks_col, "talk_id", "talk_", 5)
    except Exception as exc:
        logger.warning("Citation FK scan error: %s", exc)
        cit_result = {"sampled": 0, "hits": 0, "misses": 0, "miss_ids": [], "passed": False}
    print(f"  Citations spot-check: {cit_result['hits']} hits, {cit_result['misses']} misses {'PASS' if cit_result['passed'] else 'FAIL'}")

    overall_passed = para_result["passed"] and cit_result["passed"]
    status = "PASS" if overall_passed else "FAIL"
    print(f"VER-04: FK integrity ... {status}")

    return {
        "passed": overall_passed,
        "scans": {
            "paragraphs_to_talks": {
                "sampled": para_result["sampled"],
                "hits": para_result["hits"],
                "misses": para_result["misses"],
                "miss_talk_ids": para_result["miss_ids"],
                "passed": para_result["passed"],
            },
            "citations_to_talks": {
                "sampled": cit_result["sampled"],
                "hits": cit_result["hits"],
                "misses": cit_result["misses"],
                "miss_talk_ids": cit_result["miss_ids"],
                "passed": cit_result["passed"],
            },
        },
    }


# =============================================================================
# VER-05: Topics metadata verification
# =============================================================================


def check_topics_metadata(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """
    VER-05: Verify topics metadata flows through to Weaviate.

    Samples 5 talk records from ConferenceTalks and verifies:
      - "topics" property is a list (may be empty)
      - "title" is a non-empty string
      - "speaker_name" is a non-empty string

    Returns:
        Dict with keys: passed, details (list of per-talk check results)
    """
    print("VER-05: Topics metadata ...")

    talks_col = client.collections.use(WEAVIATE_COLLECTION_NAMES["talks"])

    try:
        sample = talks_col.query.fetch_objects(
            limit=5,
            return_properties=["title", "speaker_name", "topics"],
        )
    except Exception as exc:
        logger.warning("VER-05 fetch error: %s", exc)
        print(f"VER-05: Topics metadata ... FAIL (fetch error: {exc})")
        return {"passed": False, "error": str(exc), "details": []}

    details: List[Dict[str, Any]] = []
    all_pass = True

    for obj in sample.objects:
        props = obj.properties
        title = props.get("title") or ""
        speaker_name = props.get("speaker_name") or ""
        topics = props.get("topics")

        title_ok = bool(title.strip())
        speaker_ok = bool(speaker_name.strip())
        topics_ok = isinstance(topics, list)  # may be empty list — that is valid

        obj_pass = title_ok and speaker_ok and topics_ok
        if not obj_pass:
            all_pass = False

        details.append({
            "uuid": str(obj.uuid),
            "title": title,
            "speaker_name": speaker_name,
            "topics_type": type(topics).__name__,
            "topics_count": len(topics) if isinstance(topics, list) else None,
            "title_ok": title_ok,
            "speaker_ok": speaker_ok,
            "topics_ok": topics_ok,
            "passed": obj_pass,
        })

    checked = len(details)
    passed_count = sum(1 for d in details if d["passed"])
    status = "PASS" if all_pass else "FAIL"
    print(f"  Sampled {checked} talks: {passed_count}/{checked} have title, speaker_name, and list topics")
    print(f"VER-05: Topics metadata ... {status}")

    return {
        "passed": all_pass,
        "details": details,
    }


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post-pipeline verification (Weaviate): run VER-01 through VER-05 and write JSON report."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_REPORT_PATH),
        help="Path for the verification report JSON (default: data/weaviate_verification_report.json)",
    )
    parser.add_argument(
        "--embedding",
        action="store_true",
        default=False,
        help="Enable VER-02 semantic search via the embedding server (requires llama-server with nomic-embed-text; see EMBEDDING_URL)",
    )
    args = parser.parse_args()

    report_path = Path(args.output)

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    host = os.environ.get("WEAVIATE_HOST", "localhost")
    port = int(os.environ.get("WEAVIATE_PORT", "8080"))
    grpc_port = int(os.environ.get("WEAVIATE_GRPC_PORT", "50051"))

    print("=" * 60)
    print("Pipeline Verification (Weaviate)")
    print(f"Run timestamp: {datetime.datetime.now().isoformat()}")
    print(f"Weaviate: {host}:{port} (gRPC: {grpc_port})")
    print("=" * 60)
    print()

    # Build optional embedding function for VER-02
    ef: Any = None
    if args.embedding:
        try:
            # VER-02 embeds search queries, so use the query task prefix.
            ef = get_embedding_function(task="query")
            ef(["test"])  # reachability probe
            print("Embedding server initialized (nomic-embed-text, query task).")
        except Exception as exc:
            print(f"WARNING: --embedding requested but embedding server unavailable: {exc}")
            print("         VER-02 will be skipped.")
            ef = None

    # Connect to Weaviate with context manager
    with weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port) as wv_client:
        # Run all checks
        ver01_result = check_counts(wv_client)
        print()
        ver02_result = check_semantic_search(wv_client, ef)
        print()
        ver03_result = check_metadata_filters(wv_client)
        print()
        ver04_result = check_fk_integrity(wv_client)
        print()
        ver05_result = check_topics_metadata(wv_client)
        print()

    # Overall pass: VER-01, VER-03, VER-04, VER-05 are automated; VER-02 is manual review
    ver01_passed = ver01_result.get("passed", False)
    ver03_passed = ver03_result.get("passed", False)
    ver04_passed = ver04_result.get("passed", False)
    ver05_passed = ver05_result.get("passed", False)
    overall_passed = ver01_passed and ver03_passed and ver04_passed and ver05_passed

    automated_pass_count = sum([ver01_passed, ver03_passed, ver04_passed, ver05_passed])

    print("=" * 60)
    print(f"Overall: {automated_pass_count}/4 automated checks PASS | VER-02: manual review")
    print("=" * 60)

    # Build and write JSON report
    report = {
        "run_timestamp": datetime.datetime.now().isoformat(),
        "weaviate_host": host,
        "weaviate_port": port,
        "ver_01": ver01_result,
        "ver_02": ver02_result,
        "ver_03": ver03_result,
        "ver_04": ver04_result,
        "ver_05": ver05_result,
        "overall_passed": overall_passed,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport written to: {report_path}")
    sys.exit(0 if overall_passed else 1)


if __name__ == "__main__":
    main()
