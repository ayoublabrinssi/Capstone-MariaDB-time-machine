# Measurements

What system versioning costs on this data, and what an old date costs in particular. Made with `scripts/measure.sh` on 13 November 2026.

**Setup.** MacBook Pro 2017, Intel Core i5-7267U, Colima VM with 2 CPUs and 4 GB, MariaDB 12.3.3 in Docker, `innodb_buffer_pool_size` 128 MB, so every table here fits in memory. Everything runs in a scratch database built from copies of `article`; the main database is not touched.

**Method.** Inside one run, the client timings (section 2, and the 220 moments and the synthetic key in section 4) are the median of 5 passes after a warm-up pass, taken from Python around the query. The server time in section 3 is one `ANALYZE` per run with no warm-up, the server times in section 4 are the median of 5, and each retention statement in section 5 is timed once per run, because it can only run once on a fresh copy. The whole script was then run three times in a row. A time below is the median of the three runs, with the lowest and highest run in brackets. Row counts come from `ANALYZE FORMAT=JSON` and are the same in every run. The raw output of the three runs is in [results/measurements.txt](../results/measurements.txt), [measurements-run2.txt](../results/measurements-run2.txt) and [measurements-run3.txt](../results/measurements-run3.txt).

**How far to trust the times.** This is a laptop, not a quiet server. A query takes about 1.4 ms just to travel from Python through Docker and back (the first-row query below reads one row and takes that long), so differences under half a millisecond between two designs are inside the noise: the brackets overlap. A first version of this page (3 November, one run of 3 passes) gave 3.10 ms for the partitioned table where the three runs here give 1.90. The row counts, the times inside the server, and the times on the large synthetic key are the numbers to lean on.

To repeat it: `scripts/measure.sh`, then `scripts/measure.sh --out results/measurements-run2.txt` for a second run.

## 1. Size

One row per version, text kept in its own table. Sizes from `information_schema.TABLES` after `ANALYZE TABLE`.

| Table | Rows | Data | Index | Per row |
|---|---|---|---|---|
| partitioned, 1x | 31,179 | 4.6 MB | 0 | 148 B |
| partitioned, 2x | 62,358 | 13.5 MB | 0 | 216 B |
| partitioned, 4x | 124,716 | 34.1 MB | 0 | 273 B |
| no partitions, 1x | 31,179 | 5.8 MB | 0 | 185 B |
| classic revision table, 1x | 31,179 | 8.9 MB | 1.6 MB | 337 B |

What these numbers say, and what they do not:

- **The index is the solid difference.** The versioned table needs no index besides its primary key, because that key already ends in `row_end`. The classic table carries its own `(page_id, edit_time)` index: 1.6 MB, 52 bytes per row.
- **Allocated bytes per row move: 148, 216, 273 for the same rows.** That is not the rows growing. It is looked into below.
- **The two hidden columns** are `TIMESTAMP(6)`, 7 bytes each: 14 bytes per version.
- **The text is not in these tables.** Section 6 measures what happens when it is.

### How the table grows

The table above reads `DATA_LENGTH`, what the table holds on disk. `scripts/growth.sh` looks under that number, output in [results/growth.txt](../results/growth.txt). For each table it reads the pages of the primary key that hold rows and the bytes of the rows in them, from `information_schema.INNODB_BUFFER_PAGE` with the whole table in memory, and it checks that it saw every version. These are counts of pages and bytes, the same on any machine, so one run is enough.

First the real history, written in the order a live table writes it: a version becomes a history row when it ends, so by `row_end`.

| Versions that had ended | Versions | Row bytes per version | Partitioned: pages in use, how full | No partitions: pages in use, how full |
|---|---|---|---|---|
| before 2006 | 1,133 | 87 B | 38, 16 % | 12, 50 % |
| before 2011 | 9,018 | 102 B | 136, 41 % | 80, 70 % |
| before 2016 | 16,415 | 105 B | 235, 45 % | 138, 76 % |
| before 2021 | 22,438 | 108 B | 318, 47 % | 188, 79 % |
| all, with the 45 current rows | 31,179 | 114 B | 449, 48 % | 269, 80 % |

