#!/usr/bin/env python3
"""How does the versioned table grow?

scripts/measure.py reports the size information_schema gives for a table.
That number moved in a way the rows could not explain, so this script looks
under it. For each table it reads three things:

  allocated   DATA_LENGTH of information_schema.TABLES: what the table holds on disk
  in use      the pages of the primary key that hold rows
  row bytes   the bytes of the rows in those pages

"In use" and "row bytes" come from information_schema.INNODB_BUFFER_PAGE,
which lists every page in memory with its records, after the whole table was
read into memory. The script checks that it saw every version that way.

It grows the real history in the order a live table would have written it
(a version becomes history when it ends, so by row_end), with and without
yearly partitions, and measures at five points in time. Then it rebuilds
both tables, and last it repeats the 1x, 2x and 4x copies of measure.py.

Sizes, pages and bytes do not depend on the machine. Works in a scratch
database (timemachine_growth) that is dropped at the end.
Writes results/growth.txt. Run with scripts/growth.sh (a few seconds).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import PARTITIONS, ROOT, VERSIONED, connect, one, read_env, run  # noqa: E402

DB = "timemachine_growth"
OUT = ROOT / "results" / "growth.txt"
STEPS = ("2006-01-01", "2011-01-01", "2016-01-01", "2021-01-01", "2107-01-01")   # the last one takes everything, the current rows too
TABLES = ("grow_part", "grow_flat", "copy1", "copy2", "copy4")
PAGE = 16384

ADD = """INSERT INTO {name} (page_id, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end)
SELECT page_id + %s, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end
FROM timemachine.article FOR SYSTEM_TIME ALL WHERE row_end >= %s AND row_end < %s ORDER BY row_end"""
ALLOCATED = """SELECT DATA_LENGTH AS bytes FROM information_schema.TABLES
WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s"""
# TABLE_NAME there reads `db`.`table`, with /* Partition `p3` */ after it for a partition.
IN_USE = """SELECT COUNT(*) AS pages, COALESCE(SUM(NUMBER_RECORDS), 0) AS records, COALESCE(SUM(DATA_SIZE), 0) AS bytes
FROM information_schema.INNODB_BUFFER_PAGE
WHERE PAGE_TYPE = 'INDEX' AND INDEX_NAME = 'PRIMARY' AND (TABLE_NAME = %s OR TABLE_NAME LIKE %s)"""
PER_PARTITION = """SELECT p.PARTITION_NAME AS name, p.DATA_LENGTH DIV %s AS allocated,
  (SELECT COUNT(*) FROM information_schema.INNODB_BUFFER_PAGE b
   WHERE b.PAGE_TYPE = 'INDEX' AND b.INDEX_NAME = 'PRIMARY'
     AND b.TABLE_NAME = CONCAT(%s, ' /* Partition `', p.PARTITION_NAME, '` */')) AS in_use
