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

# Dates to update

`dates-to-update.csv` is rebuilt every Sunday by the *Dates to update* workflow (`scripts/dates_to_update.py`). It has two parts, hand-entered dates first:

**1. Month/year dates that Wikipedia gives to the day.** For well-known games (at least 1,000 English Wikipedia views in 60 days) whose Wikidata release date is only a month or a year, with no day date in that year, the script reads the "released" line of the English Wikipedia article (upcoming games first). Same rules as the differences report: **the row is a hint** — find the real announcement (publisher, store page, press coverage cited in the article), then add the day on Wikidata with that source as the reference. Wikipedia is never the reference.

| Check | What it means |
|---|---|
| `day-on-wikipedia` | Wikipedia gives a day inside Wikidata's month or year (e.g. Wikidata "2027", Wikipedia "23 February 2027"). Early-access days are shown with a note. |
| `later-on-wikipedia` | Wikipedia gives only later days than Wikidata's period — often a delay, or another platform's release. |

**2. Hand-entered dates.** DropSlate's owner can enter an exact date by hand with its source (DropSlate's Studio). DropSlate publishes those dates at `https://dropslate.focalnull.com/catalogue/hand-dates.json`; while that file doesn't exist, there are none to recheck. Every Sunday each one is compared with Wikidata and Wikipedia, and its source link is opened; from Monday to Saturday the same check runs for dates within 30 days of their day (written to `hand-dates-daily.csv`). Nothing is changed automatically: the owner chooses Keep, Use Wikidata or Edit.

| Check | What it means |
|---|---|
| `hand-date-differs-from-wikidata` | Wikidata now has a different day in the same year, or a later day (a delay or a correction). |
| `hand-date-differs-from-wikipedia` | Wikipedia's day differs. |
| `hand-date-matches-wikidata` | Wikidata now has the same day: the hand-entered date can be removed. |
| `hand-date-passed` | The day passed more than 7 days ago and Wikidata has no matching day: check it really came out. |
| `hand-date-source-dead` | The source link answers 404/410 or can't be reached. |

Columns: `check`, `wikidata`, `title`, `pageviews_60d`, `wikidata_date`, `wikipedia_date`, `wikipedia_platforms`, `your_date`, `your_source`, `detail`, `suggested_fix`, `fix_source`, `wikidata_url`, `enwiki_url`, `licence`. Rows built from Wikipedia dates carry its CC BY-SA 4.0 credit (see `sources/wikipedia-release-dates/LICENSE-DATA.md`).
