#!/usr/bin/env python3
"""Measures what system versioning costs on this data (README, roadmap step 6).

Everything runs in a separate database, timemachine_measure, built from
copies of the loaded article table. The main database is not touched.

  1. Size: table and index bytes at 1x, 2x and 4x the data.
  2. Speed: the 220 test moments through AS OF, on the partitioned table,
     on the same table without partitions, and on a classic revision table
     with a join, the way Wikipedia stores history. 5 runs each after one
     warm-up run; median and spread.
  3. Rows read for one old date and one recent date, from ANALYZE.
  4. Old dates: three ways to answer faster (an index on row_start, the
     application-time table, a rewritten query that stops at the first row),
     on the real data and on one synthetic article with up to a million versions.
  5. Retention: what DELETE HISTORY and DROP PARTITION remove and free.

Writes results/measurements.txt, or the file given with --out for a repeat
run. Run with scripts/measure.sh (a few minutes).
Settings come from .env. It connects as root, because it creates and drops
its own scratch database.

A table name cannot be a parameter, so on() puts one into a statement and
accepts only the scratch tables of this file. Every value that changes
(dates, article ids, sizes) goes to the server as a parameter.
"""
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "measurements.txt"
DB = "timemachine_measure"
SCALES = (1, 2, 4)
MOMENTS = ROOT / "data" / "load" / "expected_as_of.tsv"
DATES = ("2005-06-01 00:00:00", "2010-06-01 00:00:00", "2026-06-01 00:00:00")
RABAT = 57400
RUNS = 5                                  # timed passes after one warm-up pass

lines = []


def say(text=""):
    print(text)
    lines.append(text)


def read_env():
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    env.update(os.environ)
    return env


