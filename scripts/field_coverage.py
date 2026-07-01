# -*- coding: utf-8 -*-
"""
Field-coverage audit (Weaviate) — read-only.

Measures how completely each candidate filter/metadata field is populated,
so we can decide which fields are safe as HARD filters (near-100% populated)
versus which would cause false negatives and should be used only as ranking
boosts / returned metadata.

Motivation: filtering on a sparse or extraction-derived field silently drops
relevant-but-untagged records. This script turns "I'm hesitant" into a number.

What it does (no writes, no embeddings, works when Ollama is down):
  - talks collection: full paginated scan; exact populated/empty/zero rates,
    a few sample values per field, and an ISO-date sortability check on talk_date.
  - citations collection: aggregate-API counts for parse_success and book
    (too large to scan; uses filtered over_all counts).

Verdict per field (heuristic on populated %):
  >= 98%   SAFE      — fine as a hard filter
  80–98%   CAUTION   — hard filter drops a noticeable slice; prefer boost/annotate
  < 80%    BOOST-ONLY — do not hard-filter; use as a signal or returned metadata

Usage:
    pipenv run py scripts/field_coverage.py
    pipenv run py scripts/field_coverage.py --output data/field_coverage_report.json
    pipenv run py scripts/field_coverage.py --page-size 1000 --samples 5
"""

import argparse
import datetime
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

import weaviate
from weaviate.classes.query import Filter
from weaviate.classes.aggregate import Metrics

from config.weaviate_client import get_weaviate_client
from config.pipeline_config import WEAVIATE_COLLECTION_NAMES

logger = logging.getLogger(__name__)

DEFAULT_REPORT_PATH = Path(__file__).parent.parent / "data" / "field_coverage_report.json"

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# Candidate fields to audit on the talks collection.
# kind controls how "populated" is judged:
#   text     -> non-empty after strip()
#   text_date-> non-empty string; also tracks ISO-sortable fraction
#   array    -> a list with at least one element
#   int      -> not None (0 counts as populated — e.g. a real year)
#   int_id   -> not None and != 0 (0/None means "unset" for an id/role fk)
TALK_FIELDS: List[Tuple[str, str]] = [
    ("speaker_name", "text"),        # control — expect ~100%
    ("conference_year", "int"),      # control — expect ~100%
    ("conference_month", "text"),    # control — expect ~100%
    ("topics", "array"),             # extraction-derived — the field in question
    ("session_description", "text"), # structural but inconsistent across eras
    ("session_abbr", "text"),
    ("talk_date", "text_date"),      # free-text date — date-range filter depends on this
    ("speaker_role_id", "int_id"),   # role fk (0/None = unset), needs a label map anyway
    ("kicker", "text"),              # informational
    ("talk_preview", "text"),        # informational
]

SAFE_THRESHOLD = 98.0
CAUTION_THRESHOLD = 80.0

# Fields to break down by decade — tests whether empties cluster in older talks
# (the "empties are pre-enrichment era" hypothesis) rather than being random.
ERA_FIELDS = {"topics", "speaker_role_id", "talk_preview", "kicker"}


def _verdict(pct: float) -> str:
    if pct >= SAFE_THRESHOLD:
        return "SAFE"
    if pct >= CAUTION_THRESHOLD:
        return "CAUTION"
    return "BOOST-ONLY"


def _is_populated(kind: str, value: Any) -> bool:
    if value is None:
        return False
    if kind in ("text", "text_date"):
        return isinstance(value, str) and value.strip() != ""
    if kind == "array":
        return isinstance(value, list) and len(value) > 0
    if kind == "int":
        return True  # not None already handled above
    if kind == "int_id":
        try:
            return int(value) != 0
        except (TypeError, ValueError):
            return False
    return value is not None


