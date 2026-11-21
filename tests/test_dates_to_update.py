import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dates_to_update as d  # noqa: E402

TODAY = dt.date(2026, 11, 22)


def game(qid, *dates, enwiki="Game", views_title="Game"):
    return {"id": qid, "labels": {"en": views_title}, "enwiki": enwiki, "is_game": True,
            "release_dates": [{"time": t, "precision": p, "rank": "normal"} for t, p in dates]}


class InfoboxTests(unittest.TestCase):
    # Shapes copied from real articles on 21 Nov 2026 (Fable, 007 First Light, BeamNG.drive,
    # Kingdom Hearts IV, Enshrouded).
    def test_plain_day_ignores_footnote(self):
        text = "23 February 2027{{efn|Pre-ordering grants five-day [[early access]] beginning on 18 February 2027.}}"
        self.assertEqual(d.day_dates(text), [{"date": "2027-02-23", "platforms": "", "note": ""}])

    def test_platform_list(self):
        text = "{{ubl|'''PS5''', '''Windows''', '''Xbox Series&nbsp;X/S'''|27 May 2026|'''Nintendo Switch 2'''|18 March 2027}}"
        self.assertEqual(d.day_dates(text), [
            {"date": "2026-05-27", "platforms": "PS5, Windows, Xbox Series X/S", "note": ""},
            {"date": "2027-03-18", "platforms": "Nintendo Switch 2", "note": ""}])

    def test_early_access_note_and_year_only(self):
        text = "{{ubl|'''Windows'''|May 29, 2015 (early access)|'''Linux'''|\n2022 (early access)}}"
        self.assertEqual(d.day_dates(text), [{"date": "2015-05-29", "platforms": "Windows", "note": "early access"}])

    def test_no_day(self):
        self.assertEqual(d.day_dates("{{Video game release|WW|Late 2027}}"), [])
        self.assertEqual(d.day_dates("31 February 2027"), [])

    def test_start_date_template_and_comments(self):
        self.assertEqual(d.day_dates("<!-- 1 May 2020 -->{{Start date|2027|2|23|df=y}}<ref>3 March 2026</ref>"),
                         [{"date": "2027-02-23", "platforms": "", "note": ""}])

    def test_released_value_keeps_nested_templates(self):
        content = "{{Infobox video game\n| title = X\n| released = {{ubl|a|\n23 May 2026}}\n| genre = y\n}}"
        self.assertEqual(d.released_value(content), "{{ubl|a|\n23 May 2026}}")
        self.assertEqual(d.released_value("{{Infobox video game\n| genre = y\n}}"), "")


    def test_redirect_is_not_the_games_article(self):
        # "Lollipop Chainsaw 2 Back2Back" redirects to the 2012 game: its dates must not be used (L54).
        reply = {"query": {"pages": [{"title": "X", "revisions": [{"timestamp": "t", "slots": {"main": {
            "content": "#REDIRECT [[Lollipop Chainsaw]]"}}}]}]}}
        with mock.patch.object(d, "api_json", return_value=reply) as api:
            self.assertIsNone(d.read_released("X"))
        self.assertNotIn("redirects", api.call_args[0][1])

    def test_label_note(self):
        text = "{{ubl|\'\'\'[[Early access]]\'\'\'|9 April 2025|\'\'\'Full release\'\'\'|March 2027}}"
        self.assertEqual(d.day_dates(text), [{"date": "2025-04-09", "platforms": "Early access", "note": "early access"}])


class CompareTests(unittest.TestCase):
    def test_candidates_need_views_article_and_coarse_date(self):
        games = {
            "Q1": game("Q1", ("2027-01-01T00:00:00Z", 9)),
            "Q2": game("Q2", ("2027-01-01T00:00:00Z", 9), ("2027-02-23T00:00:00Z", 11)),  # day date same year
            "Q3": game("Q3", ("2010-05-01T00:00:00Z", 10)),
            "Q4": game("Q4", ("2027-01-01T00:00:00Z", 9), enwiki=""),
            "Q5": game("Q5", ("2027-01-01T00:00:00Z", 9)),
        }
        views = {"Q1": 5000, "Q2": 5000, "Q3": 90000, "Q4": 5000, "Q5": 10}
        self.assertEqual([q for q, _ in d.candidates(games, views, 1000, TODAY)], ["Q1", "Q3"])  # upcoming first

    def test_day_in_period_and_later(self):
        fable = game("Q97656849", ("2027-01-01T00:00:00Z", 9), enwiki="Fable (2027 video game)", views_title="Fable")
        rows = d.compare("Q97656849", fable, [{"date": "2027-02-23", "platforms": "", "note": ""}], 63068)
        self.assertEqual(rows[0]["check"], "day-on-wikipedia")
        self.assertEqual(rows[0]["wikidata_date"], "2027")
        self.assertEqual(rows[0]["wikipedia_date"], "2027-02-23")
        self.assertIn("Fable_%282027_video_game%29", rows[0]["enwiki_url"])
        delayed = game("Q9", ("2026-10-01T00:00:00Z", 10))
        rows = d.compare("Q9", delayed, [{"date": "2027-03-01", "platforms": "", "note": ""}], 1)
        self.assertEqual([r["check"] for r in rows], ["later-on-wikipedia"])
        self.assertEqual(rows[0]["wikidata_date"], "October 2026")
        self.assertEqual(d.compare("Q9", delayed, [], 1), [])

    def test_early_access_only_still_reported_with_note(self):
        g = game("Q8", ("2026-01-01T00:00:00Z", 9))
        rows = d.compare("Q8", g, [{"date": "2026-10-19", "platforms": "PS5", "note": "early access"}], 1)
        self.assertEqual(rows[0]["wikipedia_date"], "2026-10-19 (early access)")


