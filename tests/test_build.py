"""Unit tests for build.py's match-report classification (no DB)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from build import bucket_church_items, expected_church_category


class TestExpectedChurchItems:
    def test_known_kinds_are_expected(self):
        cases = {
            "Sustaining of General Authorities, Area Seventies, and General Officers": "sustaining",
            "The Sustaining of Church Officers": "sustaining",
            "The Solemn Assembly": "sustaining",
            "Statistical Report, 2016": "statistical report",
            "The Annual Report of the Church": "statistical report",
            "Church Auditing Department Report, 2025": "audit/finance report",
            "Church Audit Committee Report": "audit/finance report",
            "Church Finance Committee Report": "audit/finance report",
            "Address Given by President Spencer W. Kimball at the Welfare Services Meeting": "welfare services",
            "Video: The Light That Shineth in Darkness": "video",
            "Faith in Every Footstep: The Epic Pioneer Journey [Video Presentation]": "video",
            "Music and the Spoken Word": "broadcast",
        }
        for title, category in cases.items():
            assert expected_church_category("/general-conference/x", title) == category, title

    def test_one_off_by_uri(self):
        uri = "/general-conference/1995/10/the-family-a-proclamation-to-the-world"
        assert expected_church_category(uri, "The Family: A Proclamation to the World") == "one-off"

    def test_ordinary_talk_is_unexpected(self):
        assert expected_church_category("/general-conference/2026/10/12gong", "Come to the Lord in His Holy House") is None
        assert expected_church_category("/general-conference/x", None) is None

    def test_bucket(self):
        result = bucket_church_items({
            "/gc/b": "Sustaining of Church Officers",
            "/gc/a": "A Real Talk",
        })
        assert result == {
            "expected": {"sustaining": ["/gc/b"]},
            "unexpected": [{"uri": "/gc/a", "title": "A Real Talk"}],
        }
