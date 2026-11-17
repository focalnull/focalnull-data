import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_wikidata_ids as f  # noqa: E402


def claim(value, rank="normal"):
    return {"rank": rank, "mainsnak": {"datavalue": {"value": value}}}


class RecordTests(unittest.TestCase):
    def test_bucket_uses_last_three_digits(self):
        self.assertEqual(f.bucket("Q15727"), "727")
        self.assertEqual(f.bucket("Q5"), "005")

    def test_record_collects_label_wikipedia_and_ids(self):
        entity = {
            "id": "Q15727",
            "labels": {"en": {"value": "Example Game"}},
            "sitelinks": {"enwiki": {"title": "Example Game"}},
            "claims": {
                "P1733": [claim("12345", rank="deprecated"), claim("620")],
                "P6337": [claim("Example_Game")],
            },
        }
        record = f.record_from_entity(entity)
        self.assertEqual(record["wikidata"], "Q15727")
        self.assertEqual(record["label_en"], "Example Game")
        self.assertEqual(record["enwiki"], "Example Game")
        self.assertEqual(record["ids"], {"steam": "620", "pcgamingwiki": "Example_Game"})

    def test_label_falls_back_to_the_default_for_all_languages(self):
        record = f.record_from_entity({"id": "Q3", "labels": {"mul": {"value": "Tetris"}}})
        self.assertEqual(record["label_en"], "Tetris")

    def test_missing_entities_are_skipped(self):
        self.assertIsNone(f.record_from_entity({"id": "Q1", "missing": ""}))

    def test_record_without_ids_has_no_ids_key(self):
        self.assertNotIn("ids", f.record_from_entity({"id": "Q2", "claims": {}}))


class FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload, self.headers = payload, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        import json
        return json.dumps(self.payload).encode()


class MaxlagTests(unittest.TestCase):
    def test_waits_on_maxlag_then_succeeds(self):
        from unittest import mock
        replies = [FakeResponse({"error": {"code": "maxlag", "lag": 7}}), FakeResponse({"entities": {}})]
        with mock.patch.object(f.urllib.request, "urlopen", side_effect=replies), \
                mock.patch.object(f.time, "sleep") as sleep:
            self.assertEqual(f.request_json("https://example.org", {}), {"entities": {}})
        sleep.assert_called_once_with(7.0)

    def test_gives_up_after_the_last_try(self):
        from unittest import mock
        reply = FakeResponse({"error": {"code": "maxlag", "lag": 1}})
        with mock.patch.object(f.urllib.request, "urlopen", return_value=reply), \
                mock.patch.object(f.time, "sleep"):
            with self.assertRaises(RuntimeError):
                f.request_json("https://example.org", {}, tries=3)


if __name__ == "__main__":
    unittest.main()
