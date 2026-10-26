A project for area 3, "System-versioned tables: history for free" for the [MariaDB student database projects, 2026-09](https://mariadb.org/bachelor_hackathon_2026-09/).

# Wikipedia time machine on MariaDB

Pick a Moroccan city and a date, and see its Wikipedia article as it stood that day. The history is kept by one table with `WITH SYSTEM VERSIONING`, not by a revision table, triggers or application code.

> **Status:** week 1 of 6. Repository set up, article list and fetch script ready. Schema, loader, page and measurements follow week by week. Developed against MariaDB 12.3.3.

## Why

Wikipedia runs on MariaDB and keeps its history in an application-level `revision` table, designed years before system versioning existed. This project loads real revisions of 45 Moroccan city articles into a system-versioned table and answers "what did the article say on that date?" with one clause: `FOR SYSTEM_TIME AS OF`.

## Quick start

Requirements: Docker with Compose (tested with Colima on an Intel Mac), Python 3.

```sh
cp .env.example .env            # set a root password
docker compose up --wait        # MariaDB 12.3.3, database timemachine
scripts/fetch.sh --every year --limit 3   # a small sample from the Wikipedia API
scripts/install.sh              # schema (loader comes in week 2)
scripts/db.sh                   # SQL prompt
```

The full set is `scripts/fetch.sh` with no options: one revision text per quarter for every article in [data/articles.txt](data/articles.txt), plus the metadata of every revision. The files land in `data/raw/` (git-ignored, see [Data](#data)).

## How time is modelled

System versioning stamps a row with the moment the `INSERT` ran. A naive import therefore records the history of the loading script, not of the article. This project gives every row two clocks:

| Period | Columns | Meaning | Who sets it |
|---|---|---|---|
| application time | `valid_from`, `valid_to` | when this text was the live article on Wikipedia | the loader, from the revision timestamps |
| system time | `row_start`, `row_end` | when our database inserted or replaced the row | MariaDB |

The first clock answers "what did Wikipedia say in 2015?". The second answers "what did our database believe last week, before we corrected it?". Both are SQL:2011 and both are built into MariaDB. The reasoning, the alternatives and where this design stops being the right one are written up in week 2.

## Data

- [data/articles.txt](data/articles.txt): the 45 titles, one per line.
- `scripts/fetch.sh` downloads them from the MediaWiki API with [fetch/fetch.py](fetch/fetch.py) (standard library only). For each article it stores the metadata of every revision and the wikitext of the first revision of each quarter plus the latest one.
- `data/raw/manifest.json` lists what was fetched, with revision counts and dates.

The raw files are not committed (hundreds of MB). The fetch is repeatable and skips articles already on disk.

## Project structure

```
compose.yaml        MariaDB 12.3.3 in Docker, password from .env
scripts/            fetch.sh, install.sh, test.sh, db.sh
fetch/fetch.py      Wikipedia API download
sql/                schema, queries, examples
data/               articles.txt, raw/ (git-ignored)
app/                the time machine page (week 3)
docs/               AI-log.md, SELF-ASSESSMENT.md, measurements (week 4)
```

## Team

Ayoub Labrinssi, Constructor University Bremen, MSc Computer Science and Software Engineering. Supervisor: Dr. Joaquin Aguado. Partner: MariaDB Foundation.

AI use is recorded in [docs/AI-log.md](docs/AI-log.md).

## License

MIT, see [LICENSE](LICENSE). Wikipedia text is CC BY-SA 4.0 and belongs to its authors.
