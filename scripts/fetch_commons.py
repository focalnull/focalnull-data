#!/usr/bin/env python3
"""Store the licence, author and credit line of every Wikimedia Commons file our games
point to, so DropSlate can credit an image properly before it ever shows one.

Input: the Commons file names in sources/wikidata-details/games/*.json
       (commons_images = Wikidata P18, commons_logos = Wikidata P154).
Output: sources/commons/files.json, one file per line. Metadata only: no images are
        downloaded or stored here, and no file descriptions are copied.

How: the Commons API (action=query, prop=imageinfo, iiprop=extmetadata|url|size|mime),
50 file names per call (the API's maximum), one call at a time, a short pause between
calls and back-off on 429/5xx. Reads only, so no maxlag parameter (L50).

Entries are kept between runs: a file we could not check this time keeps last week's
entry. Files no game points to any more are dropped only after a complete run.
If an answer is not shaped as expected, we stop with a clear message and still save
what was fetched so far, merged with the previous file.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_wikidata_ids import request_json  # noqa: E402  (User-Agent with our repo URL, back-off on 429/5xx)

ROOT = Path(__file__).resolve().parent.parent
DETAILS = ROOT / "sources" / "wikidata-details" / "games"
OUT = ROOT / "sources" / "commons" / "files.json"
CREDITS = ROOT / "sources" / "commons" / "credits.json"  # hand-checked authors for pages that name none
API_URL = "https://commons.wikimedia.org/w/api.php"
BATCH = 50
FORMAT = 1
MAX_TEXT = 300  # author and source lines longer than this are cut (some pages hold whole paragraphs)

# Only the fields we keep, so answers stay small (some pages carry kilobytes of permission HTML).
METADATA_FIELDS = ("LicenseShortName", "LicenseUrl", "License", "UsageTerms", "AttributionRequired",
                   "Copyrighted", "Restrictions", "Artist", "Credit", "Attribution", "NonFree")
FIELDS_IN_RECORDS = {"commons_images": "image", "commons_logos": "logo"}

# How a licence lets us reuse a file. Checked against the API's licence code first
# (e.g. "cc-by-sa-4.0", "pd"), then against the short name (e.g. "GPL", "MIT").
PUBLIC_DOMAIN = "public-domain"   # free to reuse; credit is kind but not required
ATTRIBUTION = "attribution"       # free to reuse with credit (author, licence, link)
SHARE_ALIKE = "share-alike"       # free to reuse with credit; changed versions keep the same licence
CHECK = "check"                   # unknown or unusual licence: a person reads the file page first
# "Copyrighted free use": the owner allows any use; Commons doesn't ask for credit, we still give it.
# CPL (Common Public License): changed versions stay under the CPL, like the GPL.
SHARE_ALIKE_NAMES = re.compile(r"by-sa|gfdl|\bfal\b|free art|\b[al]?gpl|\bcpl\b")
ATTRIBUTION_NAMES = re.compile(r"cc[- ]by|^attribution|\bmit\b|\bbsd\b|apache|artistic|\bisc\b|zlib|wtfpl|\bogl"
                               r"|copyrighted free use")


class ShapeError(SystemExit):
    """Commons answered with something we don't understand."""


# ---------- reading the answer ----------

