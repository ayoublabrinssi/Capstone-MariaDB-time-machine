"""The database side of the page: the SQL, the connection, and the functions
that ask MariaDB one question each. Nothing here writes HTML.

Settings come from .env in the repository root (the same file Docker Compose
reads) or from the environment: DB_HOST (127.0.0.1), DB_PORT (3307),
DB_NAME (timemachine), DB_USER (timemachine_page), PAGE_DB_PASSWORD.
"""
import datetime as dt
import json
import os
import pathlib
import re
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIRST_DAY = dt.date(2001, 1, 1)

# The one query behind the page. The text joined here is the stored quarterly
# copy; exact.py swaps in the text of the exact revision when it is not that one.
AS_OF_SQL = """SELECT a.rev_id, a.editor, a.comment, a.bytes, a.row_start, a.row_end,
       a.text_rev_id, t.body
FROM article FOR SYSTEM_TIME AS OF TIMESTAMP %s AS a
LEFT JOIN revision_text AS t ON t.rev_id = a.text_rev_id
WHERE a.page_id = %s"""

TEXT_DATE_SQL = """SELECT row_start FROM article FOR SYSTEM_TIME ALL
WHERE page_id = %s AND rev_id = %s"""

PREV_SQL = """SELECT rev_id, bytes, row_start FROM article FOR SYSTEM_TIME ALL
WHERE page_id = %s AND row_end <= %s ORDER BY row_end DESC LIMIT 1"""

NEXT_SQL = """SELECT rev_id, row_start FROM article FOR SYSTEM_TIME ALL
WHERE page_id = %s AND row_start >= %s ORDER BY row_start LIMIT 1"""

DAY_SQL = """SELECT COUNT(*) AS versions FROM article
FOR SYSTEM_TIME BETWEEN TIMESTAMP %s AND TIMESTAMP %s
WHERE page_id = %s"""

SO_FAR_SQL = """SELECT COUNT(*) AS versions, COUNT(DISTINCT editor) AS editors
FROM article FOR SYSTEM_TIME ALL
WHERE page_id = %s AND row_start <= %s"""

STORAGE_SQL = """SELECT TABLE_NAME AS name, TABLE_ROWS AS approx_rows, DATA_LENGTH + INDEX_LENGTH AS size
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('article', 'article_period', 'revision_text', 'exact_text')"""

ROWS_SQL = """SELECT (SELECT COUNT(*) FROM article) AS current_rows,
       (SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL) AS all_rows,
       (SELECT COUNT(*) FROM exact_text) AS exact_texts,
       VERSION() AS version"""

PERIOD_SQL = """SELECT rev_id FROM article_period
WHERE page_id = %s AND valid_from <= %s AND valid_to > %s"""

# The same answer with less reading. Versions of one article never overlap, so
# the one live at a moment is the first one that ended after it. The key is
# (page_id, row_end): read it in order, stop at the first row, then check that
# the row had started (it had not if the moment is before the first edit).
FIRST_ROW_SQL = """SELECT rev_id FROM (
  SELECT rev_id, row_start
  FROM article FOR SYSTEM_TIME ALL
  WHERE page_id = %s
    AND row_end > %s
  ORDER BY row_end LIMIT 1
) AS v
WHERE v.row_start <= %s"""

# No AS OF in the query: the session itself travels (system_versioning_asof).
SESSION_SQL = """SELECT rev_id FROM article WHERE page_id = %s"""

# Days with reverts: edits whose comment says so, per day, busiest first.
WARS_SQL = """SELECT DATE(row_start) AS day, COUNT(*) AS edits, COUNT(DISTINCT editor) AS editors,
       SUM(comment LIKE 'Revert%%' OR comment LIKE 'Undid%%' OR comment LIKE 'rv%%'
           OR comment LIKE '%%revert%%') AS reverts
FROM article FOR SYSTEM_TIME ALL
WHERE page_id = %s
GROUP BY day HAVING reverts >= 2
ORDER BY reverts DESC, edits DESC, day
LIMIT 5"""

