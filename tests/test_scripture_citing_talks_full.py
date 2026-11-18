"""Citing talks for a KJV verse follow JST appendix passages through their Compare range, on the real data.

Runs on a temp copy of the real scripture.db built by build_scriptures.py and on the real core.<version>.db (opened
through db.Database); skips when either is missing. Expected answers come from a plain-SQL oracle written here,
independent of tools/scripture_tools.py. A KJV verse's citing talks are the titled core.db talks with

  (1) a non-JST citation (Flag != 'J') of the verse itself, or
  (2) a JST citation (Flag = 'J') of a JST verse that one of the verse's `jst` footnotes names, or
  (3) a JST citation of any JST verse of an appendix passage that has a rel='compare' heading link whose range
      covers the verse (only 'compare'; 'similar' and 'see-also' are not followed), unless the passage's Compare
      links cover more than MAX_COMPARE_VERSES KJV verses in all (today only JST Gen. 1:1-8:18, Compare Gen. 1:1-6:13).

A talk found only through route (3) carries "via": the references of those passages, printed as
get_verse(include_jst) prints them ("JST Gen. 14:25-40"). Other talks have no "via" key.

Run: pipenv run python -m pytest tests/test_scripture_citing_talks_full.py   (needs db/scripture.db and db/core.<version>.db)
"""
import json
import time
from collections import defaultdict
from functools import lru_cache

import pytest

import db as db_pkg
from db.scripture import open_scripture_db
from tests.scripture_world import core_select, need_core_db
from tools.scripture_tools import ScriptureStore, get_citing_talks, get_verse

ALL = 10**6
MAX_COMPARE_VERSES = 40      # Compare ranges over 40 KJV verses are not followed; today that skips only Gen. 1:1-6:13 (151), next largest is 34

_STATE = {}


@pytest.fixture(scope="module", autouse=True)
def real_data(full_built):
    """The built temp copy of the real store, opened read-only; the oracle caches are rebuilt for it."""
    need_core_db()
    s = open_scripture_db(str(full_built[0]))
    assert s is not None, "scripture.db is not a built store"
    _STATE["s"] = s
    for f in _CACHED:
        f.cache_clear()
    yield
    s.close()
    _STATE.clear()


@pytest.fixture(scope="module")
def store(real_data):
    return ScriptureStore.open(_STATE["s"])


def S():
    return _STATE["s"]


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _core():
    """(titled talk ids, conference talk ids, J cites {(BookID, ch, v): talks}, plain cites {(BookID, ch, v): talks})."""
    titled = {r["ID"] for r in core_select("SELECT ID FROM talk WHERE Title IS NOT NULL AND Title != ''")}
    conf = {r["TalkID"] for r in core_select("SELECT TalkID FROM conference_talk")}
    j, plain = defaultdict(set), defaultdict(set)
    for r in core_select("SELECT c.TalkID, c.BookID, c.Chapter, c.Flag, cv.Verse FROM citation c "
                        "JOIN citation_verse cv ON cv.CitationID = c.ID"):
        (j if (r["Flag"] or "") == "J" else plain)[(r["BookID"], r["Chapter"], r["Verse"])].add(r["TalkID"])
    return titled, conf, j, plain


@lru_cache(maxsize=None)
def _books():
    return {r["book_id"]: dict(r) for r in S().select("SELECT book_id, name, cite_abbr, core_book_id FROM book")}


@lru_cache(maxsize=None)
def _chapter_verses():
    out = defaultdict(list)
    for r in S().select("SELECT book_id, chapter, verse FROM verse ORDER BY book_id, chapter, verse"):
        out[(r["book_id"], r["chapter"])].append(r["verse"])
    return out


