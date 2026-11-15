"""The HTML side of the page: every function takes data and returns markup.
Nothing here talks to the database."""
import datetime as dt
import html
import pathlib
import re
from urllib.parse import quote, urlencode

import wikitext
from db import FIRST_DAY, end_of, is_current


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


def render_wars(days, page_id, compare):
    """The days with the most reverts, each a link to that day."""
    if not days:
        return ""
    items = []
    for d in days:
        href = link({"city": page_id, "date": d["day"].isoformat(), "compare": compare and compare.isoformat()})
        items.append(f'<li><a href="{esc(href)}">{nice_day(d["day"])}</a>'
                     f'<span>{d["edits"]} edits, {int(d["reverts"])} reverts, {d["editors"]} editors</span></li>')
    return f"""
<aside class="wars" aria-label="Edit wars">
  <h2>Edit wars</h2>
  <ul>{''.join(items)}</ul>
  <p class="fine">Days with the most reverts, from the edit comments in the full history
  (<code>FOR SYSTEM_TIME ALL</code>, grouped by day). Click one to read what was live at the end of it.</p>
</aside>"""


SQL_WORDS = re.compile(r"\b(SELECT|FROM|FOR SYSTEM_TIME AS OF TIMESTAMP|AS|LEFT JOIN|ON|WHERE|AND)\b")


def highlight(sql):
    return SQL_WORDS.sub(r"<b>\1</b>", esc(sql))


