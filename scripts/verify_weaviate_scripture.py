#!/usr/bin/env python3
"""Post-load verification of the scripture collections in Weaviate (SPEC-v2 §10, SCR-01..06).

Expected numbers are computed from the built scripture.db, never hard-coded:
  SCR-01  ScriptureVerses == verse rows + jst_verse rows with source_flag='F'; the jst variant == the F rows
  SCR-02  ScriptureChapters == chapter rows (pages); all five volumes present, standard verses per volume == the db's
  SCR-03  spot checks: John 3:16, Alma 32:21, 1 Ne. 3:7, D&C 45:32 text; Ex. 7:3 has_jst and names JST Ex. 7:3
  SCR-04  variant distribution: standard == verse rows, jst == F rows; has_jst count == verses with a resolved jst footnote ref
  SCR-05  no empty context_window; every verse and chapter object carries a vector
  SCR-06  'faith as a seed' -> Alma 32; BM25 'charity suffereth long' -> 1 Cor. 13:4 / Moro. 7:45;
          chapter search 'plan of salvation' -> a plausible plan-of-salvation chapter
  META    ScriptureMeta holds one object whose build_id equals the db's

  --db PATH   the built scripture.db (default db/scripture.db)
Exit 0 = every check passed. Needs Weaviate and the embedder (EMBEDDING_URL) from the environment or .env.
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PLAN = {"Alma 12", "Alma 22", "Alma 34", "Alma 40", "Alma 41", "Alma 42", "2 Ne. 2", "2 Ne. 9", "2 Ne. 31",
        "Moses 1", "Moses 5", "Moses 6", "Abr. 3", "D&C 76", "D&C 88", "D&C 93", "D&C 131", "D&C 137",
        "D&C 138", "1 Cor. 15", "Mosiah 15", "Mosiah 16", "Hel. 14", "3 Ne. 27", "Alma 11", "Alma 13"}
SPOTS = {"John 3:16": "For God so loved the world", "Alma 32:21": "And now as I said concerning faith",
         "1 Ne. 3:7": "And it came to pass that I, Nephi", "D&C 45:32": "But my disciples shall stand"}


def _load_env() -> None:
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8").read().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def expected(db_path: str) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    out = {
        "build_id": one("SELECT value FROM build_meta WHERE key='build_id'"),
        "verses": one("SELECT COUNT(*) FROM verse"),
        "jst_f": one("SELECT COUNT(*) FROM jst_verse WHERE source_flag='F'"),
        "chapters": one("SELECT COUNT(*) FROM chapter"),
        "volumes": dict(conn.execute("SELECT vo.title, COUNT(*) FROM verse v JOIN book b ON b.book_id = v.book_id "
                                     "JOIN volume vo ON vo.volume_id = b.volume_id GROUP BY vo.volume_id").fetchall()),
        "has_jst": one("SELECT COUNT(DISTINCT f.verse_id) FROM footnote_ref r JOIN footnote f ON f.footnote_id=r.footnote_id "
                       "WHERE r.category='jst' AND r.target_jst_verse_id IS NOT NULL"),
    }
    conn.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.path.join(ROOT, "db", "scripture.db"))
    args = ap.parse_args()
    _load_env()
    from weaviate.classes.aggregate import GroupByAggregate
    from weaviate.classes.query import Filter
    from config.embedding import get_embedding_function
    from config.weaviate_client import get_weaviate_client

    exp = expected(args.db)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
        if not ok:
            failures.append(name)

    client = get_weaviate_client()
    try:
        verses = client.collections.use("ScriptureVerses")
        chapters = client.collections.use("ScriptureChapters")

        def count(col, flt=None) -> int:
            return col.aggregate.over_all(total_count=True, filters=flt).total_count

        def one(ref):
            r = verses.query.fetch_objects(filters=Filter.by_property("reference").equal(ref), limit=2).objects
            return r[0].properties if r else None

        got = count(verses)
        check("SCR-01", got == exp["verses"] + exp["jst_f"], f"ScriptureVerses {got} == {exp['verses']} + {exp['jst_f']} F")
        jst = count(verses, Filter.by_property("variant").equal("jst"))
        check("SCR-01 jst", jst == exp["jst_f"], f"variant=jst {jst} == {exp['jst_f']}")
        got_c = count(chapters)
        check("SCR-02 chapters", got_c == exp["chapters"], f"ScriptureChapters {got_c} == {exp['chapters']} chapter pages")
        std = Filter.by_property("variant").equal("standard")
        groups = verses.aggregate.over_all(group_by=GroupByAggregate(prop="volume"), total_count=True, filters=std).groups
        vols = {g.grouped_by.value: g.total_count for g in groups}
        check("SCR-02 volumes", len(exp["volumes"]) == 5 and vols == exp["volumes"],
              f"standard verses per volume {vols} == db {exp['volumes']}")

        for ref, start in SPOTS.items():
            props = one(ref)
            text = props["text"] if props else None
            check(f"SCR-03 {ref}", bool(text) and text.startswith(start), repr((text or "")[:50]))
        ex = one("Ex. 7:3")
        check("SCR-03 Ex. 7:3", bool(ex) and ex["has_jst"] and "JST Ex. 7:3" in ex["jst_refs"],
              f"has_jst={ex and ex['has_jst']} jst_refs={ex and ex['jst_refs']}")

        n_std = count(verses, std)
        check("SCR-04 variants", n_std == exp["verses"] and jst == exp["jst_f"],
              f"variant=standard {n_std} == {exp['verses']} verse rows, variant=jst {jst} == {exp['jst_f']} F rows")
        has = count(verses, Filter.by_property("has_jst").equal(True))
        check("SCR-04 has_jst", has == exp["has_jst"], f"has_jst {has} == {exp['has_jst']} verses with a resolved jst footnote")
        empty = count(verses, Filter.by_property("context_window").equal(""))
        check("SCR-05 context_window", empty == 0, f"{empty} empty context_window")
        for name, col in (("verses", verses), ("chapters", chapters)):
            seen = missing = 0
            for o in col.iterator(include_vector=True):
                seen += 1
                if not (o.vector and all(len(v) for v in o.vector.values())):
                    missing += 1
            check(f"SCR-05 vectors {name}", seen > 0 and missing == 0, f"{missing} of {seen} objects without a vector")

        ef = get_embedding_function(task="query")
        refs = [o.properties["reference"] for o in verses.query.near_vector(ef(["faith as a seed"])[0], limit=10, filters=std).objects]
        check("SCR-06 semantic", any(r.startswith("Alma 32:") for r in refs), f"'faith as a seed' -> {refs}")
        bm = [o.properties["reference"] for o in verses.query.bm25("charity suffereth long", limit=5, filters=std).objects]
        check("SCR-06 keyword", bool({"1 Cor. 13:4", "Moro. 7:45"} & set(bm)), f"'charity suffereth long' -> {bm}")
        crefs = [o.properties["reference"] for o in chapters.query.near_vector(ef(["plan of salvation"])[0], limit=10).objects]
        check("SCR-06 chapters", bool(PLAN & set(crefs)), f"'plan of salvation' -> {crefs}")

        meta = list(client.collections.use("ScriptureMeta").iterator())
        check("META", len(meta) == 1 and meta[0].properties.get("build_id") == exp["build_id"],
              f"{len(meta)} object(s), build_id {(meta[0].properties.get('build_id') or '')[:12] if meta else None} vs db {exp['build_id'][:12]}")
    finally:
        client.close()
    print("ALL PASS" if not failures else f"FAILED: {', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