def connect(env):
    conn = pymysql.connect(
        host=env.get("DB_HOST", "127.0.0.1"), port=int(env.get("DB_PORT", "3307")),
        user="root", password=env.get("MARIADB_ROOT_PASSWORD", ""),   # builds scratch databases
        charset="utf8mb4", autocommit=True, cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute("SET time_zone = '+00:00'")
    return conn


def run(conn, sql, args=None):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def one(conn, sql, args=None):
    rows = run(conn, sql, args)
    return list(rows[0].values())[0] if rows else None


def timed(conn, sql, args=None):
    t = time.perf_counter()
    run(conn, sql, args)
    return (time.perf_counter() - t) * 1000


VERSIONED = """CREATE TABLE {name} (
  page_id INT NOT NULL PRIMARY KEY,
  rev_id BIGINT NOT NULL,
  editor VARCHAR(255),
  comment TEXT,
  bytes INT,
  text_rev_id BIGINT NOT NULL,
  row_start TIMESTAMP(6) AS ROW START INVISIBLE,
  row_end TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)
) WITH SYSTEM VERSIONING{partitions}"""

PARTITIONS = "\n  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2001-01-01 00:00:00' AUTO PARTITIONS 27"

CLASSIC = """CREATE TABLE {name} (
  rev_id BIGINT NOT NULL PRIMARY KEY,
  page_id INT NOT NULL,
  editor VARCHAR(255),
  comment TEXT,
  bytes INT,
  text_rev_id BIGINT NOT NULL,
  edit_time DATETIME(6) NOT NULL,
  KEY page_time (page_id, edit_time)
)"""

COPY = """INSERT INTO {name} (page_id, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end)
SELECT page_id + %s, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end
FROM timemachine.article FOR SYSTEM_TIME ALL"""

COPY_CLASSIC = """INSERT INTO {name} (rev_id, page_id, editor, comment, bytes, text_rev_id, edit_time)
SELECT rev_id, page_id, editor, comment, bytes, text_rev_id, row_start
FROM timemachine.article FOR SYSTEM_TIME ALL"""

AS_OF = "SELECT rev_id, editor, bytes FROM {name} FOR SYSTEM_TIME AS OF TIMESTAMP %s WHERE page_id = %s"
AS_OF_CLASSIC = ("SELECT rev_id, editor, bytes FROM {name} WHERE page_id = %s AND edit_time <= %s "
                 "ORDER BY edit_time DESC LIMIT 1")
ALL_AS_OF = "SELECT COUNT(*) AS n, SUM(bytes) AS b FROM {name} FOR SYSTEM_TIME AS OF TIMESTAMP %s"

# The versions of one primary key never overlap in system time, so the row
# that was live at T is the one with the smallest row_end after T. Reading the
# key (page_id, row_end) in order and stopping at the first row finds it; the
# outer WHERE drops it again when T is before the article existed.
FIRST_ROW = ("SELECT rev_id, editor, bytes FROM (SELECT rev_id, editor, bytes, row_start FROM {name} "
             "FOR SYSTEM_TIME ALL WHERE page_id = %s AND row_end > %s ORDER BY row_end LIMIT 1) AS v "
             "WHERE v.row_start <= %s")
# The same question to the application-time table of the main database.
PERIOD = ("SELECT rev_id, bytes FROM timemachine.article_period "
          "WHERE page_id = %s AND valid_from <= %s AND valid_to > %s")

BIG = """CREATE TABLE big (
  page_id INT NOT NULL PRIMARY KEY,
  rev_id BIGINT NOT NULL,
  editor VARCHAR(255),
  bytes INT,
  row_start TIMESTAMP(6) AS ROW START INVISIBLE,
  row_end TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)
) WITH SYSTEM VERSIONING"""
# One version a minute from 1 January 2001, made by the Sequence engine.
BIG_FILL = """INSERT INTO big (page_id, rev_id, bytes, row_start, row_end)
SELECT %s, seq, seq MOD 5000,
       TIMESTAMP('2001-01-01 00:00:00') + INTERVAL seq MINUTE,
       TIMESTAMP('2001-01-01 00:00:00') + INTERVAL seq + 1 MINUTE
FROM seq_1_to_1000000 WHERE seq <= %s"""
BIG_SIZES = (10_000, 100_000, 1_000_000)


TABLES = {"v1", "v2", "v4", "v1_flat", "v1_flat_idx", "v1_idx", "classic", "big", "ret_part", "ret_flat"}


def on(template, name, **more):
    """Puts a table name into a statement. A table name cannot be sent as a
    parameter, so only the scratch tables listed above are accepted. Every
    value still goes to the server as a parameter."""
    if name not in TABLES:
        raise ValueError(f"not a table of this script: {name}")
    return template.format(name=name, **more)


def build(conn, name, scale, partitioned=True, start_index=False):
    """A copy of article at 1x, 2x or 4x. Extra copies get other page ids."""
    run(conn, on(VERSIONED, name, partitions=PARTITIONS if partitioned else ""))
    if start_index:
        add_start_index(conn, name)
    run(conn, "SET @@system_versioning_insert_history = 1")
    for i in range(scale):
        run(conn, on(COPY, name), (i * 1_000_000,))
    run(conn, "SET @@system_versioning_insert_history = 0")
    run(conn, on("ANALYZE TABLE {name}", name))


def add_start_index(conn, name):
    """A second index that starts at row_start. Adding it is an ALTER, which a
    versioned table refuses unless told to keep its history."""
    run(conn, "SET @@system_versioning_alter_history = KEEP")
    run(conn, on("ALTER TABLE {name} ADD KEY by_start (page_id, row_start)", name))
    run(conn, "SET @@system_versioning_alter_history = ERROR")


def size(conn, name):
    row = run(conn, """SELECT TABLE_ROWS AS rows_, DATA_LENGTH AS data_, INDEX_LENGTH AS index_, DATA_FREE AS free_
                       FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s""", (DB, name))[0]
    exact = one(conn, on("SELECT COUNT(*) FROM {name} FOR SYSTEM_TIME ALL", name)) if "classic" not in name \
        else one(conn, on("SELECT COUNT(*) FROM {name}", name))
    return exact, int(row["data_"]), int(row["index_"]), int(row["free_"])


def mb(n):
    return f"{n / 1e6:.1f} MB"


def moments():
    out = []
    for line in MOMENTS.read_text().splitlines():
        page_id, at, _ = line.split("\t")
        out.append((at, int(page_id)))
    return out


def runs(conn, sql, params, n=RUNS):
    """n timed passes over all params after one warm-up pass. Total ms per pass."""
    totals = []
    for i in range(n + 1):
        t = time.perf_counter()
        for p in params:
            run(conn, sql, p)
        total = (time.perf_counter() - t) * 1000
        if i > 0:
            totals.append(total)
    return totals


def spread(totals):
    return f"median {statistics.median(totals):.0f} ms, min {min(totals):.0f}, max {max(totals):.0f}"


def rows_read(conn, sql, args):
    """What the engine examined, from ANALYZE FORMAT=JSON: index entries when the
    condition is checked inside the index (r_index_rows), rows otherwise (r_rows).
    Derived tables are skipped, the base table under them is counted."""
    plan = json.loads(one(conn, "ANALYZE FORMAT=JSON " + sql, args))

    def walk(node):
        if isinstance(node, dict):
            if "r_rows" in node and "table_name" in node:
                yield node
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    tables = [t for t in walk(plan) if not t["table_name"].startswith("<")]
    examined = sum(t.get("r_index_rows", t["r_rows"]) for t in tables)
    return examined, plan["query_block"].get("r_total_time_ms")


def key_used(conn, sql, args):
    """The key chosen for the base table (the derived table row is skipped)."""
    rows = [r for r in run(conn, "EXPLAIN " + sql, args) if not r["table"].startswith("<")]
    return rows[0]["key"] or "full scan"


def partitions_used(conn, sql, args):
    rows = run(conn, "EXPLAIN PARTITIONS " + sql, args)
    used = rows[0]["partitions"] or ""
    return len([p for p in used.split(",") if p])


def main():
    env = read_env()
    conn = connect(env)
    version = one(conn, "SELECT VERSION()")
    pool = int(one(conn, "SELECT @@innodb_buffer_pool_size"))
    say("Measurements for the Wikipedia time machine")
    say(f"MariaDB {version}, innodb_buffer_pool_size {mb(pool)}, "
        f"client {platform.system()} {platform.machine()}, {os.cpu_count()} CPUs seen by Python")
    say(f"Run on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    say()

    run(conn, "DROP DATABASE IF EXISTS timemachine_measure")
    run(conn, "CREATE DATABASE timemachine_measure")
    run(conn, "USE timemachine_measure")

    # 1. Size at 1x, 2x, 4x -------------------------------------------------
    say("1. Size: one version per revision, 31,179 rows at 1x")
    say(f"{'table':<28}{'rows':>10}{'data':>12}{'index':>12}{'per row':>10}")
    for scale in SCALES:
        name = f"v{scale}"
        t = time.perf_counter()
        build(conn, name, scale)
        load_ms = (time.perf_counter() - t) * 1000
        rows, data, index, free = size(conn, name)
        say(f"{name + ' (partitioned, ' + str(scale) + 'x)':<28}{rows:>10,}{mb(data):>12}{mb(index):>12}"
            f"{(data + index) / rows:>8.0f} B   loaded in {load_ms / 1000:.1f} s")
    build(conn, "v1_flat", 1, partitioned=False)
    rows, data, index, free = size(conn, "v1_flat")
    say(f"{'v1_flat (no partitions)':<28}{rows:>10,}{mb(data):>12}{mb(index):>12}{(data + index) / rows:>8.0f} B")
    run(conn, on(CLASSIC, "classic"))
    run(conn, on(COPY_CLASSIC, "classic"))
    run(conn, "ANALYZE TABLE classic")
    rows, data, index, free = size(conn, "classic")
    say(f"{'classic (revision table)':<28}{rows:>10,}{mb(data):>12}{mb(index):>12}{(data + index) / rows:>8.0f} B")
    say("Sizes from information_schema.TABLES after ANALYZE TABLE. The text is not in these tables.")
    say()

    # 2. Speed: the 220 test moments -------------------------------------------
    say(f"2. Speed: the 220 test moments, one AS OF each, {RUNS} runs after a warm-up")
    ms = moments()
    for label, sql, params in (
        ("v1 (partitioned)", on(AS_OF, "v1"), ms),
        ("v1_flat (no partitions)", on(AS_OF, "v1_flat"), ms),
        ("classic (ORDER BY edit_time DESC LIMIT 1)", on(AS_OF_CLASSIC, "classic"), [(p, t) for t, p in ms]),
    ):
        totals = runs(conn, sql, params)
        say(f"{label:<44}{spread(totals)}, {statistics.median(totals) / len(ms):.2f} ms per query")
    say()

    say("   The same, with 4x the rows in the table (v4): one article's cost should not change")
    totals = runs(conn, on(AS_OF, "v4"), ms)
    say(f"{'v4 (partitioned, 4x)':<44}{spread(totals)}, {statistics.median(totals) / len(ms):.2f} ms per query")
    say()

    say(f"   All 45 articles at once (COUNT and SUM over AS OF), {RUNS} runs each")
    for scale in SCALES:
        for date in DATES:
            totals = runs(conn, on(ALL_AS_OF, f"v{scale}"), [(date,)])
            say(f"{'v' + str(scale) + ' AS OF ' + date[:10]:<44}{spread(totals)}")
    say()

    # 3. Rows read --------------------------------------------------------------
    say("3. Rows read to answer one question (Rabat), from ANALYZE FORMAT=JSON")
    say(f"{'table':<28}{'date':<14}{'rows read':>10}{'partitions':>12}{'ms':>8}")
    for name in ("v1", "v1_flat", "classic"):
        for date in DATES:
            if name == "classic":
                sql, args = on(AS_OF_CLASSIC, name), (RABAT, date)
            else:
                sql, args = on(AS_OF, name), (date, RABAT)
            r, t = rows_read(conn, sql, args)
            parts = partitions_used(conn, sql, args) if name == "v1" else 0
            say(f"{name:<28}{date[:10]:<14}{r:>10,.0f}{(str(parts) + ' of 27') if parts else '-':>12}{t:>8.2f}")
    say()

    # 4. Old dates ---------------------------------------------------------------
    say("4. Old dates: three ways to read fewer rows")
    say("   AS OF reads every version that ended after the moment. Tried against it:")
    say("   a second index (page_id, row_start), the application-time table, and a query")
    say("   that reads the key in order and stops at the first row (FIRST_ROW in this file).")
    build(conn, "v1_flat_idx", 1, partitioned=False, start_index=True)
    build(conn, "v1_idx", 1, start_index=True)
    for name in ("v1_flat", "v1_flat_idx"):
        rows, data, index, free = size(conn, name)
        say(f"   {name:<14} data {mb(data)}, index {mb(index)}")
    say()
    say(f"   Rows or index entries examined for Rabat, and the key the optimizer chose")
    say(f"   {'query':<46}{'2005-06-01':>16}{'2010-06-01':>16}{'2026-06-01':>16}")
    variants = (
        ("AS OF, no partitions", on(AS_OF, "v1_flat"), lambda d: (d, RABAT)),
        ("AS OF, no partitions, + index on row_start", on(AS_OF, "v1_flat_idx"), lambda d: (d, RABAT)),
        ("AS OF, partitioned, + index on row_start", on(AS_OF, "v1_idx"), lambda d: (d, RABAT)),
        ("application-time table (article_period)", PERIOD, lambda d: (RABAT, d, d)),
        ("first row only, no partitions", on(FIRST_ROW, "v1_flat"), lambda d: (RABAT, d, d)),
        ("first row only, partitioned", on(FIRST_ROW, "v1"), lambda d: (RABAT, d, d)),
    )
    server_ms = []
    for label, sql, args in variants:
        cells, times = [], []
        for date in DATES:
            rows_read(conn, sql, args(date))  # warm-up
            passes = [rows_read(conn, sql, args(date)) for _ in range(RUNS)]
            examined, ms_taken = passes[0][0], statistics.median(ms for _, ms in passes)
            key = key_used(conn, sql, args(date)) if "index on row_start" in label else ""
            cells.append(f"{examined:,.0f}" + (f" ({key})" if key else ""))
            times.append(f"{ms_taken:.2f}")
        say(f"   {label:<46}{cells[0]:>16}{cells[1]:>16}{cells[2]:>16}")
        server_ms.append((label, times))
    say()
    say(f"   Time inside the server for the same questions (r_total_time_ms of ANALYZE), median of {RUNS}, in ms")
    say(f"   {'query':<46}{'2005-06-01':>16}{'2010-06-01':>16}{'2026-06-01':>16}")
    for label, times in server_ms:
        say(f"   {label:<46}{times[0]:>16}{times[1]:>16}{times[2]:>16}")
    say()
    say(f"   The 220 test moments again, {RUNS} runs after a warm-up")
    same = sum(1 for at, page in ms
               if run(conn, on(AS_OF, "v1"), (at, page)) == run(conn, on(FIRST_ROW, "v1"), (page, at, at)))
    say(f"   first row only gives the same answer as AS OF for {same} of {len(ms)} moments")
    for label, sql, params in (
        ("AS OF, no partitions, + index on row_start", on(AS_OF, "v1_flat_idx"), ms),
        ("AS OF, partitioned, + index on row_start", on(AS_OF, "v1_idx"), ms),
        ("application-time table (article_period)", PERIOD, [(p, t, t) for t, p in ms]),
        ("first row only, no partitions", on(FIRST_ROW, "v1_flat"), [(p, t, t) for t, p in ms]),
        ("first row only, partitioned", on(FIRST_ROW, "v1"), [(p, t, t) for t, p in ms]),
    ):
        totals = runs(conn, sql, params)
        say(f"   {label:<46}{spread(totals)}, {statistics.median(totals) / len(ms):.2f} ms per query")
    say()

    say("   One synthetic article with many versions, one a minute (Sequence engine).")
    say("   Asked for the moment 10% into its history, so 90% of the versions ended after it.")
    run(conn, BIG)
    run(conn, "SET @@system_versioning_insert_history = 1")
    t = time.perf_counter()
    for n in BIG_SIZES:
        run(conn, BIG_FILL, (n, n))
    load_ms = (time.perf_counter() - t) * 1000
    run(conn, "SET @@system_versioning_insert_history = 0")
    run(conn, "ANALYZE TABLE big")
    say(f"   {sum(BIG_SIZES):,} versions loaded in {load_ms / 1000:.1f} s")

    def moment(n, share):
        return one(conn, "SELECT TIMESTAMP('2001-01-01 00:00:30') + INTERVAL %s MINUTE", (int(n * share),))

    def big_line(label, sql, args):
        examined, _ = rows_read(conn, sql, args)
        totals = runs(conn, sql, [args])
        say(f"   {label:<38}{examined:>12,.0f}{statistics.median(totals):>10.2f} ms   {key_used(conn, sql, args)}")

    head = f"   {'versions and query':<38}{'examined':>12}{'median':>13}   key"
    say(head)
    for n in BIG_SIZES:
        at = moment(n, 0.1)
        big_line(f"{n:,} AS OF", on(AS_OF, "big"), (at, n))
        big_line(f"{n:,} first row only", on(FIRST_ROW, "big"), (n, at, at))
    say("   For the largest article the optimizer leaves the key and scans the whole table.")
    add_start_index(conn, "big")
    run(conn, "ANALYZE TABLE big")
    n = BIG_SIZES[-1]
    forced = on(AS_OF, "big").replace(" WHERE", " FORCE INDEX (by_start) WHERE")
    say()
    say(f"   The {n:,}-version article after adding the index on row_start, at three moments")
    say(head.replace("versions and query", "moment and query  "))
    for share in (0.1, 0.5, 0.9):
        at = moment(n, share)
        where = f"{int(share * 100)}% in,"
        big_line(f"{where} AS OF", on(AS_OF, "big"), (at, n))
        big_line(f"{where} AS OF, index forced", forced, (at, n))
        big_line(f"{where} first row only", on(FIRST_ROW, "big"), (n, at, at))
    say()

    # 5. Retention --------------------------------------------------------------
    say("5. Retention: forgetting history before 2010")
    build(conn, "ret_part", 1)
    build(conn, "ret_flat", 1, partitioned=False)
    for name in ("ret_part", "ret_flat"):
        before = size(conn, name)
        try:
            t = time.perf_counter()
            run(conn, on("DELETE HISTORY FROM {name} BEFORE SYSTEM_TIME '2010-01-01 00:00:00'", name))
            took = (time.perf_counter() - t) * 1000
            run(conn, on("ANALYZE TABLE {name}", name))
            after = size(conn, name)
            say(f"DELETE HISTORY on {name}: {before[0]:,} -> {after[0]:,} rows in {took:.0f} ms; "
                f"data {mb(before[1])} -> {mb(after[1])}, free {mb(after[3])}")
            # InnoDB keeps the freed pages until the table is rebuilt. OPTIMIZE
            # is an ALTER, so a versioned table refuses it unless told to keep history.
            # The refusal comes back as result rows while the statement itself succeeds.
            status = run(conn, on("OPTIMIZE TABLE {name}", name))
            failed = [r["Msg_text"] for r in status if r["Msg_type"] == "error"]
            if failed:
                say(f"   OPTIMIZE TABLE: {failed[0]}")
            run(conn, "SET @@system_versioning_alter_history = KEEP")
            t = time.perf_counter()
            run(conn, on("OPTIMIZE TABLE {name}", name))
            took = (time.perf_counter() - t) * 1000
            run(conn, "SET @@system_versioning_alter_history = ERROR")
            run(conn, on("ANALYZE TABLE {name}", name))
            after = size(conn, name)
            say(f"   after OPTIMIZE TABLE with alter_history = KEEP ({took:.0f} ms): data {mb(after[1])}, free {mb(after[3])}")
        except pymysql.MySQLError as e:
            say(f"DELETE HISTORY on {name}: refused, error {e.args[0]}: {e.args[1]}")
    # Dropping yearly partitions p0..p8 (versions that ended 2001 to 2009)
    before = size(conn, "v1")
    try:
        t = time.perf_counter()
        run(conn, "ALTER TABLE v1 DROP PARTITION p0, p1, p2, p3, p4, p5, p6, p7, p8")
        took = (time.perf_counter() - t) * 1000
        run(conn, "ANALYZE TABLE v1")
        after = size(conn, "v1")
        say(f"DROP PARTITION p0..p8 on v1: {before[0]:,} -> {after[0]:,} rows in {took:.0f} ms; "
            f"data {mb(before[1])} -> {mb(after[1])}")
    except pymysql.MySQLError as e:
        say(f"DROP PARTITION on v1: refused, error {e.args[0]}: {e.args[1]}")
    say()
    say("Scratch database timemachine_measure is left in place; drop it with scripts/measure.sh --clean")
    out = OUT
    if "--out" in sys.argv:  # a repeat run keeps its own file: --out results/measurements-run2.txt
        out = (ROOT / sys.argv[sys.argv.index("--out") + 1]).resolve()
    out.write_text("\n".join(lines) + "\n")
    print(f"\nWritten to {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        run(connect(read_env()), "DROP DATABASE IF EXISTS timemachine_measure")
        print(f"dropped {DB}")
    else:
        main()
