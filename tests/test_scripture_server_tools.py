"""find_cross_references and corpus_stats for the scripture collections, called through the MCP server on the
embedded Weaviate with the fake embedder."""
from tests.scripture_world import blob, call_tools, q1


def _section(result, direction):
    """The part of a find_cross_references result that holds outgoing ("out") or incoming ("in") references."""
    if direction == "out":
        return result[next(k for k in result if "out" in k.lower())]
    return result[next(k for k in result if "in" in k.lower() and "out" not in k.lower())]


def test_cross_references_outgoing_and_incoming(loaded):
    _, _, env = loaded
    a, ex, john, gen = call_tools(env, [
        ("find_cross_references", {"book": "Alma", "chapter": 32, "verse": 21}),
        ("find_cross_references", {"book": "Exodus", "chapter": 4, "verse": 16}),
        ("find_cross_references", {"book": "John", "chapter": 3, "verse": 16}),
        ("find_cross_references", {"book": "Genesis", "chapter": 6, "verse": 18}),
    ])
    assert isinstance(a, dict), blob(a)[:300]
    out_keys = [k for k in a if "out" in k.lower()]
    in_keys = [k for k in a if "in" in k.lower() and "out" not in k.lower()]
    assert out_keys and in_keys, f"result needs outgoing and incoming sections: keys {list(a)}"
    out = blob(a[out_keys[0]])
    assert "John 20:29" in out and "Heb. 11:1" in out and "Ether 12:6" in out, f"Alma 32:21 outgoing: {out[:400]}"
    assert "21a" in out or "note21_a" in out, "outgoing refs are grouped by footnote (marker)"
    assert "Ex. 7:1" in blob(_section(ex, "out")), f"Ex 4:16 outgoing: {blob(_section(ex, 'out'))[:300]}"
    inc = blob(_section(ex, "in"))
    assert "Ex. 7:1" in inc and "Moses 1:25" in inc, f"Ex 4:16 incoming must include Ex. 7:1 and Moses 1:25: {inc[:400]}"
    assert "D&C 45:5" in blob(_section(john, "in")), f"John 3:16 incoming: {blob(_section(john, 'in'))[:300]}"
    assert "Gen. 9:9" in blob(_section(gen, "in")), f"Gen 6:18 incoming: {blob(_section(gen, 'in'))[:300]}"


def test_cross_references_need_no_embedder(loaded):
    _, _, env = loaded
    (r,) = call_tools(dict(env, EMBEDDING_URL="http://127.0.0.1:9"),
                      [("find_cross_references", {"book": "1 Nephi", "chapter": 3, "verse": 7})])
    assert isinstance(r, dict), f"find_cross_references reads SQLite and must not need the embedder: {blob(r)[:200]}"


def _groups(r):
    if isinstance(r, list):
        r = r[0] if r else {}
    g = r.get("groups") or r.get("by") or next((v for v in r.values() if isinstance(v, (list, dict)) and v), None)
    if isinstance(g, dict):
        return {str(k): int(v) for k, v in g.items()}
    out = {}
    for x in g or []:
        vals = [v for v in x.values() if isinstance(v, int) and not isinstance(v, bool)]
        keys = [v for v in x.values() if not (isinstance(v, int) and not isinstance(v, bool))]
        if vals:
            out[str(keys[0] if keys else "?")] = vals[0]
    return out


def test_corpus_stats_covers_both_scripture_collections(loaded):
    db, _, env = loaded
    tot, vol, jst, ch = call_tools(env, [
        ("corpus_stats", {"collection": "scripture_verses"}),
        ("corpus_stats", {"collection": "scripture_verses", "group_by": "volume"}),
        ("corpus_stats", {"collection": "scripture_verses", "group_by": "has_jst"}),
        ("corpus_stats", {"collection": "scripture_chapters", "group_by": "book"}),
    ])
    n = q1(db, "SELECT COUNT(*) FROM verse") + q1(db, "SELECT COUNT(*) FROM jst_verse WHERE source_flag='F'")
    assert str(n) in blob(tot), f"scripture_verses total should be {n}: {blob(tot)[:200]}"
    gv = _groups(vol)
    assert len(gv) >= 5 and sum(gv.values()) == n, f"group_by volume: {gv}"
    n_std = q1(db, "SELECT COUNT(*) FROM verse")
    gj = _groups(jst)
    assert len(gj) >= 2 and sum(gj.values()) in (n, n_std), f"group_by has_jst: {gj}"
    assert len(_groups(ch)) >= 10, f"scripture_chapters group_by book: {blob(ch)[:300]}"
    (talks,) = call_tools(env, [("corpus_stats", {"collection": "talks"})])
    assert "total" in blob(talks)
