#!/usr/bin/env python3
"""Store each game's facts from Wikidata, so DropSlate can read them from files
instead of asking Wikidata's query service game by game.

Input: the game IDs in matched/*.json (written by "Refresh game IDs").
Output:
  sources/wikidata-details/games/<bucket>.json  one game per line, same buckets as matched/
  sources/wikidata-details/labels.json          English (and "mul") names of every item the
                                                games point to (platforms, regions, companies,
                                                genres, series...), plus company logo file names

What each game record holds is described in sources/wikidata-details/LICENSE-DATA.md.

How: the Wikidata API's wbgetentities, 50 games per call (the API's maximum), one call
at a time, a short pause between calls and back-off on 429/5xx. Reads only, so no maxlag
parameter (L50). Two small query-service calls per run list the classes that count as a
video game and the classes that don't (expansion packs, mods).

If an answer is not shaped as expected, we stop with a clear message. Each bucket file is
written only once all its games were fetched, so a stopped run never leaves half a bucket.
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_wikidata_ids import API_URL, SPARQL_URL, bucket, request_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MATCHED = ROOT / "matched"
OUT = ROOT / "sources" / "wikidata-details"
GAMES = OUT / "games"
LABELS = OUT / "labels.json"
BATCH = 50
FORMAT = 1

# Same languages DropSlate uses for titles and search names.
NAME_LANGUAGES = ("en", "mul", "sv", "da", "nb", "fi", "nl", "de", "fr", "es", "it", "pt", "pl", "ja",
                  "ca", "ro", "ru", "tr", "ko", "zh")
GAME_CLASS = "Q7889"            # video game
NOT_GAME_CLASSES = ("Q1066707", "Q209163")  # the classes DropSlate leaves out (and their subclasses)

# Simple facts: "truthy" values (preferred statements if any, otherwise normal ones), like wdt: in SPARQL.
TRUTHY = {
    "P31": "instance_of",
    "P178": "developers",
    "P123": "publishers",
    "P136": "genres",
    "P179": "series",
    "P404": "game_modes",
    "P408": "engines",
    "P908": "pegi",
    "P852": "esrb",
    "P1651": "youtube",
    "P1733": "steam",
    "P5794": "igdb",
    "P2725": "gog",
    "P8084": "eshop",
}
# Links between games: every statement that isn't deprecated, with its series ordinal (P1545).
RELATIONS = ("P179", "P155", "P156", "P144", "P747", "P629", "P4969")
ITEM_FIELDS = ("instance_of", "platforms", "developers", "publishers", "genres", "series",
               "game_modes", "engines", "pegi", "esrb")
COMPANY_FIELDS = ("developers", "publishers")
QID = re.compile(r"^Q[1-9][0-9]*$")


class ShapeError(SystemExit):
    """Wikidata answered with something we don't understand."""


# ---------- reading statements ----------

def normalise_time(value: str) -> str:
    """'+2021-10-00T00:00:00Z' -> '2021-10-01T00:00:00Z', the way the query service writes it."""
    match = re.fullmatch(r"([+-])(\d{1,16})-(\d{2})-(\d{2})(T\d{2}:\d{2}:\d{2}Z)", value)
    if not match:
        raise ShapeError(f"Unexpected time value: {value!r}")
    sign, year, month, day, rest = match.groups()
    month = "01" if month == "00" else month
    day = "01" if day == "00" else day
    return f"{'-' if sign == '-' else ''}{int(year):04d}-{month}-{day}{rest}"


def snak_value(snak: dict):
    """The plain value of a main snak or qualifier; None for 'unknown value', 'no value' and coordinates."""
    if not isinstance(snak, dict):
        raise ShapeError(f"Unexpected snak: {snak!r}")
    if snak.get("snaktype") != "value":
        return None
    data = snak.get("datavalue")
    if not isinstance(data, dict):
        raise ShapeError(f"Snak without a value: {snak.get('property')}")
    kind, value = data.get("type"), data.get("value")
    if kind == "wikibase-entityid":
        return value.get("id") if isinstance(value, dict) else None
    if kind == "string":
        return value if isinstance(value, str) else None
    if kind == "time":
        return normalise_time(value["time"]) if isinstance(value, dict) else None
    if kind == "monolingualtext":
        return value.get("text") if isinstance(value, dict) else None
    if kind == "quantity":
        return value.get("amount", "").lstrip("+") if isinstance(value, dict) else None
    return None


