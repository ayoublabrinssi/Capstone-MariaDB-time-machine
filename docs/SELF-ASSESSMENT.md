# Weekly self-assessment

Capstone Project I. Main dish: system-versioned tables (area 3), a Wikipedia time machine.
Repo: https://github.com/ayoublabrinssi/Capstone-MariaDB-time-machine
Team: Ayoub Labrinssi (alone; Team IV did not answer, the supervisor was told on 26 Oct 2026)

Newest week first.

## Week of 9 to 15 November 2026

### Ayoub Labrinssi
- **Work done:** built the last part on MariaDB's answer from the meeting (system versioning records from the day it is switched on; importing the past is the exception). Measured three ways to make an old date cheaper: an index on `row_start`, the application-time table, and a query that reads the key in order and stops at the first row. The last one reads 1 row where `AS OF` reads 1,845, and is now on the page next to the `AS OF` answer. Tested the edges of system time (dates before 1970, overlapping versions on import, statement and transaction time, backups) in `sql/examples/limits.sql` and `scripts/backup_check.sh`. Wrote the import tutorial with a small reusable example, the notes for MariaDB, and the CI workflow. Then ran MariaDB's evaluation prompt on the result twice and fixed what it found: the exact text of every revision on the page, a read-only database user, a three-article sample for a fast first run, who can change history (`scripts/trust_check.sh`), what the text would cost inside the versioned row (`scripts/text_cost.sh`), how the table really grows (`scripts/growth.sh`), and wrong answers after an import without yearly partitions (`limits.sql`, step 9). 40 database checks and 62 Python tests. Wrote the findings up for people who are not experts: one page per finding in `docs/findings/`, with a small example, the server's answer, what works around it and the command to see it, plus a page with figures you can click through, and a "What we found" section in the README.
- **Hours:** TO FILL IN
- **Evidence:** `results/measurements.txt` and the two repeat runs, `results/limits.txt`, `results/import_history.txt`, `results/backup.txt`, `results/tests.txt`, `docs/import-tutorial.md`, `docs/findings/`, `docs/details.md`, `docs/contributions.md`.
- **Plan for next week:** file the findings with MariaDB (the list is in `docs/contributions.md`), prepare the final presentation of 3 December.
- **AI tools:** Claude (Anthropic): the measurements of section 4, the limits and import examples, the tutorial and notes, CI, tests, the findings pages, the shorter README, the UML diagrams, the icons, the plain diagrams in the README, the start menu. AI log entries 7 to 13.
- **Notes, blockers:**

## Week of 2 to 8 November 2026

### Ayoub Labrinssi
- **Work done:** added the measurements (size, speed, rows read, retention, against a plain table and a classic revision table), time travel for a whole session, the retention example and the edit-war list on the page. Presented the project to MariaDB on 5 November and asked why an old date is slow (the key is sorted by end time) and why keeping the real dates needs declared columns and a session switch.
- **Hours:** TO FILL IN
- **Evidence:** `docs/measurements.md`, `results/retention.txt`, `results/tests.txt` (20 database checks and 30 page tests at the end of that week), commit 9a44cd7.
- **Plan for next week:** act on MariaDB's answer: the cost of old dates and the import path.
- **AI tools:** Claude (Anthropic): measurement script, retention example, page additions, tests. AI log entry 6.
- **Notes, blockers:**

## Week of 26 October to 1 November 2026

### Ayoub Labrinssi
- **Work done:** chose area 3 and the theme (Moroccan cities). Created the repository with the Docker setup, the helper scripts, the article list, the fetch script and the first schema. Fetched the revision history of the articles (45 articles, 31,179 revisions). Built the schema (system-versioned `article` with yearly partitions, bitemporal `article_period`), the loader with the real edit dates, 10 queries, the Wikipedia correction and fleet examples, and 15 tests. Built the page: pick a city and a date, compare two dates side by side, searchable city list, calendar, logo, an under-the-hood panel (query time, partitions read, plan, row_start/row_end, cross-check), edits per year, the query shown under the article, pictures and tables in the text, a light/dark switch, a row of facts above the article and a step-by-step view of what MariaDB did (from ANALYZE); 28 page tests.
- **Hours:** 5
- **Evidence:** `results/tests.txt` (15 of 15 database checks and 28 page tests pass), `results/queries.txt`, `results/wikipedia_correction.txt`, `results/fleet.txt`, `design/screenshots/`.
- **Plan for next week:** measurements (issue #5): table sizes, AS OF timing with and without partitions, DELETE HISTORY, comparison with a classic revision table.
- **AI tools:** Claude (Anthropic): plan, repo skeleton, fetch script, schema, loader, queries, tests, page. AI log entries 1 to 4.
- **Notes, blockers:**
