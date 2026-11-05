"""The real raw store db/scripture.db is complete.

Runs on a temp copy of the real store; skips when db/scripture.db is missing or empty.
Independent reference: canonical chapter counts of the LDS standard works.
"""
import json
import re

import pytest

from tests.scripture_world import VOLUMES, _href_uri, q, q1

# numbered chapter pages per volume: /scriptures/<vol>/<book>/<n>
EXPECTED_CHAPTERS = {"ot": 929, "nt": 260, "bofm": 239, "dc-testament": 138 + 2, "pgp": 16}
# a few per-book counts as a cross-check
EXPECTED_BOOK = {("ot", "ps"): 150, ("ot", "gen"): 50, ("nt", "matt"): 28, ("bofm", "alma"): 63,
                 ("dc-testament", "dc"): 138, ("dc-testament", "od"): 2, ("pgp", "moses"): 8,
                 ("pgp", "abr"): 5, ("nt", "jude"): 1, ("bofm", "enos"): 1}


@pytest.fixture
def db(full_store):
    return full_store


def test_every_toc_link_is_stored(db):
    stored = {r[0]: r[1] for r in q(db, "SELECT uri, status FROM raw_latest WHERE lang='eng'")}
    for v in VOLUMES + ["jst"]:
        assert f"/scriptures/{v}" in stored, f"volume TOC /scriptures/{v} not stored"
        body = json.loads(q1(db, "SELECT json FROM raw_latest WHERE uri=? AND lang='eng'", (f"/scriptures/{v}",)))["content"]["body"]
        links = {u for u in (_href_uri(h) for h in re.findall(r'href="([^"]+)"', body)) if u}
        missing = sorted(u for u in links if stored.get(u) != 200)
        assert not missing, f"{v}: {len(missing)} TOC links without a 200 raw row, e.g. {missing[:8]}"


def test_chapter_counts_match_the_standard_works(db):
    uris = [r[0] for r in q(db, "SELECT uri FROM raw_latest WHERE lang='eng' AND status=200")]
    got, per_book = {}, {}
    for u in uris:
        m = re.fullmatch(r"/scriptures/([^/]+)/([^/]+)/(\d+)", u)
        if m and m.group(1) in EXPECTED_CHAPTERS:
            got[m.group(1)] = got.get(m.group(1), 0) + 1
            per_book[(m.group(1), m.group(2))] = per_book.get((m.group(1), m.group(2)), 0) + 1
    print("numbered chapter pages per volume:", got)
    assert got == EXPECTED_CHAPTERS, f"chapter pages per volume {got} != {EXPECTED_CHAPTERS}"
    bad = {k: (per_book.get(k), n) for k, n in EXPECTED_BOOK.items() if per_book.get(k) != n}
    assert not bad, f"per-book chapter counts (got, expected): {bad}"


def test_raw_rows_are_untouched_api_responses(db):
    bad = q(db, """SELECT uri FROM raw_latest WHERE lang='eng' AND status=200
                   AND (json NOT LIKE '{%' OR length(content_hash) != 64) LIMIT 5""")
    assert not bad, f"raw rows that are not JSON / have no sha256: {bad}"
    body = json.loads(q1(db, "SELECT json FROM raw_latest WHERE uri='/scriptures/bofm/alma/32'"))
    assert "content" in body and "footnotes" in body["content"], "alma/32 raw JSON is not the content-endpoint response"


EXPECTED_VERSES = {"ot": 23145, "nt": 7957, "bofm": 6604, "dc-testament": 3654, "pgp": 635}


def test_chapter_rows_are_the_real_pages(db):
    """Stub rows (empty bodies, made-up hashes) must not pass: count verses in the stored HTML itself."""
    verses, with_fn, chapters, hashes, wrong_uri = {}, 0, 0, set(), []
    for uri, js, h in q(db, "SELECT uri, json, content_hash FROM raw_latest WHERE lang='eng' AND status=200"):
        m = re.fullmatch(r"/scriptures/([^/]+)/([^/]+)/(\d+)", uri)
        if not m or m.group(1) not in EXPECTED_VERSES:
            continue
        d = json.loads(js)
        if d.get("uri") != uri:
            wrong_uri.append(uri)
        c = d.get("content") or {}
        verses[m.group(1)] = verses.get(m.group(1), 0) + len(re.findall(r'<p class="verse[" ]', c.get("body", "")))
        chapters += 1
        hashes.add(h)
        if m.group(2) != "od" and c.get("footnotes"):
            with_fn += 1
    assert not wrong_uri, f"stored JSON whose own 'uri' differs from the row's uri: {wrong_uri[:5]}"
    assert len(hashes) == chapters, f"{chapters} chapter rows but only {len(hashes)} distinct content hashes"
    print("verses in stored chapter HTML per volume:", verses)
    assert verses == EXPECTED_VERSES, f"<p class=verse> per volume in the stored pages {verses} != {EXPECTED_VERSES}"
    assert with_fn >= (chapters - 2) * 0.99, f"only {with_fn}/{chapters - 2} chapter pages have footnotes"