class _TextOnly(HTMLParser):
    """Plain text from the small HTML snippets Commons gives (author, source).
    Hidden parts (display:none) are dropped and <br> becomes a comma."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0
        self.stack: list[bool] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "img", "hr", "wbr"):
            if not self.hidden and tag == "br":
                self.parts.append(", ")
            return
        style = (dict(attrs).get("style") or "").replace(" ", "").lower()
        hide = "display:none" in style or tag in ("style", "script")
        self.stack.append(hide)
        if hide:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("br", "img", "hr", "wbr") or not self.stack:
            return
        if self.stack.pop():
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value) -> str:
    if value is None:
        return ""
    parser = _TextOnly()
    parser.feed(str(value))
    parser.close()
    text = re.sub(r"\s+", " ", "".join(parser.parts)).strip()
    text = re.sub(r"\s*,(\s*,)+", ",", text)       # "A, , B" -> "A, B"
    text = re.sub(r"\s+,", ",", text).strip(" ,")
    if len(text) > MAX_TEXT:
        text = text[: MAX_TEXT - 1].rstrip() + "…"
    return text


def meta(extmetadata: dict, key: str) -> str:
    entry = extmetadata.get(key)
    if entry is None:
        return ""
    if not isinstance(entry, dict) or "value" not in entry:
        raise ShapeError(f"Unexpected extmetadata field {key}: {entry!r}"[:300])
    return str(entry["value"])


def reuse_class(code: str, short_name: str, non_free: str = "") -> str:
    """How a licence lets us reuse the file (see the constants above)."""
    if non_free.strip().lower() in ("true", "1"):
        return CHECK
    code, short = code.strip().lower(), short_name.strip().lower()
    if code == "pd" or code.startswith("pd-") or code.startswith("cc0") or short.startswith("public domain") \
            or short.startswith("cc0"):
        return PUBLIC_DOMAIN
    for text in (code, short):
        if not text:
            continue
        if SHARE_ALIKE_NAMES.search(text):
            return SHARE_ALIKE
        if ATTRIBUTION_NAMES.search(text):
            return ATTRIBUTION
    return CHECK


def without_tracking(url: str) -> str:
    """Commons adds ?utm_... to file URLs in API answers; we keep the plain address."""
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if not k.startswith("utm_")]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def file_record(page: dict, credit: dict | None = None) -> dict:
    """One entry for files.json from one page of the API answer."""
    title = page.get("title")
    if not isinstance(title, str) or not title.startswith("File:"):
        raise ShapeError(f"Unexpected page in the answer: {str(page)[:300]}")
    if page.get("missing") or page.get("invalid"):
        return {"missing": True}
    info = page.get("imageinfo")
    if not isinstance(info, list) or not info or not isinstance(info[0], dict):
        if page.get("imagerepository") == "":
            return {"missing": True}  # a description page whose file was deleted
        raise ShapeError(f"{title}: no imageinfo in the answer")
    info = info[0]
    extmetadata = info.get("extmetadata")
    if not isinstance(extmetadata, dict) or not isinstance(info.get("url"), str) \
            or not isinstance(info.get("descriptionurl"), str):
        raise ShapeError(f"{title}: imageinfo without url, descriptionurl or extmetadata")

    licence = plain_text(meta(extmetadata, "LicenseShortName"))
    code = meta(extmetadata, "License").strip()
    restrictions = sorted({r for r in meta(extmetadata, "Restrictions").split("|") if r.strip()})
    author = plain_text(meta(extmetadata, "Attribution")) or plain_text(meta(extmetadata, "Artist"))
    author_from = None
    if not author and credit and credit.get("author"):
        # Commons names no author: use the name we checked by hand on the file page (credits.json).
        author, author_from = credit["author"], "credits.json"
    reuse = reuse_class(code, licence, meta(extmetadata, "NonFree"))
    required = meta(extmetadata, "AttributionRequired").strip().lower()
    # Some pages don't say; then the licence decides (CC BY, GPL... always need credit).
    needs_credit = required == "true" or (required != "false" and reuse in (ATTRIBUTION, SHARE_ALIKE))
    if needs_credit and not author:
        reuse = CHECK  # credit is required but Commons names no author: a person reads the page first
    if credit and credit.get("check"):
        reuse = CHECK  # we read the page and found a reason to hold the file back (see "note")
    record = {
        "page": info["descriptionurl"],
        "url": without_tracking(info["url"]),
        "mime": info.get("mime"),
        "width": info.get("width"),
        "height": info.get("height"),
        "bytes": info.get("size"),
        "licence": licence or None,
        "licence_code": code or None,
        "licence_url": meta(extmetadata, "LicenseUrl").strip() or None,
        "reuse": reuse,
        "attribution_required": needs_credit,
        "author": author or None,
        "author_from": author_from,
        "note": (credit or {}).get("note") if (credit and (author_from or credit.get("check"))) else None,
        "source": plain_text(meta(extmetadata, "Credit")) or None,
        "restrictions": restrictions,
    }
    # Commons' own suggested form: "Author, Licence, via Wikimedia Commons".
    record["credit_line"] = ", ".join(x for x in (author or "Unknown author", licence or "see file page",
                                                   "via Wikimedia Commons"))
    if title[5:] != page.get("_requested"):
        record["title"] = title[5:]
    return {k: v for k, v in record.items() if v is not None and v != [] and v != ""}


def fetch_batch(names: list[str], credits: dict | None = None) -> dict[str, dict]:
    """Entries for up to 50 file names (as Wikidata writes them, without "File:")."""
    params = {
        "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
        "prop": "imageinfo", "iiprop": "extmetadata|url|size|mime",
        "iiextmetadatalanguage": "en", "iiextmetadatafilter": "|".join(METADATA_FIELDS),
        "titles": "|".join(f"File:{n}" for n in names),
    }
    reply = request_json(f"{API_URL}?{urllib.parse.urlencode(params)}")  # GET: reads only
    if not isinstance(reply, dict):
        raise ShapeError("Commons answered with something that is not a JSON object")
    if "error" in reply:
        raise ShapeError(f"Commons API error: {reply['error']}")
    if "continue" in reply:
        raise ShapeError("Commons split the answer (continue); the batch is too big for one answer")
    query = reply.get("query")
    pages = query.get("pages") if isinstance(query, dict) else None
    if not isinstance(pages, list):
        raise ShapeError("Reply has no query.pages list")

    # Follow the API's steps from what we asked to the page it answered with.
    steps = {}
    for key in ("normalized", "redirects"):
        for hop in query.get(key, []) or []:
            if not isinstance(hop, dict) or "from" not in hop or "to" not in hop:
                raise ShapeError(f"Unexpected {key} entry: {hop!r}")
            steps.setdefault(key, {})[hop["from"]] = hop["to"]
    by_title = {p.get("title"): p for p in pages if isinstance(p, dict)}
    found = {}
    for name in names:
        title = f"File:{name}"
        title = steps.get("normalized", {}).get(title, title)
        title = steps.get("redirects", {}).get(title, title)
        page = by_title.get(title)
        if page is None:
            raise ShapeError(f"Commons did not answer for {name!r}")
        found[name] = file_record(dict(page, _requested=name), (credits or {}).get(name))
    return found


# ---------- files ----------

def wanted_files() -> dict[str, set[str]]:
    """Every Commons file name in the details files, with how games use it (image / logo)."""
    wanted: dict[str, set[str]] = {}
    paths = sorted(glob.glob(str(DETAILS / "*.json")))
    if not paths:
        raise SystemExit("No game details found. Run 'Refresh game details' first.")
    for path in paths:
        records = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ShapeError(f"{path} is not a list of games")
        for record in records:
            for field, use in FIELDS_IN_RECORDS.items():
                for name in record.get(field, []) if isinstance(record, dict) else []:
                    if isinstance(name, str) and name.strip() and "|" not in name:
                        wanted.setdefault(name.strip(), set()).add(use)
    return dict(sorted(wanted.items()))


def read_credits(path: Path | None = None) -> dict:
    """Hand-checked authors: {"format": 1, "files": {name: {"author", "note", "checked"} or {"check": true, "note"}}}."""
    path = path or CREDITS
    if not path.exists():
        return {}
    files = json.loads(path.read_text(encoding="utf-8")).get("files")
    if not isinstance(files, dict) or not all(
            isinstance(v, dict) and isinstance(v.get("note"), str) and (v.get("author") or v.get("check"))
            for v in files.values()):
        raise ShapeError(f"{path.name}: every entry needs a note and an author (or \"check\": true)")
    return files


def read_files(path: Path | None = None) -> dict:
    path = path or OUT
    if not path.exists():
        return {}
    files = json.loads(path.read_text(encoding="utf-8")).get("files")
    return files if isinstance(files, dict) else {}


def write_files(files: dict, today: str, path: Path | None = None) -> None:
    path = path or OUT
    rows = [f" {json.dumps(name, ensure_ascii=False)}: "
            f"{json.dumps(entry, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}"
            for name, entry in sorted(files.items())]
    text = '{"format": %d, "as_of": "%s", "files": {\n' % (FORMAT, today) + ",\n".join(rows) + "\n}}\n"
    json.loads(text)  # never write a file we can't read back
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def merge(previous: dict, fetched: dict, wanted: dict[str, set[str]], complete: bool) -> dict:
    """This run's entries, plus last run's entries for files we didn't reach this time.
    Files no game uses any more are dropped only when this run checked every file."""
    result = {}
    for name, uses in wanted.items():
        entry = fetched.get(name) or previous.get(name)
        if entry is not None:
            result[name] = dict(entry, used_as=sorted(uses))
    if not complete:
        for name, entry in previous.items():
            result.setdefault(name, entry)
    return result


def counts(files: dict) -> dict[str, int]:
    tally: dict[str, int] = {}
    for entry in files.values():
        key = "missing" if entry.get("missing") else entry.get("reuse", CHECK)
        tally[key] = tally.get(key, 0) + 1
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="only check the first N file names (0 = all)")
    parser.add_argument("--pause", type=float, default=0.5, help="seconds between API calls")
    args = parser.parse_args()

    wanted = wanted_files()
    names = list(wanted)[: args.limit] if args.limit else list(wanted)
    print(f"Checking {len(names)} of {len(wanted)} Commons files", flush=True)
    previous = read_files()
    credits = read_credits()
    fetched: dict[str, dict] = {}
    failure = None
    started = time.monotonic()
    for start in range(0, len(names), BATCH):
        try:
            fetched.update(fetch_batch(names[start:start + BATCH], credits))
        except (SystemExit, Exception) as err:  # save what we have, then report the problem
            failure = err
            break
        time.sleep(args.pause)

    complete = failure is None and len(fetched) == len(wanted)
    files = merge(previous, fetched, wanted, complete)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    write_files(files, today)

    tally = counts(files)
    kept = sum(1 for n in wanted if n not in fetched and n in previous)
    minutes = (time.monotonic() - started) / 60
    lines = [
        f"- Files checked this run: {len(fetched)} of {len(wanted)}",
        f"- Kept from the last run (not checked this time): {kept}",
        f"- Public domain / CC0: {tally.get(PUBLIC_DOMAIN, 0)}",
        f"- Free with credit: {tally.get(ATTRIBUTION, 0)}",
        f"- Free with credit, same licence for changed versions: {tally.get(SHARE_ALIKE, 0)}",
        f"- Licence to check by hand: {tally.get(CHECK, 0)}",
        f"- Missing on Commons (deleted or renamed without a redirect): {tally.get('missing', 0)}",
        f"- Minutes: {minutes:.1f}",
    ]
    print("\n".join(lines))
    with Path(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null")).open("a", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")
    if failure is not None:
        print(f"Stopped early: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
