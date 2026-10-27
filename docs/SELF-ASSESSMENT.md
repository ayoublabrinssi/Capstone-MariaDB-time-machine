# Weekly self-assessment

Capstone Project I. Main dish: system-versioned tables (area 3), a Wikipedia time machine.
Repo: https://github.com/ayoublabrinssi/Capstone-MariaDB-time-machine
Team: Ayoub Labrinssi (alone; Team IV did not answer, the supervisor was told on 26 Oct 2026)

Newest week first.

## Week of 26 October to 1 November 2026

### Ayoub Labrinssi
- **Work done:** chose area 3 and the theme (Moroccan cities). Created the repository with the Docker setup, the helper scripts, the article list, the fetch script and the first schema. Fetched the revision history of the articles (45 articles, 31,179 revisions). Built the schema (system-versioned `article` with yearly partitions, bitemporal `article_period`), the loader with the real edit dates, 10 queries, the Wikipedia correction and fleet examples, and 15 tests. Built the page: pick a city and a date, compare two dates side by side, searchable city list, calendar, logo, an under-the-hood panel (query time, partitions read, plan, row_start/row_end, cross-check), edits per year, the query shown under the article, pictures and tables in the text, a light/dark switch, a row of facts above the article and a step-by-step view of what MariaDB did (from ANALYZE); 28 page tests.
- **Hours:** 5
- **Evidence:** `results/tests.txt` (15 of 15 database checks and 28 page tests pass), `results/queries.txt`, `results/wikipedia_correction.txt`, `results/fleet.txt`, `docs/screenshots/`.
- **Plan for next week:** measurements (issue #5): table sizes, AS OF timing with and without partitions, DELETE HISTORY, comparison with a classic revision table.
- **AI tools:** Claude (Anthropic): plan, repo skeleton, fetch script, schema, loader, queries, tests, page. AI log entries 1 to 4.
- **Notes, blockers:**