FROM information_schema.PARTITIONS p WHERE p.TABLE_SCHEMA = %s AND p.TABLE_NAME = %s"""

lines = []


def say(text=""):
    print(text)
    lines.append(text)


def on(template, name):
    """A table name cannot be sent as a parameter, so only the scratch tables
    of this script are accepted."""
    if name not in TABLES:
        raise ValueError(f"not a table of this script: {name}")
    return template.format(name=name, partitions="")


def create(conn, name, partitioned):
    if name not in TABLES:
        raise ValueError(f"not a table of this script: {name}")
    run(conn, VERSIONED.format(name=name, partitions=PARTITIONS if partitioned else ""))


def measure(conn, name, schema=DB):
    """versions, allocated bytes, pages in use, row bytes."""
    full = f"`{schema}`.`{name}`"
    run(conn, f"ANALYZE TABLE {full}")
    # Reads every row with its columns, so that every page is in memory.
    versions = one(conn, f"SELECT COUNT(rev_id + LENGTH(COALESCE(comment, ''))) FROM {full} FOR SYSTEM_TIME ALL")
    allocated = int(one(conn, ALLOCATED, (schema, name)))
    used = run(conn, IN_USE, (full, full + " /* Partition %"))[0]
    if used["records"] < versions:
        raise SystemExit(f"{name}: only {used['records']:,} of {versions:,} versions were in memory. "
                         "Give the server a larger innodb_buffer_pool_size and run again.")
    return versions, allocated, int(used["pages"]), int(used["bytes"])


def row(label, m):
    versions, allocated, pages, row_bytes = m
    in_use = pages * PAGE
    return (f"{label:<34}{versions:>9,}{row_bytes / versions:>9.0f} B{pages:>8,}{100 * row_bytes / in_use:>7.0f} %"
            f"{in_use / versions:>8.0f} B{in_use / 1e6:>9.1f} MB{allocated / 1e6:>9.1f} MB{allocated / versions:>8.0f} B")


HEAD = (f"{'':<34}{'versions':>9}{'row':>11}{'pages':>8}{'full':>9}{'in use':>10}{'in use':>12}"
        f"{'allocated':>12}{'allocated':>10}\n"
        f"{'':<34}{'':>9}{'bytes':>11}{'in use':>8}{'':>9}{'per version':>10}{'':>12}{'':>12}{'per version':>10}")


def partitions(conn, name):
    full = f"`{DB}`.`{name}`"
    return run(conn, PER_PARTITION, (PAGE, full, DB, name))


def main():
    conn = connect(read_env())
    pool = int(one(conn, "SELECT @@innodb_buffer_pool_size"))
    say("How the versioned table grows")
    say(f"MariaDB {one(conn, 'SELECT VERSION()')}, pages of {int(one(conn, 'SELECT @@innodb_page_size')) // 1024} KB, "
        f"innodb_buffer_pool_size {pool / 1e6:.1f} MB")
    say("allocated = DATA_LENGTH of information_schema.TABLES. in use = the pages of the primary key that")
    say("hold rows, row bytes = the rows in them (information_schema.INNODB_BUFFER_PAGE, whole table in memory).")
    say()

    run(conn, "DROP DATABASE IF EXISTS " + DB)
    run(conn, "CREATE DATABASE " + DB)
    run(conn, "USE " + DB)
    try:
        say("0. The table the load made (timemachine.article, loaded article by article)")
        say(HEAD)
        say(row("article", measure(conn, "article", "timemachine")))
        say()

        say("1. The same history written the way a live table writes it: each version when it ends")
        say(HEAD)
        create(conn, "grow_part", True)
        create(conn, "grow_flat", False)
        run(conn, "SET @@system_versioning_insert_history = 1")
        grown = {"grow_part": [], "grow_flat": []}
        start = "1970-01-01"
        for end in STEPS:
            for name in grown:
                run(conn, on(ADD, name), (0, start, end))
                grown[name].append(measure(conn, name))
            start = end
        for name, label in (("grow_part", "partitioned"), ("grow_flat", "no partitions")):
            for end, m in zip(STEPS, grown[name]):
                when = f"ended before {end[:4]}" if end != STEPS[-1] else "all of it"
                say(row(f"{label + ',':<15}{when}", m))
        first, last = grown["grow_flat"][0], grown["grow_flat"][-1]
        say(f"   From the first point to the last the versions grow {last[0] / first[0]:.1f} times, "
            f"the row bytes {last[3] / first[3]:.1f} times,")
        say(f"   the pages in use {last[2] / first[2]:.1f} times (no partitions).")
        say()

        say("2. Both tables rebuilt (ALTER TABLE ... FORCE with system_versioning_alter_history = KEEP)")
        say(HEAD)
        run(conn, "SET @@system_versioning_insert_history = 0")
        run(conn, "SET @@system_versioning_alter_history = KEEP")
        for name, label in (("grow_part", "partitioned"), ("grow_flat", "no partitions")):
            run(conn, on("ALTER TABLE {name} FORCE", name))
            say(row(f"{label}, rebuilt", measure(conn, name)))
        run(conn, "SET @@system_versioning_alter_history = ERROR")
        say()

        say("3. The 1x, 2x and 4x copies of scripts/measure.py, where allocated per version moved")
        say(HEAD)
        run(conn, "SET @@system_versioning_insert_history = 1")
        for scale in (1, 2, 4):
            name = f"copy{scale}"
            create(conn, name, True)
            for i in range(scale):   # the same statement as measure.py: the whole history, extra copies under other ids
                run(conn, on(ADD.replace(" ORDER BY row_end", ""), name), (i * 1_000_000, "1970-01-01", "2107-01-01"))
            say(row(f"partitioned, {scale}x", measure(conn, name)))
        run(conn, "SET @@system_versioning_insert_history = 0")
        say("   Pages per partition, allocated and in use:")
        for scale in (1, 2, 4):
            parts = partitions(conn, f"copy{scale}")
            big = [p for p in parts if p["allocated"] > 32]
            small = [p for p in parts if p["allocated"] <= 32]
            text = (f"   {scale}x: {len(small)} of {len(parts)} partitions hold 32 pages or fewer, "
                    f"allocated {sum(p['allocated'] for p in small)}, in use {sum(p['in_use'] for p in small)}.")
            if big:
                sizes = sorted({int(p["allocated"]) for p in big})
                text += (f" {len(big)} are past 32: allocated {', '.join(str(s) for s in sizes)} pages each, "
                         f"in use {min(p['in_use'] for p in big)} to {max(p['in_use'] for p in big)}.")
            say(text)
    finally:
        run(conn, "DROP DATABASE IF EXISTS " + DB)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nWritten to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
