import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_pageviews as p  # noqa: E402


class PageviewTests(unittest.TestCase):
    def test_total_skips_missing_days(self):
        self.assertEqual(p.page_total({"title": "A", "pageviews": {"2026-11-01": 10, "2026-11-02": None}}), 10)
        self.assertIsNone(p.page_total({"title": "A"}))

    def test_total_rejects_odd_counts(self):
        with self.assertRaises(p.ShapeError):
            p.page_total({"title": "A", "pageviews": {"2026-11-01": "10"}})
        with self.assertRaises(p.ShapeError):
            p.page_total({"title": "A", "pageviews": [1, 2]})

    def test_redirects_and_normalised_titles_map_back(self):
        replies = [
            {"continue": {"pvipcontinue": "B", "continue": "||"},
             "query": {"normalized": [{"from": "a_game", "to": "A game"}],
                       "redirects": [{"from": "A game", "to": "A Game (video game)"}],
                       "pages": [{"title": "A Game (video game)", "pageviews": {"d1": 5, "d2": 7}},
                                 {"title": "Gone", "missing": True, "pageviews": {"d1": None}}]}},
            {"batchcomplete": True,
             "query": {"pages": [{"title": "B", "pageviews": {"d1": 3}}]}},
        ]
        with mock.patch.object(p, "request_json", side_effect=replies), mock.patch.object(p.time, "sleep"):
            result = p.views_for_batch(["a_game", "B", "Gone"], pause=0)
        self.assertEqual(result, {"a_game": 12, "B": 3})

    def test_reply_without_pages_stops(self):
        with mock.patch.object(p, "request_json", return_value={"query": {}}):
            with self.assertRaises(p.ShapeError):
                p.views_for_batch(["A"], pause=0)

    def test_api_error_stops(self):
        with mock.patch.object(p, "request_json", return_value={"error": {"code": "badvalue"}}):
            with self.assertRaises(p.ShapeError):
                p.views_for_batch(["A"], pause=0)


if __name__ == "__main__":
    unittest.main()
