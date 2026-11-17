# Wikidata game details

- **What we take:** for every game in `matched/`, the facts DropSlate shows on its calendar and game pages, read from Wikidata with the `wbgetentities` API (50 games per call):
  - names: labels and aliases in the languages DropSlate searches (all labels when a game has no English or multilingual name), the English description and the English Wikipedia article title;
  - release dates (P577) with their precision (9 = year, 10 = month, 11 = day), rank and qualifiers, including platform (P400), region (P291) and release type (P3831, e.g. early access);
  - platforms (P400), developers (P178), publishers (P123), genres (P136), series (P179), game modes (P404), engines (P408), PEGI (P908) and ESRB (P852) ratings;
  - YouTube trailer ID (P1651), Steam (P1733), IGDB (P5794), GOG (P2725) and Nintendo eShop (P8084) IDs, and current official websites (P856 without an end date);
  - Wikimedia Commons file names of the game's image (P18) and logo (P154) — names only, no files;
  - links to other games: series with its number (P179 + P1545), follows (P155), followed by (P156), based on (P144), edition of (P747/P629) and the like (P4969);
  - `is_game`: whether the item is a video game and not an expansion pack or mod;
  - `lastrevid` and `modified`, so DropSlate can tell which games changed.
- **Names of linked items** (`labels.json`): the English and multilingual names of every platform, region, company, genre, series and release type the games point to, plus a company's logo file name on Wikimedia Commons (P154; only the name, no image).
- **Licence:** Wikidata's structured data is released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). No attribution is required, but we give it gladly: thank you to everyone who edits Wikidata.
- **Format:** `games/<bucket>.json` uses the same 1,000 buckets as `matched/` (last three digits of the Wikidata number), one game per line. Dates are written like the Wikidata Query Service writes them (`2023-08-01T00:00:00Z` for "August 2023"); always read `precision` before showing a day or a month. Statements ranked "deprecated" are left out; "unknown value" and "no value" are left out too.
- **Script:** `scripts/fetch_wikidata_details.py` · **Workflow:** *Refresh game details* (Sundays)