Then the same two tables rebuilt, and the table the load makes:

| Table | Pages in use | How full | In use per version | Allocated |
|---|---|---|---|---|
| partitioned, written in time order | 449 | 48 % | 236 B | 7.4 MB |
| partitioned, rebuilt | 274 | 79 % | 144 B | 4.5 MB |
| no partitions, written in time order | 269 | 80 % | 141 B | 5.8 MB |
| no partitions, rebuilt | 236 | 92 % | 124 B | 4.7 MB |
| `article` as `scripts/install.sh` loads it | 448 | 48 % | 235 B | 7.3 MB |

And the three copies of the first table:

| Copy | Row bytes per version | In use per version | Allocated per version | Partitions past 32 pages |
|---|---|---|---|---|
| 1x | 114 B | 148 B | 148 B | 0 of 27 |
| 2x | 114 B | 168 B | 216 B | 4, allocated 33 or 97 pages, using 33 to 39 |
| 4x | 114 B | 172 B | 273 B | 21, allocated 97 pages each, using 42 to 79 |

- **A version costs about 114 bytes of row, in every table.** That number does not move with the design or the size. It moved over the years, from 87 to 114, because edit comments got longer. Growth is one row per edit: from the first point to the last the versions grow 27.5 times and the row bytes 36 times.
- **What is on disk is that row divided by how full the pages are**, and how full depends on how the rows arrived. Written in time order into yearly partitions, the pages end up 48 % full, so a version takes 236 bytes. Without partitions the same order leaves them 80 % full. A rebuild brings the partitioned table to 79 %: 7.4 MB becomes 4.5 MB with the same rows.
- **The table of this project is in the half-full state.** `article` holds 3.6 MB of rows in 7.3 MB. The page shows that size. It was left as it is: at this size the 3 MB do not matter, and a rebuild is one statement (`ALTER TABLE article FORCE` with `system_versioning_alter_history = KEEP`).
- **The 148, 216, 273 of the first table are steps, not growth.** Up to 32 pages a partition is given one page at a time, and allocated equals in use. Past 32 pages it is given 64 at once: every such partition at 4x holds 97 pages and uses 42 to 79 of them. With 27 partitions that is up to 1 MB of empty room each. It is a fixed cost of partitioning that stops mattering once a partition holds many megabytes.

## 2. Speed on the real data

The 220 test moments, one question each, on one article at a time:

| Table and query | Per query |
|---|---|
| partitioned, `AS OF` | 1.90 ms (1.79 to 3.37) |
| no partitions, `AS OF` | 1.61 ms (1.52 to 3.05) |
| classic revision table, `ORDER BY edit_time DESC LIMIT 1` | 1.48 ms (1.29 to 1.99) |
| partitioned with 4x the rows, `AS OF` | 1.97 ms (1.89 to 2.07) |

- **All three designs answer in about 2 ms or less at this size.** The medians put the partitioned table last and the classic table first, but the brackets overlap. The 220 moments are spread over all 45 articles; the longest history, Casablanca, has 4,039 versions, and reading a few thousand rows from memory costs about as much as the round trip.
- **Four times the rows does not slow one article down.** The cost depends on that article's versions, not on the table, which is what the primary key promises.

All 45 articles at once, `COUNT(*)` and `SUM(bytes)` over `AS OF`:

| Date | 1x | 2x | 4x |
|---|---|---|---|
| 2005-06-01 | 18 ms (18 to 23) | 36 ms (35 to 69) | 67 ms (66 to 155) |
| 2010-06-01 | 14 ms (14 to 28) | 27 ms (26 to 51) | 51 ms (51 to 93) |
| 2026-06-01 | 2 ms (2 to 4) | 3 ms (3 to 18) | 5 ms (5 to 13) |

Linear in the data, and about ten times cheaper for a recent date than for an old one. This difference is far outside the noise: pruning works for recent dates.

## 3. Rows read for one question

