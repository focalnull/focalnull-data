import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_wikidata_details as d  # noqa: E402


def item(prop, qid, rank="normal", quals=None, sid="x"):
    statement = {"id": sid, "rank": rank, "mainsnak": {
        "snaktype": "value", "property": prop,
        "datavalue": {"type": "wikibase-entityid", "value": {"entity-type": "item", "id": qid}}}}
    if quals:
        statement["qualifiers"] = quals
    return statement


def qual(prop, qid):
    return {"snaktype": "value", "property": prop,
            "datavalue": {"type": "wikibase-entityid", "value": {"id": qid}}}


def date(time, precision, rank="normal", quals=None, sid="Q1$a"):
    statement = {"id": sid, "rank": rank, "mainsnak": {
        "snaktype": "value", "property": "P577",
        "datavalue": {"type": "time", "value": {
            "time": time, "precision": precision,
            "calendarmodel": "http://www.wikidata.org/entity/Q1985727"}}}}
    if quals:
        statement["qualifiers"] = quals
    return statement


def string(prop, value, rank="normal", quals=None):
    statement = {"rank": rank, "mainsnak": {"snaktype": "value", "property": prop,
                                            "datavalue": {"type": "string", "value": value}}}
    if quals:
        statement["qualifiers"] = quals
    return statement


# Shaped like Baldur's Gate 3 (Q64441774) as wbgetentities returned it on 17 Nov 2026.
BG3 = {
    "id": "Q64441774", "lastrevid": 2570088067, "modified": "2026-11-16T01:21:46Z",
    "labels": {"mul": {"language": "mul", "value": "Baldur's Gate 3"},
               "ru": {"language": "ru", "value": "Baldur's Gate III"}},
    "aliases": {"en": [{"language": "en", "value": "BG3"}]},
    "descriptions": {"en": {"language": "en", "value": "2023 role-playing video game"}},
    "sitelinks": {"enwiki": {"site": "enwiki", "title": "Baldur's Gate 3"}},
    "claims": {
        "P31": [item("P31", "Q7889")],
        "P400": [item("P400", "Q1406"), item("P400", "Q14116"), item("P400", "Q1", rank="deprecated")],
        "P178": [item("P178", "Q2001")],
        "P123": [item("P123", "Q2001")],
        "P179": [item("P179", "Q2640148", quals={"P1545": [{"snaktype": "value", "datavalue": {
            "type": "string", "value": "3"}}]})],
        "P155": [item("P155", "Q804859")],
        "P1651": [string("P1651", "old"), string("P1651", "new", rank="preferred")],
        "P856": [string("P856", "https://old.example", quals={"P582": [{"snaktype": "value", "datavalue": {
                     "type": "time", "value": {"time": "+2020-00-00T00:00:00Z"}}}]}),
                 string("P856", "https://baldursgate3.game")],
        "P577": [
            date("+2020-10-06T00:00:00Z", 11, quals={
                "P3831": [qual("P3831", "Q17042291")],
                "P400": [qual("P400", "Q1406"), qual("P400", "Q14116")]}, sid="Q64441774$a"),
            date("+2023-08-03T00:00:00Z", 11, rank="preferred", quals={
                "P3831": [qual("P3831", "Q116856827")], "P400": [qual("P400", "Q1406")]}, sid="Q64441774$b"),
            date("+2023-09-00T00:00:00Z", 10, quals={"P291": [qual("P291", "Q46")]}, sid="Q64441774$c"),
            date("+2019-00-00T00:00:00Z", 9, rank="deprecated", sid="Q64441774$d"),
            {"rank": "normal", "mainsnak": {"snaktype": "somevalue", "property": "P577"}},
        ],
    },
}


