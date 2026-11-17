import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_commons as c  # noqa: E402


def field(value):
    return {"value": value, "source": "commons-desc-page", "hidden": ""}


def page(title, licence, code, artist, *, url_name=None, attribution=None, restrictions="", credit="Own work",
         required="true", licence_url=None):
    name = url_name or title.replace(" ", "_")
    metadata = {
        "LicenseShortName": field(licence), "UsageTerms": field(licence),
        "AttributionRequired": field(required), "Copyrighted": field("True"),
        "Restrictions": field(restrictions), "Artist": field(artist), "Credit": field(credit),
    }
    if code:
        metadata["License"] = field(code)
    if licence_url:
        metadata["LicenseUrl"] = field(licence_url)
    if attribution:
        metadata["Attribution"] = field(attribution)
    return {"pageid": 1, "ns": 6, "title": f"File:{title}", "imagerepository": "local", "imageinfo": [{
        "size": 142960, "width": 636, "height": 252,
        "url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{name}"
               "?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original",
        "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{name}",
        "descriptionshorturl": "https://commons.wikimedia.org/wiki/Special:Redirect/page/1",
        "extmetadata": metadata, "mime": "image/png"}]}


# Shaped like the real answer from commons.wikimedia.org/w/api.php on 17 Nov 2026 (checked in the browser).
REPLY = {"batchcomplete": True, "query": {
    "normalized": [{"fromencoded": False, "from": "File:Banjo_Kazooie_logo.png", "to": "File:Banjo Kazooie logo.png"}],
    "redirects": [{"from": "File:Old name.png", "to": "File:New name.png"}],
    "pages": [
        {"ns": 6, "title": "File:Does not exist 12345.png", "missing": True, "imagerepository": ""},
        page("Banjo Kazooie logo.png", "Public domain", "pd",
             '<a href="https://en.wikipedia.org/wiki/Microsoft" class="extiw">Microsoft Corporation</a>',
             restrictions="trademarked", required="false", credit="Own Work"),
        page("Arcade game.jpg", "CC BY-SA 3.0", "cc-by-sa-3.0",
             '<a href="//commons.wikimedia.org/wiki/User:Kulmalukko" title="User:Kulmalukko">Tiia Monto</a>',
             credit='<span class="int-own-work" lang="en">Own work</span>',
             licence_url="https://creativecommons.org/licenses/by-sa/3.0"),
        page("Luigi's Mansion Logo.png", "Public domain", "pd",
             'Unknown author<span style="display: none;">Unknown author</span>', url_name="Luigi%27s_Mansion_Logo.png",
             restrictions="trademarked", required="false"),
        page("Shank 2 gameplay.png", "CC BY 3.0", "cc-by-3.0", "Klei", licence_url="https://creativecommons.org/licenses/by/3.0",
             attribution='<a rel="nofollow" class="external text" href="https://www.youtube.com/@kleient">Klei Entertainment</a>'),
        page("MegaMek.png", "GPL", "", "MegaMek team", licence_url="http://www.gnu.org/licenses/gpl.html"),
        page("New name.png", "CC0", "cc0", "Someone", required="false"),
        # Like "ZX Laser Squad.png": only a licence name, no author and no "attribution required" field.
        {"ns": 6, "title": "File:ZX Laser Squad.png", "imagerepository": "local", "imageinfo": [{
            "size": 5779, "width": 1024, "height": 768, "mime": "image/png",
            "url": "https://upload.wikimedia.org/wikipedia/commons/a/ad/ZX_Laser_Squad.png",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:ZX_Laser_Squad.png",
            "extmetadata": {"LicenseShortName": field("Attribution"), "Restrictions": field("")}}]},
    ]}}