@lru_cache(maxsize=None)
def _footnote_jst():
    """{(book_id, ch, v): {(core BookID, JST ch, JST v)}} from the verse's `jst` footnotes."""
    out = defaultdict(set)
    for r in S().select("SELECT v.book_id, v.chapter, v.verse, jv.core_book_id, jv.chapter AS jc, jv.verse AS jvv "
                        "FROM footnote_ref r JOIN footnote f ON f.footnote_id = r.footnote_id "
                        "JOIN verse v ON v.verse_id = f.verse_id JOIN jst_verse jv ON jv.jst_verse_id = r.target_jst_verse_id "
                        "WHERE r.category = 'jst'"):
        out[(r["book_id"], r["chapter"], r["verse"])].add((r["core_book_id"], r["jc"], r["jvv"]))
    return out


@lru_cache(maxsize=None)
def _passage_jst():
    out = defaultdict(set)
    for r in S().select("SELECT pv.passage_id, jv.core_book_id, jv.chapter, jv.verse FROM jst_passage_verse pv "
                        "JOIN jst_verse jv USING (jst_verse_id)"):
        out[r["passage_id"]].add((r["core_book_id"], r["chapter"], r["verse"]))
    return out


def _covered(ref):
    """The KJV (book_id, ch, v) a heading link's range covers, walking the verses that exist."""
    c0 = ref["target_chapter"]
    c1 = ref["target_chapter_end"] or c0
    first = (c0, ref["target_verse_start"] or 0)
    last = (c1, ref["target_verse_end"] or ref["target_verse_start"] or ALL)
    return [(ref["target_book_id"], c, v) for c in range(c0, c1 + 1)
            for v in _chapter_verses().get((ref["target_book_id"], c), []) if first <= (c, v) <= last]


@lru_cache(maxsize=None)
def _reach_all(rel):
    """{(book_id, ch, v): {passage_id}} for every heading link of this rel, and {passage_id: KJV verses covered}."""
    out, size = defaultdict(set), defaultdict(set)
    for r in S().select("SELECT * FROM jst_passage_ref WHERE rel = ? AND target_book_id IS NOT NULL", (rel,)):
        for k in _covered(r):
            out[k].add(r["passage_id"])
            size[r["passage_id"]].add(k)
    return out, {p: len(ks) for p, ks in size.items()}


@lru_cache(maxsize=None)
def _reach(rel="compare"):
    """_reach_all without the passages whose Compare links cover more than MAX_COMPARE_VERSES verses (compare only)."""
    out, size = _reach_all(rel)
    if rel != "compare":
        return out
    big = {p for p, n in size.items() if n > MAX_COMPARE_VERSES}
    return {k: ps - big for k, ps in out.items() if ps - big}


def big_passages():
    return {p for p, n in _reach_all("compare")[1].items() if n > MAX_COMPARE_VERSES}


@lru_cache(maxsize=None)
def passage_reference(pid):
    """'JST ' + the KJV book's cite abbreviation + the verse spec printed in the heading."""
    r = S().select("SELECT b.cite_abbr, p.verse_spec FROM jst_passage p JOIN book b ON b.book_id = p.book_id "
                   "WHERE p.passage_id = ?", (pid,))[0]
    return f"JST {r['cite_abbr']} {r['verse_spec'].strip()}"


def oracle(book_id, ch, v, passages=True):
    titled, _, j, plain = _core()
    core_book = _books()[book_id]["core_book_id"]
    talks = set(plain.get((core_book, ch, v), ())) if core_book is not None else set()
    for key in _footnote_jst().get((book_id, ch, v), ()):
        talks |= j.get(key, set())
    if passages:
        for pid in _reach().get((book_id, ch, v), ()):
            for key in _passage_jst()[pid]:
                talks |= j.get(key, set())
    return talks & titled


def passage_only(book_id, ch, v):
    return oracle(book_id, ch, v) - oracle(book_id, ch, v, passages=False)


