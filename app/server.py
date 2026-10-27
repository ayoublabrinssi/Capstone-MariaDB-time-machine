"""The time machine page: pick a city and a date, see its article that day.

Python standard library plus PyMySQL. Start it with scripts/run.sh, then open
http://127.0.0.1:8000. Every question goes to MariaDB as one query with
FOR SYSTEM_TIME AS OF; the page shows that query under the article.

Settings come from .env in the repository root (the same file Docker Compose
reads) or from the environment: MARIADB_ROOT_PASSWORD, DB_HOST (127.0.0.1),
DB_PORT (3307), DB_NAME (timemachine), PORT (8000).
"""
import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse

import wikitext

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIRST_DAY = dt.date(2001, 1, 1)
STILL_LIVE = 2038  # row_end of a current row is 2038-01-19, the TIMESTAMP maximum

# The one query behind the page. The text is a stored sample, see the README.
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
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('article', 'article_period', 'revision_text')"""

ROWS_SQL = """SELECT (SELECT COUNT(*) FROM article) AS current_rows,
       (SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL) AS all_rows,
       VERSION() AS version"""

PERIOD_SQL = """SELECT rev_id FROM article_period
WHERE page_id = %s AND valid_from <= %s AND valid_to > %s"""

PARTITION_ROWS_SQL = """SELECT PARTITION_NAME AS name, TABLE_ROWS AS approx_rows
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'article'"""

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


def connect():
    import pymysql  # imported here so the pure functions can be tested without it

    conn = pymysql.connect(
        host=ENV.get("DB_HOST", "127.0.0.1"),
        port=int(ENV.get("DB_PORT", "3307")),
        user=ENV.get("DB_USER", "root"),
        password=ENV.get("MARIADB_ROOT_PASSWORD", ""),
        database=ENV.get("DB_NAME", "timemachine"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        # The edit times were loaded in UTC, so every question is asked in UTC.
        cur.execute("SET time_zone = '+00:00'")
        cur.execute("SET SESSION TRANSACTION READ ONLY")
    return conn


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
        return row


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


def storage(conn):
    with conn.cursor() as cur:
        cur.execute(STORAGE_SQL)
        sizes = {r["name"]: r for r in cur.fetchall()}
        cur.execute(ROWS_SQL)
        return {"tables": sizes, **cur.fetchone()}


def partition_rows(conn):
    with conn.cursor() as cur:
        cur.execute(PARTITION_ROWS_SQL)
        return {r["name"]: r["approx_rows"] for r in cur.fetchall()}


def edits_per_year(conn, page_id):
    with conn.cursor() as cur:
        cur.execute(PER_YEAR_SQL, (page_id,))
        return {r["year"]: r["edits"] for r in cur.fetchall()}


# ---------------------------------------------------------------- rendering

def esc(value):
    return html.escape(str(value), quote=True)


def nice_day(value):
    return f"{value.day} {value:%b %Y}"


def nice_time(value):
    return f"{nice_day(value)}, {value:%H:%M} UTC"


def link(params):
    return "/?" + urlencode({k: v for k, v in params.items() if v})


def city_name(title):
    """'Fez, Morocco' is the Wikipedia title; the page says 'Fez'."""
    return title.split(",")[0]


def long_day(value):
    return f"{value.day} {value:%B %Y}"


def render_ask(all_pages, page_id, day, compare, view, today):
    """The question as a sentence. Native controls are the fallback without
    JavaScript; app.js replaces them with a searchable city list and a calendar."""
    options = "".join(
        f'<option value="{p["page_id"]}" data-revisions="{p["revisions"]}" '
        f'data-first="{p["first_edit"].date().isoformat()}"'
        f'{" selected" if p["page_id"] == page_id else ""}>{esc(city_name(p["title"]))}</option>'
        for p in all_pages
    )
    limits = f'min="{FIRST_DAY}" max="{today.isoformat()}"'
    keep_view = f'<input type="hidden" name="view" value="{view}">' if view == "changes" else ""
    return f"""
