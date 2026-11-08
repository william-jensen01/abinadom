"""_scripture_status: build-id comparison and "no finished load" handling (SPEC-v2 §9.3)."""
from types import SimpleNamespace

import server


class _Col:
    def __init__(self, props):
        self.props = props

    def iterator(self):
        return iter([SimpleNamespace(properties=self.props)] if self.props is not None else [])


class _Client:
    def __init__(self, existing, meta):
        self.collections = SimpleNamespace(exists=lambda n: existing, use=lambda n: _Col(meta))


def _store(build_id):
    return SimpleNamespace(db=SimpleNamespace(scalar=lambda q: build_id))


def test_mismatch_reports_both_ids(caplog):
    loaded, st = server._scripture_status(_Client(True, {"build_id": "old"}), _store("new"))
    assert loaded and st["mismatch"] and st["file_build_id"] == "new" and st["loaded_build_id"] == "old"
    assert "mismatch" in caplog.text


def test_slice_without_finished_build_is_not_a_mismatch():
    loaded, st = server._scripture_status(_Client(True, {"loading_build_id": "x"}), _store("new"))
    assert loaded and not st["mismatch"] and st["loaded_build_id"] is None and st["loading_build_id"] == "x"


def test_missing_collections_and_db():
    loaded, st = server._scripture_status(_Client(False, None), None)
    assert not loaded and not st["db"] and not st["mismatch"]
