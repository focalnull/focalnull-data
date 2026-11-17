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

    def test_missing_entities_are_skipped(self):
        self.assertIsNone(f.record_from_entity({"id": "Q1", "missing": ""}))

    def test_record_without_ids_has_no_ids_key(self):
        self.assertNotIn("ids", f.record_from_entity({"id": "Q2", "claims": {}}))


if __name__ == "__main__":
    unittest.main()
