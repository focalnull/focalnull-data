# Wikipedia page views

- **What we take:** for every game in `matched/` with an English Wikipedia article, the total number of times that article was read in the last 60 days (one number per game). Redirects are followed, so a renamed article keeps its count.
- **Why:** DropSlate adds well-known games first, and how often an article is read is a fair, open measure of that.
- **Licence:** Wikimedia's analytics data (page views included) is released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). Thank you to the Wikimedia Foundation for publishing it.
- **Note:** no article text is copied, only the counts.
- **Script:** `scripts/fetch_pageviews.py` · **Output:** `sources/wikipedia-pageviews/pageviews.json` (`{"as_of", "days", "games": {Wikidata ID: views}}`)
