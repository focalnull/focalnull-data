# Differences report

`differences.csv` lists places where our sources disagree with Wikidata, or where Wikidata disagrees with itself, so a person can check them and fix Wikidata properly. It is rebuilt every Sunday by the *Differences report* workflow (`scripts/report_differences.py`), from the files already in this repository. Best-known games (most Wikipedia page views) come first.

**Every row is a hint, not a fix.** Nothing here is ever copied into Wikidata by a script.

## How to use it

1. Open the game on Wikidata (`wikidata_url`).
2. Check the difference against the source named in `fix_source` (a store page, the publisher, press coverage, the Commons log).
3. Only if that source confirms it, make the change on Wikidata **with that source as the reference**.
4. If the source doesn't confirm it, leave Wikidata as it is. DropSlate keeps showing the Wikidata value until Wikidata changes.

## Rules

- **Each fix needs its own source.** A row's hint is never the reference.
- **ProtonDB data (ODbL) and anything CC BY-NC-SA are never copied into Wikidata** (Wikidata is CC0). ProtonDB only tells us *where to look*: for example, people reported playing a game before the release date Wikidata has, so we look for the real date on the Steam page or in the publisher's announcement.
- Don't delete other people's statements without a source; if a value looks wrong but nothing proves it, leave it or deprecate it with a reason.
- Release dates that were early access, betas or playtests get the qualifier *object has role* (P3831).

## Checks

| Check | What it means | Hint from |
|---|---|---|
| `store-id-without-platform` | The game has a Steam, GOG, Epic or Nintendo eShop ID, but no platform that store sells for (Steam/GOG/Epic → Windows, macOS, Linux; eShop → Switch, Switch 2, Wii U, 3DS). Often a PC or eShop re-release that was never added. Check the store page first: some IDs belong to a collection or DLC. | Wikidata |
| `platform-not-a-platform` | A store, service, category or file format is used as a platform (P400), e.g. Steam or PlayStation Store. | Wikidata |
| `date-platform-not-listed` | A release date names a platform in its qualifier that the item doesn't list as a platform. | Wikidata |
| `platform-in-wrong-qualifier` | A release date's *place of publication* (P291) holds a platform or a store instead of a place. | Wikidata |
| `reports-before-release` | People reported playing the game on Linux before its earliest release date on Wikidata: an earlier release (early access, beta, an older PC release) is probably missing, or a date is wrong. | ProtonDB (ODbL) |
| `playtest-before-release` | The same for a game that isn't out yet: usually a playtest, demo or beta. Optional to add, only with a source. | ProtonDB (ODbL) |
| `commons-file-missing` | Wikidata's image (P18) or logo (P154) points to a Commons file that doesn't exist (any more). | Wikimedia Commons |

## Columns

`check`, `wikidata`, `title`, `pageviews_60d` (English Wikipedia views in the last 60 days, CC0), `detail`, `suggested_fix`, `fix_source`, `hint_from`, `licence`, `wikidata_url`, `enwiki`.

## Licence

This report is a derived database. Each row's `licence` column says which licence that row is under:

- rows from Wikidata facts: **CC0**;
- rows with `hint_from` = `protondb`: **ODbL 1.0** — derived from the [ProtonDB reports export](https://github.com/bdefore/protondb-data) by ProtonDB, shared under the same licence with this credit (see `sources/protondb/LICENSE-DATA.md`);
- rows with `hint_from` = `commons`: **CC BY-SA 4.0**, like `sources/commons/files.json`.