ASKED = ["Banjo_Kazooie_logo.png", "Arcade game.jpg", "Luigi's Mansion Logo.png", "Shank 2 gameplay.png",
         "MegaMek.png", "Old name.png", "Does not exist 12345.png", "ZX Laser Squad.png"]


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake(url, data=None, tries=40):
            self.calls.append((url, data))
            return json.loads(json.dumps(REPLY))

        patcher = mock.patch.object(c, "request_json", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.found = c.fetch_batch(ASKED)

    def test_one_polite_get_request_with_the_fields_we_need(self):
        self.assertEqual(len(self.calls), 1)
        url, data = self.calls[0]
        self.assertIsNone(data)  # GET, reads only
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        self.assertTrue(url.startswith("https://commons.wikimedia.org/w/api.php?"))
        self.assertEqual(query["prop"], "imageinfo")
        self.assertEqual(query["iiprop"], "extmetadata|url|size|mime")
        self.assertNotIn("maxlag", query)
        self.assertEqual(query["titles"].split("|")[0], "File:Banjo_Kazooie_logo.png")
        self.assertIn("LicenseShortName", query["iiextmetadatafilter"])

    def test_every_asked_name_gets_an_entry(self):
        self.assertEqual(sorted(self.found), sorted(ASKED))
        self.assertEqual(self.found["Does not exist 12345.png"], {"missing": True})

    def test_public_domain_logo(self):
        entry = self.found["Banjo_Kazooie_logo.png"]
        self.assertEqual(entry["reuse"], "public-domain")
        self.assertFalse(entry["attribution_required"])
        self.assertEqual(entry["restrictions"], ["trademarked"])
        self.assertEqual(entry["author"], "Microsoft Corporation")
        self.assertEqual(entry["credit_line"], "Microsoft Corporation, Public domain, via Wikimedia Commons")
        self.assertEqual(entry["title"], "Banjo Kazooie logo.png")  # name as Commons writes it
        self.assertEqual(entry["url"], "https://upload.wikimedia.org/wikipedia/commons/a/ab/Banjo_Kazooie_logo.png")
        self.assertEqual(entry["page"], "https://commons.wikimedia.org/wiki/File:Banjo_Kazooie_logo.png")
        self.assertEqual((entry["width"], entry["height"], entry["bytes"], entry["mime"]),
                         (636, 252, 142960, "image/png"))

    def test_share_alike_photo_with_html_author(self):
        entry = self.found["Arcade game.jpg"]
        self.assertEqual(entry["reuse"], "share-alike")
        self.assertTrue(entry["attribution_required"])
        self.assertEqual(entry["author"], "Tiia Monto")
        self.assertEqual(entry["source"], "Own work")
        self.assertEqual(entry["licence_url"], "https://creativecommons.org/licenses/by-sa/3.0")
        self.assertEqual(entry["credit_line"], "Tiia Monto, CC BY-SA 3.0, via Wikimedia Commons")
        self.assertNotIn("title", entry)
        self.assertNotIn("restrictions", entry)

    def test_hidden_text_is_dropped(self):
        self.assertEqual(self.found["Luigi's Mansion Logo.png"]["author"], "Unknown author")

    def test_attribution_field_wins_over_artist(self):
        entry = self.found["Shank 2 gameplay.png"]
        self.assertEqual(entry["author"], "Klei Entertainment")
        self.assertEqual(entry["reuse"], "attribution")

    def test_licence_without_code_and_redirect(self):
        self.assertEqual(self.found["MegaMek.png"]["reuse"], "share-alike")
        self.assertNotIn("licence_code", self.found["MegaMek.png"])
        self.assertEqual(self.found["Old name.png"]["title"], "New name.png")
        self.assertEqual(self.found["Old name.png"]["reuse"], "public-domain")


    def test_licences_seen_in_the_first_full_run(self):
        # Shapes from run #1 (17 Nov 2026): "Copyrighted free use" and CPL pages with an author.
        for licence, required, expected in (("Copyrighted free use", "false", "attribution"),
                                            ("CPL", "true", "share-alike")):
            reply = {"query": {"pages": [page("X.png", licence, "", "Messhof", required=required)]}}
            with self.subTest(licence=licence), mock.patch.object(c, "request_json", return_value=reply):
                entry = c.fetch_batch(["X.png"])["X.png"]
                self.assertEqual(entry["reuse"], expected)
                self.assertEqual(entry["credit_line"], f"Messhof, {licence}, via Wikimedia Commons")

    def test_credit_needed_but_no_author_is_checked_by_hand(self):
        entry = self.found["ZX Laser Squad.png"]
        self.assertTrue(entry["attribution_required"])  # the licence decides when the page doesn't say
        self.assertEqual(entry["reuse"], "check")
        self.assertEqual(entry["credit_line"], "Unknown author, Attribution, via Wikimedia Commons")
        self.assertNotIn("author", entry)


class ShapeTests(unittest.TestCase):
    def run_with(self, reply, names=("A.png",)):
        with mock.patch.object(c, "request_json", return_value=reply):
            return c.fetch_batch(list(names))

    def test_unexpected_answers_stop_with_a_clear_message(self):
        for reply in ({"error": {"code": "badvalue"}}, {"query": {}}, [],
                      {"continue": {"iicontinue": "x"}, "query": {"pages": []}},
                      {"query": {"pages": []}},  # no answer for the asked name
                      {"query": {"pages": [{"title": "File:A.png", "imageinfo": [{"url": "u"}]}]}}):
            with self.subTest(reply=reply), self.assertRaises(c.ShapeError):
                self.run_with(reply)

    def test_deleted_file_without_imageinfo(self):
        reply = {"query": {"pages": [{"title": "File:A.png", "imagerepository": ""}]}}
        self.assertEqual(self.run_with(reply), {"A.png": {"missing": True}})


class LicenceTests(unittest.TestCase):
    def test_reuse_classes(self):
        cases = {
            ("pd", "Public domain"): "public-domain", ("cc0", "CC0"): "public-domain",
            ("cc-by-4.0", "CC BY 4.0"): "attribution", ("", "MIT"): "attribution", ("", "BSD"): "attribution",
            ("", "Attribution"): "attribution", ("", "WTFPL"): "attribution", ("", "Artistic 2.0"): "attribution",
            ("cc-by-sa-4.0", "CC BY-SA 4.0"): "share-alike", ("cc-by-sa-3.0-de", "CC BY-SA 3.0 de"): "share-alike",
            ("", "GPLv3"): "share-alike", ("", "AGPL"): "share-alike", ("", "LGPL"): "share-alike",
            ("", "GFDL 1.2"): "share-alike", ("", "FAL"): "share-alike",
            ("", "Copyrighted free use"): "attribution", ("", "CPL"): "share-alike",
            ("", "ZLIB"): "attribution", ("", "Apache License 2.0"): "attribution", ("", "GPLv2"): "share-alike",
            ("", "NetHack GPL"): "share-alike", ("cc-by-sa-2.5-nl", "CC BY-SA 2.5 nl"): "share-alike",
            ("", "Fair use"): "check", ("", ""): "check",
        }
        for (code, name), expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(c.reuse_class(code, name), expected)
        self.assertEqual(c.reuse_class("cc-by-4.0", "CC BY 4.0", non_free="true"), "check")

    def test_plain_text(self):
        self.assertEqual(c.plain_text('<a>Ubisoft Bordeaux</a>,<br><a>Ubisoft</a>'), "Ubisoft Bordeaux, Ubisoft")
        self.assertEqual(c.plain_text("Pin &amp; Co"), "Pin & Co")
        self.assertEqual(len(c.plain_text("x" * 1000)), c.MAX_TEXT)
        self.assertEqual(c.plain_text(None), "")


class FileTests(unittest.TestCase):
    def test_entries_are_kept_between_runs(self):
        old = {"A.png": {"reuse": "attribution"}, "B.png": {"reuse": "share-alike"}, "Gone.png": {"reuse": "check"}}
        wanted = {"A.png": {"image"}, "B.png": {"logo"}, "C.png": {"image", "logo"}}
        fetched = {"A.png": {"reuse": "public-domain"}, "C.png": {"missing": True}}
        partial = c.merge(old, fetched, wanted, complete=False)
        self.assertEqual(partial["A.png"], {"reuse": "public-domain", "used_as": ["image"]})
        self.assertEqual(partial["B.png"], {"reuse": "share-alike", "used_as": ["logo"]})  # not checked: kept
        self.assertEqual(partial["C.png"], {"missing": True, "used_as": ["image", "logo"]})
        self.assertIn("Gone.png", partial)  # dropped only after a complete run
        full = c.merge(old, dict(fetched, **{"B.png": {"reuse": "share-alike"}}), wanted, complete=True)
        self.assertEqual(sorted(full), ["A.png", "B.png", "C.png"])

    def test_write_and_read_back(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "commons" / "files.json"
            files = {"Ä logo.svg": {"reuse": "public-domain", "used_as": ["logo"]}, "B.png": {"missing": True}}
            c.write_files(files, "2026-11-22", path)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(json.loads(text), {"format": 1, "as_of": "2026-11-22", "files": files})
            self.assertEqual(len(text.splitlines()), 4)  # one file per line, small diffs between runs
            self.assertEqual(c.read_files(path), files)

    def test_wanted_files_reads_images_and_logos(self):
        with tempfile.TemporaryDirectory() as folder:
            games = Path(folder)
            (games / "000.json").write_text(json.dumps([
                {"id": "Q1000", "commons_images": ["Shot.png"], "commons_logos": ["Logo.svg"]},
                {"id": "Q2000", "commons_logos": ["Logo.svg", " "]},
                {"id": "Q3000"}]), encoding="utf-8")
            with mock.patch.object(c, "DETAILS", games):
                self.assertEqual(c.wanted_files(), {"Logo.svg": {"logo"}, "Shot.png": {"image"}})


if __name__ == "__main__":
    unittest.main()
