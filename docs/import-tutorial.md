# Loading existing history into a system-versioned table

System versioning records changes from the day it is switched on. This page is for the other case: you already have the history (a change log, an audit table, a revision table) and want `FOR SYSTEM_TIME AS OF` to answer with the real dates. It is what this project does with 31,179 Wikipedia revisions. Tested on MariaDB 12.3.3.

A runnable version on six rows is in [sql/examples/import_history.sql](../sql/examples/import_history.sql), output in [results/import_history.txt](../results/import_history.txt).

## The five steps

**1. Name the system columns.** A table made with only `WITH SYSTEM VERSIONING` has `row_start` and `row_end` too, but hidden. The import works on those as well. Declaring them keeps the names and the type in plain sight:

```sql
CREATE TABLE price (
  product   VARCHAR(20)  NOT NULL PRIMARY KEY,
  price     DECIMAL(8,2) NOT NULL,
  row_start TIMESTAMP(6) AS ROW START INVISIBLE,
  row_end   TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)
) WITH SYSTEM VERSIONING
  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2019-01-01 00:00:00' AUTO PARTITIONS 9;
```

**2. Create the partitions before loading.** `AUTO` makes partitions as the server clock moves, so on its own it puts every imported row into one partition. That is worse than untidy: after the first live write `AUTO` adds the missing years, the imported rows stay behind, and `AS OF` stops finding them ([limits.sql](../sql/examples/limits.sql), step 9). `STARTS` before your oldest change and enough `PARTITIONS` to reach today spreads the history by year. `AUTO` keeps adding the years to come. Skip the `PARTITION BY` line if you do not need to drop old years later.

**3. Open the switch and write both columns.** Without it the server answers error 1906.

```sql
SET time_zone = '+00:00';                        -- say which zone your dates are in
SET @@system_versioning_insert_history = 1;      -- this session only

INSERT INTO price (product, price, row_start, row_end)
SELECT product, price, changed_at, next_change
FROM (SELECT product, price, changed_at,
             LEAD(changed_at) OVER (PARTITION BY product ORDER BY changed_at) AS next_change
      FROM price_log) AS steps
WHERE next_change IS NOT NULL;
```

A version ends at the moment the next change of the same key starts. `LEAD()` gives that moment.

**4. Load the current rows with `row_start` only.** The last change of each key is the live row. Leave `row_end` out and the server marks it as still live.

```sql
INSERT INTO price (product, price, row_start)
SELECT product, price, changed_at FROM ... WHERE next_change IS NULL;

SET @@system_versioning_insert_history = 0;
```

**5. Check the result yourself.** With the switch on, the server trusts you. It accepts two versions of one key that cover the same time, and `AS OF` then returns two rows for one primary key. This query must return 0:

```sql
SELECT COUNT(*) FROM (
  SELECT row_end, LEAD(row_start) OVER (PARTITION BY product ORDER BY row_end) AS next_start
  FROM price FOR SYSTEM_TIME ALL) AS v
WHERE next_start IS NOT NULL AND next_start <> row_end;
```

After that the table is an ordinary versioned table. A change made today is stamped by the server clock and joins the imported history. [sql/examples/live_edit.sql](../sql/examples/live_edit.sql) shows that on the Wikipedia table: one `UPDATE`, and the server closes the last imported row itself.

## What to know before you start

| Limit | What happens | What to do |
|---|---|---|
| History cannot start before 1970-01-01 00:00:01 UTC | error 1292, the columns are `TIMESTAMP` | keep older dates in an application-time period (`DATE` or `DATETIME` columns with `PERIOD FOR`) |
| Imported rows are not placed by `AUTO` | without a partition for their year they sit in the wrong one, and after the first live write `AS OF` returns nothing for them | `STARTS` and `PARTITIONS` before the load; `CHECK TABLE` finds misplaced rows, `REPAIR TABLE` moves them |
| Overlaps are not checked on import | both rows are stored, `AS OF` returns two | run the check in step 5; `WITHOUT OVERLAPS` exists only for application time |
| System time cannot be corrected later | a wrong date stays wrong | keep a second, application-time table for data you may fix ([wikipedia_correction.sql](../sql/examples/wikipedia_correction.sql)) |
| The key is `(your key, row_end)` | `AS OF` an old date reads every later version of that key | use the first-row query below for single-key lookups |
| `ALTER TABLE` that changes columns is refused after versioning is on (error 4119) | adding a plain index still works | settle the columns first, or set `system_versioning_alter_history = KEEP` |
| Tables versioned by transaction id (`BIGINT` columns) | no import (1906), no `SYSTEM_TIME` partitions (4110) | use `TIMESTAMP(6)` columns for imported history |
| A plain `mariadb-dump` holds the current rows only | the history is gone after a restore, with no warning | `mariadb-dump --dump-history` ([scripts/backup_check.sh](../scripts/backup_check.sh)) |
| Dates are read in the session time zone | the same literal can mean two moments | set `time_zone` before loading and before asking |
| Any user who can write to the table can write a past | `system_versioning_insert_history` and `SET @@timestamp` need no special right | after the import, restart the server with `secure_timestamp=YES`; keep `DELETE HISTORY` for one account ([scripts/trust_check.sh](../scripts/trust_check.sh)) |
| With `secure_timestamp=YES` nothing can be imported | error 1290, for root too | load first, switch the option on after |

Each row is shown running in [sql/examples/limits.sql](../sql/examples/limits.sql).

## The other way in: replay

If the old changes can be run again in order, there is a second route with no switch and no `row_start` in any statement. Set the session clock before each change and let the server write the history:

```sql
SET @@timestamp = UNIX_TIMESTAMP('2019-03-01 00:00:00'); INSERT INTO price VALUES ('tea', 10.00);
SET @@timestamp = UNIX_TIMESTAMP('2021-06-01 00:00:00'); UPDATE price SET price = 12.50 WHERE product = 'tea';
SET @@timestamp = DEFAULT;
```

The server closes each version where the next one starts, so there can be no overlap and no gap, and the columns do not have to be declared. The costs: one statement per change instead of one bulk load (this project loads 31,179 versions with two `LOAD DATA` statements), and the changes must come in time order for each key. One step back is accepted without an error and loses a version, shown in step 8 of [sql/examples/limits.sql](../sql/examples/limits.sql). Use the replay for a short log you trust to be in order, the switch for everything else.

## One key, an old date

`AS OF T` reads every version of the key that ended after `T` and keeps the one that had started. On a key with a long history and an old `T` that is almost all of them. Versions of one key never overlap (step 5 made sure), so the live one is the first that ended after `T`:

```sql
SELECT price
FROM (SELECT price, row_start FROM price FOR SYSTEM_TIME ALL
      WHERE product = 'tea' AND row_end > '2020-01-01 00:00:00'
      ORDER BY row_end LIMIT 1) AS v
WHERE v.row_start <= '2020-01-01 00:00:00';
```

It reads one row whatever the date. The outer `WHERE` returns nothing when the key did not exist yet. Measured on Rabat's 1,878 versions and on a synthetic key with a million versions in [measurements.md](measurements.md), section 4.