class DetailTests(unittest.TestCase):
    def setUp(self):
        self.record = d.game_record(BG3, {"Q7889"}, {"Q1066707"})

    def test_times_are_written_like_the_query_service(self):
        self.assertEqual(d.normalise_time("+2021-10-00T00:00:00Z"), "2021-10-01T00:00:00Z")
        self.assertEqual(d.normalise_time("+2002-00-00T00:00:00Z"), "2002-01-01T00:00:00Z")
        self.assertEqual(d.normalise_time("-0500-00-00T00:00:00Z"), "-0500-01-01T00:00:00Z")
        with self.assertRaises(d.ShapeError):
            d.normalise_time("2021")

    def test_release_dates_keep_precision_rank_and_qualifiers(self):
        dates = self.record["release_dates"]
        self.assertEqual([x["statement"] for x in dates], ["Q64441774$a", "Q64441774$b", "Q64441774$c"])
        self.assertEqual(dates[0], {"statement": "Q64441774$a", "time": "2020-10-06T00:00:00Z",
                                    "precision": 11, "rank": "normal",
                                    "qualifiers": {"P3831": ["Q17042291"], "P400": ["Q1406", "Q14116"]}})
        self.assertEqual(dates[1]["rank"], "preferred")
        self.assertEqual(dates[2]["time"], "2023-09-01T00:00:00Z")
        self.assertEqual(dates[2]["precision"], 10)
        self.assertEqual(dates[2]["qualifiers"], {"P291": ["Q46"]})

    def test_simple_facts(self):
        r = self.record
        self.assertEqual(r["platforms"], ["Q1406", "Q14116"])  # deprecated left out
        self.assertEqual(r["developers"], ["Q2001"])
        self.assertEqual(r["series"], ["Q2640148"])
        self.assertEqual(r["youtube"], ["new"])  # preferred wins
        self.assertEqual(r["official_websites"], ["https://baldursgate3.game"])  # ended site left out
        self.assertEqual(r["relations"], {"P179": [{"id": "Q2640148", "ordinal": "3"}],
                                          "P155": [{"id": "Q804859"}]})
        self.assertEqual(r["enwiki"], "Baldur's Gate 3")
        self.assertEqual(r["labels"], {"mul": "Baldur's Gate 3", "ru": "Baldur's Gate III"})
        self.assertEqual(r["aliases"], {"en": ["BG3"]})
        self.assertTrue(r["is_game"])
        self.assertEqual(r["lastrevid"], 2570088067)

    def test_expansions_are_not_games(self):
        entity = json.loads(json.dumps(BG3))
        entity["claims"]["P31"].append(item("P31", "Q1066707"))
        self.assertFalse(d.game_record(entity, {"Q7889"}, {"Q1066707"})["is_game"])

    def test_all_labels_kept_when_no_english_name(self):
        entity = json.loads(json.dumps(BG3))
        entity["labels"] = {"ja": {"value": "ゲーム"}, "ar": {"value": "لعبة"}}
        self.assertEqual(d.game_record(entity, {"Q7889"}, set())["labels"], {"ar": "لعبة", "ja": "ゲーム"})

    def test_referenced_items_and_companies(self):
        items, companies = d.referenced_items(self.record)
        self.assertEqual(companies, {"Q2001"})
        self.assertTrue({"Q1406", "Q14116", "Q17042291", "Q116856827", "Q46", "Q804859", "Q7889"} <= items)

    def test_redirects_and_deleted_items_are_skipped(self):
        reply = {"entities": {"Q64441774": BG3, "Q5": {"id": "Q5", "missing": ""},
                              "Q9": dict(BG3, id="Q9")}}
        with mock.patch.object(d, "request_json", return_value=reply):
            records, skipped = d.fetch_games(["Q64441774", "Q5", "Q6"], {"Q7889"}, set())
        self.assertEqual([r["id"] for r in records], ["Q64441774"])
        self.assertEqual(skipped, 2)

    def test_api_errors_and_odd_shapes_stop(self):
        with mock.patch.object(d, "request_json", return_value={"error": {"code": "x"}}):
            with self.assertRaises(d.ShapeError):
                d.get_entities(["Q1"], "labels", "en")
        with mock.patch.object(d, "request_json", return_value={"entities": []}):
            with self.assertRaises(d.ShapeError):
                d.get_entities(["Q1"], "labels", "en")
        with self.assertRaises(d.ShapeError):
            d.game_record({"id": "Q1", "claims": []}, set(), set())

    def test_labels_include_company_logos(self):
        reply_companies = {"entities": {"Q2001": {"id": "Q2001", "labels": {"en": {"value": "Larian Studios"}},
                                                  "claims": {"P154": [string("P154", "Larian.svg")]}}}}
        reply_other = {"entities": {"Q1406": {"id": "Q1406", "labels": {"en": {"value": "Microsoft Windows"},
                                                                         "fr": {"value": "x"}}}}}
        with mock.patch.object(d, "request_json", side_effect=[reply_companies, reply_other]), \
                mock.patch.object(d.time, "sleep"):
            labels = d.fetch_labels(["Q1406", "Q2001"], {"Q2001"}, pause=0)
        self.assertEqual(labels, {"Q2001": {"en": "Larian Studios", "logo": "Larian.svg"},
                                  "Q1406": {"en": "Microsoft Windows"}})

    def test_files_are_valid_json_one_entry_per_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(d, "GAMES", Path(tmp) / "games"), \
                    mock.patch.object(d, "LABELS", Path(tmp) / "labels.json"):
                d.write_bucket("774", [self.record, {"id": "Q774", "is_game": True}])
                text = (Path(tmp) / "games" / "774.json").read_text(encoding="utf-8")
                self.assertEqual([r["id"] for r in json.loads(text)], ["Q774", "Q64441774"])
                self.assertEqual(len(text.splitlines()), 4)
                d.write_labels({"Q20": {"en": "b"}, "Q3": {"en": "a"}}, "2026-11-17")
                self.assertEqual(d.read_labels(), {"Q3": {"en": "a"}, "Q20": {"en": "b"}})


if __name__ == "__main__":
    unittest.main()
