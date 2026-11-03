# -*- coding: utf-8 -*-
"""
Unit tests for the pipeline orchestrator: scripts/run_pipeline.py

All tests mock external dependencies (DB, Weaviate, extractors) using
unittest.mock.patch so no real database, embedding service or Weaviate is needed.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.run_pipeline as run_pipeline
from scripts.run_pipeline import _get_all_gc_talk_ids, _iter_extractions, _record_failure


# =============================================================================
# Helpers
# =============================================================================


def _make_pipeline_result(talk_id=1, success=True):
    """Build a mock TalkPipelineResult."""
    result = MagicMock()
    result.talk_id = talk_id
    result.success = success
    result.metadata = MagicMock()
    result.paragraphs = MagicMock()
    result.citations = MagicMock()
    result.footnotes = MagicMock()
    result.errors = [] if success else ["extraction failed"]
    return result


def _make_validation(is_valid=True):
    """Build a mock ValidationReport."""
    v = MagicMock()
    v.is_valid = is_valid
    v.errors = [] if is_valid else ["validation error"]
    return v


def _default_pipeline(content_db_arg, core_db_arg, talk_id, *args, **kwargs):
    result = _make_pipeline_result(talk_id=talk_id)
    result.metadata.talk_id = talk_id
    return result


def _run(
    argv=(),
    *,
    tmp_path,
    all_ids=(1, 2),
    loaded_ids=(),
    gc_ids=None,
    existing_failed=None,
    pipeline_side_effect=None,
    validation=None,
    insert_failures=None,
    load_side_effect=None,
):
    """
    Run main() with everything external mocked.

    all_ids:         what _get_all_gc_talk_ids returns (full-corpus runs)
    loaded_ids:      talk IDs the loader reports as already in Weaviate
    gc_ids:          IDs core_db treats as GC talks (targeted runs); defaults to all_ids
    insert_failures: {talk_id: error} the loader reports after its final flush
    """
    gc_ids = set(all_ids if gc_ids is None else gc_ids)

    loader = MagicMock()
    loader.__enter__ = MagicMock(return_value=loader)
    loader.__exit__ = MagicMock(return_value=False)
    loader.existing_talk_ids.return_value = set(loaded_ids)
    loader.load.side_effect = load_side_effect
    pending = {}
    loader.flush.side_effect = lambda: pending.update(insert_failures or {})
    loader.pop_insert_failures.side_effect = lambda: (dict(pending), pending.clear())[0]

    mock_db = MagicMock()
    mock_db.select.side_effect = lambda sql, params=(): [
        {"ID": tid} for tid in params if tid in gc_ids
    ]

    failed_path = tmp_path / "failed_talks.json"
    if existing_failed is not None:
        failed_path.write_text(json.dumps(existing_failed), encoding="utf-8")

    with (
        patch.object(run_pipeline, "FAILED_TALKS_PATH", failed_path),
        patch.object(run_pipeline, "core_db", mock_db),
        patch.object(run_pipeline, "_get_all_gc_talk_ids", return_value=list(all_ids)) as all_ids_mock,
        patch.object(run_pipeline, "fetch_all_books", return_value={}),
        patch.object(run_pipeline, "get_weaviate_client", return_value=MagicMock()),
        patch.object(run_pipeline, "WeaviateLoader", return_value=loader) as loader_cls,
        patch.object(run_pipeline, "get_embedding_function", return_value=None),
        patch.object(run_pipeline, "resolve_embedding_url", return_value=None),
        patch.object(
            run_pipeline,
            "process_talk_pipeline",
            side_effect=pipeline_side_effect or _default_pipeline,
        ) as pipeline,
        patch.object(
            run_pipeline, "validate_talk", return_value=validation or _make_validation(True)
        ) as validate,
    ):
        # Mocks don't cross process boundaries, so run in-process unless a test asks
        workers = [] if "--workers" in argv else ["--workers", "1"]
        sys.argv = ["run_pipeline.py", *argv, *workers]
        run_pipeline.main()

    return SimpleNamespace(
        processed=[c[0][2] for c in pipeline.call_args_list],
        validate=validate,
        loader=loader,
        loader_cls=loader_cls,
        loaded=[c[0][0][0].talk_id for c in loader.load.call_args_list],
        all_ids_mock=all_ids_mock,
        failed=json.loads(failed_path.read_text(encoding="utf-8")) if failed_path.exists() else None,
    )


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


# =============================================================================
# Helpers under test
# =============================================================================


def test_get_all_gc_talk_ids():
    """_get_all_gc_talk_ids queries core_db with INNER JOIN conference_talk and returns int list."""
    mock_db = MagicMock()
    mock_db.select.return_value = [{"ID": 1}, {"ID": 2}]

    with patch.object(run_pipeline, "core_db", mock_db):
        result = _get_all_gc_talk_ids()

    sql = mock_db.select.call_args[0][0]
    assert "INNER JOIN conference_talk" in sql, f"Expected INNER JOIN conference_talk in SQL: {sql}"
    assert result == [1, 2]


def test_record_failure_writes_json(tmp_path):
    """_record_failure appends to list and writes JSON file to disk."""
    failed_talks = []
    fake_path = tmp_path / "failed_talks.json"

    with patch.object(run_pipeline, "FAILED_TALKS_PATH", fake_path):
        _record_failure(123, "some error", failed_talks)

    assert failed_talks == [{"talk_id": 123, "error": "some error"}]
    assert json.loads(fake_path.read_text(encoding="utf-8")) == [
        {"talk_id": 123, "error": "some error"}
    ]


# =============================================================================
# Full-corpus runs
# =============================================================================


def test_full_loop_extracts_validates_and_loads_each_talk(tmp_path):
    r = _run(tmp_path=tmp_path, all_ids=(1, 2))
    assert r.processed == [1, 2]
    assert r.validate.call_count == 2
    assert r.loader.load.call_count == 2
    assert r.loader.flush.call_count >= 1  # final flush


def test_resume_skips_loaded_talks_with_one_scan(tmp_path):
    """Loaded talks come from one existing_talk_ids() scan, not a talk_exists() per talk."""
    r = _run(tmp_path=tmp_path, all_ids=(1, 2, 3), loaded_ids={1, 3})
    assert r.processed == [2]
    assert r.loader.existing_talk_ids.call_count == 1
    assert r.loader.talk_exists.call_count == 0


def test_force_reprocesses_without_scanning(tmp_path):
    r = _run(["--force"], tmp_path=tmp_path, all_ids=(1, 2), loaded_ids={1, 2})
    assert r.processed == [1, 2]
    assert r.loader.existing_talk_ids.call_count == 0


def test_extraction_exception_is_recorded(tmp_path):
    r = _run(tmp_path=tmp_path, all_ids=(42,), pipeline_side_effect=_boom)
    assert r.failed == [{"talk_id": 42, "error": "boom"}]
    assert r.loader.load.call_count == 0


def test_unsuccessful_result_is_recorded(tmp_path):
    def unsuccessful(content_db_arg, core_db_arg, talk_id, *args, **kwargs):
        return _make_pipeline_result(talk_id=talk_id, success=False)

    r = _run(tmp_path=tmp_path, all_ids=(7,), pipeline_side_effect=unsuccessful)
    assert r.failed == [{"talk_id": 7, "error": "extraction failed"}]


def test_validation_failure_is_recorded_and_not_loaded(tmp_path):
    r = _run(tmp_path=tmp_path, all_ids=(7,), validation=_make_validation(False))
    assert [e["talk_id"] for e in r.failed] == [7]
    assert r.loader.load.call_count == 0


def test_load_exception_is_recorded_against_that_talk(tmp_path):
    """An embedding/load error for one talk doesn't take other talks down with it."""
    def load(bundle):
        if bundle[0].talk_id == 2:
            raise RuntimeError("embed down")

    r = _run(tmp_path=tmp_path, all_ids=(1, 2, 3), load_side_effect=load)
    assert r.failed == [{"talk_id": 2, "error": "embed down"}]
    assert r.loader.load.call_count == 3