Rabat, from `ANALYZE FORMAT=JSON`. The time is the server's own, without the round trip.

| Table | Date | Rows read | Partitions opened | Time in the server |
|---|---|---|---|---|
| partitioned | 2005-06-01 | 1,845 | 23 of 27 | 1.97 ms (1.77 to 3.27) |
| partitioned | 2010-06-01 | 1,385 | 18 of 27 | 1.35 ms (1.35 to 2.76) |
| partitioned | 2026-06-01 | 60 | 2 of 27 | 0.08 ms (0.08 to 0.12) |
| no partitions | 2005-06-01 | 1,845 | | 1.35 ms (1.33 to 1.95) |
| no partitions | 2010-06-01 | 1,385 | | 1.44 ms (1.05 to 1.62) |
| no partitions | 2026-06-01 | 60 | | 0.06 ms (0.06 to 0.08) |
| classic | 2005-06-01 | 1 | | 0.02 ms (0.02 to 0.08) |
| classic | 2010-06-01 | 1 | | 0.02 ms (0.02 to 0.03) |
| classic | 2026-06-01 | 1 | | 0.03 ms (0.02 to 0.03) |

The key is `(page_id, row_end)`. `AS OF T` takes every row of the article with `row_end > T`, then keeps the one with `row_start <= T`. For an old date that is almost every version: 1,845 of Rabat's 1,878. Inside the server the old date costs about twenty times the recent one, and the classic table, with its index on the edit time, reads one row whatever the date. Partitions do not cut the rows for an old date: 23 of 27 are opened and the same 1,845 rows are read.

## 4. Old dates: three ways to read fewer rows

MariaDB's explanation, from the meeting on 5 November 2026: system versioning is designed to record from the day it is switched on, and a table that lives that way is asked about recent moments. A key sorted by end time is right for that. An imported history that is asked about 2005 is the opposite case. Three ways around it were tried.

| Way | What it is | Needs |
|---|---|---|
| Index on the start | `ALTER TABLE ... ADD KEY by_start (page_id, row_start)` | `system_versioning_alter_history = KEEP`, 1.6 MB of index on 5.8 MB of data |
| Application time | the same question to `article_period` (`valid_from <= T AND valid_to > T`) | the second table |
| First row only | read the key in order from `T` and stop at the first row | nothing: no index, no schema change |

The first-row query, with the reason it is correct:

```sql
SELECT rev_id, editor, bytes
FROM (SELECT rev_id, editor, bytes, row_start
      FROM article FOR SYSTEM_TIME ALL
      WHERE page_id = ? AND row_end > ?        -- T
      ORDER BY row_end LIMIT 1) AS v
WHERE v.row_start <= ?;                        -- T
```

Versions of one article never overlap, so the version live at `T` is the one with the smallest `row_end` after `T`. That is the first row of the key from `T` on. The outer `WHERE` drops it when the article did not exist yet. It gives the same revision as `AS OF` for all 220 test moments (`tests/tests.sql`, check 22).

Rows or index entries examined for Rabat, and the key the optimizer chose:

| Query | 2005-06-01 | 2010-06-01 | 2026-06-01 |
|---|---|---|---|
| `AS OF`, no partitions | 1,845 | 1,385 | 60 |
| `AS OF` + index on the start, no partitions | 34 (`by_start`) | 1,385 (`PRIMARY`) | 60 (`PRIMARY`) |
| `AS OF` + index on the start, partitioned | 14 (`by_start`) | 48 (`by_start`) | 60 (`PRIMARY`) |
| application-time table | 1,845 | 1,385 | 60 |
| first row only, no partitions | 1 | 1 | 1 |
| first row only, partitioned | 1 | 1 | 1 |

Time inside the server for the same questions, in ms (median of the three runs):

