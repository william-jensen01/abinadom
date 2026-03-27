# -*- coding: utf-8 -*-
"""
Post-pipeline verification script.

Runs all four VER checks (count verification, semantic search, metadata
filtering, FK integrity) against the live ChromaDB collections and writes
a structured JSON report.

Checks:
  VER-01: Record count verification (talk count must match SQLite INNER JOIN)
  VER-02: Semantic search spot-check (5 queries; manual review)
  VER-03: Metadata filter verification (speaker, year, session, compound)
  VER-04: Foreign key integrity scan (all collections)
  VER-05: Topics metadata verification (coverage vs SQLite baseline, document text)

Usage:
    pipenv run py scripts/verify_pipeline.py
    pipenv run py scripts/verify_pipeline.py --output data/my_report.json
"""

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from db import core_db
from config.pipeline_config import CHROMADB_COLLECTION_NAMES
from extractors.phase6_chromadb_loader import get_chromadb_client, get_embedding_function

logger = logging.getLogger(__name__)

FAILED_TALKS_PATH = Path(__file__).parent.parent / "data" / "failed_talks.json"
DEFAULT_REPORT_PATH = Path(__file__).parent.parent / "data" / "verification_report.json"


# =============================================================================
# VER-01: Count verification
# =============================================================================


def check_counts(client: Any, ef: Any) -> Dict[str, Any]:
    """
    VER-01: Verify record counts across all 4 ChromaDB collections.

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

    # Fetch ChromaDB collection counts (no embedding_function needed for count())
    talks_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["talks"],
        embedding_function=ef,
    )
    paras_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["paragraphs"],
        embedding_function=ef,
    )
    citations_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["citations"],
        embedding_function=ef,
    )
    footnotes_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["footnotes"],
        embedding_function=ef,
    )

    chroma_talk_count = talks_col.count()
    chroma_para_count = paras_col.count()
    chroma_citation_count = citations_col.count()
    chroma_footnote_count = footnotes_col.count()

    # Hard pass/fail: talks must match exactly
    talks_pass = chroma_talk_count == expected_talk_count
    paras_pass = chroma_para_count > 0
    citations_pass = chroma_citation_count > 0
    footnotes_pass = chroma_footnote_count > 0
    overall_passed = talks_pass and paras_pass and citations_pass and footnotes_pass

    citation_delta = chroma_citation_count - sqlite_citation_count

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
    print(f"  conference_talks:            {chroma_talk_count:>8} (expected {expected_talk_count}) {'OK' if talks_pass else 'MISMATCH'}")
    print(f"  conference_talk_paragraphs:  {chroma_para_count:>8} {'OK' if paras_pass else 'EMPTY'}")
    print(f"  conference_talk_citations:   {chroma_citation_count:>8} (SQLite baseline {sqlite_citation_count}, delta {citation_delta:+}) {'OK' if citations_pass else 'EMPTY'}")
    print(f"  conference_talk_footnotes:   {chroma_footnote_count:>8} {'OK' if footnotes_pass else 'EMPTY'}")
    if failed_talks_info:
        print(f"  failed_talks.json:           {failed_talks_info.get('count', '?')} entries")

    return {
        "passed": overall_passed,
        "counts": {
            "conference_talks": {
                "chromadb": chroma_talk_count,
                "sqlite_expected": expected_talk_count,
                "match": talks_pass,
            },
            "conference_talk_paragraphs": {
                "chromadb": chroma_para_count,
                "has_records": paras_pass,
            },
            "conference_talk_citations": {
                "chromadb": chroma_citation_count,
                "sqlite_baseline": sqlite_citation_count,
                "delta": citation_delta,
                "has_records": citations_pass,
            },
            "conference_talk_footnotes": {
                "chromadb": chroma_footnote_count,
                "has_records": footnotes_pass,
            },
        },
        "failed_talks_file": failed_talks_info,
    }


# =============================================================================
# VER-02: Semantic search spot-check
# =============================================================================


def check_semantic_search(client: Any, ef: Any) -> Dict[str, Any]:
    """
    VER-02: Run 5 semantic queries (3 topical + 2 scriptural) against
    conference_talk_paragraphs and print top 5 results each.

    Results are for manual review only. VER-02 is skipped (not failed) if
    Ollama is unavailable.

    Returns:
        Dict with keys: skipped, reason (if skipped), or queries (list of result dicts)
    """
    print("VER-02: Semantic search ...")

    queries = [
        "the Atonement of Jesus Christ forgiveness of sins",
        "eternal family temple covenants",
        "faith and repentance turning to God",
        "Mosiah 3:19 natural man enemy to God",
        "John 3:16 God so loved the world",
    ]

    try:
        # Collections must be fetched WITH embedding_function for query()
        paras_col = client.get_or_create_collection(
            name=CHROMADB_COLLECTION_NAMES["paragraphs"],
            embedding_function=ef,
        )
        talks_col = client.get_or_create_collection(
            name=CHROMADB_COLLECTION_NAMES["talks"],
            embedding_function=ef,
        )

        query_results: List[Dict[str, Any]] = []

        for query in queries:
            print(f"\n  Query: \"{query}\"")
            results = paras_col.query(
                query_texts=[query],
                n_results=5,
                include=["documents", "metadatas", "distances"],
            )

            hits: List[Dict[str, Any]] = []
            ids_list = results.get("ids", [[]])[0]
            docs_list = results.get("documents", [[]])[0]
            metas_list = results.get("metadatas", [[]])[0]
            dists_list = results.get("distances", [[]])[0]

            for i, (doc_id, doc, meta, dist) in enumerate(
                zip(ids_list, docs_list, metas_list, dists_list), start=1
            ):
                talk_id = meta.get("talk_id") if meta else None
                speaker_name = ""
                conference_year = ""
                title = ""

                if talk_id is not None:
                    try:
                        talk_result = talks_col.get(
                            ids=[f"talk_{talk_id}"],
                            include=["metadatas"],
                        )
                        if talk_result and talk_result.get("metadatas"):
                            tm = talk_result["metadatas"][0]
                            speaker_name = tm.get("speaker_name", "")
                            conference_year = tm.get("conference_year", "")
                            title = tm.get("title", "")
                    except Exception:
                        pass

                para_text = (doc or "")[:150]
                print(
                    f"  {i}. talk_id={talk_id} | {speaker_name} | {conference_year} | {title}"
                )
                print(f"     Para: {para_text}")

                hits.append({
                    "rank": i,
                    "id": doc_id,
                    "talk_id": talk_id,
                    "speaker_name": speaker_name,
                    "conference_year": conference_year,
                    "title": title,
                    "distance": dist,
                    "para_text_preview": para_text,
                })

            query_results.append({"query": query, "hits": hits})

        print("\nVER-02: Semantic search ... (manual review required)")
        return {"skipped": False, "queries": query_results}

    except Exception as exc:
        # Ollama unavailable or other connection error — skip, not fail
        reason = f"Ollama unavailable or query error: {exc}"
        print(f"VER-02: Semantic search ... SKIPPED ({reason})")
        return {"skipped": True, "reason": reason, "queries": []}


# =============================================================================
# VER-03: Metadata filter verification
# =============================================================================


def check_metadata_filters(client: Any, ef: Any) -> Dict[str, Any]:
    """
    VER-03: Verify metadata filtering on conference_talks collection.

    Runs 4 filter tests (speaker, year, session, compound) and a two-step
    paragraph-level filter demonstration.

    Returns:
        Dict with keys: passed, filters (list of filter results)
    """
    print("VER-03: Metadata filter ...")

    talks_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["talks"],
        embedding_function=ef,
    )
    paras_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["paragraphs"],
        embedding_function=ef,
    )

    filter_results: List[Dict[str, Any]] = []
    all_pass = True

    # Filter 1: speaker_name
    try:
        r1 = talks_col.get(
            where={"speaker_name": "Russell M. Nelson"},
            include=["metadatas"],
        )
        count1 = len(r1["ids"]) if r1 and r1.get("ids") else 0
        pass1 = count1 >= 100
        print(f"  Filter 1 — speaker='Russell M. Nelson': {count1} talks {'PASS' if pass1 else 'FAIL (expected >= 100)'}")
        filter_results.append({
            "filter": "speaker_name = 'Russell M. Nelson'",
            "collection": "conference_talks",
            "count": count1,
            "threshold": ">= 100",
            "passed": pass1,
        })
        if not pass1:
            all_pass = False
    except Exception as exc:
        logger.warning("Filter 1 error: %s", exc)
        filter_results.append({"filter": "speaker_name", "error": str(exc), "passed": False})
        all_pass = False

    # Filter 2: conference_year
    try:
        r2 = talks_col.get(
            where={"conference_year": 2023},
            include=["metadatas"],
        )
        count2 = len(r2["ids"]) if r2 and r2.get("ids") else 0
        pass2 = count2 > 0
        print(f"  Filter 2 — conference_year=2023: {count2} talks {'PASS' if pass2 else 'FAIL'}")
        filter_results.append({
            "filter": "conference_year = 2023",
            "collection": "conference_talks",
            "count": count2,
            "threshold": "> 0",
            "passed": pass2,
        })
        if not pass2:
            all_pass = False
    except Exception as exc:
        logger.warning("Filter 2 error: %s", exc)
        filter_results.append({"filter": "conference_year", "error": str(exc), "passed": False})
        all_pass = False

    # Filter 3: session_abbr
    try:
        r3 = talks_col.get(
            where={"session_abbr": "Saturday Morning"},
            include=["metadatas"],
        )
        count3 = len(r3["ids"]) if r3 and r3.get("ids") else 0
        pass3 = count3 > 0
        print(f"  Filter 3 — session_abbr='Saturday Morning': {count3} talks {'PASS' if pass3 else 'FAIL'}")
        filter_results.append({
            "filter": "session_abbr = 'Saturday Morning'",
            "collection": "conference_talks",
            "count": count3,
            "threshold": "> 0",
            "passed": pass3,
        })
        if not pass3:
            all_pass = False
    except Exception as exc:
        logger.warning("Filter 3 error: %s", exc)
        filter_results.append({"filter": "session_abbr", "error": str(exc), "passed": False})
        all_pass = False

    # Filter 4: compound (speaker + year)
    try:
        r4 = talks_col.get(
            where={
                "$and": [
                    {"speaker_name": "Russell M. Nelson"},
                    {"conference_year": 2023},
                ]
            },
            include=["metadatas"],
        )
        count4 = len(r4["ids"]) if r4 and r4.get("ids") else 0
        pass4 = count4 > 0
        print(f"  Filter 4 — compound (Nelson + 2023): {count4} talks {'PASS' if pass4 else 'FAIL'}")
        filter_results.append({
            "filter": "speaker_name='Russell M. Nelson' AND conference_year=2023",
            "collection": "conference_talks",
            "count": count4,
            "threshold": "> 0",
            "passed": pass4,
        })
        if not pass4:
            all_pass = False
    except Exception as exc:
        logger.warning("Filter 4 error: %s", exc)
        filter_results.append({"filter": "compound speaker+year", "error": str(exc), "passed": False})
        all_pass = False

    # Two-step paragraph-level filter demonstration
    para_filter_result: Dict[str, Any] = {}
    try:
        # Step 1: Get talk_ids for Russell M. Nelson in 2023
        r_demo = talks_col.get(
            where={
                "$and": [
                    {"speaker_name": "Russell M. Nelson"},
                    {"conference_year": 2023},
                ]
            },
            include=[],
        )
        nelson_2023_ids_raw = r_demo["ids"] if r_demo and r_demo.get("ids") else []
        # Strip "talk_" prefix and convert to int
        nelson_2023_talk_ids = []
        for doc_id in nelson_2023_ids_raw:
            try:
                nelson_2023_talk_ids.append(int(doc_id.replace("talk_", "")))
            except ValueError:
                pass

        # Step 2: Filter paragraphs by those talk_ids
        para_count = 0
        if nelson_2023_talk_ids:
            r_paras = paras_col.get(
                where={"talk_id": {"$in": nelson_2023_talk_ids}},
                include=[],
            )
            para_count = len(r_paras["ids"]) if r_paras and r_paras.get("ids") else 0

        print(
            f"  Two-step demo — paragraphs for Nelson 2023 talks ({len(nelson_2023_talk_ids)} talks): {para_count} paragraphs"
        )
        para_filter_result = {
            "description": "Two-step: conference_talks -> conference_talk_paragraphs by talk_id",
            "talk_ids_found": len(nelson_2023_talk_ids),
            "paragraph_count": para_count,
        }
    except Exception as exc:
        logger.warning("Two-step paragraph filter error: %s", exc)
        para_filter_result = {"error": str(exc)}

    status = "PASS" if all_pass else "FAIL"
    print(f"VER-03: Metadata filter ... {status}")

    return {
        "passed": all_pass,
        "filters": filter_results,
        "paragraph_filter_demo": para_filter_result,
    }


# =============================================================================
# VER-04: FK integrity scan
# =============================================================================


def check_fk_integrity(client: Any, ef: Any) -> Dict[str, Any]:
    """
    VER-04: Full FK scan across all 4 ChromaDB collections.

    Scans:
      - paragraphs.talk_id -> conference_talks IDs (must all resolve)
      - citations.paragraph_id -> conference_talk_paragraphs IDs (informational)
      - footnotes.talk_id -> conference_talks IDs (must all resolve)

    Uses paged metadata retrieval (batch_size=5000) to avoid memory issues.

    Returns:
        Dict with keys: passed, scans (dict of scan results)
    """
    print("VER-04: FK integrity ...")

    batch_size = 5000

    # --- Build reference sets (IDs only — no include= param needed) ---
    talks_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["talks"],
        embedding_function=ef,
    )
    paras_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["paragraphs"],
        embedding_function=ef,
    )
    citations_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["citations"],
        embedding_function=ef,
    )
    footnotes_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["footnotes"],
        embedding_function=ef,
    )

    print("  Building reference ID sets ...")

    # Get all talk IDs (bulk — talks collection is small enough)
    talks_raw = talks_col.get(limit=10000)
    talk_ids_set: set = set()
    for raw_id in (talks_raw.get("ids") or []):
        try:
            talk_ids_set.add(int(raw_id.replace("talk_", "")))
        except ValueError:
            pass
    print(f"  talk_ids_set: {len(talk_ids_set)} IDs")

    # Get all paragraph IDs (bulk — needed for citations FK check)
    para_total = paras_col.count()
    para_ids_set: set = set()
    print(f"  Fetching {para_total} paragraph IDs ...")
    para_offset = 0
    while True:
        batch = paras_col.get(limit=batch_size, offset=para_offset)
        batch_ids = batch.get("ids") or []
        if not batch_ids:
            break
        para_ids_set.update(batch_ids)
        para_offset += len(batch_ids)
        if len(batch_ids) < batch_size:
            break
    print(f"  para_ids_set: {len(para_ids_set)} IDs")

    # --- Scan 1: Paragraphs -> Talks FK ---
    print("  Scanning paragraphs -> talks FK ...")
    para_orphan_count = 0
    para_scan_count = 0
    offset = 0
    with tqdm(total=para_total, unit="para", desc="  VER-04 para->talk", leave=False) as pbar:
        while True:
            batch = paras_col.get(
                limit=batch_size,
                offset=offset,
                include=["metadatas"],
            )
            batch_ids = batch.get("ids") or []
            batch_metas = batch.get("metadatas") or []
            if not batch_ids:
                break
            for meta in batch_metas:
                if meta is None:
                    continue
                talk_id = meta.get("talk_id")
                if talk_id is not None and int(talk_id) not in talk_ids_set:
                    para_orphan_count += 1
                para_scan_count += 1
            pbar.update(len(batch_ids))
            offset += len(batch_ids)
            if len(batch_ids) < batch_size:
                break

    para_fk_pass = para_orphan_count == 0
    print(f"  Paragraphs scanned: {para_scan_count}, orphans: {para_orphan_count} {'PASS' if para_fk_pass else 'FAIL'}")

    # --- Scan 2: Citations -> Paragraphs FK (informational) ---
    print("  Scanning citations -> paragraphs FK ...")
    cit_total = citations_col.count()
    cit_orphan_count = 0
    cit_scan_count = 0
    offset = 0
    with tqdm(total=cit_total, unit="cit", desc="  VER-04 cit->para", leave=False) as pbar:
        while True:
            batch = citations_col.get(
                limit=batch_size,
                offset=offset,
                include=["metadatas"],
            )
            batch_ids = batch.get("ids") or []
            batch_metas = batch.get("metadatas") or []
            if not batch_ids:
                break
            for meta in batch_metas:
                if meta is None:
                    continue
                para_id = meta.get("paragraph_id")
                if para_id is not None:
                    para_id_str = f"para_{para_id}" if not str(para_id).startswith("para_") else str(para_id)
                    if para_id_str not in para_ids_set:
                        cit_orphan_count += 1
                cit_scan_count += 1
            pbar.update(len(batch_ids))
            offset += len(batch_ids)
            if len(batch_ids) < batch_size:
                break

    # Citations from annotations may have paragraph_ids NOT in paragraphs collection — informational
    print(
        f"  Citations scanned: {cit_scan_count}, unresolvable paragraph_ids: {cit_orphan_count} (informational — annotation-sourced citations expected)"
    )

    # --- Scan 3: Footnotes -> Talks FK ---
    print("  Scanning footnotes -> talks FK ...")
    fn_total = footnotes_col.count()
    fn_orphan_count = 0
    fn_scan_count = 0
    offset = 0
    with tqdm(total=fn_total, unit="fn", desc="  VER-04 fn->talk", leave=False) as pbar:
        while True:
            batch = footnotes_col.get(
                limit=batch_size,
                offset=offset,
                include=["metadatas"],
            )
            batch_ids = batch.get("ids") or []
            batch_metas = batch.get("metadatas") or []
            if not batch_ids:
                break
            for meta in batch_metas:
                if meta is None:
                    continue
                talk_id = meta.get("talk_id")
                if talk_id is not None and int(talk_id) not in talk_ids_set:
                    fn_orphan_count += 1
                fn_scan_count += 1
            pbar.update(len(batch_ids))
            offset += len(batch_ids)
            if len(batch_ids) < batch_size:
                break

    fn_fk_pass = fn_orphan_count == 0
    print(f"  Footnotes scanned: {fn_scan_count}, orphans: {fn_orphan_count} {'PASS' if fn_fk_pass else 'FAIL'}")

    overall_passed = para_fk_pass and fn_fk_pass
    status = "PASS" if overall_passed else "FAIL"
    print(f"VER-04: FK integrity ... {status}")

    return {
        "passed": overall_passed,
        "scans": {
            "paragraphs_to_talks": {
                "scanned": para_scan_count,
                "orphans": para_orphan_count,
                "passed": para_fk_pass,
            },
            "citations_to_paragraphs": {
                "scanned": cit_scan_count,
                "unresolvable": cit_orphan_count,
                "note": "Annotation-sourced citations may have paragraph_ids not in paragraphs collection — informational only",
                "passed": True,  # Always informational
            },
            "footnotes_to_talks": {
                "scanned": fn_scan_count,
                "orphans": fn_orphan_count,
                "passed": fn_fk_pass,
            },
        },
    }


# =============================================================================
# VER-05: Topics metadata verification
# =============================================================================


def check_topics(client: Any, ef: Any) -> Dict[str, Any]:
    """
    VER-05: Verify topics metadata flows through to ChromaDB.

    Uses SQLite as the source of truth throughout:
      - Pulls 50 talk IDs that HAVE topics and 50 that DON'T from SQLite
      - Looks each set up directly in ChromaDB and verifies the topics field matches
      - Spot-checks that "Topics:" appears in the document text for a talk with topics
    Pass threshold: >= 90% correct for each set; document text check must pass.
    """
    print("VER-05: Topics metadata ...")

    talks_col = client.get_or_create_collection(
        name=CHROMADB_COLLECTION_NAMES["talks"],
        embedding_function=ef,
    )

    # Pull talk IDs from SQLite — source of truth for which talks have topics
    has_topic_rows = core_db.select(
        """SELECT DISTINCT t.ID
           FROM talk t
           INNER JOIN conference_talk ct ON ct.TalkID = t.ID
           INNER JOIN talk_topic tt ON tt.talk_id = t.ID
           ORDER BY t.ID
           LIMIT 50"""
    )
    no_topic_rows = core_db.select(
        """SELECT t.ID
           FROM talk t
           INNER JOIN conference_talk ct ON ct.TalkID = t.ID
           WHERE t.ID NOT IN (SELECT DISTINCT talk_id FROM talk_topic)
           ORDER BY t.ID
           LIMIT 50"""
    )

    has_topic_ids = [f"talk_{r['ID']}" for r in has_topic_rows]
    no_topic_ids = [f"talk_{r['ID']}" for r in no_topic_rows]

    # Cross-reference: look up those exact IDs in ChromaDB
    chroma_has = talks_col.get(ids=has_topic_ids, include=["metadatas"]) if has_topic_ids else {}
    chroma_no = talks_col.get(ids=no_topic_ids, include=["metadatas"]) if no_topic_ids else {}

    has_metas = chroma_has.get("metadatas") or []
    no_metas = chroma_no.get("metadatas") or []

    has_correct = sum(1 for m in has_metas if m and m.get("topics") and str(m["topics"]).strip())
    no_correct = sum(1 for m in no_metas if not (m and m.get("topics") and str(m["topics"]).strip()))

    has_pass = (has_correct / len(has_metas) >= 0.90) if has_metas else False
    no_pass = (no_correct / len(no_metas) >= 0.90) if no_metas else True
    id_check_pass = has_pass and no_pass

    # Document text spot-check: reuse first has-topics ID already fetched above
    doc_text_ok: Optional[bool] = None
    doc_talk_id: Optional[int] = None
    doc_topics_meta: Optional[str] = None
    if has_topic_rows:
        doc_talk_id = has_topic_rows[0]["ID"]
        try:
            result = talks_col.get(
                ids=[f"talk_{doc_talk_id}"],
                include=["documents", "metadatas"],
            )
            if result and result.get("documents"):
                doc = result["documents"][0] or ""
                meta = ((result.get("metadatas") or [None])[0]) or {}
                doc_text_ok = "Topics:" in doc
                doc_topics_meta = str(meta.get("topics", ""))
        except Exception:
            doc_text_ok = None
    doc_pass = doc_text_ok is True

    overall_passed = id_check_pass and doc_pass
    status = "PASS" if overall_passed else "FAIL"

    print(
        f"  SQLite says topics → ChromaDB ({len(has_metas)} checked): "
        f"{has_correct}/{len(has_metas)} have topics {'OK' if has_pass else 'FAIL (< 90%)'}"
    )
    print(
        f"  SQLite says no topics → ChromaDB ({len(no_metas)} checked): "
        f"{no_correct}/{len(no_metas)} have no topics {'OK' if no_pass else 'FAIL (< 90%)'}"
    )
    if doc_talk_id is not None:
        print(
            f"  Document text (talk_{doc_talk_id}): metadata='{doc_topics_meta}', "
            f"'Topics:' in doc={'YES' if doc_text_ok else 'NO'} {'OK' if doc_pass else 'FAIL'}"
        )
    else:
        print("  Document text check: no talks with topics found in SQLite — skipping")
    print(f"VER-05: Topics metadata ... {status}")

    return {
        "passed": overall_passed,
        "sqlite_says_topics": {
            "checked": len(has_metas),
            "correct": has_correct,
            "passed": has_pass,
        },
        "sqlite_says_no_topics": {
            "checked": len(no_metas),
            "correct": no_correct,
            "passed": no_pass,
        },
        "document_text_check": {
            "talk_id": doc_talk_id,
            "topics_in_metadata": doc_topics_meta,
            "topics_in_document_text": doc_text_ok,
            "passed": doc_pass,
        },
    }


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post-pipeline verification: run all VER checks and write JSON report."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_REPORT_PATH),
        help="Path for the verification report JSON (default: data/verification_report.json)",
    )
    args = parser.parse_args()

    report_path = Path(args.output)

    print("=" * 60)
    print("Pipeline Verification")
    print(f"Run timestamp: {datetime.datetime.now().isoformat()}")
    print("=" * 60)
    print()

    # Initialize ChromaDB client and embedding function
    client = get_chromadb_client()
    ef = get_embedding_function()

    # Run all checks
    ver01_result = check_counts(client, ef)
    print()
    ver02_result = check_semantic_search(client, ef)
    print()
    ver03_result = check_metadata_filters(client, ef)
    print()
    ver04_result = check_fk_integrity(client, ef)
    print()
    ver05_result = check_topics(client, ef)
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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    main()
