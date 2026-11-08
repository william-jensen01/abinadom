"""search() over scripture_verses / scripture_chapters: the filter builder (on the fixture store) and the tool's
routing, against a mocked Weaviate collection."""
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from db.scripture import open_scripture_db
from tools.scripture_tools import ScriptureStore, build_scripture_filter, format_scripture_result


@pytest.fixture(scope="module")
def store(built_db):
    return ScriptureStore.open(open_scripture_db(str(built_db)))


def _names(f):
    """{property: value} of a Weaviate filter's leaves."""
    if f is None:
        return {}
    if getattr(f, "filters", None):
        return {k: v for sub in f.filters for k, v in _names(sub).items()}
    return {f.target: f.value}


def test_verse_filter_defaults_to_standard(store):
    assert _names(build_scripture_filter(store, "verses")) == {"variant": "standard"}
    assert build_scripture_filter(store, "verses", variant="both") is None
    assert _names(build_scripture_filter(store, "verses", variant="jst")) == {"variant": "jst"}
    assert "Unknown variant" in build_scripture_filter(store, "verses", variant="kjv")
    assert build_scripture_filter(store, "chapters") is None


def test_book_filter_accepts_both_names_for_the_dc(store):
    for text in ("D&C", "Sections", "Doctrine and Covenants"):
        f = build_scripture_filter(store, "chapters", book=text)
        assert set(_names(f)["book"]) == {"Doctrine and Covenants", "Sections"}, text
    assert _names(build_scripture_filter(store, "chapters", book="1 Ne."))["book"] == ["1 Nephi"]
    assert _names(build_scripture_filter(store, "chapters", book="Nowhere"))["book"] == ["Nowhere"]


def test_volume_filter_takes_title_or_slug(store):
    for text in ("bofm", "Book of Mormon", "BOFM"):
        assert "The Book of Mormon" in _names(build_scripture_filter(store, "chapters", volume=text))["volume"], text
    f = build_scripture_filter(store, "verses", book="Alma", chapter=32)
    assert set(_names(f)) == {"book", "chapter", "variant"}


def test_result_rows_carry_reference():
    v = format_scripture_result("verses", {"reference": "Alma 32:21", "text": "Now faith", "book": "Alma",
                                           "volume": "Book of Mormon", "chapter": 32, "verse": 21,
                                           "variant": "standard", "has_jst": False}, relevance=0.5, score_type="bm25")
    assert v["reference"] == "Alma 32:21" and v["snippet"] == "Now faith" and v["score_type"] == "bm25"
    c = format_scripture_result("chapters", {"reference": "Alma 32", "title": "Alma 32", "summary": "Faith",
                                             "kind": "chapter"})
    assert c["reference"] == "Alma 32" and c["snippet"] == "Alma 32\n\nFaith"


def _ctx(props):
    from server import AppContext
    obj = MagicMock()
    obj.properties = props
    obj.metadata = MagicMock(score=0.9, distance=0.1, certainty=0.9)
    col = MagicMock()
    for fn in (col.query.hybrid, col.query.bm25, col.query.near_vector, col.query.fetch_objects):
        fn.return_value.objects = [obj]
    col.aggregate.over_all.return_value.total_count = 1
    client = MagicMock()
    client.collections.use.return_value = col
    ctx = MagicMock()
    ctx.lifespan_context = {"app": AppContext(client=client)}
    return ctx, client, col


def _search(ctx, **kw):
    from server import search
    with patch("server.get_embedding_function", return_value=lambda t: [[0.1] * 4]), \
         patch("server.resolve_embedding_url", return_value="http://x"):
        return asyncio.run(search(ctx=ctx, **kw))


def test_search_routes_to_scripture_collections():
    ctx, client, col = _ctx({"reference": "Alma 32:21", "text": "Now faith", "variant": "standard"})
    out = json.loads(_search(ctx, query="faith", collection="scripture_verses", book="Alma"))
    client.collections.use.assert_called_with("ScriptureVerses")
    assert out["results"][0]["reference"] == "Alma 32:21" and out["search_mode"] == "hybrid"
    assert col.query.hybrid.call_args.kwargs["alpha"] == 0.4          # keyword-leaning default for verses
    flt = col.query.hybrid.call_args.kwargs["filters"]
    assert set(_names(flt)) == {"book", "variant"}                    # no scripture.db: book matched as written

    _search(ctx, query="faith", collection="scripture_chapters")
    client.collections.use.assert_called_with("ScriptureChapters")
    assert col.query.hybrid.call_args.kwargs["alpha"] == 0.7

    _search(ctx, query="faith", collection="scripture_verses", alpha=0.0)
    assert col.query.bm25.called


def test_search_rejects_mixed_filters():
    ctx, client, _ = _ctx({})
    assert "only to the scripture" in _search(ctx, query="x", collection="paragraphs", book="Alma")
    assert "only to talk" in _search(ctx, query="x", collection="scripture_verses", speaker="Holland")
    assert "only to the scripture_verses" in _search(ctx, query="x", collection="scripture_chapters", variant="jst")
    assert "Unknown collection" in _search(ctx, query="x", collection="nope")