| Query | 2005-06-01 | 2010-06-01 | 2026-06-01 |
|---|---|---|---|
| `AS OF`, no partitions | 1.37 | 1.04 | 0.06 |
| `AS OF` + index on the start, no partitions | 0.03 | 1.00 | 0.06 |
| `AS OF` + index on the start, partitioned | 0.09 | 0.08 | 0.08 |
| application-time table | 1.09 | 0.81 | 0.05 |
| first row only, no partitions | 0.02 | 0.02 | 0.02 |
| first row only, partitioned | 0.08 | 0.07 | 0.04 |

The 220 moments again, from the client:

| Query | Per query |
|---|---|
| `AS OF` + index on the start, no partitions | 1.53 ms (1.51 to 2.24) |
| `AS OF` + index on the start, partitioned | 1.65 ms (1.60 to 2.31) |
| application-time table | 1.44 ms (1.43 to 2.16) |
| first row only, no partitions | 1.40 ms (1.30 to 1.79) |
| first row only, partitioned | 1.47 ms (1.43 to 1.99) |

On the real data every way lands between 1.4 and 1.7 ms from the client, because the round trip dominates. The row counts and the server times tell them apart. To see it from the client the key has to be longer, so the script builds one synthetic article with one version a minute and asks for the moment 10% into its history:

| Versions of the key | `AS OF`: rows read | `AS OF`: time | First row: rows read | First row: time |
|---|---|---|---|---|
| 10,000 | 9,001 | 7.18 ms (6.99 to 7.81) | 1 | 1.48 ms (1.43 to 1.59) |
| 100,000 | 90,001 | 60.97 ms (59.41 to 74.68) | 1 | 1.47 ms (1.21 to 1.74) |
| 1,000,000 | 1,110,000 (full scan) | 658 ms (648 to 734) | 1 | 1.62 ms (1.56 to 1.74) |

And the million-version key after adding the index on the start, at three moments:

| Moment | `AS OF`, optimizer's choice | `AS OF`, index forced | First row only |
|---|---|---|---|
| 10% into the history | 1,110,000 rows, full scan, 659 ms (654 to 773) | 100,000 entries, 33 ms (33 to 36) | 1 row, 1.51 ms (1.39 to 1.63) |
| 50% | 500,001 rows, `PRIMARY`, 329 ms (325 to 359) | 500,000 entries, 158 ms (158 to 183) | 1 row, 1.50 ms (1.42 to 1.59) |
| 90% | 100,001 rows, `PRIMARY`, 69 ms (66 to 114) | 900,000 entries, 287 ms (286 to 317) | 1 row, 1.48 ms (1.46 to 1.76) |

What follows from these numbers:

- **The application-time table does not help.** Its key ends in the period end too, so it reads the same rows as `AS OF`.
- **The index on the start helps old dates only.** It reads the versions that started before `T`, the primary key reads those that ended after `T`. Each is good at one end of the history and both are worst in the middle, where half of the versions qualify either way.
- **The optimizer does not always pick it.** For the million-version key at 10% it scans the whole table, about twenty times slower than the same query with the index forced. The plan estimate does not seem to count the rows that index condition pushdown removes.
- **The first-row query reads one row for any date and any size**, with no index and no schema change. Its time is the round trip. It is only correct while versions do not overlap, which the server guarantees for history it wrote itself and not for imported history, so `tests/tests.sql` checks it for the loaded data (check 21).

## 5. Retention

Forgetting every version that ended before 2010, on a 1x copy:

| Step | Versions | Data | Time |
|---|---|---|---|
| before | 31,179 | 4.6 MB | |
| `DELETE HISTORY ... BEFORE SYSTEM_TIME '2010-01-01'`, partitioned | 23,670 | 4.6 MB, nothing freed | 30 ms (29 to 124) |
| then `OPTIMIZE TABLE` with `system_versioning_alter_history = KEEP` | 23,670 | 3.6 MB | 366 ms (353 to 1,157) |
| `DELETE HISTORY`, no partitions | 23,670 | 5.8 MB, nothing freed | 51 ms (48 to 121) |
| then `OPTIMIZE TABLE` with `KEEP` | 23,670 | 3.7 MB | 107 ms (90 to 131) |
| `ALTER TABLE ... DROP PARTITION p0 ... p8` | 23,670 | 3.6 MB | 14 ms (14 to 31) |