<form class="ask" method="get" action="/">
  <p class="sentence">
    <span>Show me</span>
    <span class="field" data-kind="city"><select name="city" class="native" aria-label="City">{options}</select></span>
    <span>as it was on</span>
    <span class="field" data-kind="date"><input type="date" name="date" class="native" aria-label="Date"
      value="{day.isoformat()}" {limits} required></span>
  </p>
  <p class="sentence second">
    <span>and compare it with</span>
    <span class="field" data-kind="date" data-optional="1"><input type="date" name="compare" class="native"
      aria-label="Second date" value="{compare.isoformat() if compare else ''}" {limits}></span>
  </p>
  {keep_view}
  <button type="submit" class="go">Travel</button>
</form>"""


def render_strip(per_year, page_id, day, compare, today):
    """Edits per year, one bar per year; a click opens 1 July of that year."""
    years = list(range(FIRST_DAY.year, today.year + 1))
    top = max(per_year.values() or [1])
    bars = []
    for year in years:
        n = per_year.get(year, 0)
        cls = "on" if year == day.year else ("cmp" if compare and year == compare.year else "")
        href = link({"city": page_id, "date": f"{year}-07-01", "compare": compare and compare.isoformat()})
        label = f"{year}: {n:,} edit{'s' if n != 1 else ''}"
        bars.append(
            f'<a class="{cls}" href="{esc(href)}" title="{label}" aria-label="{label}">'
            f'<i style="--h:{n / top:.3f}"></i><b>{year if year % 5 == 0 else ""}</b></a>'
        )
    return f"""
<nav class="strip" style="--years:{len(years)}" aria-label="Edits per year">{''.join(bars)}</nav>"""


SQL_WORDS = re.compile(r"\b(SELECT|FROM|FOR SYSTEM_TIME AS OF TIMESTAMP|AS|LEFT JOIN|ON|WHERE|AND)\b")


def highlight(sql):
    return SQL_WORDS.sub(r"<b>\1</b>", esc(sql))


def render_partitions(read, rows):
    """The 27 partitions of article, lit when this query read them."""
    names = [f"p{i}" for i in range(26)] + ["pn"]
    cells = []
    for n in names:
        year = "current rows" if n == "pn" else f"ended in {2001 + int(n[1:])}"
        approx = rows.get(n)
        tip = f"{n}: versions that {year}" if n != "pn" else "pn: the current rows"
        if approx is not None:
            tip += f", about {approx:,} rows"
        cells.append(f'<i class="{"read" if n in read else ""}" title="{tip}"></i>')
    return (f'<div class="parts">{"".join(cells)}</div>'
            '<div class="parts-axis"><span>2001</span><span>2013</span><span>now</span></div>')


IP_ADDRESS = re.compile(r"^(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9A-Fa-f:]+:[0-9A-Fa-f:]+)$")


def editor_kind(name):
    if not name:
        return "name hidden by Wikipedia"
    if IP_ADDRESS.match(name):
        return "not logged in, an IP address"
    if re.search(r"bot\b", name, re.I):
        return "a bot"
    return "a registered editor"


def span(delta):
    """A length of time in the largest unit that fits: "19 hours", "3 months"."""
    hours = delta.total_seconds() / 3600
    for size, unit in ((24 * 365, "year"), (24 * 30, "month"), (24, "day"), (1, "hour")):
        if hours >= size:
            n = int(hours // size)
            return f"{n} {unit}{'s' if n != 1 else ''}"
    return "less than an hour"


def render_card(v, page, day, label=None, tone=""):
    """The facts about the version on show, set as a card on top of the article."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    still = v["row_end"].year >= STILL_LIVE
    live = (f"still live, {span(now - v['row_start'])} so far" if still
            else f"until {nice_time(v['row_end'])}, {span(v['row_end'] - v['row_start'])}")
    grew = ""
    if v["prev"] and v["prev"]["bytes"] is not None:
        d = v["bytes"] - v["prev"]["bytes"]
        grew = f"this edit {'added' if d >= 0 else 'removed'} {abs(d):,} bytes"
    age = span(dt.datetime.combine(day, dt.time(23, 59)) - page["first_edit"])
    head = f'<p class="card-label">{esc(label)}</p>' if label else ""
    return f"""
<section class="card {tone}" aria-label="About this version">
  {head}
  <dl>
    <div><dt>Revision</dt><dd><a href="https://en.wikipedia.org/w/index.php?oldid={v["rev_id"]}">{v["rev_id"]}</a></dd>
      <dd class="sub">version {v["versions"]:,} of {page["revisions"]:,}</dd></div>
    <div><dt>Edited by</dt><dd class="editor">{esc(v["editor"] or "hidden")}</dd><dd class="sub">{editor_kind(v["editor"])}</dd></div>
    <div><dt>Size</dt><dd>{v["bytes"]:,} bytes</dd><dd class="sub">{grew or "the first version"}</dd></div>
    <div><dt>Live from</dt><dd>{nice_time(v["row_start"])}</dd><dd class="sub">{live}</dd></div>
    <div><dt>Article age</dt><dd>{age}</dd><dd class="sub">{v["editors"]:,} different editors so far</dd></div>
  </dl>
</section>"""


