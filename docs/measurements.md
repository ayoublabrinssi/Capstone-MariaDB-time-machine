# Measurements

What system versioning costs on this data, measured with `scripts/measure.sh` on 3 November 2026. Raw output in [results/measurements.txt](../results/measurements.txt).

Setup: MacBook Pro 2017, Intel Core i5-7267U, Colima VM with 2 CPUs and 4 GB, MariaDB 12.3.3 in Docker, `innodb_buffer_pool_size` 128 MB. Everything runs in a scratch database built from copies of `article`, so the main database is untouched. Times are from Python around each query, 3 runs after a warm-up run; the median is given with the fastest and slowest run.

## 1. Size

One row per version, text kept in its own table. Sizes from `information_schema.TABLES` after `ANALYZE TABLE`.

| Table | Rows | Data | Index | Per row |
|---|---|---|---|---|
| partitioned, 1x | 31,179 | 4.6 MB | 0 | 148 B |
| partitioned, 2x | 62,358 | 13.5 MB | 0 | 216 B |
| partitioned, 4x | 124,716 | 34.1 MB | 0 | 273 B |
| no partitions, 1x | 31,179 | 5.8 MB | 0 | 185 B |
| classic revision table, 1x | 31,179 | 8.9 MB | 1.6 MB | 337 B |

The versioned table is the smallest: the two hidden columns cost 16 bytes per row and the history needs no extra index, because the primary key already ends in `row_end`. The classic table carries its own `(page_id, edit_time)` index. The versioned table grows faster than linear here (2x the rows, 3x the bytes), which is page fill after the interleaved load, not a property of versioning; the same 148 B per row applies after an `OPTIMIZE`.

## 2. Speed

The 220 test moments, one `AS OF` each, on one article at a time:

| Table | Median for 220 queries | Fastest, slowest | Per query |
|---|---|---|---|
| partitioned | 681 ms | 493, 697 | 3.10 ms |
| no partitions | 408 ms | 395, 437 | 1.85 ms |
| classic (`ORDER BY edit_time DESC LIMIT 1`) | 372 ms | 318, 383 | 1.69 ms |
| partitioned, 4x the rows | 521 ms | 467, 542 | 2.37 ms |

Two things stand out.

- **Partitions make the single-article question slower, not faster.** A query on 1 June 2010 opens 18 of the 27 partitions and reads the same 1,385 rows it would read without partitions, plus the cost of opening each one. Partitions pay off for retention (below) and for recent dates on big tables, not for this access pattern at this size.
- **The classic table is faster for one article.** Its index is on `edit_time`, so `ORDER BY edit_time DESC LIMIT 1` reads 1 row. The versioned table reads every version that ended after the moment (1,845 for 1 June 2005). The difference is 1.4 ms here; on a table with millions of versions per page it would matter.

Four times the rows did not make one article's query slower (the per-page cost depends on that page's versions, not on the table), which is what the primary key promises.

All 45 articles at once, `COUNT(*)` and `SUM(bytes)` over `AS OF`:

| Date | 1x | 2x | 4x |
|---|---|---|---|
| 2005-06-01 | 21 ms | 40 ms | 75 ms |
| 2010-06-01 | 15 ms | 30 ms | 56 ms |
| 2026-06-01 | 2 ms | 3 ms | 6 ms |

Linear in the data, and ten times cheaper for a recent date than for an old one: pruning works for recent dates.

## 3. Rows read for one question

Rabat, from `ANALYZE FORMAT=JSON`:

| Table | Date | Rows read | Partitions opened | Time |
|---|---|---|---|---|
| partitioned | 2005-06-01 | 1,845 | 23 of 27 | 1.83 ms |
| partitioned | 2010-06-01 | 1,385 | 18 of 27 | 1.78 ms |
| partitioned | 2026-06-01 | 60 | 2 of 27 | 0.08 ms |
| no partitions | 2005-06-01 | 1,845 | | 1.30 ms |
| no partitions | 2010-06-01 | 1,385 | | 0.92 ms |
| no partitions | 2026-06-01 | 60 | | 0.12 ms |
| classic | any | 1 | | 0.02 ms |

The key is `(page_id, row_end)`. `AS OF T` keeps rows with `row_end > T`, then filters on `row_start`. For an old date that is almost every version. The session setting `system_versioning_asof` prunes the same partitions as `AS OF` in the query (the page checks this on every answer).

## 4. Retention

Forgetting every version that ended before 2010, on a 1x copy:

| Step | Versions | Data | Time |
|---|---|---|---|
| before | 31,179 | 4.6 MB | |
| `DELETE HISTORY ... BEFORE SYSTEM_TIME '2010-01-01'`, partitioned | 23,670 | 4.6 MB, nothing freed | 35 ms |
| then `OPTIMIZE TABLE` with `system_versioning_alter_history = KEEP` | 23,670 | 3.6 MB | 941 ms |
| `DELETE HISTORY`, no partitions | 23,670 | 5.8 MB, 4.2 MB marked free | 60 ms |
| then `OPTIMIZE TABLE` with `KEEP` | 23,670 | 3.7 MB | 195 ms |
| `ALTER TABLE ... DROP PARTITION p0 ... p8` | 23,670 | 3.6 MB | 23 ms |

- `DELETE HISTORY` removes the rows but gives nothing back until the table is rebuilt.
- `OPTIMIZE TABLE` on a versioned table fails unless `system_versioning_alter_history` is `KEEP`. The failure comes back as rows in the result ("Not allowed for system-versioned", then "Operation failed"), and the statement itself succeeds, so a script that checks the return code thinks it worked. The example in `sql/examples/retention.sql` shows both outputs.
- Dropping partitions is the cheap way: 23 ms, space back at once. Only the oldest partitions can be dropped (error 4116 otherwise), so the rule is "keep the last N years".

## What this changes in the project

- The README's "where it loses" now has numbers.
- For this access pattern (one article, one date) the table would be faster without partitions. They stay, because they are what makes retention cheap and because recent-date queries on all articles prune well.
- The findings about `OPTIMIZE` and `DROP PARTITION` go to MariaDB with the others (step 7).