def statements(claims: dict, prop: str) -> list[dict]:
    values = claims.get(prop, [])
    if not isinstance(values, list):
        raise ShapeError(f"Claims for {prop} are not a list")
    return [s for s in values if isinstance(s, dict) and s.get("rank") != "deprecated"]


def truthy(claims: dict, prop: str) -> list:
    kept = statements(claims, prop)
    preferred = [s for s in kept if s.get("rank") == "preferred"]
    values = []
    for s in preferred or kept:
        value = snak_value(s.get("mainsnak"))
        if value is not None and value not in values:
            values.append(value)
    return values


def all_values(claims: dict, prop: str) -> list:
    values = []
    for s in statements(claims, prop):
        value = snak_value(s.get("mainsnak"))
        if value is not None and value not in values:
            values.append(value)
    return values


def qualifiers(statement: dict) -> dict:
    result = {}
    for prop, snaks in (statement.get("qualifiers") or {}).items():
        values = [v for v in (snak_value(s) for s in snaks) if v is not None]
        if values:
            result[prop] = values
    return result


def release_dates(claims: dict) -> list[dict]:
    dates = []
    for s in statements(claims, "P577"):
        snak = s.get("mainsnak", {})
        if snak.get("snaktype") != "value":
            continue
        value = snak.get("datavalue", {}).get("value")
        if not isinstance(value, dict) or not isinstance(value.get("precision"), int):
            raise ShapeError(f"Unexpected release date in statement {s.get('id')}")
        entry = {
            "statement": s.get("id"),
            "time": normalise_time(value.get("time", "")),
            "precision": value["precision"],
            "rank": s.get("rank"),
        }
        if str(value.get("calendarmodel", "")).endswith("/Q1985786"):
            entry["calendar"] = "julian"
        found = qualifiers(s)
        if found:
            entry["qualifiers"] = found
        dates.append(entry)
    return dates


def official_websites(claims: dict) -> list[str]:
    """P856 without an end date (P582); preferred ones only when there are any, like DropSlate's sync."""
    current = [s for s in statements(claims, "P856") if "P582" not in (s.get("qualifiers") or {})]
    preferred = [s for s in current if s.get("rank") == "preferred"]
    sites = []
    for s in preferred or current:
        value = snak_value(s.get("mainsnak"))
        if isinstance(value, str) and value not in sites:
            sites.append(value)
    return sites


def relations(claims: dict) -> dict:
    found = {}
    for prop in RELATIONS:
        items = []
        for s in statements(claims, prop):
            target = snak_value(s.get("mainsnak"))
            if not isinstance(target, str) or not QID.match(target):
                continue
            entry = {"id": target}
            ordinal = (qualifiers(s).get("P1545") or [None])[0]
            if ordinal:
                entry["ordinal"] = ordinal
            if s.get("rank") == "preferred":
                entry["rank"] = "preferred"
            items.append(entry)
        if items:
            found[prop] = items
    return found


def term_values(terms, languages=NAME_LANGUAGES) -> dict:
    if not isinstance(terms, dict):
        raise ShapeError("Unexpected labels/aliases block")
    result = {}
    for lang, value in terms.items():
        if languages and lang not in languages:
            continue
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            result[lang] = value["value"]
        elif isinstance(value, list):
            names = [v["value"] for v in value if isinstance(v, dict) and isinstance(v.get("value"), str)]
            if names:
                result[lang] = names
    return dict(sorted(result.items()))


