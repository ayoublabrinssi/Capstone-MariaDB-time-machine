# What this project gives back to MariaDB

What goes back to MariaDB, and where. Each finding is explained in plain words, with a small example and the command that reproduces it, in [findings/](findings/README.md). This page is the list for filing. "Docs" means the [System-Versioned Tables](https://mariadb.com/docs/server/reference/sql-structure/temporal-tables/system-versioned-tables) page, read on 13 November 2026.

Status: written up, not filed yet. The questions behind the import tutorial and finding 3 were asked at the meeting with MariaDB on 5 November 2026 (see "What MariaDB said" in the README).

| What | Goes to | Explained in | Reproduce with |
|---|---|---|---|
| A page on loading existing history | documentation (Knowledge Base) | [import-tutorial.md](import-tutorial.md) | [sql/examples/import_history.sql](../sql/examples/import_history.sql) |
| `AUTO` makes no partitions for imported history, and `AS OF` then loses answers after the first live write | bug report (JIRA), or a docs note under "Automatically Creating Partitions" | [finding 1](findings/01-auto-partitions-lose-imported-history.md) | [sql/examples/limits.sql](../sql/examples/limits.sql), step 9 |
| One step back with the session clock loses a version, with no error | bug report (JIRA), or a docs note next to `SET @@timestamp` | [finding 2](findings/02-clock-set-back-loses-a-version.md) | [sql/examples/limits.sql](../sql/examples/limits.sql), step 8 |
| `AS OF` on a full primary key could stop at the first row | optimizer request (JIRA) | [finding 3](findings/03-old-dates-read-the-whole-history.md) | `scripts/measure.sh`, section 4 |
| `OPTIMIZE TABLE` on a versioned table fails in the result rows but the statement succeeds | bug report (JIRA), or a docs note under "Removing Old History" | [finding 4](findings/04-optimize-says-it-worked.md) | [sql/examples/retention.sql](../sql/examples/retention.sql) |
| Who may write a past, and how to lock it after an import | documentation: a "Securing history" section | [finding 5](findings/05-anyone-can-write-the-past.md) | [scripts/trust_check.sh](../scripts/trust_check.sh) |
| Imported versions are not checked for overlaps | documentation, maybe an optional check | [finding 6](findings/06-imported-versions-can-overlap.md) | [sql/examples/limits.sql](../sql/examples/limits.sql), step 2 |
| The `WITHOUT OVERLAPS` error prints the period end before its start | bug report (JIRA) | [finding 7](findings/07-smaller-things.md) | [sql/examples/fleet.sql](../sql/examples/fleet.sql) |
| System time cannot hold a date before 1970, and the error does not say why | documentation, under Limitations | [finding 7](findings/07-smaller-things.md) | [sql/examples/limits.sql](../sql/examples/limits.sql), step 1 |

## Already in the docs, confirmed here

Not contributions, but tested so the README can say them with confidence: an `UPDATE` that changes nothing still makes a version, `TRUNCATE` is refused (4137), tables versioned by transaction id cannot be partitioned by `SYSTEM_TIME` (4110), a column declared `WITHOUT SYSTEM VERSIONING` changes without making a version, `FROM ... TO` leaves out the last instant that `BETWEEN` includes, `AUTO` adds a yearly partition when the clock passes the last one ([sql/examples/live_edit.sql](../sql/examples/live_edit.sql)), and a plain `mariadb-dump` leaves the history out unless `--dump-history` is given. One thing found next to them that the page does not say: a table versioned by transaction id cannot take imported history at all (error 1906 even with the switch on).
