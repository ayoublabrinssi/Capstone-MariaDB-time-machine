"""The time machine page: pick a city and a date, see its article that day.

Python standard library plus PyMySQL. Start it with scripts/run.sh, then open
http://127.0.0.1:8000. Every question goes to MariaDB as one query with
FOR SYSTEM_TIME AS OF; the page shows that query next to the article.

  db.py        the SQL and the functions that ask MariaDB
  exact.py     the exact text of a revision, fetched from Wikipedia once and kept
  views.py     the HTML
  wikitext.py  wikitext to plain blocks, and the diff
  server.py    this file: one request in, one page out

Settings come from .env in the repository root or from the environment, see
db.py. PORT (8000) is the port of the page.
"""
import datetime as dt
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import db
import exact
import views
import wikitext
from views import city_name, esc, link, long_day, nice_day


def render_page(params):
    conn = db.connect()
    try:
        all_pages = db.pages(conn)
        by_id = {p["page_id"]: p for p in all_pages}
        default = next((p["page_id"] for p in all_pages if p["title"] == "Rabat"), all_pages[0]["page_id"])
        try:
            page_id = int(params.get("city", [default])[0])
        except ValueError:
            page_id = default
        page_id = page_id if page_id in by_id else default
        day = db.parse_day(params.get("date", [""])[0]) or dt.date(2010, 1, 1)
        compare = db.parse_day(params.get("compare", [""])[0])
        view = "changes" if params.get("view", [""])[0] == "changes" else "side"
        page = by_id[page_id]

        today = dt.datetime.now(dt.timezone.utc).date()
        body = [views.render_ask(all_pages, page_id, day, compare, view, today)]
        body.append(views.render_strip(db.edits_per_year(conn, page_id), page_id, day, compare, today))
        body.append(views.render_wars(db.edit_wars(conn, page_id), page_id, compare))

        v = db.version_at(conn, page_id, day)
        if v is not None:
            v["title"] = page["title"]
            exact.fill(conn, v)
        if v is None:
            first = page["first_edit"]
            body.append(
                f'<section class="empty"><h2>{esc(city_name(page["title"]))} had no Wikipedia article yet on {long_day(day)}.</h2>'
                f'<p>The first edit was made on {long_day(first)}. '
                f'<a href="{esc(link({"city": page_id, "date": first.date().isoformat()}))}">Open the first version</a></p></section>'
            )
        elif compare:
            w = db.version_at(conn, page_id, compare)
            if w is None:
                main = (f'<section class="empty"><h2>There was no article yet on {long_day(compare)}.</h2>'
                        f'<p>Pick a second date after {long_day(page["first_edit"])}.</p></section>')
            else:
                exact.fill(conn, w)
                cards = (views.render_card(v, page, day, f"First date, {long_day(day)}", "first")
                         + views.render_card(w, page, compare, f"Second date, {long_day(compare)}", "second"))
                main = views.render_compare((day, v), (compare, w), view,
                                            {"city": page_id, "date": day.isoformat(), "compare": compare.isoformat()}, cards)
            hood = views.render_hood(v, page_id, day, compare, db.partitions(conn), db.storage(conn))
            body.append(f'<div class="reading"><section class="compare">{main}</section>{hood}</div>')
        else:
            hood = views.render_hood(v, page_id, day, compare, db.partitions(conn), db.storage(conn))
            body.append(
                f'<div class="reading"><div class="main">{views.render_card(v, page, day)}'
                f'<article class="text"><h1 class="article-title">{esc(city_name(page["title"]))}</h1>'
                f'{views.render_notes(v)}{views.render_blocks(wikitext.clean(v["body"]))}</article></div>{hood}</div>'
            )
        title = f"{city_name(page['title'])}, {nice_day(day)}"
        return views.layout(title, "\n".join(body), len(all_pages))
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/":
            self.send_error(404)
            return
        try:
            page = render_page(parse_qs(url.query))
            status = 200
        except Exception as exc:
            # The full reason goes to the terminal, never to the browser.
            traceback.print_exc()
            if db.is_database_error(exc):
                status = 503
                message = ("The database did not answer. Is it running and loaded? Try "
                           "<code>docker compose up --wait</code>, then <code>scripts/install.sh</code>.")
            else:
                status = 500
                message = ("The page could not build this view. The reason is in the terminal "
                           "where <code>scripts/run.sh</code> is running.")
            page = views.layout("Error", f'<p class="empty">{message}</p>')
        data = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    port = int(db.ENV.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Open http://127.0.0.1:{port}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