def test_final_summary_printed(tmp_path, capsys):
    _run(tmp_path=tmp_path, all_ids=(1,))
    out = capsys.readouterr().out
    for label in ("Run complete", "Processed:", "Skipped", "Failed:", "Load failed:"):
        assert label in out


# =============================================================================
# Weaviate buffering and insert failures
# =============================================================================


def test_loader_is_buffered_by_default(tmp_path):
    r = _run(tmp_path=tmp_path)
    assert r.loader_cls.call_args.kwargs["buffered"] is True


def test_unbuffered_flag_disables_buffering(tmp_path):
    r = _run(["--unbuffered"], tmp_path=tmp_path)
    assert r.loader_cls.call_args.kwargs["buffered"] is False


def test_legacy_buffered_flag_still_accepted(tmp_path):
    r = _run(["--buffered"], tmp_path=tmp_path)
    assert r.loader_cls.call_args.kwargs["buffered"] is True


def test_insert_failures_are_recorded_and_not_counted_processed(tmp_path, capsys):
    r = _run(tmp_path=tmp_path, all_ids=(1, 2), insert_failures={2: "weaviate X: bad"})
    assert r.failed == [{"talk_id": 2, "error": "weaviate X: bad"}]
    out = capsys.readouterr().out
    assert "Processed:         1" in out
    assert "Load failed:       1" in out


