# Wikidata

- **What we take:** every item that is an instance of *video game* (Q7889) with at least one platform (P400) and one publication date (P577): its English label, its English Wikipedia article title, and the identifiers other sites use for it (Steam, GOG, Epic Games Store, IGDB, MobyGames, PCGamingWiki, HowLongToBeat, Metacritic).
- **Licence:** Wikidata's structured data is released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). No attribution is required, but we give it gladly: thank you to everyone who edits Wikidata.
- **Note:** identifiers are facts that point to other sites. Nothing from those sites is copied here.
- **Script:** `scripts/fetch_wikidata_ids.py` · **Output:** `matched/*.json`
