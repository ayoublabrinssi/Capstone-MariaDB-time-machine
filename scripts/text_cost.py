#!/usr/bin/env python3
"""What would it cost to keep the article text inside the versioned row?

The schema keeps the text out of the versioned table: a version row holds a
pointer, and the text sits in revision_text. This script builds the other
design for one article and measures both, in a scratch database
(timemachine_text_cost) that is dropped at the end.

  pointer   article as it is: version rows with a pointer, texts in their own table
  inline    the same versions with the text in every version row

For each: the size on disk, and what AS OF reads at an old, a middle and a
recent date (rows, disk pages and time inside the server, from
ANALYZE FORMAT=JSON, median of 5 after one warm-up).

The text put into each inline row is the stored quarterly copy that version
points at. It stands in for the exact text of that revision, which has about
the same size.

Writes results/text_cost.txt. Run with scripts/text_cost.sh (a few seconds).
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import ROOT, connect, read_env, run  # noqa: E402

DB = "timemachine_text_cost"
OUT = ROOT / "results" / "text_cost.txt"
DATES = ("2005-06-01 00:00:00", "2010-06-01 00:00:00", "2026-06-01 00:00:00")
RUNS = 5

POINTER = """CREATE TABLE pointer (
  page_id INT NOT NULL PRIMARY KEY, rev_id BIGINT NOT NULL, editor VARCHAR(255), comment TEXT,
  bytes INT, text_rev_id BIGINT NOT NULL,
  row_start TIMESTAMP(6) AS ROW START INVISIBLE, row_end TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)) WITH SYSTEM VERSIONING"""
POINTER_TEXT = "CREATE TABLE pointer_text (rev_id BIGINT NOT NULL PRIMARY KEY, body MEDIUMTEXT NOT NULL)"
INLINE = """CREATE TABLE inline (
  page_id INT NOT NULL PRIMARY KEY, rev_id BIGINT NOT NULL, editor VARCHAR(255), comment TEXT,
  bytes INT, body MEDIUMTEXT NOT NULL,
  row_start TIMESTAMP(6) AS ROW START INVISIBLE, row_end TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)) WITH SYSTEM VERSIONING"""

FILL_POINTER = """INSERT INTO pointer (page_id, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end)
SELECT page_id, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end
FROM timemachine.article FOR SYSTEM_TIME ALL WHERE page_id = %s"""
FILL_POINTER_TEXT = "INSERT INTO pointer_text SELECT rev_id, body FROM timemachine.revision_text WHERE page_id = %s"
FILL_INLINE = """INSERT INTO inline (page_id, rev_id, editor, comment, bytes, body, row_start, row_end)
SELECT a.page_id, a.rev_id, a.editor, a.comment, a.bytes, t.body, a.row_start, a.row_end
FROM timemachine.article FOR SYSTEM_TIME ALL a
JOIN timemachine.revision_text t ON t.rev_id = a.text_rev_id WHERE a.page_id = %s"""

SIZE = """SELECT DATA_LENGTH + INDEX_LENGTH AS size FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"""

WAYS = (
    ("pointer, AS OF", """SELECT a.rev_id, t.body FROM pointer FOR SYSTEM_TIME AS OF TIMESTAMP %s a
JOIN pointer_text t ON t.rev_id = a.text_rev_id WHERE a.page_id = %s""", "tp"),
    ("inline, AS OF", "SELECT rev_id, body FROM inline FOR SYSTEM_TIME AS OF TIMESTAMP %s WHERE page_id = %s", "tp"),
    ("inline, first-row query", """SELECT rev_id, body FROM (
  SELECT rev_id, body, row_start FROM inline FOR SYSTEM_TIME ALL
  WHERE page_id = %s AND row_end > %s ORDER BY row_end LIMIT 1) AS v