# =============================================================================
# Targeted runs: --talk-ids / --from-failed
# =============================================================================


def test_talk_ids_processes_only_named_talks_even_if_loaded(tmp_path):
    """--talk-ids redoes exactly the named talks, ignoring what's loaded, no full-corpus query."""
    r = _run(["--talk-ids", "5", "3"], tmp_path=tmp_path, gc_ids={3, 5, 9}, loaded_ids={3, 5})
    assert r.processed == [5, 3]
    assert r.loader.existing_talk_ids.call_count == 0
    assert r.all_ids_mock.call_count == 0
    assert [c[0][0] for c in r.loader.delete_talk.call_args_list] == [5, 3]


def test_talk_ids_skips_unknown_and_duplicates(tmp_path, capsys):
    r = _run(["--talk-ids", "5", "404", "5"], tmp_path=tmp_path, gc_ids={5})
    assert r.processed == [5]
    assert "404" in capsys.readouterr().out


def test_talk_ids_no_valid_ids_exits_before_setup(tmp_path):
    r = _run(["--talk-ids", "404"], tmp_path=tmp_path, gc_ids=set())
    assert r.processed == []
    assert r.loader_cls.call_count == 0


def test_talk_ids_failed_extraction_does_not_delete(tmp_path):
    """A redo that fails extraction keeps the old Weaviate objects."""
    r = _run(["--talk-ids", "5"], tmp_path=tmp_path, gc_ids={5}, pipeline_side_effect=_boom)
    assert r.loader.delete_talk.call_count == 0
    assert r.failed == [{"talk_id": 5, "error": "boom"}]


def test_talk_ids_validation_failure_does_not_delete(tmp_path):
    r = _run(["--talk-ids", "5"], tmp_path=tmp_path, gc_ids={5}, validation=_make_validation(False))
    assert r.loader.delete_talk.call_count == 0
    assert [e["talk_id"] for e in r.failed] == [5]


def test_targeted_run_merges_failure_log(tmp_path):
    """Redone talks that succeed are dropped from the log; other entries are kept."""
    existing = [{"talk_id": 1, "error": "old"}, {"talk_id": 2, "error": "old"}]
    r = _run(["--talk-ids", "1"], tmp_path=tmp_path, gc_ids={1, 2}, existing_failed=existing)
    assert r.failed == [{"talk_id": 2, "error": "old"}]