def render_notes(v):
    notes = []
    if v["text_rev_id"] != v["rev_id"] and v["text_date"]:
        notes.append(f"The text is the stored copy from {nice_day(v['text_date'])}: one text per quarter is stored, "
                     "and the revision link opens this exact version.")
    notes.append("Pictures load from Wikipedia as the files are today. Infoboxes and other templates are left out.")
    return f'<p class="fine notes">{" ".join(notes)}</p>'


def clean_condition(text):
    text = text.replace("TIMESTAMP/*WITH LOCAL TIME ZONE*/", "TIMESTAMP ")
    return re.sub(r" and ", "\nAND ", text)


def render_hood(v, page_id, day, compare, part_rows, store):
    def jump(found, word):
        if not found:
            return f"<dd>none, this is the {word} version</dd>"
        target = found["row_start"].date().isoformat()
        href = link({"city": page_id, "date": target, "compare": compare and compare.isoformat()})
        return (f'<dd><a href="{esc(href)}">{found["rev_id"]}</a>'
                f'<span>{nice_time(found["row_start"])}</span></dd>')

    an = v["analyze"]
    a, t = an["tables"].get("a", {}), an["tables"].get("t", {})
    real = {name: info for name, info in an["tables"].items()}
    plan_rows = "".join(
        f'<tr><td>{esc(p["table"])}</td><td>{esc(p["type"])}</td><td>{esc(p["key"] or "")}</td>'
        f'<td>{esc(p["rows"])}</td><td>{esc(real.get(p["table"], {}).get("r_rows", ""))}</td>'
        f'<td>{esc(real.get(p["table"], {}).get("pages", ""))}</td></tr>'
        for p in v["plan"]
    )
    agree = v["period_rev"] == v["rev_id"]
    check = (f'<p class="check ok">Same revision, {v["period_rev"]}.</p>' if agree
             else f'<p class="check bad">Different: {v["period_rev"]}.</p>')
    raw_end = f'{v["row_end"]:%Y-%m-%d %H:%M:%S.%f}'
    end_note = ("The maximum TIMESTAMP: MariaDB's way of saying the row is current."
                if v["row_end"].year >= STILL_LIVE else "The moment the next edit replaced it.")
    used = len(v["partitions"])
    read = a.get("r_rows") or 0
    kept = f'{a["r_filtered"]:.2f}%' if a.get("r_filtered") is not None else "?"
    text_note = ("its own text" if v["text_rev_id"] == v["rev_id"]
                 else f"the stored text of revision {v['text_rev_id']}")
    tables = store["tables"]
    mb = lambda name: f'{(tables.get(name, {}).get("size") or 0) / 1e6:.1f} MB'
    history = store["all_rows"] - store["current_rows"]
    return f"""
<aside class="hood" aria-label="How MariaDB answered">
  <h2>Under the hood</h2>

  <section>
    <h3>The query</h3>
    <pre class="code"><code>{highlight(v["sql"])}</code></pre>
    <p class="fine">Answered in {v["ms"]:.1f} ms, measured by the page. MariaDB's own count:
    {an["ms"]:.2f} ms, of which {an["plan_ms"]:.2f} ms to plan it.</p>
  </section>

  <section>
    <h3>What MariaDB did</h3>
    <ol class="steps">
      <li>Took the end of your day as the moment to ask about:
        <code>{end_of(day)}</code> UTC.</li>
      <li>Turned <code>AS OF</code> into a plain condition on the two hidden columns:
        <pre class="code"><code>{highlight(clean_condition(a.get("condition", "")))}</code></pre>
        A version counts when it started by that moment and ended after it.</li>
      <li>Skipped {27 - used} of the 27 partitions: they only hold versions that had already ended.
        It opened the other {used}.
        {render_partitions(v["partitions"], part_rows)}</li>
      <li>Used the primary key <code>({", ".join(a.get("parts", [])) or "page_id, row_end"})</code> to read only
        {esc(city_name(v.get("title", "")) or "this city")}'s versions that ended after that moment:
        <strong>{read:,} rows</strong>, {a.get("pages") or "?"} pages of disk.</li>
      <li>Kept the rows that had also started by then: <strong>1 row</strong> ({kept} of what it read).
        This is revision {v["rev_id"]}.</li>
      <li>Fetched {text_note} from <code>revision_text</code> by its primary key
        ({t.get("access") or "eq_ref"}, {t.get("r_rows") or 1} row).</li>
    </ol>
    <p class="fine">From <code>ANALYZE FORMAT=JSON</code>, which runs the query and counts. Older dates read more
    rows: the key starts at <code>row_end</code>, so every version that ended after your date is a candidate.</p>
  </section>

  <section>
    <h3>Query plan</h3>
    <table class="plan"><thead><tr><th>table</th><th>type</th><th>key</th><th>guessed</th><th>read</th><th>pages</th></tr></thead>
    <tbody>{plan_rows}</tbody></table>
    <p class="fine"><code>EXPLAIN PARTITIONS</code> guesses the rows before running;
    <code>ANALYZE</code> counts them after.</p>
  </section>

  <section>
    <h3>This row in system time</h3>
    <dl class="raw">
      <dt><code>row_start</code></dt><dd><code>{v["row_start"]:%Y-%m-%d %H:%M:%S.%f}</code></dd>
      <dt><code>row_end</code></dt><dd><code>{raw_end}</code></dd>
    </dl>
    <p class="fine">Both columns are <code>INVISIBLE</code>: <code>SELECT *</code> does not show them.
    {end_note}</p>
  </section>

  <section>
    <h3>Before and after</h3>
    <dl class="near">
      <dt>Previous version</dt>{jump(v["prev"], "first")}
      <dt>Next version</dt>{jump(v["next"], "latest")}
      <dt>Edits on {nice_day(day)}</dt><dd>{v["that_day"]}</dd>
    </dl>
    <p class="fine">Read with <code>FOR SYSTEM_TIME ALL</code> and <code>BETWEEN</code>.</p>
  </section>

  <section>
    <h3>Cross-check</h3>
    <p class="fine">The same moment asked to <code>article_period</code>, the bitemporal copy that keeps the edit
    times as application time:</p>
    {check}
  </section>

  <section>
    <h3>What is stored</h3>
    <dl class="near">
      <dt><code>article</code></dt><dd>{store["all_rows"]:,} rows, {mb("article")}<span>{store["current_rows"]} current, {history:,} history</span></dd>
      <dt><code>revision_text</code></dt><dd>about {(tables.get("revision_text", {}).get("approx_rows") or 0):,} texts, {mb("revision_text")}<span>one per article per quarter</span></dd>
      <dt><code>article_period</code></dt><dd>about {(tables.get("article_period", {}).get("approx_rows") or 0):,} rows, {mb("article_period")}<span>application time plus its own system time</span></dd>
      <dt>Server</dt><dd>MariaDB {esc(store["version"].split("-")[0])}<span>session in UTC, read only</span></dd>
    </dl>
  </section>
</aside>"""