def audit_talks(
    client: weaviate.WeaviateClient, page_size: int, samples: int
) -> Dict[str, Any]:
    """Full paginated scan of the talks collection; exact per-field coverage."""
    print("Scanning talks collection (full scan) ...")
    col = client.collections.use(WEAVIATE_COLLECTION_NAMES["talks"])

    return_props = [name for name, _ in TALK_FIELDS]
    counters = {name: 0 for name, _ in TALK_FIELDS}
    sample_values: Dict[str, List[Any]] = {name: [] for name, _ in TALK_FIELDS}
    # era[name][decade] = [populated, total]
    era: Dict[str, Dict[int, List[int]]] = {name: {} for name in ERA_FIELDS}
    iso_ok = 0  # talk_date ISO-sortable count
    total = 0

    offset = 0
    while True:
        page = col.query.fetch_objects(
            limit=page_size,
            offset=offset,
            return_properties=return_props,
        )
        objs = page.objects
        if not objs:
            break

        for obj in objs:
            total += 1
            props = obj.properties
            year = props.get("conference_year")
            decade = (year // 10) * 10 if isinstance(year, int) and year > 0 else None
            for name, kind in TALK_FIELDS:
                val = props.get(name)
                pop = _is_populated(kind, val)
                if pop:
                    counters[name] += 1
                    if len(sample_values[name]) < samples and val not in sample_values[name]:
                        sample_values[name].append(val)
                    if kind == "text_date" and isinstance(val, str) and ISO_DATE_RE.match(val):
                        iso_ok += 1
                if name in ERA_FIELDS and decade is not None:
                    bucket = era[name].setdefault(decade, [0, 0])
                    bucket[1] += 1
                    if pop:
                        bucket[0] += 1

        offset += len(objs)
        if len(objs) < page_size:
            break

    fields: Dict[str, Any] = {}
    for name, kind in TALK_FIELDS:
        populated = counters[name]
        pct = (populated / total * 100.0) if total else 0.0
        entry: Dict[str, Any] = {
            "kind": kind,
            "total": total,
            "populated": populated,
            "empty": total - populated,
            "populated_pct": round(pct, 2),
            "verdict": _verdict(pct),
            "samples": sample_values[name],
        }
        if kind == "text_date":
            iso_pct = (iso_ok / total * 100.0) if total else 0.0
            entry["iso_sortable"] = iso_ok
            entry["iso_sortable_pct"] = round(iso_pct, 2)
        if name in ERA_FIELDS:
            entry["by_decade"] = {
                str(d): {
                    "populated": p,
                    "total": t,
                    "populated_pct": round((p / t * 100.0) if t else 0.0, 1),
                }
                for d, (p, t) in sorted(era[name].items())
            }
        fields[name] = entry

    return {"collection": WEAVIATE_COLLECTION_NAMES["talks"], "total": total, "fields": fields}


def _agg_count(col, filters=None) -> int:
    """Total count via aggregate, optionally filtered."""
    if filters is None:
        return col.aggregate.over_all(total_count=True).total_count
    return col.aggregate.over_all(total_count=True, filters=filters).total_count


def audit_citations(client: weaviate.WeaviateClient) -> Dict[str, Any]:
    """Aggregate-API coverage for the (large) citations collection.

    parse_success drives whether book/chapter/verse fields are populated, which
    is exactly what find_by_scripture and any citation-count filter depend on.
    """
    print("Auditing citations collection (aggregate API) ...")
    col = client.collections.use(WEAVIATE_COLLECTION_NAMES["citations"])
    fields: Dict[str, Any] = {}

    try:
        total = _agg_count(col)
    except Exception as exc:
        logger.warning("citations total count failed: %s", exc)
        return {"collection": WEAVIATE_COLLECTION_NAMES["citations"], "error": str(exc)}

    # parse_success == True fraction
    try:
        true_count = _agg_count(col, Filter.by_property("parse_success").equal(True))
        pct = (true_count / total * 100.0) if total else 0.0
        fields["parse_success"] = {
            "total": total,
            "true": true_count,
            "false": total - true_count,
            "true_pct": round(pct, 2),
            "verdict": _verdict(pct),
            "note": "Citations with parse_success=False have no book/chapter/verse; "
                    "find_by_scripture cannot surface them (inherent false negatives).",
        }
    except Exception as exc:
        logger.warning("parse_success aggregate failed: %s", exc)
        fields["parse_success"] = {"error": str(exc)}

    # book populated — aggregate METRICS count (non-null count), NOT filters.
    # book is a tokenized TEXT property: filtering on "" yields no tokens
    # ("only stopwords provided") and null-state filters need indexNullState.
    # The count metric sidesteps both — it reports how many objects have a value.
    try:
        res = col.aggregate.over_all(
            total_count=True,
            return_metrics=Metrics("book").text(count=True),
        )
        book_count = res.properties["book"].count
        pct = (book_count / total * 100.0) if total else 0.0
        fields["book"] = {
            "total": total,
            "populated": book_count,
            "empty": total - book_count,
            "populated_pct": round(pct, 2),
            "verdict": _verdict(pct),
            "method": "aggregate Metrics('book').text(count=True) — non-null count",
        }
    except Exception as exc:
        logger.warning("book aggregate failed: %s", exc)
        fields["book"] = {"error": str(exc)}

    return {"collection": WEAVIATE_COLLECTION_NAMES["citations"], "total": total, "fields": fields}


def _print_table(section: str, result: Dict[str, Any]) -> None:
    print("\n" + "=" * 72)
    print(f"{section}: {result.get('collection', '?')}  (total records: {result.get('total', '?')})")
    print("=" * 72)
    fields = result.get("fields", {})
    if not fields:
        print(f"  (no field data — {result.get('error', 'unknown error')})")
        return
    print(f"  {'field':<22}{'populated %':>13}   {'verdict':<11} samples")
    print(f"  {'-' * 22}{'-' * 13:>13}   {'-' * 11:<11} {'-' * 20}")
    for name, e in fields.items():
        if "error" in e:
            print(f"  {name:<22}{'ERROR':>13}   {'-':<11} {e['error']}")
            continue
        pct = e.get("populated_pct", e.get("true_pct", 0.0))
        verdict = e.get("verdict", "?")
        extra = ""
        if "iso_sortable_pct" in e:
            extra = f"[ISO-sortable: {e['iso_sortable_pct']}%] "
        samples = e.get("samples", [])
        sample_str = extra + (", ".join(repr(s) for s in samples[:3]) if samples else "")
        print(f"  {name:<22}{pct:>12.2f}%   {verdict:<11} {sample_str[:60]}")


def _print_era(talks_result: Dict[str, Any]) -> None:
    """Print populated % by decade for the sparse cohort — tests the older-talks hypothesis."""
    fields = talks_result.get("fields", {})
    era_fields = [n for n in fields if "by_decade" in fields[n]]
    if not era_fields:
        return
    decades = sorted({int(d) for n in era_fields for d in fields[n]["by_decade"]})
    print("\n" + "=" * 72)
    print("SPARSITY BY DECADE (populated %) — tests 'empties are older talks'")
    print("=" * 72)
    header = "  " + f"{'decade':<10}" + "".join(f"{n[:12]:>14}" for n in era_fields)
    print(header)
    print("  " + "-" * (10 + 14 * len(era_fields)))
    for d in decades:
        row = f"  {str(d) + 's':<10}"
        for n in era_fields:
            cell = fields[n]["by_decade"].get(str(d))
            row += f"{(str(cell['populated_pct']) + '%') if cell else '-':>14}"
        print(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only field-coverage audit for Weaviate collections."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_REPORT_PATH),
        help="Path for the JSON report (default: data/field_coverage_report.json)",
    )
    parser.add_argument("--page-size", type=int, default=1000, help="Talks scan page size (default 1000)")
    parser.add_argument("--samples", type=int, default=5, help="Sample values to collect per field (default 5)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    host = os.environ.get("WEAVIATE_HOST", "localhost")
    port = os.environ.get("WEAVIATE_PORT", "8080")
    print("=" * 72)
    print("Field-Coverage Audit (Weaviate) — read-only")
    print(f"Run timestamp: {datetime.datetime.now().isoformat()}")
    print(f"Weaviate: {host}:{port}")
    print("=" * 72)

    client = get_weaviate_client()
    try:
        talks_result = audit_talks(client, page_size=args.page_size, samples=args.samples)
        citations_result = audit_citations(client)
    finally:
        client.close()

    _print_table("TALKS", talks_result)
    _print_era(talks_result)
    _print_table("CITATIONS", citations_result)

    print("\nLegend: SAFE >= 98%%  |  CAUTION 80-98%% (prefer boost/annotate)  |  BOOST-ONLY < 80%%")

    report = {
        "run_timestamp": datetime.datetime.now().isoformat(),
        "weaviate_host": host,
        "weaviate_port": port,
        "thresholds": {"safe": SAFE_THRESHOLD, "caution": CAUTION_THRESHOLD},
        "talks": talks_result,
        "citations": citations_result,
    }

    report_path = Path(args.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport written to: {report_path}")


if __name__ == "__main__":
    main()
