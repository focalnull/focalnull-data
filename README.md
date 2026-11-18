# focalnull-data

Open video game data, gathered from free sources and matched together, one game at a time.

This is the data side of **[DropSlate](https://dropslate.focalnull.com)**, a free video game release calendar and catalogue: what came out when, on which platforms, what's coming next, and where a game's story began. DropSlate is part of **[FocalNull](https://focalnull.com)**, my small corner of the internet for games, photography and the things I love.

## Why this exists

I've played games for as long as I can remember, and I've always wanted one quiet place where I could look up a game and see its whole life: the first release, the ports, the remasters, the early-access years, the day it finally reached my console. No ads, no algorithms, no scores shouted at me. Just the history, told properly.

Most of that history already exists, written down by thousands of volunteers on Wikidata, Wikipedia and Wikimedia Commons, and by communities like ProtonDB and PCGamingWiki. It's scattered, though. This repository brings the free, openly licensed parts together and matches them to the same game, so every game ends up with one tidy record.

Keeping it public felt right. The data came from open communities, so the matched result should be open too.

## What's in here

| Path | What it holds |
|---|---|
| `matched/` | One record per game, spread over 1,000 small JSON files by the last three digits of its Wikidata number (for example, Q15727 lives in `727.json`). Each record has the game's English name, its English Wikipedia article and the IDs other sites use for it |
| `sources/<name>/` | One folder per extra source: a `LICENSE-DATA.md` saying what we take, its licence and its credit, plus that source's data file (for example `sources/protondb/summary.json`, or `sources/commons/files.json` for image licences and credits) |
| `reports/differences.csv` | Places where our sources disagree with Wikidata, or Wikidata disagrees with itself, best-known games first: hints for a person to check and fix on Wikidata with a proper source (rules in `reports/README.md`) |
| `scripts/` | The small scripts that fetch each source and build the report (Python, no extra packages) |
| `tests/` | Checks that run on every change |
| `.github/workflows/` | The jobs that refresh the data |

Every game is keyed by its **Wikidata ID**. Wikidata already links most games to their Steam, GOG, Epic, IGDB, MobyGames, PCGamingWiki, HowLongToBeat and Metacritic pages, so that ID is what lets every source line up with the same game.

## Sources and credits

| Source | What we use | Licence | Status |
|---|---|---|---|
| [Wikidata](https://www.wikidata.org) | Every video game with a platform and a release date (about 135,000), its English name, its English Wikipedia article and the IDs other sites use for it | CC0 | Live |
| [Wikidata](https://www.wikidata.org) game details | For each game: release dates with their precision, platform, region and release type (early access, full release…), developers, publishers, series, genres, trailer, official website and names (`sources/wikidata-details/`) | CC0 | Live |
| [ProtonDB](https://www.protondb.com) | How many players report that a Steam game works on Linux and Steam Deck, overall and in the last 12 months (counts only, joined by Steam ID) | ODbL — this data stays under ODbL | Live |
| [PCGamingWiki](https://www.pcgamingwiki.com) | A link to each game's PCGamingWiki page (the page name comes from Wikidata). Their data API is not open to anonymous use, so no PCGamingWiki content is copied here | — (links only) | Live |
| [Wikipedia page views](https://www.mediawiki.org/wiki/Extension:PageViewInfo) | How often each game's English Wikipedia article was read in the last 60 days, so well-known games are added first (`sources/wikipedia-pageviews/pageviews.json`) | CC0 | Live |
| [Wikimedia Commons](https://commons.wikimedia.org) | For each image and logo a game points to on Wikidata: its licence, author, credit line and links (`sources/commons/files.json`; metadata only, no image files here) | Images: per file, as stated on each file. Our metadata file: CC BY-SA 4.0 | Live |

Nothing here is copied from store pages, press kits or sites that don't offer an open licence. Other sites' IDs are just facts that point to their pages. Logos, box art and trademarks belong to their owners and are not stored in this repository.

## How it works

1. **Find the games.** *Refresh game IDs* asks Wikidata for every video game with a platform and a release date and writes `matched/`. *Refresh game details* then stores each game's facts (release dates, platforms, companies, series and more) in `sources/wikidata-details/`, 50 games per request. One request at a time, with a short pause between them, so we stay a polite guest.
2. **Add the other sources.** Each source has its own job (for example *Refresh ProtonDB summary*, about once a month) that joins its data to our games by ID and keeps its own licence and credit.
3. **Compare** *(coming)*. Where sources disagree, for example on a release year, the difference goes into a report. The fix is then made at the source, usually on Wikidata, with a proper reference, so every project that uses it benefits.
4. **Feed DropSlate.** Once a day, [DropSlate](https://dropslate.focalnull.com) reads these files and adds new or changed games to its calendar and catalogue, well-known games first. The app itself (calendar, game pages, design) lives elsewhere; this repository only holds open data and the small scripts that collect it.

Every Sunday the jobs run in order: game IDs, then game details, then Wikipedia page views, then Commons metadata. ProtonDB is refreshed by hand about once a month, when a new export appears.

## Using the images

`sources/commons/files.json` lists every Wikimedia Commons image and logo our games point to, with what you need to reuse it fairly: the licence, the author, a ready-made credit line ("Author, Licence, via Wikimedia Commons") and links to the file and its page. The images themselves stay on Commons. Each file also gets a `reuse` value, our quick reading of its licence:

| `reuse` | Licences | What it asks of you |
|---|---|---|
| `public-domain` | Public domain, CC0 | Nothing. Credit is still a kind thing to do |
| `attribution` | CC BY, MIT, BSD, zlib, Apache, "Copyrighted free use" | Show the credit line and a link to the licence |
| `share-alike` | CC BY-SA, GFDL, GPL family, CPL, Free Art License | The same, and a changed version (even a crop) keeps the same licence |
| `check` | Anything unusual, or a licence that needs credit while the page names no author | Read the file's page before using it |

Some older Commons pages never say who made the image. For those we checked the page by hand and wrote the name into `sources/commons/credits.json`, each with a note on where it comes from; entries that use it show `"author_from": "credits.json"`.

Two more things worth knowing. Many game logos are public domain because they are only text, but they are still trade marks (`"restrictions": ["trademarked"]`), so use them to name the game, not to suggest a partnership. And a file marked `{"missing": true}` was deleted from Commons; the game's Wikidata entry still points to it and can be tidied up. The `reuse` value is a quick guide, not legal advice: the licence on the file's own page is what counts.

## Spotted a mistake?

The best place to fix a game's facts is at the source: edit it on [Wikidata](https://www.wikidata.org), ideally with a reference. The fix reaches this repository on the next run and DropSlate the day after, and everyone else who uses Wikidata benefits too. If something looks wrong in how the data is matched here, please open an issue. Looking for something to fix? `reports/differences.csv` lists likely gaps every week; each row is a hint, so please check it against a real source before editing.

## Licence

- **Data** keeps the licence of the source it came from (see each `sources/<name>/LICENSE-DATA.md`). Wikidata-derived files are CC0; the Commons metadata file is CC BY-SA 4.0, and every image it describes keeps its own licence.
- **Scripts** in this repository are MIT-licensed.

DropSlate and FocalNull are not affiliated with any game publisher, platform holder or the sources listed above.

Made with a lot of love for video games by Vic · [focalnull.com](https://focalnull.com)
