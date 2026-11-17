# focalnull-data

Open video game data, gathered from free sources and matched together, one game at a time.

This is the data side of **[DropSlate](https://dropslate.focalnull.com)**, a free video game release calendar and catalogue: what came out when, on which platforms, what's coming next, and where a game's story began. DropSlate is part of **[FocalNull](https://focalnull.com)**, my small corner of the internet for games, photography and the things I love.

## Why this exists

I've played games for as long as I can remember, and I've always wanted one quiet place where I could look up a game and see its whole life: the first release, the ports, the remasters, the early-access years, the day it finally reached my console. No ads, no algorithms, no scores shouted at me. Just the history, told properly.

Most of that history already exists, written down by thousands of volunteers on Wikidata, Wikipedia and Wikimedia Commons, and by communities like ProtonDB and PCGamingWiki. It's scattered, though. This repository brings the free, openly licensed parts together and matches them to the same game, so every game ends up with one tidy record.

Keeping it public felt right. The data came from open communities, so the matched result should be open too.

## What's in here

| Folder | What it holds |
|---|---|
| `sources/<name>/` | One folder per source: a small script that fetches it, and a `LICENSE-DATA.md` with that source's licence and credit |
| `matched/` | One small JSON file per game, named after its Wikidata ID (for example `Q15727.json`), combining everything we're allowed to combine |
| `.github/workflows/` | The scheduled job that refreshes the data |

Every game is keyed by its **Wikidata ID**. Wikidata already links most games to their Steam, GOG, IGDB, MobyGames and PCGamingWiki pages, so that ID is what lets the sources line up.

## Sources and credits

| Source | What we use | Licence |
|---|---|---|
| [Wikidata](https://www.wikidata.org) | Games, release dates, platforms, release types (early access, betas…), developers, series, links to other sites | CC0 |
| [Wikipedia page views](https://wikimedia.org/api/rest_v1/) | How often a game's article is read, to fetch well-known games first | Public statistics |
| [Wikimedia Commons](https://commons.wikimedia.org) | Which freely licensed images exist for a game, with their author and licence (links only, no image files here) | Per file, as stated on each file |
| [ProtonDB](https://www.protondb.com) *(coming)* | Linux and Steam Deck compatibility | ODbL — the ProtonDB data stays under ODbL |
| [PCGamingWiki](https://www.pcgamingwiki.com) *(coming)* | PC details such as engine and controller support | CC BY-NC-SA — credit kept, non-commercial |

Nothing here is copied from store pages, press kits or sites that don't offer an open licence. Logos, box art and trademarks belong to their owners and are not stored in this repository.

## How it connects to DropSlate

1. The workflow in this repository fetches the open sources on a schedule and updates `matched/`.
2. Once a day, DropSlate reads `matched/` and adds new or changed games to its catalogue.
3. The app itself (calendar, game pages, design) lives elsewhere. This repository only holds the data and the small scripts that collect it.

## Spotted a mistake?

The best place to fix a game's facts is at the source: edit it on [Wikidata](https://www.wikidata.org), ideally with a reference. The fix reaches this repository on the next run and DropSlate the day after, and everyone else who uses Wikidata benefits too. If something looks wrong in how the data is matched here, please open an issue.

## Licence

- **Data** keeps the licence of the source it came from (see each `sources/<name>/LICENSE-DATA.md`). Wikidata-derived files are CC0.
- **Scripts** in this repository are MIT-licensed.

DropSlate and FocalNull are not affiliated with any game publisher, platform holder or the sources listed above.

Made with a lot of love for video games by Vic · [focalnull.com](https://focalnull.com)
