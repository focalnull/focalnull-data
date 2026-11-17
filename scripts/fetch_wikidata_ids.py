#!/usr/bin/env python3
"""Fetch every video game on Wikidata that has a platform and a release date,
with the IDs other sites use for it, and write them to matched/<bucket>.json.

Standard library only. Polite to Wikimedia: one request at a time, a clear
User-Agent, maxlag, and back-off on 429/503.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "focalnull-data/0.1 (https://github.com/focalnull/focalnull-data)"
SPARQL_URL = "https://query.wikidata.org/sparql"
API_URL = "https://www.wikidata.org/w/api.php"
ROOT = Path(__file__).resolve().parent.parent
MATCHED = ROOT / "matched"
BATCH = 50

# Wikidata property -> key in our files. These are identifiers (facts), not copied content.
EXTERNAL_IDS = {
    "P1733": "steam",
    "P2725": "gog",
    "P6278": "epic",
    "P5794": "igdb",
    "P11688": "mobygames",
    "P6337": "pcgamingwiki",
    "P2816": "howlongtobeat",
    "P1712": "metacritic",
}

LIST_QUERY = """SELECT DISTINCT ?game WHERE {
  ?game wdt:P31 wd:Q7889; wdt:P400 []; wdt:P577 [].
}"""


def request_json(url: str, data: dict | None = None, tries: int = 6) -> dict:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    for attempt in range(tries):
        req = urllib.request.Request(url, data=body, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json, application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.load(resp)
            if isinstance(payload, dict) and payload.get("error", {}).get("code") == "maxlag":
                raise urllib.error.HTTPError(url, 503, "maxlag", {}, None)
            return payload
        except urllib.error.HTTPError as err:
            if err.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            wait = int(err.headers.get("Retry-After", 0) or 0) if err.headers else 0
            time.sleep(max(wait, 5 * (attempt + 1)))
        except urllib.error.URLError:
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def list_game_ids() -> list[str]:
    result = request_json(SPARQL_URL, {"query": LIST_QUERY, "format": "json"})
    ids = {b["game"]["value"].rsplit("/", 1)[-1] for b in result["results"]["bindings"]}
    return sorted((i for i in ids if i.startswith("Q") and i[1:].isdigit()), key=lambda q: int(q[1:]))


def bucket(qid: str) -> str:
    """Spread games over 1,000 files by the last three digits of the Q-number."""
    return f"{int(qid[1:]) % 1000:03d}"


def first_value(claims: dict, prop: str) -> str | None:
    for claim in claims.get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def record_from_entity(entity: dict) -> dict | None:
    qid = entity.get("id", "")
    if not qid.startswith("Q") or "missing" in entity:
        return None
    claims = entity.get("claims", {})
    record = {"wikidata": qid}
    label = entity.get("labels", {}).get("en", {}).get("value")
    if label:
        record["label_en"] = label
    enwiki = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
    if enwiki:
        record["enwiki"] = enwiki
    ids = {key: value for prop, key in EXTERNAL_IDS.items() if (value := first_value(claims, prop))}
    if ids:
        record["ids"] = ids
    return record


def fetch_entities(qids: list[str]) -> list[dict]:
    payload = request_json(API_URL, {
        "action": "wbgetentities", "ids": "|".join(qids), "format": "json",
        "props": "labels|claims|sitelinks", "languages": "en", "sitefilter": "enwiki",
        "maxlag": "5",
    })
    return [rec for e in payload.get("entities", {}).values() if (rec := record_from_entity(e))]


def write_buckets(records: list[dict]) -> int:
    groups: dict[str, list[dict]] = {}
    for rec in records:
        groups.setdefault(bucket(rec["wikidata"]), []).append(rec)
    MATCHED.mkdir(exist_ok=True)
    for name, items in groups.items():
        items.sort(key=lambda r: int(r["wikidata"][1:]))
        text = json.dumps(items, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        (MATCHED / f"{name}.json").write_text(text, encoding="utf-8")
    return len(groups)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="only fetch the first N games (0 = all)")
    parser.add_argument("--pause", type=float, default=0.2, help="seconds between API calls")
    args = parser.parse_args()

    qids = list_game_ids()
    print(f"Games with a platform and a release date on Wikidata: {len(qids)}")
    if args.limit:
        qids = qids[: args.limit]
    records: list[dict] = []
    for start in range(0, len(qids), BATCH):
        records.extend(fetch_entities(qids[start:start + BATCH]))
        if start and start % 5000 == 0:
            print(f"  fetched {start} / {len(qids)}", flush=True)
        time.sleep(args.pause)
    files = write_buckets(records)
    with_ids = sum(1 for r in records if r.get("ids"))
    print(f"Wrote {len(records)} games into {files} files; {with_ids} have at least one external ID.")
    summary = Path(__import__("os").environ.get("GITHUB_STEP_SUMMARY", "/dev/null"))
    with summary.open("a", encoding="utf-8") as out:
        out.write(f"- Games: {len(records)}\n- Files: {files}\n- With external IDs: {with_ids}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
