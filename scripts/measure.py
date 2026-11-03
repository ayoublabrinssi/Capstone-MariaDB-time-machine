#!/usr/bin/env python3
"""Measures what system versioning costs on this data (README, roadmap step 6).

Everything runs in a separate database, timemachine_measure, built from
copies of the loaded article table. The main database is not touched.

  1. Size: table and index bytes at 1x, 2x and 4x the data.
  2. Speed: the 220 test moments through AS OF, on the partitioned table,
     on the same table without partitions, and on a classic revision table
     with a join, the way Wikipedia stores history. 3 runs each after one
     warm-up run; median and spread.
  3. Rows read for one old date and one recent date, from ANALYZE.
  4. Retention: what DELETE HISTORY and DROP PARTITION remove and free.

Writes results/measurements.txt. Run with scripts/measure.sh.
Settings come from .env like the page does (app/server.py).
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
OPEN_END = "2106-02-07 06:28:15.999999"   # row_end of a current row

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
        user=env.get("DB_USER", "root"), password=env.get("MARIADB_ROOT_PASSWORD", ""),
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


def build(conn, name, scale, partitioned=True):
    """A copy of article at 1x, 2x or 4x. Extra copies get other page ids."""
    run(conn, VERSIONED.format(name=name, partitions=PARTITIONS if partitioned else ""))
    run(conn, "SET @@system_versioning_insert_history = 1")
    for i in range(scale):
        run(conn, COPY.format(name=name), (i * 1_000_000,))
    run(conn, "SET @@system_versioning_insert_history = 0")
    run(conn, f"ANALYZE TABLE {name}")


def size(conn, name):
    row = run(conn, """SELECT TABLE_ROWS AS rows_, DATA_LENGTH AS data_, INDEX_LENGTH AS index_, DATA_FREE AS free_
                       FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s""", (DB, name))[0]
    exact = one(conn, f"SELECT COUNT(*) FROM {name} FOR SYSTEM_TIME ALL") if "classic" not in name \
        else one(conn, f"SELECT COUNT(*) FROM {name}")
    return exact, int(row["data_"]), int(row["index_"]), int(row["free_"])


def mb(n):
    return f"{n / 1e6:.1f} MB"


def moments():
    out = []
    for line in MOMENTS.read_text().splitlines():
        page_id, at, _ = line.split("\t")
        out.append((at, int(page_id)))
    return out


def runs(conn, sql, params, n=3):
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
    """r_rows of the table scan in ANALYZE FORMAT=JSON: rows the engine read."""
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

    tables = list(walk(plan))
    return tables[0]["r_rows"] if tables else None, plan["query_block"].get("r_total_time_ms")


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

    run(conn, f"DROP DATABASE IF EXISTS {DB}")
    run(conn, f"CREATE DATABASE {DB}")
    run(conn, f"USE {DB}")

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
    run(conn, CLASSIC.format(name="classic"))
    run(conn, COPY_CLASSIC.format(name="classic"))
    run(conn, "ANALYZE TABLE classic")
    rows, data, index, free = size(conn, "classic")
    say(f"{'classic (revision table)':<28}{rows:>10,}{mb(data):>12}{mb(index):>12}{(data + index) / rows:>8.0f} B")
    say("Sizes from information_schema.TABLES after ANALYZE TABLE. The text is not in these tables.")
    say()

    # 2. Speed: the 220 test moments -------------------------------------------
    say("2. Speed: the 220 test moments, one AS OF each, 3 runs after a warm-up")
    ms = moments()
    for label, sql, params in (
        ("v1 (partitioned)", AS_OF.format(name="v1"), ms),
        ("v1_flat (no partitions)", AS_OF.format(name="v1_flat"), ms),
        ("classic (ORDER BY edit_time DESC LIMIT 1)", AS_OF_CLASSIC.format(name="classic"), [(p, t) for t, p in ms]),
    ):
        totals = runs(conn, sql, params)
        say(f"{label:<44}{spread(totals)}, {statistics.median(totals) / len(ms):.2f} ms per query")
    say()

    say("   The same, with 4x the rows in the table (v4): one article's cost should not change")
    totals = runs(conn, AS_OF.format(name="v4"), ms)
    say(f"{'v4 (partitioned, 4x)':<44}{spread(totals)}, {statistics.median(totals) / len(ms):.2f} ms per query")
    say()

    say("   All 45 articles at once (COUNT and SUM over AS OF), 3 runs each")
    for scale in SCALES:
        for date in DATES:
            totals = runs(conn, ALL_AS_OF.format(name=f"v{scale}"), [(date,)])
            say(f"{'v' + str(scale) + ' AS OF ' + date[:10]:<44}{spread(totals)}")
    say()

    # 3. Rows read --------------------------------------------------------------
    say("3. Rows read to answer one question (Rabat), from ANALYZE FORMAT=JSON")
    say(f"{'table':<28}{'date':<14}{'rows read':>10}{'partitions':>12}{'ms':>8}")
    for name in ("v1", "v1_flat", "classic"):
        for date in DATES:
            if name == "classic":
                sql, args = AS_OF_CLASSIC.format(name=name), (RABAT, date)
            else:
                sql, args = AS_OF.format(name=name), (date, RABAT)
            r, t = rows_read(conn, sql, args)
            parts = partitions_used(conn, sql, args) if name == "v1" else 0
            say(f"{name:<28}{date[:10]:<14}{r:>10,.0f}{(str(parts) + ' of 27') if parts else '-':>12}{t:>8.2f}")
    say()

    # 4. Retention --------------------------------------------------------------
    say("4. Retention: forgetting history before 2010")
    build(conn, "ret_part", 1)
    build(conn, "ret_flat", 1, partitioned=False)
    for name in ("ret_part", "ret_flat"):
        before = size(conn, name)
        try:
            t = time.perf_counter()
            run(conn, f"DELETE HISTORY FROM {name} BEFORE SYSTEM_TIME '2010-01-01 00:00:00'")
            took = (time.perf_counter() - t) * 1000
            run(conn, f"ANALYZE TABLE {name}")
            after = size(conn, name)
            say(f"DELETE HISTORY on {name}: {before[0]:,} -> {after[0]:,} rows in {took:.0f} ms; "
                f"data {mb(before[1])} -> {mb(after[1])}, free {mb(after[3])}")
            # InnoDB keeps the freed pages until the table is rebuilt. OPTIMIZE
            # is an ALTER, so a versioned table refuses it unless told to keep history.
            # The refusal is a status row, not an error.
            status = run(conn, f"OPTIMIZE TABLE {name}")
            failed = [r["Msg_text"] for r in status if r["Msg_type"] == "error"]
            if failed:
                say(f"   OPTIMIZE TABLE: {failed[0]}")
            run(conn, "SET @@system_versioning_alter_history = KEEP")
            t = time.perf_counter()
            run(conn, f"OPTIMIZE TABLE {name}")
            took = (time.perf_counter() - t) * 1000
            run(conn, "SET @@system_versioning_alter_history = ERROR")
            run(conn, f"ANALYZE TABLE {name}")
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
    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nWritten to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        run(connect(read_env()), f"DROP DATABASE IF EXISTS {DB}")
        print(f"dropped {DB}")
    else:
        main()