def file_url(name, width=640):
    """Wikipedia serves any file by name, so no image is stored in the database."""
    return f"https://en.wikipedia.org/wiki/Special:FilePath/{quote(name.replace(' ', '_'))}?width={width}"


def render_image(text):
    name, caption = wikitext.image(text)
    page = "https://en.wikipedia.org/wiki/File:" + quote(name.replace(" ", "_"))
    # a file deleted since then gives an error, so the figure hides itself
    return (f'<figure class="img"><a href="{esc(page)}"><img src="{esc(file_url(name))}" alt="{esc(caption or name)}" '
            f'loading="lazy" onerror="this.closest(\'figure\').hidden=true"></a>'
            + (f"<figcaption>{esc(caption)}</figcaption>" if caption else "") + "</figure>")


def render_table(text):
    caption, rows = wikitext.table(text)
    body = "".join(
        "<tr>" + "".join(f"<{'th' if head else 'td'}>{esc(cell)}</{'th' if head else 'td'}>" for head, cell in row) + "</tr>"
        for row in rows)
    return (f'<div class="table"><table>{f"<caption>{esc(caption)}</caption>" if caption else ""}'
            f"{body}</table></div>")


def render_block(kind, text):
    if kind in ("img", "gimg"):
        return render_image(text)
    if kind == "table":
        return render_table(text)
    tag = {"h": "h3", "li": "li", "p": "p"}[kind]
    return f"<{tag}>{esc(text)}</{tag}>"


