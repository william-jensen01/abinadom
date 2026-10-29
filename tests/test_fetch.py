"""Unit tests for the fetch side (no network): JSON helpers and fetch functions."""

import datetime
import json
from unittest.mock import MagicMock

import pytest
import requests

from api.fetch_talk_previews import all_conferences, fetch_previews, fetch_talk_list, parse_conference
from process_topic_talks.extract_talk_metadata import fetch_all_metadata
from scripts.process_topics import fetch_topics_index, process_topics
from utils.json_io import merge_by_key, read_json, write_json


def _response(payload=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    if status >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)
    return resp


def _session(pages):
    """Fake session: pages maps a URI suffix to a payload, an HTTP status or an exception."""
    session = MagicMock()

    def get(url, timeout):
        uri = url.split("uri=", 1)[1]
        page = pages[uri]
        if isinstance(page, Exception):
            raise page
        if isinstance(page, int):
            return _response(status=page)
        return _response(page)

    session.get.side_effect = get
    return session


def _talk_page(title="T", aid="1", role="Apostle", preview="P"):
    return {
        "content": {
            "meta": {"title": title, "pageAttributes": {"data-aid": aid}},
            "content": {
                "body": f'<p class="author-role">{role}</p>',
                "head": {"page-meta-social": {"pageMeta": {"description": preview}}},
            },
        }
    }


# ---------------------------------------------------------------------------
# utils/json_io
# ---------------------------------------------------------------------------
class TestJsonIo:
    def test_write_json_is_sorted_utf8_with_trailing_newline(self, tmp_path):
        path = tmp_path / "out.json"
        write_json(str(path), [{"uri": "/b", "t": "Élder"}, {"uri": "/a", "t": "x"}])
        raw = path.read_bytes()
        assert raw.endswith(b"]\n")
        assert b"\r\n" not in raw
        assert "Élder".encode("utf-8") in raw  # not \u-escaped
        assert [r["uri"] for r in json.loads(raw)] == ["/a", "/b"]

    def test_write_json_is_byte_stable(self, tmp_path):
        path = tmp_path / "out.json"
        records = [{"uri": "/b"}, {"uri": "/a"}]
        write_json(str(path), records)
        first = path.read_bytes()
        write_json(str(path), read_json(str(path)))
        assert path.read_bytes() == first

    def test_read_json_missing_file_is_empty(self, tmp_path):
        assert read_json(str(tmp_path / "nope.json")) == []

    def test_merge_replaces_and_adds(self):
        existing = [{"uri": "/a", "old": 1}, {"uri": "/b", "v": 1}]
        new = [{"uri": "/b", "v": 2}, {"uri": "/c", "v": 3}]
        merged = {r["uri"]: r for r in merge_by_key(existing, new)}
        assert merged == {
            "/a": {"uri": "/a", "old": 1},
            "/b": {"uri": "/b", "v": 2},  # replaced, not updated
            "/c": {"uri": "/c", "v": 3},
        }


# ---------------------------------------------------------------------------
# Conferences and talk pages
# ---------------------------------------------------------------------------
class TestConferences:
    def test_parse_conference(self):
        assert parse_conference("2025-10") == (2025, "10")
        with pytest.raises(Exception):
            parse_conference("2025-07")

    def test_all_conferences_through_current_month(self):
        confs = all_conferences(datetime.date(2026, 4, 2))
        assert confs[0] == (1971, "04")
        assert confs[-1] == (2026, "04")
        assert all_conferences(datetime.date(2026, 3, 31))[-1] == (2025, "10")

    def test_newest_conference_404_is_skipped(self):
        toc = {"toc": {"entries": [{}, {"section": {"entries": [{"content": {"uri": "/t1", "title": "A"}}]}}]}}
        session = _session({"/general-conference/2026/04": toc, "/general-conference/2026/10": 404})
        talks = fetch_talk_list(session, [(2026, "04"), (2026, "10")])
        assert [t["uri"] for t in talks] == ["/t1"]

    def test_older_conference_404_raises(self):
        session = _session({"/general-conference/2026/04": 404, "/general-conference/2026/10": {"toc": {}}})
        with pytest.raises(requests.exceptions.HTTPError):
            fetch_talk_list(session, [(2026, "04"), (2026, "10")])

    def test_metadata_in_input_order_and_failures_skipped(self):
        session = _session({
            "/z": _talk_page(title="Z", aid="9"),
            "/x": requests.exceptions.ConnectionError("down"),
            "/a": _talk_page(title="A &amp; B", aid="1"),
        })
        results = fetch_all_metadata(session, ["/z", "/x", "/a"])
        assert results == [
            {"uri": "/z", "title": "Z", "speaker_role": "Apostle", "data_aid": "9"},
            {"uri": "/a", "title": "A & B", "speaker_role": "Apostle", "data_aid": "1"},
        ]

    def test_previews_failures_skipped(self):
        session = _session({"/a": _talk_page(preview="Hi"), "/x": requests.exceptions.Timeout("slow")})
        results = fetch_previews(session, [{"uri": "/a", "title": "A"}, {"uri": "/x", "title": "X"}])
        assert results == [{"uri": "/a", "title": "A", "preview": "Hi"}]


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------
class TestTopics:
    def test_topics_index_reads_search_items(self):
        items = [{"type": "collection", "title": "faith", "uri": "/general-conference/topics/faith"}]
        page = {"collection": {"sections": [{"entries": [{"type": "search", "items": items}]}]}}
        assert fetch_topics_index(_session({"/general-conference/topics": page})) == items

    def test_entries_sorted_uri_descending(self):
        page = {"collection": {"sections": [
            {"entries": [{"uri": "/gc/2019/04/21b"}, {"uri": "/gc/2025/10/11a"}]},
            {"entries": [{"uri": "/gc/2019/04/31c"}]},
        ]}}
        results, missing = process_topics([{"title": "faith", "uri": "/t/faith"}], _session({"/t/faith": page}))
        assert [e["uri"] for e in results[0]["entries"]] == ["/gc/2025/10/11a", "/gc/2019/04/31c", "/gc/2019/04/21b"]
        assert missing == []

    def test_404_topic_keeps_previous_entries(self):
        topic = {"title": "values", "uri": "/t/values"}
        old = {"values": [{"uri": "/gc/1"}]}
        results, missing = process_topics([topic], _session({"/t/values": 404}), old)
        assert results == [{"topic": "values", "entries": [{"uri": "/gc/1"}]}]
        assert missing == [topic]

    def test_other_errors_abort(self):
        topics = [{"title": "a", "uri": "/t/a"}]
        with pytest.raises(requests.exceptions.HTTPError):
            process_topics(topics, _session({"/t/a": 500}), {"a": [{"uri": "/gc/1"}]})
        with pytest.raises(requests.exceptions.ConnectionError):
            process_topics(topics, _session({"/t/a": requests.exceptions.ConnectionError()}))
