import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import report_differences as r  # noqa: E402

LABELS = {"Q1406": {"en": "Microsoft Windows"}, "Q19610114": {"en": "Nintendo Switch"},
          "Q337535": {"en": "Steam"}, "Q10677": {"en": "PlayStation"}, "Q16338": {"en": "personal computer"}}


def game(qid, **fields):
    record = {"id": qid, "labels": {"en": f"Game {qid}"}, "is_game": True, "platforms": [], "release_dates": []}
    record.update(fields)
    return record


def date_(time, precision=11, rank="normal", **qualifiers):
    return {"statement": "x", "time": time, "precision": precision, "rank": rank, "qualifiers": qualifiers}


class ChecksTest(unittest.TestCase):
    def rows(self, games, matched=None, pageviews=None, protondb=None, commons=None, as_of="2026-11-17"):
        return r.build_rows({g["id"]: g for g in games}, matched or {}, LABELS, pageviews, protondb, commons, as_of)

    def checks(self, rows):
        return [(row["check"], row["wikidata"]) for row in rows]

    def test_store_id_without_matching_platform(self):
        rows = self.rows([
            game("Q1", platforms=["Q10677"], steam=["205950"]),             # Steam ID, console only -> row
            game("Q2", platforms=["Q1406"], steam=["10"]),                  # Steam + Windows -> fine
            game("Q3", platforms=["Q1406"], eshop=["portal-2-switch"]),     # eShop ID, no Nintendo console -> row
            game("Q4", platforms=["Q16338"]),                               # "personal computer" counts as PC
            game("Q5", platforms=["Q10677"], is_game=False, steam=["1"]),   # not a game -> skipped
        ], matched={"Q4": {"epic": "abc"}, "Q6": {"steam": "7"}})
        self.assertEqual(self.checks(rows), [("store-id-without-platform", "Q1"), ("store-id-without-platform", "Q3")])
        self.assertIn("Steam ID (P1733 = 205950)", rows[0]["detail"])
        self.assertIn("PlayStation (Q10677)", rows[0]["detail"])
        self.assertEqual(rows[0]["licence"], "CC0")

    def test_epic_id_comes_from_matched(self):
        rows = self.rows([game("Q7", platforms=["Q10677"])], matched={"Q7": {"epic": "fortnite"}})
        self.assertEqual(self.checks(rows), [("store-id-without-platform", "Q7")])
        self.assertIn("Epic Games Store", rows[0]["detail"])

    def test_store_used_as_platform(self):
        rows = self.rows([game("Q8", platforms=["Q337535", "Q1406"])])
        self.assertEqual(self.checks(rows), [("platform-not-a-platform", "Q8")])
        self.assertIn("Steam (Q337535)", rows[0]["detail"])

    def test_date_platform_not_listed_and_personal_computer(self):
        rows = self.rows([
            game("Q9", platforms=["Q1406"], release_dates=[date_("2020-01-02T00:00:00Z", P400=["Q19610114"])]),
            game("Q10", platforms=["Q1406"], release_dates=[date_("2009-12-23T00:00:00Z", P400=["Q16338"])]),
            game("Q11", platforms=["Q1406"], release_dates=[date_("2009-12-23T00:00:00Z", rank="deprecated",
                                                                  P400=["Q19610114"])]),
        ])
        self.assertEqual(self.checks(rows), [("date-platform-not-listed", "Q10"), ("date-platform-not-listed", "Q9")])
        self.assertIn("Change the date's platform qualifier to Microsoft Windows", rows[0]["suggested_fix"])
        self.assertIn("Add platform (P400) Nintendo Switch (Q19610114)", rows[1]["suggested_fix"])

    def test_platform_or_store_in_place_of_publication(self):
        rows = self.rows([
            game("Q12", platforms=["Q1406"], release_dates=[date_("2024-04-05T00:00:00Z", P291=["Q1406"])]),
            game("Q13", platforms=["Q1406"], release_dates=[date_("2013-10-31T00:00:00Z", P291=["Q337535"])]),
            game("Q14", platforms=["Q1406"], release_dates=[date_("2013-10-31T00:00:00Z", P291=["Q29"])]),  # Spain
        ])
        self.assertEqual(self.checks(rows), [("platform-in-wrong-qualifier", "Q12"), ("platform-in-wrong-qualifier", "Q13")])
        self.assertIn("qualifier platform (P400) = Microsoft Windows", rows[0]["suggested_fix"])
        self.assertIn("distributed by (P750)", rows[1]["suggested_fix"])

    def test_reports_before_release_split_by_released_and_upcoming(self):
        protondb = {"1": {"latest": "2024-07-20"}, "2": {"latest": "2026-09-30"}, "3": {"latest": "2023-01-01"},
                    "4": {"latest": "2024-08-10"}}
        rows = self.rows([
            game("Q15", platforms=["Q1406"], steam=["1"], release_dates=[date_("2024-08-23T00:00:00Z")]),
            game("Q16", platforms=["Q1406"], steam=["2"], release_dates=[date_("2027-01-01T00:00:00Z", 9)]),
            game("Q17", platforms=["Q1406"], steam=["3"], release_dates=[date_("2020-05-01T00:00:00Z")]),  # fine
            # Month precision: "August 2024" may mean 10 Aug, so a report on 10 Aug is no difference.
            game("Q18", platforms=["Q1406"], steam=["4"], release_dates=[date_("2024-08-01T00:00:00Z", 10)]),
        ], protondb=protondb)
        self.assertEqual(self.checks(rows), [("playtest-before-release", "Q16"), ("reports-before-release", "Q15")])
        for row in rows:
            self.assertEqual(row["hint_from"], "protondb")
            self.assertEqual(row["licence"], "ODbL 1.0")
            self.assertIn("never ProtonDB", row["fix_source"])

    def test_commons_missing_file(self):
        commons = {"Gone.png": {"missing": True, "used_as": ["logo"]}, "Here.png": {"reuse": "public-domain"}}
        rows = self.rows([game("Q19", platforms=["Q1406"], commons_logos=["Gone.png", "Here.png"])], commons=commons)
        self.assertEqual(self.checks(rows), [("commons-file-missing", "Q19")])
        self.assertTrue(rows[0]["detail"].startswith('Logo (P154) = "Gone.png"'))
        self.assertEqual(rows[0]["licence"], "CC BY-SA 4.0")

    def test_missing_sources_skip_their_checks(self):
        rows = self.rows([game("Q20", platforms=["Q1406"], steam=["1"], release_dates=[date_("2024-08-23T00:00:00Z")],
                               commons_logos=["Gone.png"])], protondb=None, commons=None)
        self.assertEqual(rows, [])

    def test_sorted_by_page_views_best_known_first(self):
        rows = self.rows([game("Q21", platforms=["Q337535"]), game("Q22", platforms=["Q337535"]),
                          game("Q23", platforms=["Q337535"])], pageviews={"Q22": 500, "Q23": 7})
        self.assertEqual([row["wikidata"] for row in rows], ["Q22", "Q23", "Q21"])
        self.assertEqual(rows[2]["pageviews_60d"], "")

    def test_period_start(self):
        self.assertEqual(str(r.period_start("2023-08-01T00:00:00Z", 10)), "2023-08-01")
        self.assertEqual(str(r.period_start("2023-08-14T00:00:00Z", 9)), "2023-01-01")
        self.assertIsNone(r.period_start("2023-01-01T00:00:00Z", 8))   # decade: too vague to compare
        self.assertIsNone(r.period_start("-0500-01-01T00:00:00Z", 9))


class MainTest(unittest.TestCase):
    def test_writes_csv_and_survives_missing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            games = root / "sources" / "wikidata-details" / "games"
            games.mkdir(parents=True)
            (games / "000.json").write_text(
                "[\n" + json.dumps(game("Q1000", platforms=["Q337535"])) + ",\n{broken\n]\n", encoding="utf-8")
            (root / "matched").mkdir()
            out = root / "reports" / "differences.csv"
            output = io.StringIO()
            with mock.patch.object(r, "ROOT", root), redirect_stdout(output):
                self.assertEqual(r.main(["--out", str(out)]), 0)
            text = output.getvalue()
            self.assertIn("ProtonDB: sources/protondb/summary.json not found", text)
            self.assertIn("000.json line 3 is not valid JSON", text)
            with out.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["check"] for row in rows], ["platform-not-a-platform"])
            self.assertEqual(list(rows[0].keys()), list(r.COLUMNS))


if __name__ == "__main__":
    unittest.main()
