# 3. An old date reads almost the whole history

**In one sentence.** For one article, `AS OF` reads every version that ended after the date you ask for, so an old date reads almost the whole history; since versions never overlap, the first of those rows is already the answer, and a query that stops there reads one row instead of 1,845.

[← All findings](README.md)

## The idea

Every time an article changes, MariaDB keeps the old version as a line: "this text, from this date, until this date". It stores the lines of one article **sorted by the "until" date**. That is because the primary key of a versioned table is `(page_id, row_end)`.

When you ask "what did the article say on 1 June 2005?", the right line is the one where *from ≤ date < until*.

Picture a shelf of boxes sorted by the day each box was closed. You want the box that was open on 1 June 2005. You walk to the first box closed after that day: that is your box. MariaDB walks there too. But it is not sure no other box also matches, so it opens every box after that one, to the end of the shelf. It finds nothing more.

## See it happen

A small article with 10 versions, sorted the way MariaDB stores them:

| Version | From | Until | `AS OF` 1 June 2018 | First-row query |
|---|---|---|---|---|
| 1 | Jan 2016 | Mar 2017 | jumped over | jumped over |
| 2 | Mar 2017 | Jun 2018 | jumped over | jumped over |
| 3 | Jun 2018 | Feb 2019 | **read: the answer** | **read: the answer, stop** |
| 4 | Feb 2019 | May 2020 | read, thrown away | |
| 5 | May 2020 | Jan 2021 | read, thrown away | |
| 6 | Jan 2021 | Apr 2022 | read, thrown away | |
| 7 | Apr 2022 | Jul 2023 | read, thrown away | |
| 8 | Jul 2023 | Sep 2024 | read, thrown away | |
| 9 | Sep 2024 | Oct 2025 | read, thrown away | |
| 10 | Oct 2025 | now | read, thrown away | |
| | | | **8 rows read** | **1 row read** |

The sort order lets MariaDB **jump** over versions 1 and 2. That part is fast. The problem is what comes after: `AS OF` also has to check "from ≤ date", and it does not know the versions never overlap. So it reads to the end.

The older the date, the more it reads. On the real article for Rabat, 1,878 versions:

| Rabat, as of | Rows `AS OF` reads | Rows the first-row query reads |
|---|---|---|
| 1 June 2005 | 1,845 | 1 |
| 1 June 2010 | 1,385 | 1 |
| 1 June 2026 | 60 | 1 |

## Why one row is enough

In a versioned table each version ends exactly when the next one starts. So the first line that ends after your date is always the answer, as long as the article already existed then. This query asks for exactly that:

```sql
-- AS OF: reads every version that ended after the date
SELECT rev_id FROM article
  FOR SYSTEM_TIME AS OF TIMESTAMP '2005-06-01 00:00:00'
  WHERE page_id = 57400;                                  -- Rabat

-- first-row query: reads one version
SELECT rev_id
FROM (SELECT rev_id, row_start FROM article FOR SYSTEM_TIME ALL
      WHERE page_id = 57400 AND row_end > '2005-06-01 00:00:00'
      ORDER BY row_end LIMIT 1) AS v
WHERE v.row_start <= '2005-06-01 00:00:00';               -- did the article exist yet?
```

Both return the same revision for all 220 test moments (check 22 in [tests/tests.sql](../../tests/tests.sql)).

## How we found it

The page of this project shows, next to every answer, how many rows MariaDB read to find it (`ANALYZE FORMAT=JSON`). Old dates read far more than recent ones. I asked MariaDB why at the meeting on 5 November 2026. Their answer: system versioning is designed to record from today forward, so it is tuned for recent dates. The project then measured three ways around it, and the first-row query won. The [README](../../README.md#the-old-date-problem) has the full comparison.

## Why it matters

On 45 articles it costs a few milliseconds. On a long history it is the difference between usable and not:

| Versions of one key | `AS OF`, 10% into the history | First-row query |
|---|---|---|
| 10,000 | 9,001 rows, 7 ms | 1 row, 1.5 ms |
| 100,000 | 90,001 rows, 61 ms | 1 row, 1.5 ms |
| 1,000,000 | full scan, 658 ms | 1 row, 1.6 ms |

A second index on `row_start` does not save it. For the million-version key the optimizer ignored that index and scanned the table, about twenty times slower than with the index forced. Numbers in [measurements.md](../measurements.md), section 4.

## What works

- **Use the first-row query** when you ask about one key at one moment. No index, no schema change. The page uses it ("A shorter way" in the side panel), and so does query 13 in [sql/queries.sql](../../sql/queries.sql).
- **Make sure versions never overlap**, because the shortcut is only right then. Check 21 tests it for every article, since the server does not check imported history ([finding 6](06-imported-versions-can-overlap.md)).

## What we suggest to MariaDB

The optimizer is the part of MariaDB that decides how to read the data. When a query gives the whole primary key (one article) and asks `AS OF` one moment, it could stop at the first row, as the query above does. Then every date would cost one row. The catch is that it is only safe when versions cannot overlap, and imported history can ([finding 6](06-imported-versions-can-overlap.md), [finding 2](02-clock-set-back-loses-a-version.md)).

A second, smaller point: with the extra index on `row_start`, the optimizer's cost estimate does not seem to count what index condition pushdown removes, which is why it picks the full scan.

## Try it yourself

<details>
<summary>See it on the page</summary>

Start the page (`scripts/start.sh --data sample`), pick Rabat and a date in 2005, and open "A shorter way" in the side panel. It shows the rows each query read.
</details>

<details>
<summary>See it in SQL</summary>

```sh
scripts/db.sh -t < sql/queries.sql
```

Query 13 runs both ways with `ANALYZE` on Rabat and on Casablanca (Casablanca needs the full data, not the sample). The output is in [results/queries.txt](../../results/queries.txt). The large synthetic keys are measured by `scripts/measure.sh` (several minutes).
</details>