def render_partitions(read, parts):
    """One cell per partition of article, lit when this query read it."""
    cells, years = [], []
    for part in parts:
        name, ends = part["name"], str(part["ends_before"])
        if ends[:4].isdigit():
            year = int(ends[:4]) - 1       # the partition ends before 1 January of the next year
            years.append(year)
            tip = f"{name}: versions that ended in {year}"
        else:
            tip = f"{name}: the current rows"
        if part["approx_rows"] is not None:
            tip += f", about {part['approx_rows']:,} rows"
        cells.append(f'<i class="{"read" if name in read else ""}" title="{tip}"></i>')
    first = years[0] if years else ""
    middle = years[len(years) // 2] if years else ""
    return (f'<div class="parts" style="--parts:{len(cells)}">{"".join(cells)}</div>'
            f'<div class="parts-axis"><span>{first}</span><span>{middle}</span><span>now</span></div>')


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
    still = is_current(v["row_end"])
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


WHY_OLDER = {
    "off": "exact texts are switched off (EXACT_TEXT=off)",
    "offline": "Wikipedia could not be reached for this exact revision",
    "hidden": "Wikipedia no longer gives out the text of this revision",
}


def render_notes(v):
    notes = []
    source = v.get("text_from", "older")
    if source in ("kept", "fetched"):
        notes.append(f"This is the exact text of revision {v['rev_id']}. It is not one of the texts the load stores "
                     "(one per quarter), so the page asked Wikipedia for it once and keeps it in "
                     "<code>exact_text</code>.")
    elif source == "older" and v["text_date"]:
        why = WHY_OLDER.get(v.get("text_why"), WHY_OLDER["offline"])
        notes.append(f"The text is the stored copy from {nice_day(v['text_date'])}, not this exact revision: "
                     f"{why}. The revision link opens the exact version.")
    notes.append("Pictures load from Wikipedia as the files are today. Infoboxes and other templates are left out.")
    return f'<p class="fine notes">{" ".join(notes)}</p>'


def clean_condition(text):
    text = text.replace("TIMESTAMP/*WITH LOCAL TIME ZONE*/", "TIMESTAMP ")
    return re.sub(r" and ", "\nAND ", text)


def render_hood(v, page_id, day, compare, parts, store):
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
    n_session = len(v["session_partitions"])
    session = (f'<p class="check ok">Same revision, {v["session_rev"]}, and the same {n_session} partitions opened.</p>'
               if v["session_rev"] == v["rev_id"]
               else f'<p class="check bad">Different: {v["session_rev"]}.</p>')
    first = (f'<p class="check ok">Same revision, {v["first_rev"]}. It read {v["first_rows"]:,.0f} row'
             f'{"" if v["first_rows"] == 1 else "s"} where <code>AS OF</code> read {a.get("r_rows") or 0:,}.</p>'
             if v["first_rev"] == v["rev_id"]
             else f'<p class="check bad">Different: {v["first_rev"]}.</p>')
    raw_end = f'{v["row_end"]:%Y-%m-%d %H:%M:%S.%f}'
    end_note = ("The maximum TIMESTAMP: MariaDB's way of saying the row is current."
                if is_current(v["row_end"]) else "The moment the next edit replaced it.")
    used = len(v["partitions"])
    read = a.get("r_rows") or 0
    kept = f'{a["r_filtered"]:.2f}%' if a.get("r_filtered") is not None else "?"
    text_note = ("its own text" if v["text_rev_id"] == v["rev_id"]
                 else f"the stored text of revision {v['text_rev_id']}")
    swap = ""
    if v.get("text_from") in ("kept", "fetched"):
        swap = (f'<li>That stored text is an older copy, so the page read the exact text of revision {v["rev_id"]} '
                f'from <code>exact_text</code> instead'
                + (", after asking Wikipedia for it." if v["text_from"] == "fetched" else ".") + "</li>")
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
      <li>Skipped {len(parts) - used} of the {len(parts)} partitions: they only hold versions that had already ended.
        It opened the other {used}.
        {render_partitions(v["partitions"], parts)}</li>
      <li>Used the primary key <code>({", ".join(a.get("parts", [])) or "page_id, row_end"})</code> to read only
        {esc(city_name(v.get("title", "")) or "this city")}'s versions that ended after that moment:
        <strong>{read:,} rows</strong>, {a.get("pages") or "?"} pages of disk.</li>
      <li>Kept the rows that had also started by then: <strong>1 row</strong> ({kept} of what it read).
        This is revision {v["rev_id"]}.</li>
      <li>Fetched {text_note} from <code>revision_text</code> by its primary key
        ({t.get("access") or "eq_ref"}, {t.get("r_rows") or 1} row).</li>
      {swap}
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
    <h3>A shorter way</h3>
    <p class="fine">Versions of one article never overlap, so the one live at a moment is the first one
    that ended after it. Reading the key in order and stopping at the first row is enough:</p>
    <pre class="code"><code>{highlight(v["first_sql"])}</code></pre>
    {first}
    <p class="fine"><code>AS OF</code> cannot stop early today: the server does not know the versions of a key
    never overlap. Numbers for every date in docs/measurements.md.</p>
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
    <p class="fine">And with no <code>AS OF</code> in the query at all. One session setting moves every query to that
    moment, the way a whole site could travel in time:</p>
    <pre class="code"><code><b>SET</b> @@system_versioning_asof = '{end_of(day)}';
<b>SELECT</b> rev_id <b>FROM</b> article <b>WHERE</b> page_id = {page_id};</code></pre>
    {session}
  </section>

  <section>
    <h3>What is stored</h3>
    <dl class="near">
      <dt><code>article</code></dt><dd>{store["all_rows"]:,} rows, {mb("article")}<span>{store["current_rows"]} current, {history:,} history</span></dd>
      <dt><code>revision_text</code></dt><dd>about {(tables.get("revision_text", {}).get("approx_rows") or 0):,} texts, {mb("revision_text")}<span>one per article per quarter</span></dd>
      <dt><code>exact_text</code></dt><dd>{store.get("exact_texts", 0):,} texts, {mb("exact_text")}<span>exact revisions fetched when first opened</span></dd>
      <dt><code>article_period</code></dt><dd>about {(tables.get("article_period", {}).get("approx_rows") or 0):,} rows, {mb("article_period")}<span>application time plus its own system time</span></dd>
      <dt>Server</dt><dd>MariaDB {esc(store["version"].split("-")[0])}<span>session in UTC, read only, as a user that may only read and add to the text cache</span></dd>
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
    exact_both = old.get("text_from") != "older" and new.get("text_from") != "older"
    if not exact_both and old["text_rev_id"] == new["text_rev_id"] and old["body"] == new["body"]:
        return head + (
            f'<p class="note">Both versions fall back to the same stored text, so there is nothing to compare here. '
            f'The exact texts could not be fetched from Wikipedia. See the {links}.</p>'
        )
    basis = "the exact texts of both revisions" if exact_both else "the stored texts"
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
        f'<p class="legend"><del>removed</del> <ins>added</ins> Compared on {basis}, see the {links}.</p></div>'
        f'{shown}'
    )



def layout(title, body, cities=None):
    """cities is the number of articles loaded: 45, or 3 with the sample. None when the database did not answer."""
    about = f"The Wikipedia articles of {cities} Moroccan cities" if cities else "The Wikipedia articles of Moroccan cities"
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
  <p class="about">{about}, every edit since 2001, kept by MariaDB.</p>
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

