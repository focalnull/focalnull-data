# ProtonDB

- **What we take:** from ProtonDB's public monthly report export, the number of reports per Steam game and how many say the game works ("yes" verdict), overall and in the last 12 months, plus the date of the newest report — only for games we already have (matched by the Steam ID from Wikidata).
- **Source:** [bdefore/protondb-data](https://github.com/bdefore/protondb-data), exports by [ProtonDB](https://www.protondb.com).
- **Licence:** the ProtonDB reports data is made available under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/); individual contents under the [Database Contents License (DbCL) 1.0](https://opendatacommons.org/licenses/dbcl/1-0/). Our summary in this folder is a derived database and is shared under the **same ODbL licence**, with this credit.
- **Not included:** report text, user notes or any personal data. Our numbers are a simple count, not ProtonDB's own medal rating.
- **Script:** `scripts/fetch_protondb.py` · **Output:** `sources/protondb/summary.json`