def render_blocks(blocks, limit=None):
    """The article as HTML. List items go in a list, gallery images in a grid."""
    out, shown = [], blocks if limit is None else blocks[:limit]
    group = None
    for kind, text in shown:
        wrap = {"li": "ul", "gimg": "gallery"}.get(kind)
        if wrap != group:
            if group:
                out.append("</ul>" if group == "ul" else "</div>")
            if wrap:
                out.append("<ul>" if wrap == "ul" else '<div class="gallery">')
            group = wrap
        out.append(render_block(kind, text))
    if group:
        out.append("</ul>" if group == "ul" else "</div>")
    return "\n".join(out)


def render_diff(changes):
    out = []
    for op, kind, parts in changes:
        if op == "skip":
            out.append(f'<p class="skip">{parts} unchanged block{"s" if parts != 1 else ""}</p>')
        elif op in ("del", "add") and kind in wikitext.MEDIA:
            out.append(f'<div class="{op} k-{kind}">{render_block(kind, parts)}</div>')
        elif op in ("del", "add"):
            out.append(f'<p class="{op} k-{kind}">{esc(parts)}</p>')
        else:
            words = "".join(
                f"<{'del' if w == 'del' else 'ins'}>{esc(t)}</{'del' if w == 'del' else 'ins'}> " if w != "same" else f"{esc(t)} "
                for w, t in parts
            )
            out.append(f'<p class="mod k-{kind}">{words}</p>')
    return "\n".join(out)


def render_words(parts):
    out = []
    for op, text in parts:
        tag = {"del": "del", "add": "ins"}.get(op)
        out.append(f"<{tag}>{esc(text)}</{tag}>" if tag else esc(text))
    return " ".join(out)


