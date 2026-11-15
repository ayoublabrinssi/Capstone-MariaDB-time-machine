# What we found

[← Back to the README](../../README.md)

Loading 25 years of real Wikipedia history into a system-versioned table pushed the feature past the case it was built for. System versioning is designed to record from today forward. Here it had to take a past that already happened. Along the way MariaDB 12.3.3 did a few things that surprised me. This folder explains each one in plain words, with a small example, the exact answer the server gave, and what works around it.

Every finding has a file in this repository that reproduces it. You can check each claim yourself in a minute.

> **Want to click through it?** Open [explorer.html](explorer.html) in a browser (download it, or open it from your clone). It has the same findings as moving figures: step through an import, drag a date, watch `AS OF` read row by row.

## The findings

| | Finding | In one sentence | Kind |
|---|---|---|---|
| 1 | [A past date stops answering after an import](01-auto-partitions-lose-imported-history.md) | With `AUTO` partitions, imported history all lands in the first partition, and after the first live change `AS OF` stops looking there. | <img src="../../design/icons/bug.svg" width="24" height="24" alt="" align="absmiddle"> may be a bug |
| 2 | [Setting the clock back loses a version](02-clock-set-back-loses-a-version.md) | An `UPDATE` stamped before the current version started is accepted, the current version disappears, and some dates get two answers. | <img src="../../design/icons/bug.svg" width="24" height="24" alt="" align="absmiddle"> may be a bug |
| 3 | [An old date reads almost the whole history](03-old-dates-read-the-whole-history.md) | `AS OF` 2005 reads 1,845 of Rabat's 1,878 versions to return one, while a query that stops at the first match reads 1. | <img src="../../design/icons/lightbulb.svg" width="24" height="24" alt="" align="absmiddle"> idea for the optimizer |
| 4 | [`OPTIMIZE TABLE` fails but says it worked](04-optimize-says-it-worked.md) | After `DELETE HISTORY` the space only comes back with a rebuild, and `OPTIMIZE` refuses the rebuild without raising an error. | <img src="../../design/icons/bug.svg" width="24" height="24" alt="" align="absmiddle"> may be a bug |
| 5 | [Anyone who can write can write the past](05-anyone-can-write-the-past.md) | On a default server, a user with only `INSERT` and `UPDATE` can add a version dated 2015 or 2030. | <img src="../../design/icons/book-open.svg" width="24" height="24" alt="" align="absmiddle"> documentation |
| 6 | [Imported versions can overlap](06-imported-versions-can-overlap.md) | The server checks that an imported version ends after it starts, but not that it does not overlap another one. | <img src="../../design/icons/book-open.svg" width="24" height="24" alt="" align="absmiddle"> documentation |
| 7 | [Smaller things worth knowing](07-smaller-things.md) | The 1970 floor, a confusing error message, backups that drop the history, and two more. | <img src="../../design/icons/book-open.svg" width="24" height="24" alt="" align="absmiddle"> documentation |

"May be a bug" means the server does something that loses or hides data without an error. It may be intended, but then the documentation should say so. None of these is filed with MariaDB yet; [contributions.md](../contributions.md) tracks what goes where.

## How each page is laid out

1. **The idea.** What is going on, with an everyday comparison.
2. **See it happen.** A small example, step by step, with what the server actually answered.
3. **How we found it.** What the project was doing when it ran into it.
4. **Why it matters.** Who gets hurt, and how.
5. **What works.** What this project does about it, and what you can do.
6. **What we suggest to MariaDB.**
7. **Try it yourself.** The command, and the file with the full output.

## Words used on these pages

| Word | Meaning here |
|---|---|
| version | one row of history: the article (or price) as it was between two moments |
| `row_start`, `row_end` | when a version became true, and when it stopped being true. The current version ends in 2106, the server's "never" |
| system time | the time the server writes into `row_start` and `row_end` |
| `AS OF` | `FOR SYSTEM_TIME AS OF`: "give me the rows as they were at this moment" |
| partition | one part of a table. Here: one partition per year of `row_end` |
| import | writing old versions with their real dates, with `system_versioning_insert_history = 1` |

## Measured, not bugs

Some things are not wrong, just worth knowing before choosing this feature. They are measured in [measurements.md](../measurements.md):

- One version costs 114 bytes of row in every design tried. On disk the table is twice that, because history written in time order leaves pages half full.
- Putting the full article text inside the versioned row makes Rabat 80 MB instead of 5 MB.
- Partitions by year help recent dates only: `AS OF` 2026 opens 2 of 27 partitions, `AS OF` 2005 opens 23. Their real value is cleanup: `DROP PARTITION` removes a year in 14 ms and gives the space back.
- A plain `mariadb-dump` restores 45 of 31,179 versions. Only `--dump-history` keeps the history.
