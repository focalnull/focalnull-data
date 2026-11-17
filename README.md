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
| `sources/<name>/` | One folder per extra source: a `LICENSE-DATA.md` saying what we take, its licence and its credit, plus that source's data file (for example `sources/protondb/summary.json`) |
| `scripts/` | The small scripts that fetch each source (Python, no extra packages) |
| `tests/` | Checks that run on every change |
| `.github/workflows/` | The jobs that refresh the data |

Every game is keyed by its **Wikidata ID**. Wikidata already links most games to their Steam, GOG, Epic, IGDB, MobyGames, PCGamingWiki, HowLongToBeat and Metacritic pages, so that ID is what lets every source line up with the same game.

## Sources and credits

| Source | What we use | Licence | Status |
|---|---|---|---|
| [Wikidata](https://www.wikidata.org) | Every video game with a platform and a release date (about 135,000), its English name, its English Wikipedia article and the IDs other sites use for it | CC0 | Live |
| [ProtonDB](https://www.protondb.com) | How many players report that a Steam game works on Linux and Steam Deck, overall and in the last 12 months (counts only, joined by Steam ID) | ODbL — this data stays under ODbL | Live |
| [PCGamingWiki](https://www.pcgamingwiki.com) | A link to each game's PCGamingWiki page (the page name comes from Wikidata). Their data API is not open to anonymous use, so no PCGamingWiki content is copied here | — (links only) | Live |
| [Wikipedia page views](https://www.mediawiki.org/wiki/Extension:PageViewInfo) | How often each game's English Wikipedia article was read in the last 60 days, so well-known games are added first (`sources/wikipedia-pageviews/pageviews.json`) | CC0 | Live |
| [Wikimedia Commons](https://commons.wikimedia.org) | Which freely licensed images exist for a game, with their author and licence (links only, no image files here) | Per file, as stated on each file | Coming |

Nothing here is copied from store pages, press kits or sites that don't offer an open licence. Other sites' IDs are just facts that point to their pages. Logos, box art and trademarks belong to their owners and are not stored in this repository.

## How it works

1. **Find the games.** *Refresh game IDs* asks Wikidata for every video game with a platform and a release date and writes `matched/`. One request at a time, with a short pause between them, so we stay a polite guest.
2. **Add the other sources.** Each source has its own job (for example *Refresh ProtonDB summary*, about once a month) that joins its data to our games by ID and keeps its own licence and credit.
3. **Compare** *(coming)*. Where sources disagree, for example on a release year, the difference goes into a report. The fix is then made at the source, usually on Wikidata, with a proper reference, so every project that uses it benefits.
4. **Feed DropSlate.** Once a day, [DropSlate](https://dropslate.focalnull.com) reads these files and adds new or changed games to its calendar and catalogue, well-known games first. The app itself (calendar, game pages, design) lives elsewhere; this repository only holds open data and the small scripts that collect it.

For now the jobs are started by hand while we check the results. They will run on a schedule once DropSlate's daily import is in place.

## Spotted a mistake?

The best place to fix a game's facts is at the source: edit it on [Wikidata](https://www.wikidata.org), ideally with a reference. The fix reaches this repository on the next run and DropSlate the day after, and everyone else who uses Wikidata benefits too. If something looks wrong in how the data is matched here, please open an issue.

## Licence

- **Data** keeps the licence of the source it came from (see each `sources/<name>/LICENSE-DATA.md`). Wikidata-derived files are CC0.
- **Scripts** in this repository are MIT-licensed.

DropSlate and FocalNull are not affiliated with any game publisher, platform holder or the sources listed above.

Made with a lot of love for video games by Vic · [focalnull.com](https://focalnull.com)
