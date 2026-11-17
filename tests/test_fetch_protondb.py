import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_protondb as p  # noqa: E402


def report(app, verdict, when):
    return {"app": {"steam": {"appId": app}}, "responses": {"verdict": verdict},
            "timestamp": int(dt.datetime(*when, tzinfo=dt.timezone.utc).timestamp())}


class ProtonDBTests(unittest.TestCase):
    def test_newest_export_by_date_not_by_name(self):
        names = ["reports_apr1_2026.tar.gz", "reports_nov1_2026.tar.gz", "reports_dec1_2025.tar.gz", "README.md"]
        self.assertEqual(p.newest_export(names), "reports_nov1_2026.tar.gz")

    def test_summary_counts_only_our_games_and_recent_reports(self):
        reports = [
            report("620", "yes", (2026, 10, 1)),
            report(620, "no", (2024, 1, 1)),
            report("999", "yes", (2026, 10, 1)),
            {"app": {}, "responses": {}},
        ]
        summary, usable = p.summarise(reports, {"620"}, dt.date(2026, 11, 17))
        self.assertEqual(usable, 3)
        self.assertEqual(summary["620"], {"reports": 2, "works": 1, "reports_12m": 1, "works_12m": 1, "latest": "2026-10-01"})
        self.assertNotIn("999", summary)

    def test_report_without_verdict_is_ignored(self):
        self.assertIsNone(p.report_fields({"app": {"steam": {"appId": "1"}}, "responses": {}, "timestamp": 1}))


if __name__ == "__main__":
    unittest.main()
