#!/usr/bin/env python3
"""Count how often each game's English Wikipedia article was read in the last 60 days.

Source: the MediaWiki API on en.wikipedia.org (prop=pageviews). Wikimedia's
analytics data is released under CC0.

Input: the `enwiki` titles in matched/*.json.
Output: sources/wikipedia-pageviews/pageviews.json:
  {"as_of": "YYYY-MM-DD", "days": 60, "games": {"Q123": 4567, ...}}
Only games with an English article are listed. DropSlate uses the numbers to
add well-known games first.

Polite to Wikimedia: one request at a time, a clear User-Agent, a short pause
between calls, and back-off on 429/5xx. Reads only, so no maxlag parameter.
If the API's reply is not shaped as expected, we stop with a clear message and
write nothing (we never guess at fields).
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sources" / "wikipedia-pageviews" / "pageviews.json"
API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "focalnull-data/0.1 (https://github.com/focalnull/focalnull-data)"
DAYS = 60
BATCH = 50  # titles per request; the API answers a few at a time and continues


class ShapeError(SystemExit):
    """The API answered with something we don't understand."""


def request_json(params: dict, tries: int = 8) -> dict:
    url = API_URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code not in (429, 500, 502, 503, 504) or attempt == tries:
                raise
            header = err.headers.get("Retry-After") if err.headers else None
            wait = min(max(float(header) if header and header.isdigit() else 0, 5.0 * attempt), 120.0)
        except urllib.error.URLError:
            if attempt == tries:
                raise
            wait = min(5.0 * attempt, 120.0)
        print(f"  waiting {wait:.0f} s before retry {attempt + 1}/{tries}", flush=True)
        time.sleep(wait)
    raise RuntimeError("unreachable")


def our_titles() -> dict[str, str]:
    """English Wikipedia title -> Wikidata ID, from matched/."""
    titles: dict[str, str] = {}
    for path in sorted(glob.glob(str(ROOT / "matched" / "*.json"))):
        for record in json.loads(Path(path).read_text(encoding="utf-8")):
            title, qid = record.get("enwiki"), record.get("wikidata")
            if isinstance(title, str) and title and isinstance(qid, str):
                titles[title] = qid
    return titles


def page_total(page: dict) -> int | None:
    """Sum of daily views for one page; None when the page has no view data."""
    views = page.get("pageviews")
    if views is None:
        return None
    if not isinstance(views, dict):
        raise ShapeError(f"Unexpected pageviews value for {page.get('title')!r}: {type(views).__name__}")
    total = 0
    for day, count in views.items():
        if count is None:
            continue
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ShapeError(f"Unexpected view count on {day} for {page.get('title')!r}: {count!r}")
        total += count
    return total


def resolve(query: dict) -> dict[str, str]:
    """Map each title we asked for to the title the API answered with (normalised spelling only)."""
    mapping: dict[str, str] = {}
    for key in ("normalized",):
        for item in query.get(key, []) or []:
            if not isinstance(item, dict) or not isinstance(item.get("from"), str) or not isinstance(item.get("to"), str):
                raise ShapeError(f"Unexpected {key} entry: {item!r}")
            mapping[item["from"]] = item["to"]
    return mapping


def final_title(title: str, mapping: dict[str, str]) -> str:
    seen = set()
    while title in mapping and title not in seen:
        seen.add(title)
        title = mapping[title]
    return title


def views_for_batch(titles: list[str], pause: float) -> dict[str, int]:
    """Views per requested title for one batch, following the API's continuation."""
    params = {
        # No "redirects": a game whose article is only a redirect (e.g. "Globle (game)" -> "Wordle",
        # "Minecraft: Java Edition" -> "Minecraft") gets the redirect page's own small count,
        # not the views of the page it points to.
        "action": "query", "prop": "pageviews", "pvipdays": str(DAYS),
        "format": "json", "formatversion": "2", "titles": "|".join(titles),
    }
    totals: dict[str, int] = {}
    mapping: dict[str, str] = {}
    cont: dict = {}
    while True:
        payload = request_json({**params, **cont})
        if "error" in payload:
            raise ShapeError(f"API error: {payload['error']}")
        query = payload.get("query")
        if not isinstance(query, dict) or not isinstance(query.get("pages"), list):
            raise ShapeError("Reply has no query.pages list")
        mapping.update(resolve(query))
        for page in query["pages"]:
            if not isinstance(page, dict) or not isinstance(page.get("title"), str):
                raise ShapeError(f"Unexpected page entry: {page!r}")
            total = page_total(page)
            if total is not None and not page.get("missing"):
                totals[page["title"]] = total
        cont = payload.get("continue") or {}
        if not cont:
            break
        if not isinstance(cont, dict):
            raise ShapeError(f"Unexpected continue value: {cont!r}")
        time.sleep(pause)
    return {asked: totals[final] for asked in titles if (final := final_title(asked, mapping)) in totals}


def write(games: dict[str, int], today: dt.date) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ordered = dict(sorted(games.items(), key=lambda kv: int(kv[0][1:])))
    # One game per line keeps the file easy to read and the Git history small.
    lines = [f' "{qid}": {views}' for qid, views in ordered.items()]
    text = ('{"as_of": "%s", "days": %d, "games": {\n%s\n}}\n'
            % (today.isoformat(), DAYS, ",\n".join(lines)))
    json.loads(text)  # never write a file we can't read back
    OUT.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="only look up the first N articles (0 = all)")
    parser.add_argument("--pause", type=float, default=0.5, help="seconds between API calls")
    args = parser.parse_args()

    titles = our_titles()
    if not titles:
        raise SystemExit("No English Wikipedia titles found in matched/. Run 'Refresh game IDs' first.")
    names = sorted(titles)
    if args.limit:
        names = names[: args.limit]
    print(f"Games with an English Wikipedia article: {len(titles)}; looking up {len(names)}")
    games: dict[str, int] = {}
    for start in range(0, len(names), BATCH):
        batch = names[start:start + BATCH]
        for title, views in views_for_batch(batch, args.pause).items():
            qid = titles[title]
            games[qid] = max(games.get(qid, 0), views)
        if start and start % 2500 == 0:
            print(f"  looked up {start} / {len(names)}", flush=True)
        time.sleep(args.pause)
    today = dt.datetime.now(dt.timezone.utc).date()
    write(games, today)
    top = sorted(games.items(), key=lambda kv: -kv[1])[:5]
    print(f"Wrote views for {len(games)} games (last {DAYS} days, up to {today}).")
    summary = Path(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"))
    with summary.open("a", encoding="utf-8") as out:
        out.write(f"- Articles looked up: {len(names)}\n- Games with view counts: {len(games)}\n")
        out.write("- Most read: " + ", ".join(f"{q} ({v:,})" for q, v in top) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
