"""Differences report: where our other sources disagree with Wikidata, or Wikidata disagrees with itself.

Reads only files already in this repository (no network):
  sources/wikidata-details/games/*.json   Wikidata facts per game (CC0)
  sources/wikidata-details/labels.json    labels of platforms and other items (CC0)
  matched/*.json                          store and database IDs per game (CC0)
  sources/wikipedia-pageviews/pageviews.json  how often each game's article is read (CC0), used to sort
  sources/protondb/summary.json           ProtonDB report counts (ODbL), used only as a hint
  sources/commons/files.json              Commons file metadata (CC BY-SA 4.0)

Writes reports/differences.csv (one row per difference, best-known games first) and prints a summary.

Every row is a HINT for a person, never a fix. Rules (see reports/README.md):
  * fixes are made on Wikidata, each with its own source (store page, publisher, news, Commons log);
  * ODbL (ProtonDB) and CC BY-NC-SA data are never copied into Wikidata;
  * DropSlate keeps the Wikidata value until Wikidata is fixed.

A missing or broken source file skips its checks with a warning; it never stops the report (L30).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "differences.csv"

COLUMNS = ("check", "wikidata", "title", "pageviews_60d", "detail", "suggested_fix", "fix_source",
           "hint_from", "licence", "wikidata_url", "enwiki")

# Platforms that Steam, GOG and the Epic Games Store sell for. DOS and classic Mac OS are left out on
# purpose: on these stores old DOS/Mac games run on Windows (DOSBox etc.), which is a Windows release.
PC_PLATFORMS = {
    "Q1406",    # Microsoft Windows
    "Q14116",   # macOS
    "Q388",     # Linux
    "Q16338",   # personal computer (DropSlate shows it as Windows from 1995)
}
NINTENDO_ESHOP_PLATFORMS = {
    "Q19610114",  # Nintendo Switch
    "Q122761124", # Nintendo Switch 2
    "Q65458682",  # Nintendo Switch Lite
    "Q56942",     # Wii U
    "Q203597",    # Nintendo 3DS
}
# Values used as "platform" (P400) that are stores, services, categories or formats, not platforms.
NOT_PLATFORMS = {
    "Q337535": "Steam is a store; the platform is the operating system (e.g. Microsoft Windows)",
    "Q1052025": "PlayStation Store is a store; the platform is the console (e.g. PlayStation 4)",
    "Q22905933": "itch.io is a store; the platform is the operating system",
    "Q1486288": "GOG.com is a store; the platform is the operating system",
    "Q170073": "Xbox Network is an online service; the platform is the console",
    "Q3814081": "\"app marketplace\" is a kind of store, not a platform",
    "Q7344765": "a Wikipedia category item, not a platform",
    "Q73368": "\"online\" is not a platform",
    "Q116634": "\"online game\" is a kind of game, not a platform",
    "Q10928179": "\"online and offline\" is not a platform",
    "Q36774": "\"web page\" is not a platform (use web browser, Q6368)",
    "Q1135858": "Flash Video is a file format, not a platform",
    "Q75": "the Internet is a network, not a platform (for browser games use web browser, Q6368)",
}
STORE_CHECKS = (
    # (id field, store name, platforms that store sells for, platform to suggest, Wikidata property)
    ("steam", "Steam", PC_PLATFORMS, "Microsoft Windows (Q1406)", "P1733"),
    ("gog", "GOG", PC_PLATFORMS, "Microsoft Windows (Q1406)", "P2725"),
    ("epic", "Epic Games Store", PC_PLATFORMS, "Microsoft Windows (Q1406)", "P6278"),
    ("eshop", "Nintendo eShop", NINTENDO_ESHOP_PLATFORMS, "the Nintendo console the eShop page is for", "P8084"),
)
LICENCE = {"wikidata": "CC0", "commons": "CC BY-SA 4.0", "protondb": "ODbL 1.0"}


def warn(message: str) -> None:
    print(f"::warning::{message}")


def read_json(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        warn(f"{what}: {path.relative_to(ROOT)} not found; its checks are skipped")
    except (OSError, ValueError) as error:
        warn(f"{what}: {path.relative_to(ROOT)} could not be read ({type(error).__name__}); its checks are skipped")
    return None


def read_details(folder: Path) -> dict[str, dict]:
    """One game per line; the first and last lines are the list brackets."""
    games: dict[str, dict] = {}
    files = sorted(folder.glob("*.json"))
    if not files:
        warn("Wikidata details: no bucket files found; the report is empty")
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip().rstrip(",")
            if not line.startswith("{"):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                warn(f"Wikidata details: {path.name} line {number} is not valid JSON; skipped")
                continue
            if isinstance(record, dict) and isinstance(record.get("id"), str):
                games[record["id"]] = record
    return games


def read_matched(folder: Path) -> dict[str, dict]:
    ids: dict[str, dict] = {}
    for path in sorted(folder.glob("*.json")):
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            warn(f"matched: {path.name} is not valid JSON; skipped")
            continue
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and isinstance(entry.get("wikidata"), str):
                ids[entry["wikidata"]] = entry.get("ids") or {}
    return ids


def title_of(game: dict) -> str:
    labels = game.get("labels") or {}
    return labels.get("en") or labels.get("mul") or next(iter(labels.values()), "") or game["id"]


def as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def period_start(time: str, precision: int) -> date | None:
    """The first day a Wikidata date can mean: '2023-08-01T…' with month precision -> 1 Aug 2023."""
    if not isinstance(time, str) or time.startswith("-") or not isinstance(precision, int) or precision < 9:
        return None
    try:
        year, month, day = int(time[0:4]), int(time[5:7]), int(time[8:10])
        if precision == 9:
            return date(year, 1, 1)
        if precision == 10:
            return date(year, month, 1)
        return date(year, month, day)
    except ValueError:
        return None


def earliest_release(game: dict) -> tuple[date, dict] | None:
    best = None
    for release in game.get("release_dates") or []:
        if not isinstance(release, dict) or release.get("rank") == "deprecated":
            continue
        start = period_start(release.get("time"), release.get("precision"))
        if start and (best is None or start < best[0]):
            best = (start, release)
    return best


def label(labels: dict, qid: str) -> str:
    item = labels.get(qid) or {}
    name = item.get("en") or item.get("mul")
    return f"{name} ({qid})" if name else qid


PRECISION = {9: "year", 10: "month", 11: "day"}


def build_rows(games: dict, matched: dict, labels: dict, pageviews: dict | None,
               protondb: dict | None, commons: dict | None, as_of: str = "") -> list[dict]:
    rows: list[dict] = []
    known_platforms = {p for g in games.values() for p in as_list(g.get("platforms"))} - NOT_PLATFORMS.keys()
    today = date.fromisoformat(as_of) if as_of else date.today()

    def add(check: str, game: dict, detail: str, fix: str, source: str, hint_from: str = "wikidata") -> None:
        qid = game["id"]
        rows.append({
            "check": check, "wikidata": qid, "title": title_of(game),
            "pageviews_60d": (pageviews or {}).get(qid, ""), "detail": detail, "suggested_fix": fix,
            "fix_source": source, "hint_from": hint_from, "licence": LICENCE[hint_from],
            "wikidata_url": f"https://www.wikidata.org/wiki/{qid}", "enwiki": game.get("enwiki", ""),
        })

    files_by_game: dict[str, list[tuple[str, str]]] = {}
    for qid, game in games.items():
        for kind, field in (("image (P18)", "commons_images"), ("logo (P154)", "commons_logos")):
            for name in as_list(game.get(field)):
                files_by_game.setdefault(qid, []).append((kind, name))

    for qid, game in sorted(games.items()):
        if game.get("is_game") is False:
            continue
        platforms = set(as_list(game.get("platforms")))
        ids = dict(matched.get(qid) or {})
        for field in ("steam", "gog", "eshop"):
            if game.get(field) and not ids.get(field):
                ids[field] = game[field]

        # 1. A store sells the game, but Wikidata lists no platform that store sells for.
        for field, store, store_platforms, suggest, prop in STORE_CHECKS:
            values = as_list(ids.get(field))
            if values and not platforms & store_platforms:
                listed = ", ".join(label(labels, p) for p in sorted(platforms)) or "no platform at all"
                add("store-id-without-platform", game,
                    f"Has a {store} ID ({prop} = {', '.join(map(str, values))}) but its platforms are: {listed}",
                    f"Add platform (P400) {suggest}, and a release date (P577) with that platform as qualifier, "
                    f"if the {store} page shows the game is sold on its own (not only inside a collection or as DLC)",
                    f"The {store} store page (reference: reference URL P854 + retrieved P813)")

        # 2. A store, service or category used as a platform value.
        for value in sorted(platforms & NOT_PLATFORMS.keys()):
            add("platform-not-a-platform", game, f"Platform (P400) = {label(labels, value)}: {NOT_PLATFORMS[value]}",
                "Replace it with the real platform, keeping the statement's references; if no source names the "
                "platform, deprecate the value with a reason instead of guessing",
                "The statement's own reference, or the store page")

        for release in game.get("release_dates") or []:
            if not isinstance(release, dict) or release.get("rank") == "deprecated":
                continue
            qualifiers = release.get("qualifiers") or {}
            when = f"{str(release.get('time', ''))[:10]} ({PRECISION.get(release.get('precision'), 'other precision')})"
            # 3. A release date names a platform the item doesn't list as a platform.
            for value in as_list(qualifiers.get("P400")):
                if value not in platforms and value not in NOT_PLATFORMS:
                    if value == "Q16338" and "Q1406" in platforms:
                        fix = ("Change the date's platform qualifier to Microsoft Windows (Q1406), which the item "
                               "already lists, if the reference says Windows (or PC)")
                    else:
                        fix = (f"Add platform (P400) {label(labels, value)}, copying the release date's reference "
                               "(or correct the qualifier if the reference names another platform)")
                    add("date-platform-not-listed", game,
                        f"Release date {when} has platform qualifier {label(labels, value)}, "
                        "but the item has no platform (P400) statement for it",
                        fix, "The release date statement's own reference")
            # 4. "Place of publication" (P291) holding a platform, like BMX Streets on 17 Nov.
            for value in as_list(qualifiers.get("P291")):
                if value in NOT_PLATFORMS:
                    add("platform-in-wrong-qualifier", game,
                        f"Release date {when} has place of publication (P291) = {label(labels, value)}, "
                        "which is a store or service, not a place",
                        "On that date: remove the P291 qualifier; add distributed by (P750) for a store, and "
                        "platform (P400) = the operating system or console the reference names",
                        "The release date statement's own reference")
                elif value in known_platforms:
                    add("platform-in-wrong-qualifier", game,
                        f"Release date {when} has place of publication (P291) = {label(labels, value)}, which is a platform",
                        f"On that date: remove the P291 qualifier and add qualifier platform (P400) = {label(labels, value)}",
                        "The release date statement's own reference")

        # 5. ProtonDB has Linux reports from before the earliest release date Wikidata knows.
        steam_ids = [str(v) for v in as_list(ids.get("steam"))]
        first = earliest_release(game)
        if protondb is not None and steam_ids and first:
            latest = []
            for steam_id in steam_ids:
                entry = protondb.get(steam_id)
                if isinstance(entry, dict) and isinstance(entry.get("latest"), str):
                    try:
                        latest.append(date.fromisoformat(entry["latest"]))
                    except ValueError:
                        pass
            if latest and max(latest) < first[0]:
                release = first[1]
                upcoming = first[0] > today
                add("reports-before-release" if not upcoming else "playtest-before-release", game,
                    f"People reported playing it before its earliest release date on Wikidata "
                    f"({str(release.get('time', ''))[:10]}, {PRECISION.get(release.get('precision'), 'other')} precision; "
                    f"newest ProtonDB report {max(latest).isoformat()})",
                    ("Not out yet: probably a playtest, demo or beta. Optional: add it as a release date with "
                     "qualifier object has role (P3831) = closed beta / open beta, only with a source"
                     if upcoming else
                     "Check for a missing earlier release (early access, beta, an earlier PC release) or a wrong "
                     "date; add or correct it with qualifier object has role (P3831) where it was early access "
                     "or a beta"),
                    "The Steam page's release date, the developer's or publisher's announcement, or press coverage "
                    "(never ProtonDB: its data is ODbL and must not be copied into Wikidata)",
                    hint_from="protondb")

    # 6. Wikidata points to a Commons file that doesn't exist (any more).
    if commons is not None:
        for qid, entries in sorted(files_by_game.items()):
            game = games[qid]
            if game.get("is_game") is False:
                continue
            for kind, name in entries:
                meta = commons.get(name)
                if isinstance(meta, dict) and meta.get("missing"):
                    add("commons-file-missing", game,
                        f"{kind[0].upper()}{kind[1:]} = \"{name}\", which doesn't exist on Wikimedia Commons",
                        f"Remove the {kind} statement (or point it to the file's new name if it was renamed)",
                        "The file's Commons page (\"No file by this name exists\" / its deletion log)",
                        hint_from="commons")

    rows.sort(key=lambda r: (-(r["pageviews_60d"] or 0), r["check"], r["wikidata"], r["detail"]))
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summary(rows: list[dict], as_of: dict) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["check"]] = counts.get(row["check"], 0) + 1
    lines = ["## Differences report", "",
             "Sources: " + ", ".join(f"{k} {v}" for k, v in as_of.items() if v), "",
             "| Check | Rows |", "|---|---|"]
    lines += [f"| {check} | {count} |" for check, count in sorted(counts.items())]
    lines += [f"| **Total** | **{len(rows)}** |", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    details = ROOT / "sources" / "wikidata-details"
    games = read_details(details / "games")
    labels_file = read_json(details / "labels.json", "Labels") or {}
    labels = labels_file.get("items") if isinstance(labels_file, dict) else {}
    matched = read_matched(ROOT / "matched")
    pageviews_file = read_json(ROOT / "sources" / "wikipedia-pageviews" / "pageviews.json", "Page views")
    protondb_file = read_json(ROOT / "sources" / "protondb" / "summary.json", "ProtonDB")
    commons_file = read_json(ROOT / "sources" / "commons" / "files.json", "Commons")

    def part(data, key):
        return data.get(key) if isinstance(data, dict) and isinstance(data.get(key), dict) else None

    details_as_of = labels_file.get("as_of", "") if isinstance(labels_file, dict) else ""
    try:
        date.fromisoformat(details_as_of)
    except ValueError:
        details_as_of = ""
    rows = build_rows(games, matched, labels or {}, part(pageviews_file, "games"), part(protondb_file, "games"),
                      part(commons_file, "files"), as_of=details_as_of)
    write_csv(rows, args.out)
    as_of = {
        "Wikidata details": (labels_file or {}).get("as_of", "") if isinstance(labels_file, dict) else "",
        "page views": (pageviews_file or {}).get("as_of", "") if isinstance(pageviews_file, dict) else "",
        "ProtonDB": (protondb_file or {}).get("export", "") if isinstance(protondb_file, dict) else "",
        "Commons": (commons_file or {}).get("as_of", "") if isinstance(commons_file, dict) else "",
    }
    text = summary(rows, as_of)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(f"{len(games)} games read, {len(rows)} rows written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
