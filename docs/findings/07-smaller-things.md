# 7. Smaller things worth knowing

Five things that did not lose data here, but each cost time to understand. Each one is shown in a file of this repository.

[← All findings](README.md)

## History cannot start before 1970

`row_start` is a `TIMESTAMP`, so system time cannot go back further than 1970-01-01 00:00:01 UTC.

| Tried (import) | The server says |
|---|---|
| a version from 1969 | error 1292: Incorrect datetime value |
| a version from 1970-01-01 00:00:00 | error 1292 |
| a version from 1970-01-01 00:00:01 | accepted |

The error does not say why. This data starts in 2001, so it was not a problem here. A land register or a list of kings needs application time instead, which takes `DATE` and `DATETIME`.

**Suggestion:** a line under Limitations in the documentation. Shown in step 1 of [sql/examples/limits.sql](../../sql/examples/limits.sql).

## The `WITHOUT OVERLAPS` error is hard to read

In the fleet example, Sara is booked on truck TRK-12 from 20 to 25 March while someone else already has it. The server refuses, which is right, but the message reads:

```
ERROR 1062: Duplicate entry 'TRK-12-2026-03-25-2026-03-20' for key 'vehicle'
```

It prints the end of the period before its start, and calls an overlap a "duplicate". A user who reads it looks for a second identical booking that does not exist.

**Suggestion:** print the start first, or say "overlaps the period ... to ...". Shown in [sql/examples/fleet.sql](../../sql/examples/fleet.sql), output in [results/fleet.txt](../../results/fleet.txt).

## A plain backup leaves the history out

| Backup command | Versions after restoring |
|---|---|
| `mariadb-dump` | 45 of 31,179 |
| `mariadb-dump --dump-history` | 31,179 of 31,179, identical |

Without the option, the dump keeps only the current rows, with no warning. This one is in the documentation, but it is easy to miss when the backup job already exists. Checked by [scripts/backup_check.sh](../../scripts/backup_check.sh), output in [results/backup.txt](../../results/backup.txt).

## Each statement in a transaction gets its own time

Inside a transaction, each statement stamps its rows with its own time, not the time of `BEGIN` or `COMMIT`. A transaction with two updates leaves two history rows, and `AS OF` a moment between them returns a value that was never committed on its own. Tables versioned by transaction id avoid this, but they cannot be partitioned by `SYSTEM_TIME` and cannot take imported history at all. Shown in step 3 of [sql/examples/limits.sql](../../sql/examples/limits.sql).

## An `AS OF` date is read in the session time zone

`AS OF TIMESTAMP '2005-06-01 00:00:00'` means a different moment in a session set to UTC and in one set to +01:00. Every script and the page of this project set the session to UTC first. Shown in step 6 of [sql/examples/limits.sql](../../sql/examples/limits.sql).