def test_targeted_run_replaces_entry_when_talk_fails_again(tmp_path):
    existing = [{"talk_id": 1, "error": "old"}, {"talk_id": 2, "error": "old"}]

    def new_error(*args, **kwargs):
        raise RuntimeError("new")

    r = _run(
        ["--talk-ids", "1"], tmp_path=tmp_path, gc_ids={1, 2},
        existing_failed=existing, pipeline_side_effect=new_error,
    )
    assert r.failed == [{"talk_id": 2, "error": "old"}, {"talk_id": 1, "error": "new"}]


def _interrupt_on(talk_id_to_stop):
    """process_talk_pipeline stand-in: fails talk 1, Ctrl-C on talk_id_to_stop."""

    def side_effect(content_db_arg, core_db_arg, talk_id, *args, **kwargs):
        if talk_id == talk_id_to_stop:
            raise KeyboardInterrupt
        if talk_id == 1:
            raise RuntimeError("new")
        return _default_pipeline(content_db_arg, core_db_arg, talk_id)

    return side_effect


def test_interrupted_targeted_run_keeps_entries_for_talks_not_redone(tmp_path):
    """A crash after the first failure must not drop the remaining targets from the log."""
    existing = [{"talk_id": t, "error": "old"} for t in (9, 1, 2, 3)]
    with pytest.raises(KeyboardInterrupt):
        _run(
            ["--talk-ids", "1", "2", "3"], tmp_path=tmp_path, gc_ids={1, 2, 3, 9},
            existing_failed=existing, pipeline_side_effect=_interrupt_on(2),
        )
    failed = json.loads((tmp_path / "failed_talks.json").read_text(encoding="utf-8"))
    assert failed == [
        {"talk_id": 9, "error": "old"},
        {"talk_id": 1, "error": "new"},
        {"talk_id": 2, "error": "old"},
        {"talk_id": 3, "error": "old"},
    ]


def test_interrupted_run_records_insert_failures_from_last_flush(tmp_path):
    """Insert failures from the flush on the way out are still logged."""
    with pytest.raises(KeyboardInterrupt):
        _run(
            tmp_path=tmp_path, all_ids=(5, 2), insert_failures={5: "weaviate X: bad"},
            pipeline_side_effect=_interrupt_on(2),
        )
    failed = json.loads((tmp_path / "failed_talks.json").read_text(encoding="utf-8"))
    assert failed == [{"talk_id": 5, "error": "weaviate X: bad"}]


def test_from_failed_redoes_logged_talks(tmp_path):
    existing = [{"talk_id": 150, "error": "x"}, {"talk_id": 451, "error": "y"}]
    r = _run(["--from-failed"], tmp_path=tmp_path, gc_ids={150, 451}, existing_failed=existing)
    assert r.processed == [150, 451]
    assert r.loader.existing_talk_ids.call_count == 0
    assert r.failed == []


def test_from_failed_with_no_log_does_nothing(tmp_path, capsys):
    r = _run(["--from-failed"], tmp_path=tmp_path, gc_ids={1})
    assert r.processed == []
    assert "nothing to do" in capsys.readouterr().out


def test_talk_ids_and_from_failed_are_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        _run(["--from-failed", "--talk-ids", "1"], tmp_path=tmp_path, gc_ids={1})


# =============================================================================
# WeaviateLoader: delete_talk, existing_talk_ids, flush error handling
# =============================================================================


def _real_loader(client=None, **kwargs):
    from loaders.weaviate_loader import WeaviateLoader

    client = client or MagicMock()
    client.collections.exists.return_value = True
    return WeaviateLoader(client=client, embed_fn=lambda t: [], **kwargs), client


