"""The Weaviate topics-metadata check accepts talks without topics, which Weaviate returns as null."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import verify_weaviate_pipeline as vwp  # noqa: E402


def _client(objects):
    result = SimpleNamespace(objects=[SimpleNamespace(uuid=f"u{i}", properties=p) for i, p in enumerate(objects)])
    col = SimpleNamespace(query=SimpleNamespace(fetch_objects=lambda **kw: result))
    return SimpleNamespace(collections=SimpleNamespace(use=lambda name: col))


def test_talk_with_null_topics_passes():
    out = vwp.check_topics_metadata(_client([
        {"title": "An Indissoluble Oneness", "speaker_name": "Joseph F. Smith", "topics": None},
        {"title": "Conference Time", "speaker_name": "Howard W. Hunter", "topics": ["Faith", "Prayer"]},
    ]))
    assert out["passed"] is True
    assert [d["topics_count"] for d in out["details"]] == [0, 2]


def test_missing_title_or_speaker_still_fails():
    out = vwp.check_topics_metadata(_client([
        {"title": "", "speaker_name": "Someone", "topics": []},
        {"title": "A Talk", "speaker_name": "  ", "topics": None},
    ]))
    assert out["passed"] is False
    assert [d["passed"] for d in out["details"]] == [False, False]


def test_topics_of_the_wrong_type_still_fail():
    out = vwp.check_topics_metadata(_client([{"title": "A Talk", "speaker_name": "Someone", "topics": "Faith"}]))
    assert out["passed"] is False