def oracle_via(book_id, verses_by_chapter):
    """{talk: [passage references]} for a request over these (chapter, verse)s: the talks found only through route
    (3) for every verse they were found for, with the passages that found them (sorted)."""
    titled, _, j, _ = _core()
    plain_found = set().union(*(oracle(book_id, c, v, passages=False) for c, v in verses_by_chapter))
    via = defaultdict(set)
    for c, v in verses_by_chapter:
        for pid in _reach().get((book_id, c, v), ()):
            for key in _passage_jst()[pid]:
                for t in j.get(key, set()) & titled:
                    if t not in plain_found:
                        via[t].add(passage_reference(pid))
    return {t: sorted(refs) for t, refs in via.items()}


# ---------------------------------------------------------------------------
# Helpers on the tools
# ---------------------------------------------------------------------------

def all_talks(store, *args, **kw):
    talks, offset, total = [], 0, None
    while offset is not None:
        page = get_citing_talks(store, *args, limit=100, offset=offset, **kw)
        assert isinstance(page, dict), page
        total = page["total"]
        talks += page["citing_talks"]
        offset = page["next_offset"]
    assert len(talks) == total == len({t["talk_id"] for t in talks}), "total matches the talks listed, none twice"
    return {int(t["talk_id"][5:]): t for t in talks}


def name(book_id):
    return _books()[book_id]["name"]


def checked_verses():
    """Every KJV verse a compare link covers, plus the verse just before and after each covered run, plus the verses
    'similar' and 'see-also' links cover (those links must not be followed)."""
    covered = set(_reach())
    out = covered | set(_reach("similar")) | set(_reach("see-also"))
    for (b, c, v) in covered:
        vs = _chapter_verses()[(b, c)]
        i = vs.index(v)
        if i > 0:
            out.add((b, c, vs[i - 1]))
        if i + 1 < len(vs):
            out.add((b, c, vs[i + 1]))
    return sorted(out)


# ---------------------------------------------------------------------------
# Gen. 14:18: the talks citing JST Gen. 14:25–40
# ---------------------------------------------------------------------------

GEN = 1                      # scripture.db book_id of Genesis
NEW_GEN_14_18 = 17           # talks newly found for Gen. 14:18: 21 titled talks cite JST Gen. 14:25–40, 4 of them
                             # were already found through its JST Gen. 14:17 footnote
NEW_GEN_14_18_CONF = 10      # of those 17, the conference talks


class TestGen14:
    def test_gen_14_18_gains_the_talks_citing_jst_gen_14_25_40(self, store):
        assert _books()[GEN]["name"] == "Genesis"
        new = passage_only(GEN, 14, 18)
        _, conf, _, _ = _core()
        assert len(new) == NEW_GEN_14_18 and len(new & conf) == NEW_GEN_14_18_CONF, "the data no longer matches the known Gen. 14:18 counts"
        got = all_talks(store, "Genesis", 14, 18)
        missing = new - got.keys()
        assert not missing, f"Gen. 14:18 misses {len(missing)} talks citing JST Gen. 14:25–40, e.g. {sorted(missing)[:5]}"
        assert set(got) == oracle(GEN, 14, 18)
        for tid in new:
            cites = got[tid]["cites"]
            assert any(c.startswith("JST Gen. 14:") and 25 <= int(c.split(":")[1].split("–")[0]) <= 40 for c in cites), \
                (tid, cites)
            assert got[tid]["get_talk_available"] == (tid in conf)
        conf_only = all_talks(store, "Genesis", 14, 18, conference_only=True)
        assert set(conf_only) == oracle(GEN, 14, 18) & conf
        assert get_verse(store, "Genesis", 14, 18, include_citing_talks=True)["citing_talks_count"] == len(got)

    def test_range_counts_per_verse(self, store):
        r = get_verse(store, "Genesis", 14, 17, 21, include_citing_talks=True)
        expect = {f"Gen. 14:{v}": len(oracle(GEN, 14, v)) for v in range(17, 22)}
        assert {x["reference"]: x["count"] for x in r["citing_talks_by_verse"]} == expect
        union = set().union(*(oracle(GEN, 14, v) for v in range(17, 22)))
        assert r["citing_talks_count"] == len(union)
        assert set(all_talks(store, "Genesis", 14, 17, 21)) == union
        assert not passage_only(GEN, 14, 17) and not passage_only(GEN, 14, 21), "outside Compare Gen. 14:18–20"


