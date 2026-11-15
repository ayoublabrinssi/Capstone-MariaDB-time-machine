# 1. A past date stops answering after an import

**In one sentence.** If a table uses `AUTO` partitions and you import history before the yearly partitions exist, all of it lands in the first partition, and after the first live `UPDATE` an `AS OF` on a past date returns nothing, with no error.

[← All findings](README.md)

## The idea

Think of a filing cabinet with one drawer per year. Each old record goes in the drawer of the year it ended.

You bring in a box of old records, but the cabinet only has its first drawer, so every record goes in there. Later the cabinet notices it is missing drawers and adds them, one per year, by itself. The old records stay where they are.

Now you ask "what was true in 2018?" The cabinet thinks: anything true in 2018 ended in 2018 or later, so it opens the 2018 drawer and the ones after it. It never opens the first drawer. The record you want is in there, so you get nothing back.

That is what MariaDB does. `AUTO` adds a partition when the server's clock needs one. It does not look at the dates of imported rows. And `AS OF` skips partitions that, going by their name, cannot hold the answer.

## See it happen

The example is step 9 of [sql/examples/limits.sql](../../sql/examples/limits.sql): the price of tea, with a table partitioned by year from 2005 with `AUTO`.

```sql
CREATE TABLE limit_auto (item VARCHAR(10) PRIMARY KEY, mad DECIMAL(6,2))
  WITH SYSTEM VERSIONING
  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2005-01-01 00:00:00' AUTO;
```

**Step 1. Import four versions with their real dates.**

| Price | From | Until |
|---|---|---|
| 10.00 | March 2005 | July 2009 |
| 12.50 | July 2009 | February 2016 |
| 14.00 | February 2016 | October 2023 |
| 15.00 | October 2023 | still current |

The table has two partitions: `p0` for history and one for the current row. All three old versions go into `p0`. Asking for 1 January 2018 gives **14.00**. Correct.

**Step 2. One ordinary `UPDATE` today** (price 16.00). Now the server needs a history partition for this year, so `AUTO` adds one for every year from 2006 to today. The three imported versions stay in `p0`.

| Partition | p0 | 2006 … 2017 | 2018 … 2025 | 2026 | current |
|---|---|---|---|---|---|
| Holds | 10.00, 12.50, 14.00 | nothing | nothing | 15.00 | 16.00 |
| Opened by `AS OF` 2018 | **no** | no | yes | yes | yes |

Asking for 1 January 2018 now gives **NULL**. The row with 14.00 is still stored (`FOR SYSTEM_TIME ALL` shows it), but it sits in a partition the query skips.

**Step 3. `CHECK TABLE` and `REPAIR TABLE`.**

```
CHECK TABLE limit_auto;
error    Found a misplaced row
error    Partition p0 returned error

REPAIR TABLE limit_auto;
warning  Moved 3 misplaced rows
status   OK
```

After the repair each version is in the partition of the year it ended, and 2018 gives 14.00 again. `ALTER TABLE ... REBUILD PARTITION p0` does not help: it failed with error 1863 when I tried it by hand (that statement is not in the script).

## How we found it

The first test of the feature, in October, already showed half of it: with `AUTO` and no partition count, all imported history went into one partition. The schema was changed to make every year up front, and the project moved on. In the last round I went back to ask the next question: what happens to a table loaded the first way once it is used normally, with one live write? That is when old dates came back empty.

## Why it matters

The answer changes from right to empty at the first normal write after the import, and nothing tells you. A test run right after the import passes. The bug shows up later, in production, on old dates only.

## What works

- **Make the partitions before the load.** The schema of this project uses `STARTS '2001-01-01' ... AUTO PARTITIONS 27`, so a partition exists for every year of the data before the first row arrives ([sql/01_schema.sql](../../sql/01_schema.sql)). If the load runs after 2026, the schema adds the missing years first.
- **Check it.** Check 40 in [tests/tests.sql](../../tests/tests.sql) makes sure the partitions reach past the newest history row, and `CHECK TABLE article` reports OK on the loaded table.
- **If it already happened,** `REPAIR TABLE` moves the rows to the right partitions.

## What we suggest to MariaDB

Either put an imported row in the partition its `row_end` belongs to, creating it if needed, or refuse the row when no partition covers it. In both cases one sentence in the documentation under "Automatically Creating Partitions" would help: when you import history, create the past partitions first with `STARTS` and `PARTITIONS`.

## Try it yourself

<details>
<summary>Run it (about a second, on the database the quick start makes)</summary>

```sh
scripts/db.sh -t < sql/examples/limits.sql
```

Step 9 is at the end. The full output is in [results/limits.txt](../../results/limits.txt). Check 39 in [tests/tests.sql](../../tests/tests.sql) pins the same behaviour, so the tests will tell you if a future MariaDB version changes it.
</details>
