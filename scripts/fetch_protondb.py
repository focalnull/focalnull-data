#!/usr/bin/env python3
"""Summarise ProtonDB's public report export for the games in matched/.

Source: https://github.com/bdefore/protondb-data (ODbL / DbCL).
We download the newest monthly export, count reports per Steam app ID, and keep
only games we already have (matched by the Steam ID that Wikidata gives us).

Output: sources/protondb/summary.json — {steam_app_id: {...}} — ODbL.
If the export's shape is not what we expect, we stop with a clear message
and write nothing (we never guess at fields).
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import io
import json
import os
import re
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sources" / "protondb" / "summary.json"
LIST_URL = "https://api.github.com/repos/bdefore/protondb-data/contents/reports"
RAW_URL = "https://raw.githubusercontent.com/bdefore/protondb-data/master/reports/{name}"
USER_AGENT = "focalnull-data/0.1 (https://github.com/focalnull/focalnull-data)"
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
NAME = re.compile(r"reports_([a-z]{3})(\d{1,2})_(\d{4})\.tar\.gz")


def get(url: str) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    parts = urllib.parse.urlsplit(url)
    # Send the token only to GitHub's API host itself (exact match, not a prefix).
    if parts.scheme == "https" and parts.hostname == "api.github.com" and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=600) as resp:
        return resp.read()


def export_date(name: str) -> dt.date | None:
    match = NAME.fullmatch(name)  # whole name only: nothing before or after it
    if not match or match.group(1) not in MONTHS:
        return None
    return dt.date(int(match.group(3)), MONTHS[match.group(1)], int(match.group(2)))


def newest_export(names: list[str]) -> str:
    dated = [(d, n) for n in names if (d := export_date(n))]
    if not dated:
        raise SystemExit("No ProtonDB export files found in the reports folder.")
    return max(dated)[1]


def our_steam_ids() -> set[str]:
    ids = set()
    for path in glob.glob(str(ROOT / "matched" / "*.json")):
        for record in json.loads(Path(path).read_text(encoding="utf-8")):
            steam = record.get("ids", {}).get("steam")
            if steam and steam.isdigit():
                ids.add(steam)
    return ids


def report_fields(report: dict) -> tuple[str, str, int] | None:
    """(steam app id, verdict 'yes'/'no', unix timestamp) or None if the report lacks them."""
    app = report.get("app") or {}
    steam = (app.get("steam") or {}).get("appId")
    responses = report.get("responses") or {}
    verdict = responses.get("verdict")
    stamp = report.get("timestamp")
    if steam is None or verdict not in ("yes", "no") or not isinstance(stamp, (int, float)):
        return None
    return str(steam), verdict, int(stamp)


def summarise(reports: list, wanted: set[str], today: dt.date) -> tuple[dict, int]:
    cutoff = dt.datetime(today.year - 1, today.month, 1).timestamp()
    summary: dict[str, dict] = {}
    usable = 0
    for report in reports:
        fields = report_fields(report) if isinstance(report, dict) else None
        if not fields:
            continue
        usable += 1
        steam, verdict, stamp = fields
        if steam not in wanted:
            continue
        item = summary.setdefault(steam, {"reports": 0, "works": 0, "reports_12m": 0, "works_12m": 0, "latest": 0})
        item["reports"] += 1
        item["works"] += verdict == "yes"
        if stamp >= cutoff:
            item["reports_12m"] += 1
            item["works_12m"] += verdict == "yes"
        item["latest"] = max(item["latest"], stamp)
    for item in summary.values():
        item["latest"] = dt.datetime.fromtimestamp(item["latest"], dt.timezone.utc).date().isoformat()
    return dict(sorted(summary.items(), key=lambda kv: int(kv[0]))), usable


def load_reports(blob: bytes) -> list:
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(".json")]
        if len(members) != 1:
            raise SystemExit(f"Expected one JSON file in the export, found: {[m.name for m in members]}")
        data = json.load(tar.extractfile(members[0]))
    if not isinstance(data, list):
        raise SystemExit(f"Expected a list of reports, found {type(data).__name__}.")
    return data


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    wanted = our_steam_ids()
    if not wanted:
        raise SystemExit("matched/ has no Steam IDs yet — run 'Refresh game IDs' first.")
    names = [item["name"] for item in json.loads(get(LIST_URL))]
    name = newest_export(names)
    print(f"Newest ProtonDB export: {name}")
    reports = load_reports(get(RAW_URL.format(name=name)))
    summary, usable = summarise(reports, wanted, dt.date.today())
    print(f"Reports in export: {len(reports)}; usable: {usable}; our games with reports: {len(summary)} of {len(wanted)}")
    if reports and usable < len(reports) * 0.5:
        sample = reports[0] if isinstance(reports[0], dict) else {}
        raise SystemExit(f"Fewer than half the reports had the expected fields; first report keys: {sorted(sample)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"export": name, "games": summary}, indent=1) + "\n", encoding="utf-8")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a", encoding="utf-8") as out:
        out.write(f"- ProtonDB export: {name}\n- Reports: {len(reports)} (usable {usable})\n"
                  f"- Our games with reports: {len(summary)} of {len(wanted)} with a Steam ID\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