# ---------------------------------------------------------------------------
# Every Compare range, the verse on each side, and whole chapters
# ---------------------------------------------------------------------------

class TestCompareAll:
    def test_every_covered_verse_and_its_neighbours(self, store):
        bad = []
        for (b, c, v) in checked_verses():
            want = oracle(b, c, v)
            got = set(all_talks(store, name(b), c, v))
            if got != want:
                bad.append(f"{name(b)} {c}:{v}: missing {sorted(want - got)[:4]} extra {sorted(got - want)[:4]}")
        assert not bad, f"{len(bad)} verses differ, e.g.\n" + "\n".join(bad[:8])

    def test_whole_chapters_counts_per_verse(self, store):
        bad = []
        for (b, c) in sorted({(b, c) for rel in ("compare", "similar", "see-also") for (b, c, _) in _reach(rel)}):
            r = get_verse(store, name(b), c, include_citing_talks=True)
            got = {x["reference"]: x["count"] for x in r["citing_talks_by_verse"]}
            want = {x["reference"]: len(oracle(b, c, x["verse"])) for x in r["verses"]}
            union = set().union(*(oracle(b, c, x["verse"]) for x in r["verses"]))
            if got != want or r["citing_talks_count"] != len(union):
                diff = {k: (got.get(k), want[k]) for k in want if got.get(k) != want[k]}
                bad.append(f"{name(b)} {c}: total {r['citing_talks_count']} vs {len(union)}; got/want {dict(list(diff.items())[:4])}")
        assert not bad, f"{len(bad)} chapters differ, e.g.\n" + "\n".join(bad[:8])

    def test_routes_found_only_through_a_passage_cite_jst(self, store):
        """A talk reached only through an appendix passage shows the JST verses it cites."""
        bad = []
        for (b, c, v) in sorted(_reach()):
            only = passage_only(b, c, v)
            if not only:
                continue
            got = all_talks(store, name(b), c, v)
            for tid in only & got.keys():
                if not any(x.startswith("JST ") for x in got[tid]["cites"]):
                    bad.append(f"{name(b)} {c}:{v} talk_{tid}: {got[tid]['cites']}")
        assert not bad, "\n".join(bad[:8])

    def test_the_change_is_exercised(self):
        """Guards the oracle itself: the Compare route adds talks to many verses."""
        added = [k for k in _reach() if passage_only(*k)]
        assert len(added) >= 100, len(added)     # floor; 100+ verses gain talks on core.55


# ---------------------------------------------------------------------------
# Passages over the limit are not followed; whole chapters stay small and fast
# ---------------------------------------------------------------------------

MAX_SECONDS = 5.0            # seconds for a whole-chapter call (about 0.06 s in practice)
MAX_PAGE_BYTES = 100_000     # bytes for a 100-talk page (about 15 KB in practice)