def game_record(entity: dict, game_classes: set[str], not_game_classes: set[str]) -> dict:
    qid = entity["id"]
    claims = entity.get("claims")
    if not isinstance(claims, dict):
        raise ShapeError(f"{qid}: no claims block")
    record = {"id": qid, "lastrevid": entity.get("lastrevid"), "modified": entity.get("modified")}
    labels = term_values(entity.get("labels", {}))
    if "en" not in labels and "mul" not in labels:
        # No English or multilingual name: keep every label so DropSlate can pick the best title.
        labels = term_values(entity.get("labels", {}), languages=None)
    if labels:
        record["labels"] = labels
    aliases = term_values(entity.get("aliases", {}))
    if aliases:
        record["aliases"] = aliases
    description = entity.get("descriptions", {}).get("en", {}).get("value")
    if description:
        record["description_en"] = description
    enwiki = (entity.get("sitelinks") or {}).get("enwiki", {}).get("title")
    if enwiki:
        record["enwiki"] = enwiki
    for prop, field in TRUTHY.items():
        values = truthy(claims, prop)
        if values:
            record[field] = values
    classes = record.get("instance_of", [])
    record["is_game"] = bool(set(classes) & game_classes) and not set(classes) & not_game_classes
    platforms = all_values(claims, "P400")
    if platforms:
        record["platforms"] = platforms
    dates = release_dates(claims)
    if dates:
        record["release_dates"] = dates
    sites = official_websites(claims)
    if sites:
        record["official_websites"] = sites
    links = relations(claims)
    if links:
        record["relations"] = links
    return record


# ---------- fetching ----------

def class_sets() -> tuple[set[str], set[str]]:
    def subclasses(root_ids) -> set[str]:
        values = " ".join(f"wd:{q}" for q in root_ids)
        query = f"SELECT DISTINCT ?c WHERE {{ VALUES ?root {{ {values} }} ?c wdt:P279* ?root }}"
        reply = request_json(SPARQL_URL, {"query": query, "format": "json"})
        try:
            found = {b["c"]["value"].rsplit("/", 1)[-1] for b in reply["results"]["bindings"]}
        except (KeyError, TypeError):
            raise ShapeError("Unexpected query service reply for the class lists") from None
        return {q for q in found if QID.match(q)}

    games = subclasses([GAME_CLASS])
    not_games = subclasses(NOT_GAME_CLASSES)
    if GAME_CLASS not in games or len(games) < 100 or not set(NOT_GAME_CLASSES) <= not_games:
        raise ShapeError(f"Class lists look wrong: {len(games)} game classes, {len(not_games)} excluded")
    return games, not_games


def get_entities(ids: list[str], props: str, languages: str) -> dict:
    payload = request_json(API_URL, {
        "action": "wbgetentities", "ids": "|".join(ids), "format": "json", "formatversion": "2",
        "props": props, "languages": languages, "sitefilter": "enwiki",
    })
    if "error" in payload:
        raise ShapeError(f"Wikidata API error: {payload['error']}")
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        raise ShapeError("Reply has no entities object")
    return entities


def fetch_games(ids: list[str], game_classes, not_game_classes) -> tuple[list[dict], int]:
    """Records for the games that still exist; redirects and deleted items are left out and counted."""
    entities = get_entities(ids, "info|labels|aliases|descriptions|claims|sitelinks", "|".join(NAME_LANGUAGES))
    records, skipped = [], 0
    for key, entity in entities.items():
        if not isinstance(entity, dict):
            raise ShapeError(f"Unexpected entity for {key}")
        if "missing" in entity or entity.get("id") not in ids:
            skipped += 1  # deleted, or a redirect to another item: "Refresh game IDs" picks that up
            continue
        records.append(game_record(entity, game_classes, not_game_classes))
    return records, skipped


def fetch_labels(ids: list[str], companies: set[str], pause: float) -> dict:
    result = {}
    for wanted, props in (([q for q in ids if q in companies], "labels|claims"),
                          ([q for q in ids if q not in companies], "labels")):
        for start in range(0, len(wanted), BATCH):
            batch = wanted[start:start + BATCH]
            for key, entity in get_entities(batch, props, "en|mul").items():
                if not isinstance(entity, dict) or "missing" in entity or entity.get("id") not in batch:
                    continue
                entry = term_values(entity.get("labels", {}), languages=("en", "mul"))
                logo = truthy(entity.get("claims") or {}, "P154")[:1] if props != "labels" else []
                if logo:
                    entry["logo"] = logo[0]
                if entry:
                    result[entity["id"]] = entry
            time.sleep(pause)
    return result


def referenced_items(record: dict) -> tuple[set[str], set[str]]:
    items, companies = set(), set()
    for field in ITEM_FIELDS:
        for value in record.get(field, []):
            if isinstance(value, str) and QID.match(value):
                items.add(value)
                if field in COMPANY_FIELDS:
                    companies.add(value)
    for entries in record.get("relations", {}).values():
        items.update(e["id"] for e in entries)
    for date in record.get("release_dates", []):
        for values in date.get("qualifiers", {}).values():
            items.update(v for v in values if isinstance(v, str) and QID.match(v))
    return items, companies


