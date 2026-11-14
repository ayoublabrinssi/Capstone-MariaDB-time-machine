# 4. `OPTIMIZE TABLE` fails but says it worked

**In one sentence.** After `DELETE HISTORY` the disk space only comes back when the table is rebuilt, and `OPTIMIZE TABLE` on a versioned table refuses to rebuild it, but reports the refusal as result rows while the statement itself succeeds.

[← All findings](README.md)

## The idea

History only grows, so a real system needs a rule to forget: "keep the last N years". MariaDB gives two tools for that, `DROP PARTITION` and `DELETE HISTORY`.

`DELETE HISTORY` removes the rows, but InnoDB keeps the empty space inside the table file until the table is rebuilt. It is like taking papers out of a binder: the binder stays the same thickness until you rebind it. The usual command to rebind is `OPTIMIZE TABLE`. On a versioned table it does not rebind, and it does not clearly say so either.

## See it happen

From [sql/examples/retention.sql](../../sql/examples/retention.sql), on a copy of the `article` table:

| Step | Versions | Size on disk |
|---|---|---|
| Start | 31,102 | 4,352 KB |
| `DELETE HISTORY ... BEFORE SYSTEM_TIME '2010-01-01'` | 23,670 | 4,352 KB |
| `OPTIMIZE TABLE` | 23,670 | 4,352 KB |
| `SET system_versioning_alter_history = KEEP`, then `OPTIMIZE TABLE` | 23,670 | 3,504 KB |

7,432 versions were deleted and the size did not move. Here is what `OPTIMIZE` answered the first time:

```
OPTIMIZE TABLE article_copy;
+--------------------------+----------+----------+------------------------------------------------------------------+
| Table                    | Op       | Msg_type | Msg_text                                                         |
+--------------------------+----------+----------+------------------------------------------------------------------+
| timemachine.article_copy | optimize | note     | Table does not support optimize, doing recreate + analyze instead |
| timemachine.article_copy | optimize | error    | Not allowed for system-versioned `timemachine`.`article_copy`.    |
|                          |          |          | Change @@system_versioning_alter_history to proceed with ALTER.  |
| timemachine.article_copy | optimize | status   | Operation failed                                                 |
+--------------------------+----------+----------+------------------------------------------------------------------+
3 rows in set
```

The word "error" is inside a result row. For the client, the statement worked: no error code, and the rest of the script runs on. With `system_versioning_alter_history = KEEP` the same command rebuilds the table and the space comes back.

## How we found it

While measuring retention ([measurements.md](../measurements.md), section 5). The size after `OPTIMIZE` did not change, and the script had not stopped. Only the printed result rows showed why.

## Why it matters

A cleanup job checks the exit code of each step. Here every step succeeds, so the job reports that it freed the space. It did not. The disk keeps filling while the logs say everything is fine.

## What works

- **Use partitions to forget.** `DROP PARTITION` removes a whole year in 14 ms and gives the space back at once. That is the retention rule of this project, and the main reason the table is partitioned by year.
- **If you use `DELETE HISTORY`,** run the rebuild with `SET system_versioning_alter_history = KEEP` in the same session, and check the size afterwards instead of the exit code.

## What we suggest to MariaDB

Raise a real error, as `ALTER TABLE` does on a versioned table (error 4119), so scripts notice. Or, at least, say in "Removing Old History" that freeing the space needs `OPTIMIZE` with `system_versioning_alter_history = KEEP`. The page does not mention `OPTIMIZE` today.

## Try it yourself

<details>
<summary>Run it</summary>

```sh
scripts/db.sh -t < sql/examples/retention.sql
```

It works on a copy, prints the size after each step, and drops the copy at the end. The full output is in [results/retention.txt](../../results/retention.txt).
</details>