def test_weaviate_loader_delete_talk_clears_all_collections():
    """delete_talk filters on talk_id in every collection, talks first."""
    from config.pipeline_config import WEAVIATE_COLLECTION_NAMES

    loader, client = _real_loader()
    loader.delete_talk(42)

    used = [c[0][0] for c in client.collections.use.call_args_list]
    assert used == [
        WEAVIATE_COLLECTION_NAMES[k] for k in ["talks", "paragraphs", "citations", "footnotes"]
    ]
    delete_many = client.collections.use.return_value.data.delete_many
    assert delete_many.call_count == 4
    where = delete_many.call_args.kwargs["where"]
    assert where.target == "talk_id" and where.value == 42


def test_weaviate_loader_existing_talk_ids():
    loader, client = _real_loader()
    client.collections.use.return_value.iterator.return_value = [
        SimpleNamespace(properties={"talk_id": 1}),
        SimpleNamespace(properties={"talk_id": 7}),
    ]
    assert loader.existing_talk_ids() == {1, 7}
    assert client.collections.use.return_value.iterator.call_args.kwargs == {
        "return_properties": ["talk_id"]
    }


def _obj(talk_id, kind):
    from weaviate.classes.data import DataObject

    return DataObject(properties={"talk_id": talk_id, "doc_id_str": f"{kind}_{talk_id}"})


def _collections_by_name(client):
    """Give each collection name its own mock so inserts can be inspected per collection."""
    cols = {}

    def use(name):
        if name not in cols:
            col = MagicMock()
            col.data.insert_many.return_value = SimpleNamespace(has_errors=False, errors={})
            cols[name] = col
        return cols[name]

    client.collections.use.side_effect = use
    return cols


def _inserted_talk_ids(col):
    return [o.properties["talk_id"] for o in col.data.insert_many.call_args[0][0]]


def test_flush_withholds_talk_object_when_a_dependent_insert_fails():
    from config.pipeline_config import WEAVIATE_COLLECTION_NAMES as N

    loader, client = _real_loader(buffered=True)
    cols = _collections_by_name(client)
    cols[N["paragraphs"]] = MagicMock()
    cols[N["paragraphs"]].data.insert_many.return_value = SimpleNamespace(
        has_errors=True, errors={1: SimpleNamespace(message="bad vector")}
    )
    loader._buffers["paragraphs"] = [_obj(1, "para"), _obj(2, "para")]
    loader._buffers["talks"] = [_obj(1, "talk"), _obj(2, "talk")]

    loader.flush()

    assert _inserted_talk_ids(cols[N["talks"]]) == [1]
    assert loader.pop_insert_failures() == {2: f"weaviate {N['paragraphs']}: bad vector"}
    assert loader.pop_insert_failures() == {}
    assert all(buf == [] for buf in loader._buffers.values())


def test_flush_records_every_talk_when_insert_many_raises():
    from config.pipeline_config import WEAVIATE_COLLECTION_NAMES as N

    loader, client = _real_loader(buffered=True)
    cols = _collections_by_name(client)
    cols[N["citations"]] = MagicMock()
    cols[N["citations"]].data.insert_many.side_effect = RuntimeError("timeout")
    loader._buffers["citations"] = [_obj(3, "cite"), _obj(4, "cite")]
    loader._buffers["talks"] = [_obj(3, "talk"), _obj(4, "talk"), _obj(5, "talk")]

    loader.flush()

    assert _inserted_talk_ids(cols[N["talks"]]) == [5]
    assert set(loader.pop_insert_failures()) == {3, 4}


def test_flush_records_failed_talk_object_insert():
    from config.pipeline_config import WEAVIATE_COLLECTION_NAMES as N

    loader, client = _real_loader(buffered=True)
    cols = _collections_by_name(client)
    cols[N["talks"]] = MagicMock()
    cols[N["talks"]].data.insert_many.return_value = SimpleNamespace(
        has_errors=True, errors={0: SimpleNamespace(message="nope")}
    )
    loader._buffers["talks"] = [_obj(9, "talk")]

    loader.flush()

    assert loader.pop_insert_failures() == {9: f"weaviate {N['talks']}: nope"}