def render_side_by_side(rows, old_label, new_label):
    cells = [f'<div class="col-head">{old_label}</div><div class="col-head">{new_label}</div>']
    for row in rows:
        if row[0] == "skip":
            n = row[1]
            cells.append(f'<p class="skip wide">{n} unchanged block{"s" if n != 1 else ""}</p>')
            continue
        for side, label in zip(row[1:], (old_label, new_label)):
            if side is None:
                cells.append('<div class="cell none"></div>')
                continue
            kind, parts = side
            ops = {op for op, _ in parts}
            whole = "del" if ops == {"del"} else "add" if ops == {"add"} else ""
            # images and tables come whole, never as a word diff
            inner = render_block(kind, parts[0][1]) if kind in wikitext.MEDIA else render_words(parts)
            # data-side labels each cell when the two columns stack on a phone
            cells.append(f'<div class="cell k-{kind} {whole}" data-side="{label}">{inner}</div>')
    return f'<article class="sbs">{"".join(cells)}</article>'


def render_compare(first, second, view, params, cards=""):
    (old_day, old), (new_day, new) = sorted([first, second], key=lambda x: x[0])
    wiki_diff = f"https://en.wikipedia.org/w/index.php?diff={new['rev_id']}&oldid={old['rev_id']}"
    grew = new["bytes"] - old["bytes"]
    head = (
        f'<h2 class="diff-title">What changed between {long_day(old_day)} and {long_day(new_day)}</h2>'
        f'<p class="diff-sub">Revision {old["rev_id"]} to {new["rev_id"]}, '
        f'{"+" if grew >= 0 else "−"}{abs(grew):,} bytes.</p>'
    ) + (f'<div class="cards">{cards}</div>' if cards else "")
    if old["rev_id"] == new["rev_id"]:
        return head + '<p class="empty">The same version was live on both dates: nobody edited the article in between.</p>'
    links = f'<a href="{esc(wiki_diff)}">exact diff on Wikipedia</a>'
    if old["text_rev_id"] == new["text_rev_id"]:
        return head + (
            f'<p class="note">Both versions fall back to the same stored text, so there is nothing to compare here. '
            f'Only one text per quarter is stored. See the {links}.</p>'
        )
    changes = wikitext.diff(wikitext.clean(old["body"]), wikitext.clean(new["body"]))
    tabs = "".join(
        f'<a class="tab{" on" if view == key else ""}" href="{esc(link({**params, "view": key}))}">{label}</a>'
        for key, label in (("side", "Side by side"), ("changes", "Changes only"))
    )
    if view == "side":
        old_label = f"{nice_day(old_day)}, {old['bytes']:,} bytes"
        new_label = f"{nice_day(new_day)}, {new['bytes']:,} bytes"
        shown = render_side_by_side(wikitext.side_by_side(changes), old_label, new_label)
    else:
        shown = f'<article class="diff">{render_diff(changes)}</article>'
    return head + (
        f'<div class="diff-bar"><nav class="tabs">{tabs}</nav>'
        f'<p class="legend"><del>removed</del> <ins>added</ins> Compared on the stored texts, see the {links}.</p></div>'
        f'{shown}'
    )