# ---------- files ----------

def game_ids_by_bucket() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for path in sorted(glob.glob(str(MATCHED / "*.json"))):
        for record in json.loads(Path(path).read_text(encoding="utf-8")):
            qid = record.get("wikidata") if isinstance(record, dict) else None
            if isinstance(qid, str) and QID.match(qid):
                groups.setdefault(bucket(qid), []).append(qid)
    return {name: sorted(set(ids), key=lambda q: int(q[1:])) for name, ids in sorted(groups.items())}


def lines_json(items: list[str], opening: str, closing: str) -> str:
    text = opening + "\n" + ",\n".join(items) + "\n" + closing + "\n"
    json.loads(text)  # never write a file we can't read back
    return text


def write_bucket(name: str, records: list[dict]) -> None:
    GAMES.mkdir(parents=True, exist_ok=True)
    records.sort(key=lambda r: int(r["id"][1:]))
    rows = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records]
    (GAMES / f"{name}.json").write_text(lines_json(rows, "[", "]"), encoding="utf-8")


def write_labels(labels: dict, today: str) -> None:
    ordered = sorted(labels.items(), key=lambda kv: int(kv[0][1:]))
    rows = [f" {json.dumps(q)}: {json.dumps(v, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}"
            for q, v in ordered]
    head = '{"format": %d, "as_of": "%s", "items": {' % (FORMAT, today)
    LABELS.write_text(lines_json(rows, head, "}}"), encoding="utf-8")


def read_labels() -> dict:
    if not LABELS.exists():
        return {}
    items = json.loads(LABELS.read_text(encoding="utf-8")).get("items")
    return items if isinstance(items, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buckets", type=int, default=0,
                        help="only refresh the first N of the 1,000 bucket files (0 = all)")
    parser.add_argument("--pause", type=float, default=0.5, help="seconds between API calls")
    args = parser.parse_args()

    groups = game_ids_by_bucket()
    if not groups:
        raise SystemExit("No games found in matched/. Run 'Refresh game IDs' first.")
    names = list(groups)[: args.buckets] if args.buckets else list(groups)
    full_run = len(names) == len(groups)
    game_classes, not_game_classes = class_sets()
    print(f"Classes: {len(game_classes)} count as video games, {len(not_game_classes)} are left out")
    print(f"Refreshing {len(names)} of {len(groups)} bucket files "
          f"({sum(len(groups[n]) for n in names)} games)", flush=True)

    wanted, companies = set(), set()
    games = skipped = not_games = 0
    started = time.monotonic()
    for position, name in enumerate(names, 1):
        ids = groups[name]
        records = []
        for start in range(0, len(ids), BATCH):
            found, missing = fetch_games(ids[start:start + BATCH], game_classes, not_game_classes)
            records.extend(found)
            skipped += missing
            time.sleep(args.pause)
        write_bucket(name, records)
        for record in records:
            items, firms = referenced_items(record)
            wanted |= items
            companies |= firms
        games += len(records)
        not_games += sum(1 for r in records if not r["is_game"])
        if position % 50 == 0:
            minutes = (time.monotonic() - started) / 60
            print(f"  {position} / {len(names)} files, {games} games, {minutes:.0f} min", flush=True)

    labels = {} if full_run else read_labels()
    print(f"Looking up names for {len(wanted)} linked items ({len(companies)} companies)", flush=True)
    labels.update(fetch_labels(sorted(wanted, key=lambda q: int(q[1:])), companies, args.pause))
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    write_labels(labels, today)

    minutes = (time.monotonic() - started) / 60
    print(f"Wrote {games} games into {len(names)} files and {len(labels)} names in {minutes:.0f} min; "
          f"{skipped} deleted or redirected items skipped; {not_games} not counted as games.")
    summary = Path(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"))
    with summary.open("a", encoding="utf-8") as out:
        out.write(f"- Bucket files refreshed: {len(names)} of {len(groups)}\n- Games: {games}\n"
                  f"- Linked item names: {len(labels)}\n- Deleted or redirected (skipped): {skipped}\n"
                  f"- Not counted as games (expansions, mods...): {not_games}\n- Minutes: {minutes:.0f}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