# The partitions as the server has them now. AUTO adds one per year as time
# goes on, so the page never assumes how many there are.
PARTITIONS_SQL = """SELECT PARTITION_NAME AS name, PARTITION_DESCRIPTION AS ends_before, TABLE_ROWS AS approx_rows
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'article'
ORDER BY PARTITION_ORDINAL_POSITION"""

PER_YEAR_SQL = """SELECT YEAR(row_start) AS year, COUNT(*) AS edits
FROM article FOR SYSTEM_TIME ALL
WHERE page_id = %s
GROUP BY year ORDER BY year"""


def read_env():
    """Reads KEY=value lines from .env, then lets the real environment win."""
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    env.update(os.environ)
    return env


ENV = read_env()


def connect(readonly=True):
    """A connection as the page's own user, which may only read (plus one
    INSERT, on the table exact_text). scripts/install.sh makes that user."""
    import pymysql  # imported here so the pure functions can be tested without it

    conn = pymysql.connect(
        host=ENV.get("DB_HOST", "127.0.0.1"),
        port=int(ENV.get("DB_PORT", "3307")),
        user=ENV.get("DB_USER", "timemachine_page"),
        password=ENV.get("PAGE_DB_PASSWORD", ""),
        database=ENV.get("DB_NAME", "timemachine"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        # The edit times were loaded in UTC, so every question is asked in UTC.
        cur.execute("SET time_zone = '+00:00'")
        if readonly:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
    return conn


def is_database_error(exc):
    """True when the exception came from the driver or the server."""
    try:
        import pymysql
    except ImportError:
        return False
    return isinstance(exc, pymysql.MySQLError)


def is_current(row_end):
    """A current row ends at the largest TIMESTAMP the server has: 2106 on
    MariaDB 11.5 and later, 2038 before. No real edit is that far away."""
    return row_end.year >= 2038


def parse_day(value, today=None):
    """Returns a date from 'YYYY-MM-DD', kept between 2001-01-01 and today."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    if not value or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        day = dt.date.fromisoformat(value)
    except ValueError:
        return None
    return min(max(day, FIRST_DAY), today)


def end_of(day):
    """The moment the page asks about: the last microsecond of that day, UTC."""
    return f"{day.isoformat()} 23:59:59.999999"


def pages(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT page_id, title, revisions, first_edit, last_edit FROM page ORDER BY title")
        return cur.fetchall()


def version_at(conn, page_id, day):
    """The version of an article that was live at the end of that day, or None."""
    moment = end_of(day)
    with conn.cursor() as cur:
        started = time.perf_counter()
        cur.execute(AS_OF_SQL, (moment, page_id))
        row = cur.fetchone()
        elapsed = time.perf_counter() - started
        if row is None:
            return None
        row["ms"] = elapsed * 1000
        row["text_date"] = row["row_start"]
        if row["text_rev_id"] != row["rev_id"]:
            cur.execute(TEXT_DATE_SQL, (page_id, row["text_rev_id"]))
            found = cur.fetchone()
            row["text_date"] = found["row_start"] if found else None
        cur.execute("EXPLAIN PARTITIONS " + AS_OF_SQL, (moment, page_id))
        row["plan"] = cur.fetchall()
        mine = [p for p in row["plan"] if p["table"] == "a"]
        row["partitions"] = (mine[0]["partitions"] or "").split(",") if mine else []
        # ANALYZE runs the query again and reports what really happened
        cur.execute("ANALYZE FORMAT=JSON " + AS_OF_SQL, (moment, page_id))
        row["analyze"] = analyze(json.loads(next(iter(cur.fetchone().values()))))
        row["sql"] = cur.mogrify(AS_OF_SQL, (moment, page_id))
        # the versions on either side, read from the whole history
        cur.execute(PREV_SQL, (page_id, row["row_start"]))
        row["prev"] = cur.fetchone()
        cur.execute(NEXT_SQL, (page_id, row["row_end"]))
        row["next"] = cur.fetchone()
        cur.execute(SO_FAR_SQL, (page_id, row["row_start"]))
        row.update(cur.fetchone())
        cur.execute(DAY_SQL, (f"{day.isoformat()} 00:00:00", moment, page_id))
        row["that_day"] = cur.fetchone()["versions"]
        # the same question asked to the application-time table
        cur.execute(PERIOD_SQL, (page_id, moment, moment))
        found = cur.fetchone()
        row["period_rev"] = found["rev_id"] if found else None
        # the first-row shortcut, with the rows it really read
        cur.execute(FIRST_ROW_SQL, (page_id, moment, moment))
        found = cur.fetchone()
        row["first_rev"] = found["rev_id"] if found else None
        cur.execute("ANALYZE FORMAT=JSON " + FIRST_ROW_SQL, (page_id, moment, moment))
        row["first_rows"] = rows_read(json.loads(next(iter(cur.fetchone().values()))))
        row["first_sql"] = cur.mogrify(FIRST_ROW_SQL, (page_id, moment, moment))
        # and asked with no AS OF at all: the session is moved to that moment
        try:
            cur.execute("SET @@system_versioning_asof = %s", (moment,))
            cur.execute(SESSION_SQL, (page_id,))
            found = cur.fetchone()
            row["session_rev"] = found["rev_id"] if found else None
            cur.execute("EXPLAIN PARTITIONS " + SESSION_SQL, (page_id,))
            used = cur.fetchone()["partitions"] or ""
            row["session_partitions"] = [p for p in used.split(",") if p]
        finally:
            cur.execute("SET @@system_versioning_asof = DEFAULT")
        return row


def edit_wars(conn, page_id):
    """Days with two or more reverts on this article, busiest first."""
    with conn.cursor() as cur:
        cur.execute(WARS_SQL, (page_id,))
        return cur.fetchall()


def analyze(report):
    """Picks the numbers the page shows from ANALYZE FORMAT=JSON."""
    block = report.get("query_block", {})
    tables = {}
    for step in block.get("nested_loop", []):
        t = step.get("table", {})
        tables[t.get("table_name")] = {
            "access": t.get("access_type"),
            "key": t.get("key"),
            "parts": t.get("used_key_parts", []),
            "rows": t.get("rows"),
            "r_rows": t.get("r_rows"),
            "pages": t.get("r_engine_stats", {}).get("pages_accessed"),
            "r_filtered": t.get("r_filtered"),
            "condition": t.get("attached_condition", ""),
        }
    plan_ms = report.get("query_optimization", {}).get("r_total_time_ms", 0)
    return {"tables": tables, "ms": block.get("r_total_time_ms", 0) + plan_ms, "plan_ms": plan_ms}


def rows_read(report):
    """Rows the engine read from real tables in an ANALYZE FORMAT=JSON report,
    wherever they sit in the plan (the derived table itself is not counted)."""
    total = 0
    if isinstance(report, dict):
        if "r_rows" in report and not str(report.get("table_name", "<")).startswith("<"):
            total += report["r_rows"] * report.get("r_loops", 1)
        total += sum(rows_read(v) for v in report.values())
    elif isinstance(report, list):
        total += sum(rows_read(v) for v in report)
    return total


def storage(conn):
    with conn.cursor() as cur:
        cur.execute(STORAGE_SQL)
        sizes = {r["name"]: r for r in cur.fetchall()}
        cur.execute(ROWS_SQL)
        return {"tables": sizes, **cur.fetchone()}


def partitions(conn):
    """The partitions of article, oldest first, the current one last."""
    with conn.cursor() as cur:
        cur.execute(PARTITIONS_SQL)
        return cur.fetchall()


def edits_per_year(conn, page_id):
    with conn.cursor() as cur:
        cur.execute(PER_YEAR_SQL, (page_id,))
        return {r["year"]: r["edits"] for r in cur.fetchall()}