class HandDateTests(unittest.TestCase):
    def entry(self, **extra):
        return {"game": "Q1", "title": "Game", "date": "2026-12-04", "source_url": "https://example.org/a", **extra}

    def test_missing_file_means_none(self):
        self.assertEqual(d.load_hand_dates("/nonexistent/hand-dates.json"), [])

    def test_bad_shapes_are_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "h.json"
            path.write_text(json.dumps({"format": 1, "dates": [self.entry(), {"game": "x", "date": "2026-01-01"},
                                                               {"game": "Q2", "date": "soon"}]}))
            with mock.patch.object(d, "warn") as warned:
                self.assertEqual(len(d.load_hand_dates(str(path))), 1)
            self.assertEqual(warned.call_count, 2)
            path.write_text("[]")
            with mock.patch.object(d, "warn"):
                self.assertEqual(d.load_hand_dates(str(path)), [])

    def test_flags(self):
        games = {"Q1": game("Q1", ("2026-12-11T00:00:00Z", 11))}
        wiki = {"Q1": {"dates": [{"date": "2026-12-11", "platforms": "", "note": ""}]}}
        rows = d.recheck_hand_dates([self.entry()], games, wiki, {}, TODAY, check_sources=False)
        self.assertEqual({r["check"] for r in rows}, {"hand-date-differs-from-wikidata", "hand-date-differs-from-wikipedia"})
        self.assertEqual(rows[0]["your_date"], "2026-12-04")
        games = {"Q1": game("Q1", ("2026-12-04T00:00:00Z", 11))}
        rows = d.recheck_hand_dates([self.entry()], games, {}, {}, TODAY, check_sources=False)
        self.assertEqual([r["check"] for r in rows], ["hand-date-matches-wikidata"])

    def test_passed_without_wikidata_day(self):
        rows = d.recheck_hand_dates([self.entry(date="2026-11-10")], {}, {}, {}, TODAY, check_sources=False)
        self.assertEqual([r["check"] for r in rows], ["hand-date-passed"])

    def test_dead_source(self):
        with mock.patch.object(d, "source_alive", return_value="source answers HTTP 404"):
            rows = d.recheck_hand_dates([self.entry()], {}, {}, {}, TODAY)
        self.assertEqual([r["check"] for r in rows], ["hand-date-source-dead"])


class RunTests(unittest.TestCase):
    def test_unchanged_articles_are_not_read_again_and_errors_retry(self):
        picked = [("Q1", game("Q1", ("2027-01-01T00:00:00Z", 9), enwiki="A")),
                  ("Q2", game("Q2", ("2027-01-01T00:00:00Z", 9), enwiki="B")),
                  ("Q3", game("Q3", ("2027-01-01T00:00:00Z", 9), enwiki="C"))]
        cache = {"Q1": {"title": "A", "revision": "t1", "dates": []}}

        def read(title):
            if title == "C":
                raise ValueError("boom")
            return "1 March 2027", "t2"

        with mock.patch.object(d, "page_timestamps", return_value={"A": "t1", "B": "t2", "C": "t3"}), \
                mock.patch.object(d, "read_released", side_effect=read) as reader, \
                mock.patch.object(d, "warn"):
            stats = d.refresh_wikipedia(picked, cache, 0)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(stats, {"articles": 3, "read": 1, "unchanged": 1, "missing": 0, "errors": 1})
        self.assertEqual(cache["Q2"]["dates"][0]["date"], "2027-03-01")
        self.assertNotIn("Q3", cache)


if __name__ == "__main__":
    unittest.main()