def render_page(params):
    conn = connect()
    try:
        all_pages = pages(conn)
        by_id = {p["page_id"]: p for p in all_pages}
        default = next((p["page_id"] for p in all_pages if p["title"] == "Rabat"), all_pages[0]["page_id"])
        try:
            page_id = int(params.get("city", [default])[0])
        except ValueError:
            page_id = default
        page_id = page_id if page_id in by_id else default
        day = parse_day(params.get("date", [""])[0]) or dt.date(2010, 1, 1)
        compare = parse_day(params.get("compare", [""])[0])
        view = "changes" if params.get("view", [""])[0] == "changes" else "side"
        page = by_id[page_id]

        today = dt.datetime.now(dt.timezone.utc).date()
        body = [render_ask(all_pages, page_id, day, compare, view, today)]
        body.append(render_strip(edits_per_year(conn, page_id), page_id, day, compare, today))

        v = version_at(conn, page_id, day)
        if v is not None:
            v["title"] = page["title"]
        if v is None:
            first = page["first_edit"]
            body.append(
                f'<section class="empty"><h2>{esc(city_name(page["title"]))} had no Wikipedia article yet on {long_day(day)}.</h2>'
                f'<p>The first edit was made on {long_day(first)}. '
                f'<a href="{esc(link({"city": page_id, "date": first.date().isoformat()}))}">Open the first version</a></p></section>'
            )
        elif compare:
            w = version_at(conn, page_id, compare)
            if w is None:
                main = (f'<section class="empty"><h2>There was no article yet on {long_day(compare)}.</h2>'
                        f'<p>Pick a second date after {long_day(page["first_edit"])}.</p></section>')
            else:
                cards = (render_card(v, page, day, f"First date, {long_day(day)}", "first")
                         + render_card(w, page, compare, f"Second date, {long_day(compare)}", "second"))
                main = render_compare((day, v), (compare, w), view,
                                      {"city": page_id, "date": day.isoformat(), "compare": compare.isoformat()}, cards)
            hood = render_hood(v, page_id, day, compare, partition_rows(conn), storage(conn))
            body.append(f'<div class="reading"><section class="compare">{main}</section>{hood}</div>')
        else:
            hood = render_hood(v, page_id, day, compare, partition_rows(conn), storage(conn))
            body.append(
                f'<div class="reading"><div class="main">{render_card(v, page, day)}'
                f'<article class="text"><h1 class="article-title">{esc(city_name(page["title"]))}</h1>'
                f'{render_notes(v)}{render_blocks(wikitext.clean(v["body"]))}</article></div>{hood}</div>'
            )
        title = f"{city_name(page['title'])}, {nice_day(day)}"
        return layout(title, "\n".join(body))
    finally:
        conn.close()


def layout(title, body):
    here = pathlib.Path(__file__).parent
    css = (here / "style.css").read_text()
    js = (here / "app.js").read_text()
    logo = (here / "logo.svg").read_text().strip()
    # the favicon follows the browser's light or dark theme
    favicon = logo.replace("currentColor", "#1c1f3b").replace(
        "<path", "<style>@media (prefers-color-scheme: dark){.logo-page{fill:#e6e7f2}.logo-clock{fill:#9a90ff}}</style><path", 1)
    icon = "data:image/svg+xml," + quote(favicon)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} | time machine</title>
<link rel="icon" href="{icon}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Naskh+Arabic:wght@400;600&family=Noto+Sans+Tifinagh&family=Schibsted+Grotesk:wght@400;500;600;700;800&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap">
<style>{css}</style>
<script>(function () {{
  var root = document.documentElement, saved = null;
  root.classList.add("js");
  try {{ saved = localStorage.getItem("theme"); }} catch (e) {{}}
  if (saved === "light" || saved === "dark") root.dataset.theme = saved;
  root.dataset.mode = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}})()</script>
</head>
<body>
<header class="top">
  <a class="brand" href="/">{logo}<span>time machine</span></a>
  <p class="about">The Wikipedia articles of 45 Moroccan cities, every edit since 2001, kept by MariaDB.</p>
  <button class="theme" type="button" aria-label="Dark mode" aria-pressed="false">
    <svg class="moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"/></svg>
    <svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
    <span>Dark</span>
  </button>
</header>
<main>
{body}
</main>
<footer>Article text from Wikipedia, CC BY-SA 4.0, by its authors.
History kept by one MariaDB table <code>WITH SYSTEM VERSIONING</code>.</footer>
<script>{js}</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/":
            self.send_error(404)
            return
        try:
            page = render_page(parse_qs(url.query))
            status = 200
        except Exception as exc:  # show the reason instead of an empty page
            page = layout("Error", f'<p class="empty">The database did not answer: {esc(exc)}. '
                                   f'Is it running? Try <code>docker compose up --wait</code>.</p>')
            status = 500
        data = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    port = int(ENV.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Open http://127.0.0.1:{port}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