# =============================================================================
# Parallel extraction (_iter_extractions / _extract_talk)
# =============================================================================
# Pool tests use real spawned processes, so the extract/initializer functions
# must be module-level (picklable by reference).


def _noop_init():
    pass


def _fake_extract(talk_id):
    if talk_id == 13:
        raise ValueError("unlucky")  # escapes the worker; must come back as an error
    return talk_id, ("ok", talk_id * 10)


def _unpicklable_extract(talk_id):
    return talk_id, ("ok", lambda: None)


def test_iter_extractions_pool_returns_every_talk():
    ids = list(range(1, 30))
    out = dict(_iter_extractions(ids, workers=2, extract=_fake_extract, initializer=_noop_init))
    assert set(out) == set(ids)
    assert out[5] == ("ok", 50)
    assert out[13][0] == "error" and "unlucky" in out[13][1]


def test_iter_extractions_pool_reports_unpicklable_result_as_error():
    out = list(_iter_extractions([1], workers=2, extract=_unpicklable_extract, initializer=_noop_init))
    assert out[0][0] == 1
    assert out[0][1][0] == "error"


def test_iter_extractions_single_worker_runs_in_process_in_order():
    calls = []
    out = list(
        _iter_extractions([3, 1, 2], workers=1, extract=lambda t: (t, ("ok", t)),
                          initializer=lambda: calls.append("init"))
    )
    assert [t for t, _ in out] == [3, 1, 2]
    assert calls == ["init"]


def test_iter_extractions_bounds_in_flight_work():
    """No more than workers * 4 talks are submitted ahead of the consumer."""
    submitted = []

    class FakeFuture:
        def __init__(self, value):
            self.value = value

        def result(self):
            return self.value

    class FakePool:
        def __init__(self, *a, **k):
            pass

        def submit(self, fn, talk_id):
            submitted.append(talk_id)
            return FakeFuture(fn(talk_id))

        def shutdown(self, **k):
            pass

    with (
        patch.object(run_pipeline, "ProcessPoolExecutor", FakePool),
        patch.object(run_pipeline, "wait", lambda fs, return_when: ({next(iter(fs))}, set())),
    ):
        gen = _iter_extractions(range(100), workers=2, extract=lambda t: (t, ("ok", t)),
                                initializer=_noop_init)
        next(gen)
        assert len(submitted) == 2 * 4 + 1  # initial window + one refill
        gen.close()


def test_extract_talk_outcomes():
    """_extract_talk turns success / unsuccessful / invalid / exception into outcomes."""
    with (
        patch.object(run_pipeline, "process_talk_pipeline", side_effect=_default_pipeline),
        patch.object(run_pipeline, "validate_talk", return_value=_make_validation(True)),
    ):
        talk_id, (kind, bundle) = run_pipeline._extract_talk(4)
    assert (talk_id, kind, len(bundle)) == (4, "ok", 5)

    with patch.object(
        run_pipeline, "process_talk_pipeline",
        return_value=_make_pipeline_result(success=False),
    ):
        assert run_pipeline._extract_talk(4) == (4, ("error", "extraction failed"))

    with (
        patch.object(run_pipeline, "process_talk_pipeline", side_effect=_default_pipeline),
        patch.object(run_pipeline, "validate_talk", return_value=_make_validation(False)),
    ):
        assert run_pipeline._extract_talk(4) == (4, ("validation", ["validation error"]))

    with patch.object(run_pipeline, "process_talk_pipeline", side_effect=_boom):
        assert run_pipeline._extract_talk(4) == (4, ("error", "boom"))


def test_workers_flag_reaches_iter_extractions(tmp_path):
    with patch.object(run_pipeline, "_iter_extractions", return_value=iter([])) as it:
        _run(["--workers", "3"], tmp_path=tmp_path)
    assert it.call_args[0][1] == 3