WHERE v.row_start <= %s""", "ptt"),
)

lines = []


def say(text=""):
    print(text)
    lines.append(text)


def one(conn, sql, args=None):
    """The first row of a result, as a dictionary."""
    rows = run(conn, sql, args)
    return rows[0] if rows else None


def total(report, key):
    """Adds up one number wherever it sits in an ANALYZE FORMAT=JSON report."""
    if isinstance(report, dict):
        return sum((v if k == key and isinstance(v, (int, float)) else total(v, key)) for k, v in report.items())
    if isinstance(report, list):
        return sum(total(v, key) for v in report)
    return 0


def rows_read(report):
    """Rows read from real tables (a derived table is not counted twice)."""
    n = 0
    if isinstance(report, dict):
        if "r_rows" in report and not str(report.get("table_name", "<")).startswith("<"):
            n += report["r_rows"] * report.get("r_loops", 1)
        n += sum(rows_read(v) for v in report.values())
    elif isinstance(report, list):
        n += sum(rows_read(v) for v in report)
    return n


def measure(conn, sql, args):
    reports = []
    for _ in range(RUNS + 1):
        row = one(conn, "ANALYZE FORMAT=JSON " + sql, args)
        reports.append(json.loads(next(iter(row.values()))))
    reports = reports[1:]                       # the first pass warms the cache
    ms = statistics.median(r["query_block"]["r_total_time_ms"] for r in reports)
    return round(rows_read(reports[-1])), total(reports[-1], "pages_accessed"), ms


def main():
    title = sys.argv[1] if len(sys.argv) > 1 else "Rabat"
    conn = connect(read_env())
    page = one(conn, "SELECT page_id, revisions FROM timemachine.page WHERE title = %s", (title,))
    if page is None:
        raise SystemExit(f"No article called {title} is loaded.")
    run(conn, "DROP DATABASE IF EXISTS " + DB)
    run(conn, "CREATE DATABASE " + DB)
    run(conn, "USE " + DB)
    try:
        for ddl in (POINTER, POINTER_TEXT, INLINE):
            run(conn, ddl)
        run(conn, "SET @@system_versioning_insert_history = 1")
        run(conn, FILL_POINTER, (page["page_id"],))
        run(conn, FILL_INLINE, (page["page_id"],))
        run(conn, "SET @@system_versioning_insert_history = 0")
        run(conn, FILL_POINTER_TEXT, (page["page_id"],))
        for table in ("pointer", "pointer_text", "inline"):
            run(conn, "ANALYZE TABLE " + table)
        size = {t: one(conn, SIZE, (t,))["size"] for t in ("pointer", "pointer_text", "inline")}
        texts = one(conn, "SELECT COUNT(*) AS n FROM pointer_text")["n"]
        whole = one(conn, """SELECT COUNT(*) AS versions, SUM(bytes) AS bytes FROM timemachine.article FOR SYSTEM_TIME ALL""")
        kept = one(conn, "SELECT COUNT(*) AS n, SUM(LENGTH(body)) AS bytes FROM timemachine.revision_text")
        version = one(conn, "SELECT VERSION() AS v")["v"]

        say(f"Text inside the versioned row, or next to it? {title}, {page['revisions']:,} versions. MariaDB {version}")
        say()
        say("Size on disk")
        say(f"  pointer   {size['pointer'] / 1e6:6.1f} MB of version rows + {size['pointer_text'] / 1e6:5.1f} MB for {texts} stored texts"
            f" = {(size['pointer'] + size['pointer_text']) / 1e6:.1f} MB")
        say(f"  inline    {size['inline'] / 1e6:6.1f} MB, a full text in each of the {page['revisions']:,} version rows")
        say()
        say("One article at one moment, text included: rows read from all tables, disk pages (p), time inside the server")
        say(f"  {'':24}" + "".join(f"{d[:10]:>26}" for d in DATES))
        for name, sql, order in WAYS:
            cells = []
            for date in DATES:
                args = {"tp": (date, page["page_id"]), "ptt": (page["page_id"], date, date)}[order]
                rows, pages, ms = measure(conn, sql, args)
                cells.append(f"{rows:>7,} rows {pages:>5,} p {ms:>5.2f} ms")
            say(f"  {name:24}" + "".join(f"{c:>26}" for c in cells))
        say()
        say("All articles")
        say(f"  loaded now      {kept['n']:,} texts, one per article per quarter: {float(kept['bytes']) / 1e6:,.0f} MB of text")
        say(f"  every revision  {whole['versions']:,} texts: {float(whole['bytes']) / 1e9:.2f} GB of text, by the sizes Wikipedia reports")
    finally:
        run(conn, "DROP DATABASE IF EXISTS " + DB)
        conn.close()
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWritten to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