class TestBounded:
    def test_only_gen_1_to_6_is_over_the_limit(self):
        assert {passage_reference(p) for p in big_passages()} == {"JST Gen. 1:1–8:18"}

    @pytest.mark.parametrize("ch", [1, 3, 6])
    def test_gen_1_to_6_unchanged(self, store, ch):
        """Gen. 1:1–6:13 is reached only by the 329-verse passage: its talks are what the verse and footnotes find."""
        counts = get_verse(store, "Genesis", ch, include_citing_talks=True)
        for x in counts["citing_talks_by_verse"]:
            v = int(x["reference"].split(":")[1])
            assert x["count"] == len(oracle(GEN, ch, v, passages=False)), x
        page = get_citing_talks(store, "Genesis", ch, limit=100)
        assert all("via" not in t for t in page["citing_talks"])

    @pytest.mark.parametrize("book,ch", [("John", 1), ("Romans", 7), ("Genesis", 1), ("Genesis", 6)])
    def test_whole_chapter_bounded(self, store, book, ch):
        t = time.monotonic()
        page = get_citing_talks(store, book, ch, limit=100)
        counts = get_verse(store, book, ch, include_citing_talks=True)
        took = time.monotonic() - t
        assert took < MAX_SECONDS, f"{book} {ch}: {took:.1f}s"
        assert len(json.dumps(page, ensure_ascii=False).encode()) < MAX_PAGE_BYTES
        b = next(k for k, x in _books().items() if x["name"] == book)
        union = set().union(*(oracle(b, ch, x["verse"]) for x in counts["verses"]))
        assert page["total"] == counts["citing_talks_count"] == len(union)
        for t_ in page["citing_talks"]:
            assert len(t_["cites"]) <= 40, (t_["talk_id"], t_["cites"])   # cites are merged runs, not one per verse
            assert len(t_.get("via", ())) <= 5, (t_["talk_id"], t_["via"])  # a chapter touches few passages

    def test_john_1_largest_followed_range(self, store):
        """John 1:1–34 (34 verses) is under the limit, so it is followed, edges included."""
        john = next(k for k, x in _books().items() if x["name"] == "John")
        assert passage_only(john, 1, 2) and passage_only(john, 1, 34) and not passage_only(john, 1, 35)
        for v in (1, 2, 34, 35):
            assert set(all_talks(store, "John", 1, v)) == oracle(john, 1, v), v


# ---------------------------------------------------------------------------
# via on talks found only through passages
# ---------------------------------------------------------------------------

class TestVia:
    def test_gen_14_18(self, store):
        got = all_talks(store, "Genesis", 14, 18)
        assert got[8243]["via"] == ["JST Gen. 14:25–40"]     # talk 8243 cites only JST Gen. 14:30–31
        want = oracle_via(GEN, [(14, 18)])
        assert {t: x["via"] for t, x in got.items() if "via" in x} == want

    def test_every_covered_verse(self, store):
        bad = []
        for (b, c, v) in checked_verses():
            want = oracle_via(b, [(c, v)])
            got = {t: x["via"] for t, x in all_talks(store, name(b), c, v).items() if "via" in x}
            if got != want:
                bad.append(f"{name(b)} {c}:{v}: got {dict(list(got.items())[:2])} want {dict(list(want.items())[:2])}")
        assert not bad, f"{len(bad)} verses differ, e.g.\n" + "\n".join(bad[:8])

    @pytest.mark.parametrize("book,ch,lo,hi", [("Genesis", 14, 17, 21), ("1 Corinthians", 7, 1, 40), ("Matthew", 4, 1, 11)])
    def test_ranges(self, store, book, ch, lo, hi):
        b = next(k for k, x in _books().items() if x["name"] == book)
        verses = [v for v in _chapter_verses()[(b, ch)] if lo <= v <= hi]
        want = oracle_via(b, [(ch, v) for v in verses])
        got = {t: x["via"] for t, x in all_talks(store, book, ch, lo, hi).items() if "via" in x}
        assert got == want

    def test_passage_references_match_include_jst(self, store):
        """The via references are the ones get_verse(include_jst) attaches to the same verses (which leaves a passage
        out where the verse's own `jst` footnotes already carry all of its JST verses)."""
        bad, compared = [], 0
        for (b, c, v), pids in sorted(_reach().items()):
            jst = {j["reference"] for j in get_verse(store, name(b), c, v, include_jst=True)["verses"][0].get("jst", [])}
            for p in pids:
                if _passage_jst()[p] <= _footnote_jst().get((b, c, v), set()):
                    continue
                compared += 1
                if passage_reference(p) not in jst:
                    bad.append((name(b), c, v, passage_reference(p), sorted(jst)))
        assert not bad, bad[:5]
        assert compared >= 300, compared         # floor; 337 passage/verse pairs compared on scripture.db today


_CACHED = [_core, _books, _chapter_verses, _footnote_jst, _passage_jst, _reach_all, _reach, passage_reference]