- `DELETE HISTORY` removes the rows but gives nothing back until the table is rebuilt: the data size is the same before and after. The raw output also prints InnoDB's `DATA_FREE` (4.2 MB for the table without partitions). That figure is the same for scratch tables nothing was deleted from, so it says nothing about the delete and is not used here.
- `OPTIMIZE TABLE` on a versioned table fails unless `system_versioning_alter_history` is `KEEP`. The failure comes back as rows in the result ("Not allowed for system-versioned", then "Operation failed"), and the statement itself succeeds, so a script that checks the return code thinks it worked. `sql/examples/retention.sql` shows both outputs.
- Dropping partitions is the cheap way: the rows and the space go in one step, and it takes half the time of `DELETE HISTORY` before any rebuild. Only the oldest partitions can be dropped (error 4116 otherwise), so the rule is "keep the last N years".

## 6. Text inside the versioned row

The schema keeps the article text out of the versioned table. `scripts/text_cost.sh` builds the other design for Rabat (1,878 versions) in a scratch database and compares, output in [results/text_cost.txt](../results/text_cost.txt). The sizes, rows and pages are the same in every run and on every machine.

| Design | Size on disk |
|---|---|
| pointer: version rows, texts in their own table | 0.3 MB of rows + 4.7 MB for 94 stored texts = 5.0 MB |
| inline: a full text in each version row | 80.2 MB |

Rabat at one moment, text included, as rows read and disk pages touched:

| Design and query | 2005-06-01 | 2010-06-01 | 2026-06-01 |
|---|---|---|---|
| pointer, `AS OF` | 1,846 rows, 31 pages | 1,386 rows, 30 pages | 61 rows, 14 pages |
| inline, `AS OF` | 1,845 rows, 4,870 pages | 1,385 rows, 4,425 pages | 60 rows, 367 pages |
| inline, first-row query | 1 row, 26 pages | 1 row, 28 pages | 1 row, 14 pages |

The times are left out of the table because they moved too much between runs on the laptop. Each run takes the median of 5 inside the server. Over five runs on 13 November, `AS OF` 2005 on the inline table took 9 to 55 ms. In the four of them where all three lines were written down, the pointer design took 1.2 to 4.6 ms, the first-row query on the inline table 0.25 to 0.52 ms, and inline `AS OF` was 8 to 16 times slower than pointer. The result file holds the last run.

- **The inline table is sixteen times larger for one article.** For all 45 the texts of every revision add up to 1.21 GB by the sizes Wikipedia reports, against 65 MB for the quarterly texts the load stores.
- **An old date gets much more expensive.** `AS OF` reads the same 1,845 rows in both designs, but with the text in the row it reads the text of each of them: thousands of disk pages where the pointer design reads a few dozen. The old-date problem of section 4 is multiplied by the size of the row.
- **The first-row query takes the cost away again**, because it reads one row. With a large value in the versioned row it stops being an optimisation and becomes the only reasonable way to ask.
- **What the inline table stands in for.** Each inline row holds the stored quarterly copy that version points at, not the exact text of that revision. The size is about the same, so the result holds, but it is a stand-in and the script says so.

## What this changed in the project

- The page shows the first-row query next to every `AS OF` answer, with the rows each one read ("A shorter way" in the panel), and query 13 of `sql/queries.sql` does the same in SQL.
- The partitions stay. They do not speed up one article, and the measurements say so. They are what makes retention one cheap statement, and they prune well for recent dates over all articles.
- The index on the start was not added: it costs a quarter of the table in space and only moves the weak spot to the middle of the history.
- The size of the versioned table is now given as row bytes per version (114) and how full the pages are, not as one number from `information_schema`.
- The text stays out of the versioned row. The load stores one text per quarter, and the page fetches the exact text of a revision when it is first opened.
- The optimizer observations and the first-row plan are written up for MariaDB in [findings/03](findings/03-old-dates-read-the-whole-history.md).
