#!/usr/bin/env python3
"""Dates to update: release dates that Wikidata knows only as a month or a year, while English
Wikipedia already gives a day — and a recheck of every date DropSlate's owner entered by hand.

Weekly (Sundays, after the details files are refreshed):
  1. Candidates come from files already in this repository: every game in
     sources/wikidata-details/games/ with an English article, at least --min-views page views in
     60 days, and a release date of month or year precision with no day-precision date in the same
     year. Upcoming games first, then the best-known.
  2. For each candidate we read the infobox "released" line of its English Wikipedia article
     (MediaWiki API, section 0 only). Articles that have not changed since the last run are not
     read again (one batched timestamp request per 50 titles); what we found is kept in
     sources/wikipedia-release-dates/dates.json (dates and short platform labels only — no text).
  3. reports/dates-to-update.csv lists each game where Wikipedia's day falls in the period
     Wikidata gives (``day-on-wikipedia``) or where Wikipedia has only later dates
     (``later-on-wikipedia``, often a delay).
  4. Hand-entered dates (published by DropSlate at --hand-dates; a missing file means there are
     none yet) are compared with Wikidata and Wikipedia and their source link is checked.

Daily (--daily): only hand-entered dates of games coming out in the next 30 days (or whose day
passed in the last 7), compared with Wikidata (live) and Wikipedia; writes reports/hand-dates-daily.csv.

Every row is a HINT for a person, never a fix (reports/README.md): the date is fixed on Wikidata with
its own source (the publisher's announcement, a store page, press) — never "Wikipedia says so".
DropSlate keeps its current date until Wikidata is fixed, and nothing here changes a hand-entered
date. A failing article, source link or input file is reported and skipped; it never stops the run.

Polite to Wikimedia: one request at a time, a clear User-Agent, a short pause, back-off on 429/5xx,
no maxlag on reads (L50).
"""
from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_differences import read_details, read_json, title_of, warn  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "sources" / "wikipedia-release-dates" / "dates.json"
OUT = ROOT / "reports" / "dates-to-update.csv"
DAILY_OUT = ROOT / "reports" / "hand-dates-daily.csv"
HAND_DATES_URL = "https://dropslate.focalnull.com/catalogue/hand-dates.json"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "focalnull-data/0.1 (https://github.com/focalnull/focalnull-data)"
PAUSE = 0.5
BATCH = 50

COLUMNS = ("check", "wikidata", "title", "pageviews_60d", "wikidata_date", "wikipedia_date",
           "wikipedia_platforms", "your_date", "your_source", "detail", "suggested_fix", "fix_source",
           "wikidata_url", "enwiki_url", "licence")

MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
MONTH_NAMES = "|".join(sorted(MONTHS, key=len, reverse=True))
DMY = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_NAMES})\.?,?\s+(\d{{4}})\b", re.I)
MDY = re.compile(rf"\b({MONTH_NAMES})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I)
START_DATE = re.compile(r"\{\{\s*(?:start|release|film|video game) date(?: and age)?\s*\|"
                        r"\s*(?:df=y\s*\|\s*)?(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})", re.I)
ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
NOTE_WORDS = ("early access", "beta", "demo", "playtest", "soft launch", "premium")


# --------------------------------------------------------------------------------------------
# Network (one request at a time, with back-off)

def http_get(url: str, tries: int = 6, accept: str = "application/json") -> bytes:
    for attempt in range(1, tries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == tries:
                raise
            header = error.headers.get("Retry-After") if error.headers else None
            wait = min(max(float(header) if header and header.isdigit() else 0, 5.0 * attempt), 120.0)
        except urllib.error.URLError:
            if attempt == tries:
                raise
            wait = min(5.0 * attempt, 120.0)
        print(f"  waiting {wait:.0f} s before retry {attempt + 1}/{tries}", flush=True)
        time.sleep(wait)
    raise RuntimeError("unreachable")


def api_json(base: str, params: dict) -> dict:
    data = json.loads(http_get(base + "?" + urllib.parse.urlencode({**params, "format": "json",
                                                                     "formatversion": 2})))
    if not isinstance(data, dict):
        raise ValueError("API reply is not an object")
    time.sleep(PAUSE)
    return data


def page_timestamps(titles: list[str]) -> dict[str, str]:
    """Title -> timestamp of the article's newest revision. Redirects are not followed, so a title
    that only redirects gets the redirect page's own timestamp (and read_released skips it)."""
    found: dict[str, str] = {}
    for start in range(0, len(titles), BATCH):
        chunk = titles[start:start + BATCH]
        data = api_json(WIKIPEDIA_API, {"action": "query", "prop": "revisions", "rvprop": "timestamp",
                                        "titles": "|".join(chunk)})
        query = data.get("query")
        if not isinstance(query, dict) or not isinstance(query.get("pages"), list):
            raise ValueError("timestamp reply has no query.pages list")
        back = {t: t for t in chunk}
        for key in ("normalized",):
            for item in query.get(key) or []:
                if isinstance(item, dict) and item.get("from") in back:
                    back[item["to"]] = back.pop(item["from"])
        for page in query["pages"]:
            revisions = page.get("revisions") if isinstance(page, dict) else None
            if isinstance(revisions, list) and revisions and page.get("title") in back:
                found[back[page["title"]]] = str(revisions[0].get("timestamp", ""))
    return found


def read_released(title: str) -> tuple[str, str] | None:
    """The infobox 'released' value of one article and the revision timestamp; None if the article
    is missing or only a redirect. Redirects are never followed."""
    data = api_json(WIKIPEDIA_API, {"action": "query", "prop": "revisions", "rvprop": "content|timestamp",
                                    "rvslots": "main", "rvsection": 0, "titles": title})
    pages = (data.get("query") or {}).get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("article reply has no pages")
    revisions = pages[0].get("revisions")
    if not revisions:
        return None
    content = ((revisions[0].get("slots") or {}).get("main") or {}).get("content")
    if not isinstance(content, str):
        raise ValueError("article reply has no content")
    if re.match(r"\s*#redirect", content, flags=re.I):
        return None  # a redirect is not the game's own article: its dates belong to another page (L54)
    return released_value(content), str(revisions[0].get("timestamp", ""))


# --------------------------------------------------------------------------------------------
# Reading the infobox

def strip_markup(text: str) -> str:
    """Remove comments, references and footnote templates (whose dates are not release dates)."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<ref[^>/]*/>", " ", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text, flags=re.S)
    while True:
        match = re.search(r"\{\{\s*(?:efn|refn|sfn|cite|citation|NoteTag|r)\b", text, flags=re.I)
        if not match:
            break
        depth, index = 0, match.start()
        while index < len(text):
            if text.startswith("{{", index):
                depth += 1
                index += 2
            elif text.startswith("}}", index):
                depth -= 1
                index += 2
                if depth == 0:
                    break
            else:
                index += 1
        text = text[:match.start()] + " " + text[index:]
    return text.replace("&nbsp;", " ")


def released_value(content: str) -> str:
    """The text after '| released =' up to the next infobox parameter (nested templates kept)."""
    match = re.search(r"^\s*\|\s*released?\s*=", content, flags=re.I | re.M)
    if not match:
        return ""
    index, depth = match.end(), 0
    while index < len(content):
        if content.startswith("{{", index):
            depth += 1
            index += 2
            continue
        if content.startswith("}}", index):
            if depth == 0:
                break
            depth -= 1
            index += 2
            continue
        if content[index] == "\n" and depth == 0 and re.match(r"\n\s*\|", content[index:]):
            break
        index += 1
    return content[match.end():index].strip()


def _day(year: str, month: int, day: str) -> str | None:
    try:
        return dt.date(int(year), month, int(day)).isoformat()
    except ValueError:
        return None


def day_dates(released: str) -> list[dict]:
    """Every day-precision date in an infobox value, with the platform label written before it
    (e.g. '''PS5''') and a note such as 'early access' written right after it."""
    text = strip_markup(released)
    found: list[dict] = []
    label = ""
    for token in re.split(r"\||<br\s*/?>|\n|\{\{|\}\}", text):
        token = token.strip()
        if not token:
            continue
        dates: list[tuple[int, str]] = []
        for match in DMY.finditer(token):
            dates.append((match.start(), _day(match.group(3), MONTHS[match.group(2).lower()], match.group(1))))
        for match in MDY.finditer(token):
            dates.append((match.start(), _day(match.group(3), MONTHS[match.group(1).lower()], match.group(2))))
        for match in ISO.finditer(token):
            dates.append((match.start(), _day(match.group(1), int(match.group(2)), match.group(3))))
        if not dates:
            bold = re.findall(r"'''(.+?)'''", token)
            if bold:
                label = ", ".join(re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", b).strip() for b in bold)
            continue
        lowered = (token + " " + label).lower()
        note = next((word for word in NOTE_WORDS if word in lowered), "")
        for _, value in sorted(dates):
            if value and all(item["date"] != value or item["platforms"] != label for item in found):
                found.append({"date": value, "platforms": label, "note": note})
    # {{Start date|2027|2|23}} style templates were split apart above: read them from the whole text.
    for match in START_DATE.finditer(text):
        value = _day(match.group(1), int(match.group(2)), match.group(3))
        if value and all(item["date"] != value for item in found):
            found.append({"date": value, "platforms": "", "note": ""})
    return found


# --------------------------------------------------------------------------------------------
# Candidates and comparison

def coarse_dates(game: dict) -> list[dict]:
    """Month/year-precision dates with no day-precision date in the same year."""
    dated = [r for r in game.get("release_dates") or []
             if isinstance(r, dict) and r.get("rank") != "deprecated" and isinstance(r.get("precision"), int)
             and isinstance(r.get("time"), str) and not r["time"].startswith("-")]
    day_years = {r["time"][:4] for r in dated if r["precision"] >= 11}
    return [r for r in dated if r["precision"] in (9, 10) and r["time"][:4] not in day_years]


def candidates(games: dict, pageviews: dict, min_views: int, today: dt.date) -> list[tuple[str, dict]]:
    picked = []
    for qid, game in games.items():
        if game.get("is_game") is False or not game.get("enwiki"):
            continue
        if pageviews.get(qid, 0) < min_views or not coarse_dates(game):
            continue
        picked.append((qid, game))
    year = str(today.year)
    picked.sort(key=lambda item: (not any(r["time"][:4] >= year for r in coarse_dates(item[1])),
                                  -pageviews.get(item[0], 0), item[0]))
    return picked


def period_text(release: dict) -> str:
    time_value, precision = release["time"], release["precision"]
    if precision == 9:
        return time_value[:4]
    return f"{calendar.month_name[int(time_value[5:7])]} {time_value[:4]}"


def in_period(day: str, release: dict) -> bool:
    return day.startswith(release["time"][:4] if release["precision"] == 9 else release["time"][:7])


def describe(found: list[dict]) -> str:
    return "; ".join(f"{d['date']}" + (f" ({d['note']})" if d["note"] else "") for d in found)


def compare(qid: str, game: dict, found: list[dict], views: int) -> list[dict]:
    rows = []
    enwiki = game.get("enwiki", "")
    base = {"wikidata": qid, "title": title_of(game), "pageviews_60d": views,
            "wikidata_url": f"https://www.wikidata.org/wiki/{qid}",
            "enwiki_url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(enwiki.replace(" ", "_")),
            "licence": "hint from Wikipedia (CC BY-SA 4.0); dates are facts, no text copied",
            "your_date": "", "your_source": ""}
    for release in coarse_dates(game):
        same = [d for d in found if in_period(d["date"], release)]
        normal = [d for d in same if not d["note"]] or same
        later = [d for d in found if d["date"] > release["time"][:10] and not in_period(d["date"], release)]
        if normal:
            rows.append({**base, "check": "day-on-wikipedia", "wikidata_date": period_text(release),
                         "wikipedia_date": describe(normal),
                         "wikipedia_platforms": "; ".join(d["platforms"] for d in normal if d["platforms"]),
                         "detail": f"Wikidata gives only {period_text(release)}; English Wikipedia gives "
                                   f"{describe(normal)}",
                         "suggested_fix": "Change the date's precision to day (11) with the exact day, keeping "
                                          "its platform qualifiers, and add the source as its reference; "
                                          "or add a new day date with its platform and source",
                         "fix_source": "The publisher's or developer's announcement, an official store page or "
                                       "press coverage cited in the article (never Wikipedia itself)"})
        elif later:
            rows.append({**base, "check": "later-on-wikipedia", "wikidata_date": period_text(release),
                         "wikipedia_date": describe(later),
                         "wikipedia_platforms": "; ".join(d["platforms"] for d in later if d["platforms"]),
                         "detail": f"Wikidata gives {period_text(release)}; English Wikipedia gives only later "
                                   f"days ({describe(later)}) — a delay, or another release",
                         "suggested_fix": "If the game was delayed, add the new day date with its source and "
                                          "mark the old one deprecated (reason: delayed) or keep it as an "
                                          "earlier estimate; if it is another release, add it with its platform",
                         "fix_source": "The announcement of the new date (publisher, store page, press)"})
    return rows


# --------------------------------------------------------------------------------------------
# Hand-entered dates (DropSlate's own overrides, published as a small public file)

def load_hand_dates(location: str) -> list[dict]:
    """{"format": 1, "dates": [{"game", "title", "date", "precision", "platforms", "source_url",
    "entered"}]} — a missing file means no hand-entered dates yet."""
    try:
        if re.match(r"https?://", location):
            raw = http_get(location, tries=3)
        else:
            raw = Path(location).read_bytes()
    except FileNotFoundError:
        print(f"No hand-entered dates file at {location}: none to recheck.")
        return []
    except urllib.error.HTTPError as error:
        if error.code == 404:
            print(f"No hand-entered dates published yet ({location} answers 404): none to recheck.")
        else:
            warn(f"Hand-entered dates: {location} answered HTTP {error.code}; recheck skipped")
        return []
    except (OSError, urllib.error.URLError) as error:
        warn(f"Hand-entered dates: {location} could not be read ({type(error).__name__}); recheck skipped")
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        warn("Hand-entered dates: the file is not valid JSON; recheck skipped")
        return []
    if not isinstance(data, dict) or data.get("format") != 1 or not isinstance(data.get("dates"), list):
        warn("Hand-entered dates: unexpected shape (want format 1 with a dates list); recheck skipped")
        return []
    entries = []
    for item in data["dates"]:
        try:
            if not re.fullmatch(r"Q\d+", item["game"]):
                raise ValueError
            dt.date.fromisoformat(item["date"])
            entries.append(item)
        except (KeyError, TypeError, ValueError):
            warn("Hand-entered dates: one entry has no valid game or date; skipped")
    return entries


def source_alive(url: str) -> str:
    """'' when the source page answers, otherwise a short reason. Only https links are tried."""
    if not isinstance(url, str) or not url.startswith("https://"):
        return "no https source link"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read(2048)
            return ""
    except urllib.error.HTTPError as error:
        return f"source answers HTTP {error.code}" if error.code in (404, 410) else ""
    except (urllib.error.URLError, OSError) as error:
        return f"source unreachable ({type(error).__name__})"
    finally:
        time.sleep(PAUSE)


def live_release_dates(qids: list[str]) -> dict[str, list[dict]]:
    """Release dates (P577) straight from Wikidata, shaped like the details files."""
    result: dict[str, list[dict]] = {}
    for start in range(0, len(qids), 50):
        data = api_json(WIKIDATA_API, {"action": "wbgetentities", "ids": "|".join(qids[start:start + 50]),
                                       "props": "claims"})
        for qid, entity in (data.get("entities") or {}).items():
            dates = []
            for claim in ((entity or {}).get("claims") or {}).get("P577") or []:
                value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
                if isinstance(value.get("time"), str):
                    dates.append({"time": value["time"].lstrip("+").replace("-00", "-01"),
                                  "precision": value.get("precision"), "rank": claim.get("rank")})
            result[qid] = dates
    return result


def recheck_hand_dates(entries: list[dict], games: dict, wiki: dict, pageviews: dict,
                       today: dt.date, check_sources: bool = True) -> list[dict]:
    rows = []
    for entry in entries:
        qid, mine = entry["game"], entry["date"]
        game = games.get(qid) or {"id": qid, "labels": {"en": entry.get("title", qid)}}
        precise = sorted({r["time"][:10] for r in game.get("release_dates") or []
                          if isinstance(r, dict) and r.get("rank") != "deprecated"
                          and r.get("precision", 0) >= 11 and isinstance(r.get("time"), str)})
        wiki_days = [d["date"] for d in (wiki.get(qid) or {}).get("dates") or [] if not d.get("note")]
        enwiki = game.get("enwiki", "")
        base = {"wikidata": qid, "title": entry.get("title") or title_of(game),
                "pageviews_60d": pageviews.get(qid, ""), "your_date": mine,
                "your_source": entry.get("source_url", ""),
                "wikidata_date": "; ".join(precise) or "(no day date)",
                "wikipedia_date": "; ".join(wiki_days) or "(no day date)", "wikipedia_platforms": "",
                "wikidata_url": f"https://www.wikidata.org/wiki/{qid}",
                "enwiki_url": ("https://en.wikipedia.org/wiki/" + urllib.parse.quote(enwiki.replace(" ", "_"))
                               if enwiki else ""),
                "licence": "your own entry; Wikidata CC0; Wikipedia hint (CC BY-SA 4.0)",
                "fix_source": "Your source link, or the newer announcement"}

        def add(check: str, detail: str, fix: str) -> None:
            rows.append({**base, "check": check, "detail": detail, "suggested_fix": fix})

        if mine in precise:
            add("hand-date-matches-wikidata", "Wikidata now has the same day",
                "You can remove this hand-entered date in the Studio (Set a date → Remove)")
        else:
            same_year = [p for p in precise if p[:4] == mine[:4]]
            later = [p for p in precise if p > mine]
            if same_year or later:
                add("hand-date-differs-from-wikidata",
                    f"You entered {mine}; Wikidata now says {', '.join(same_year or later)}",
                    "Check which is right: Keep, Use Wikidata or Edit (a delay or a correction)")
        if wiki_days and mine not in wiki_days:
            add("hand-date-differs-from-wikipedia", f"You entered {mine}; English Wikipedia says "
                f"{', '.join(wiki_days)}", "Check the article's source; Keep or Edit")
        try:
            day = dt.date.fromisoformat(mine)
        except ValueError:
            continue
        if today - dt.timedelta(days=30) <= day < today - dt.timedelta(days=7) and mine not in precise:
            add("hand-date-passed", f"{mine} passed more than 7 days ago and Wikidata has no matching day",
                "Check that it really came out that day; otherwise Edit")
        if check_sources:
            reason = source_alive(entry.get("source_url", ""))
            if reason:
                add("hand-date-source-dead", reason, "Find the announcement again (or an archived copy) and Edit")
    return rows


# --------------------------------------------------------------------------------------------

def refresh_wikipedia(picked: list[tuple[str, dict]], cache: dict, limit: int) -> dict:
    """Re-read only the articles that changed since the last run (or were never read)."""
    titles = {game["enwiki"]: qid for qid, game in picked}
    stamps = page_timestamps(list(titles))
    stats = {"articles": len(titles), "read": 0, "unchanged": 0, "missing": 0, "errors": 0}
    for title, qid in titles.items():
        old = cache.get(qid) or {}
        stamp = stamps.get(title)
        if stamp is None:
            stats["missing"] += 1
            continue
        if old.get("title") == title and old.get("revision") == stamp:
            stats["unchanged"] += 1
            continue
        if limit and stats["read"] >= limit:
            continue
        try:
            got = read_released(title)
        except (urllib.error.URLError, ValueError, OSError) as error:
            stats["errors"] += 1
            warn(f"Wikipedia: {title} could not be read ({type(error).__name__}); retried next run")
            continue
        stats["read"] += 1
        if got is None:
            stats["missing"] += 1
            continue
        released, revision = got
        cache[qid] = {"title": title, "revision": revision, "dates": day_dates(released)}
    return stats


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def report(lines: list[str]) -> None:
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--daily", action="store_true", help="only hand-entered dates near their day")
    parser.add_argument("--min-views", type=int, default=1000)
    parser.add_argument("--limit", type=int, default=0, help="read at most N changed articles (0 = all)")
    parser.add_argument("--hand-dates", default=os.environ.get("HAND_DATES") or HAND_DATES_URL)
    parser.add_argument("--today", default="")
    args = parser.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()

    games = read_details(ROOT / "sources" / "wikidata-details" / "games")
    views_file = read_json(ROOT / "sources" / "wikipedia-pageviews" / "pageviews.json", "Page views") or {}
    pageviews = views_file.get("games") if isinstance(views_file.get("games"), dict) else {}
    cache_file = read_json(CACHE, "Wikipedia release dates") if CACHE.exists() else None
    cache = cache_file.get("games") if isinstance(cache_file, dict) and isinstance(cache_file.get("games"), dict) else {}
    hand = load_hand_dates(args.hand_dates)

    if args.daily:
        near = [e for e in hand
                if today - dt.timedelta(days=7) <= dt.date.fromisoformat(e["date"]) <= today + dt.timedelta(days=30)]
        if near:
            live = live_release_dates(sorted({e["game"] for e in near}))
            for qid, dates in live.items():
                games[qid] = {**(games.get(qid) or {"id": qid}), "release_dates": dates}
            refresh_wikipedia([(e["game"], games[e["game"]]) for e in near if (games.get(e["game"]) or {}).get("enwiki")],
                              cache, 0)
        rows = recheck_hand_dates(near, games, cache, pageviews, today)
        write_csv(rows, DAILY_OUT)
        report(["## Hand-entered dates — daily check", "",
                f"{len(hand)} hand-entered dates, {len(near)} within 30 days of their day, {len(rows)} flags."])
        return 0

    picked = candidates(games, pageviews, args.min_views, today)
    stats = refresh_wikipedia(picked, cache, args.limit)
    keep = {qid for qid, _ in picked} | {e["game"] for e in hand}
    cache = {qid: value for qid, value in cache.items() if qid in keep}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"format": 1, "as_of": today.isoformat(), "games": dict(sorted(cache.items()))},
                                ensure_ascii=False, indent=0) + "\n", encoding="utf-8")

    rows: list[dict] = []
    for qid, game in picked:
        rows += compare(qid, game, (cache.get(qid) or {}).get("dates") or [], pageviews.get(qid, 0))
    year = str(today.year)
    rows.sort(key=lambda r: (r["wikidata_date"][-4:] < year, -(r["pageviews_60d"] or 0), r["wikidata"]))
    hand_rows = recheck_hand_dates(hand, games, cache, pageviews, today)
    write_csv(hand_rows + rows, OUT)

    counts: dict[str, int] = {}
    for row in hand_rows + rows:
        counts[row["check"]] = counts.get(row["check"], 0) + 1
    report(["## Dates to update", "",
            f"Candidates (month/year date, ≥ {args.min_views} views): {len(picked)} · articles read "
            f"{stats['read']}, unchanged {stats['unchanged']}, no article {stats['missing']}, errors {stats['errors']}",
            f"Hand-entered dates rechecked: {len(hand)}", "", "| Check | Rows |", "|---|---|"]
           + [f"| {k} | {v} |" for k, v in sorted(counts.items())]
           + [f"| **Total** | **{len(hand_rows) + len(rows)}** |"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
