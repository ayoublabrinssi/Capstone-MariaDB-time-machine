"""Tests for the page: the wikitext cleaner, the diff, the date input, the
exact text of a revision, the error page, and the page against the database
(those are skipped when it is not running).

    python3 -m unittest discover -s tests      (or scripts/test.sh)
"""
import contextlib
import datetime as dt
import io
import pathlib
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "app"))

import db  # noqa: E402
import exact  # noqa: E402
import server  # noqa: E402
import views  # noqa: E402
import wikitext  # noqa: E402

# The tests never call Wikipedia. Where the exact text matters, a stand-in
# answers in its place.
db.ENV["EXACT_TEXT"] = "off"


class CleanTest(unittest.TestCase):
    def test_links_keep_their_label(self):
        self.assertEqual(wikitext.clean("The [[Bou Regreg|river]] and [[Salé]]."),
                         [("p", "The river and Salé.")])

    def test_templates_refs_categories_and_interwiki_are_dropped(self):
        text = ("{{Infobox {{nested}} }}Rabat<ref>source</ref> is a city."
                "[[Category:Cities]]\n[[fr:Rabat]]")
        self.assertEqual(wikitext.clean(text), [("p", "Rabat is a city.")])

    def test_images_keep_their_caption(self):
        text = "Rabat is a city.[[File:A_b.jpg|thumb|upright=1.2|left|a [[Chellah|link]] in a caption]] More."
        self.assertEqual(wikitext.clean(text), [
            ("p", "Rabat is a city."), ("img", "A b.jpg\na link in a caption"), ("p", "More.")])
        self.assertEqual(wikitext.image("A b.jpg\na link in a caption"), ("A b.jpg", "a link in a caption"))

    def test_gallery_and_infobox_photo(self):
        text = ("{{Infobox settlement\n| image_skyline = Skyline.jpg\n| caption_skyline = The [[Kasbah]]\n}}\n"
                "Intro.\n<gallery>\nFile:One.jpg|First\nImage:Two.png\n</gallery>")
        self.assertEqual(wikitext.clean(text), [
            ("img", "Skyline.jpg\nThe Kasbah"), ("p", "Intro."), ("gimg", "One.jpg\nFirst"), ("gimg", "Two.png\n")])

    def test_headings_lists_and_paragraphs(self):
        text = "Intro line one\nline two\n\n== History ==\n* first\n* second\nEnd."
        self.assertEqual(wikitext.clean(text), [
            ("p", "Intro line one line two"),
            ("h", "History"),
            ("li", "first"),
            ("li", "second"),
            ("p", "End."),
        ])

    def test_names_in_other_languages_are_kept(self):
        text = ("Rabat ({{IPAc-en|r|ə|ˈ|b|ɑː|t}}, also {{IPAc-en|r|ɑː}}; {{lang-ar|الرباط|translit=ar-Ribāṭ}}; "
                "{{lang-ber|ⵕⵕⴱⴰⵟ}}) is the capital. Tangier ({{lang|ar|طنجة}}) too.")
        self.assertEqual(wikitext.clean(text), [(
            "p", "Rabat (Arabic: الرباط, ar-Ribāṭ; Berber: ⵕⵕⴱⴰⵟ) is the capital. Tangier (طنجة) too.")])

    def test_empty_brackets_left_by_templates_are_removed(self):
        self.assertEqual(wikitext.clean("Fez ({{IPA-ar|fɛs}}) is a city{{cn}} , old."), [("p", "Fez is a city, old.")])

    def test_table_of_lists_becomes_a_list(self):
        text = "Twinned with:\n{| class=wikitable\n|- valign=top\n|\n* [[Tunis]], Tunisia\n* Honolulu\n||\n* Athens\n|}"
        self.assertEqual(wikitext.clean(text), [
            ("p", "Twinned with:"), ("li", "Tunis, Tunisia"), ("li", "Honolulu"), ("li", "Athens")])

    def test_converted_numbers_keep_their_value(self):
        text = "Highs reach {{cvt|17.2|°C|1}}, rising {{convert|7|-|8|C-change}} and {{cvt|11|and|19|°C|1}}."
        self.assertEqual(wikitext.clean(text), [("p", "Highs reach 17.2 °C, rising 7-8 °C and 11 and 19 °C.")])

    def test_tables_become_rows_and_cells(self):
        text = ("Before\n{| class=wikitable\n|+ Districts\n|-\n! Name !! style=\"x\" | People\n"
                "|-\n| [[Agdal Riyad]] || 77,257 {{ref}}\n|}\nAfter")
        blocks = wikitext.clean(text)
        self.assertEqual(blocks, [
            ("p", "Before"), ("table", "+Districts\n!Name\t!People\n|Agdal Riyad\t|77,257"), ("p", "After")])
        self.assertEqual(wikitext.table(blocks[1][1]),
                         ("Districts", [[(True, "Name"), (True, "People")], [(False, "Agdal Riyad"), (False, "77,257")]]))


class DiffTest(unittest.TestCase):
    def test_unchanged_blocks_are_counted(self):
        blocks = [("p", "a"), ("p", "b")]
        self.assertEqual(wikitext.diff(blocks, blocks), [("skip", None, 2)])

    def test_small_change_is_a_word_diff(self):
        out = wikitext.diff([("p", "Rabat has 500,000 people")], [("p", "Rabat has 600,000 people")])
        self.assertEqual(out, [("mod", "p", [
            ("same", "Rabat has"), ("del", "500,000"), ("add", "600,000"), ("same", "people")])])

    def test_rewrite_is_a_delete_and_an_add(self):
        out = wikitext.diff([("p", "old text entirely")], [("p", "something else here now")])
        self.assertEqual([op for op, _, _ in out], ["del", "add"])


    def test_images_are_never_word_diffed(self):
        out = wikitext.diff([("img", "A.jpg\nThe old caption")], [("img", "A.jpg\nThe new caption")])
        self.assertEqual([op for op, _, _ in out], ["del", "add"])


class SideBySideTest(unittest.TestCase):
    def test_rewrite_sits_next_to_its_new_version(self):
        changes = [("skip", None, 3), ("del", "p", "old"), ("add", "p", "new"), ("add", "li", "extra")]
        self.assertEqual(wikitext.side_by_side(changes), [
            ("skip", 3),
            ("row", ("p", [("del", "old")]), ("p", [("add", "new")])),
            ("row", None, ("li", [("add", "extra")])),
        ])

    def test_word_diff_is_split_between_the_columns(self):
        changes = wikitext.diff([("p", "Rabat has 500,000 people")], [("p", "Rabat has 600,000 people")])
        self.assertEqual(wikitext.side_by_side(changes), [(
            "row",
            ("p", [("same", "Rabat has"), ("del", "500,000"), ("same", "people")]),
            ("p", [("same", "Rabat has"), ("add", "600,000"), ("same", "people")]),
        )])


class FactsTest(unittest.TestCase):
    def test_rows_read_counts_real_tables_only(self):
        report = {"query_block": {"table": {"table_name": "<derived2>", "r_rows": 1, "materialized": {
            "query_block": {"table": {"table_name": "article", "r_loops": 1, "r_rows": 1}}}}}}
        self.assertEqual(db.rows_read(report), 1)
        nested = {"nested_loop": [{"table": {"table_name": "a", "r_loops": 1, "r_rows": 60}},
                                  {"table": {"table_name": "t", "r_loops": 2, "r_rows": 1}}]}
        self.assertEqual(db.rows_read(nested), 62)

    def test_editor_kind(self):
        self.assertEqual(views.editor_kind("SieBot"), "a bot")
        self.assertEqual(views.editor_kind("41.140.12.9"), "not logged in, an IP address")
        self.assertEqual(views.editor_kind("2601:206:8102:1640:99DF:15ED:8531:B675"), "not logged in, an IP address")
        self.assertEqual(views.editor_kind("El C"), "a registered editor")

    def test_span(self):
        self.assertEqual(views.span(dt.timedelta(hours=19)), "19 hours")
        self.assertEqual(views.span(dt.timedelta(days=26)), "26 days")
        self.assertEqual(views.span(dt.timedelta(days=800)), "2 years")


class DayTest(unittest.TestCase):
    today = dt.date(2026, 10, 27)

    def test_valid_day(self):
        self.assertEqual(db.parse_day("2010-01-01", self.today), dt.date(2010, 1, 1))

    def test_days_are_kept_in_range(self):
        self.assertEqual(db.parse_day("1990-05-01", self.today), dt.date(2001, 1, 1))
        self.assertEqual(db.parse_day("2099-01-01", self.today), self.today)

    def test_city_names_drop_the_disambiguation(self):
        self.assertEqual(views.city_name("Fez, Morocco"), "Fez")
        self.assertEqual(views.city_name("Rabat"), "Rabat")

    def test_bad_input_is_refused(self):
        for value in ["", "2010-13-01", "2010-1-1", "1 Jan 2010", "2010-01-01' OR 1=1"]:
            self.assertIsNone(db.parse_day(value, self.today), value)


class NoRows:
    """Stands in for a connection whose exact_text table has nothing."""
    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, args=None):
        pass

    def fetchone(self):
        return None


class ExactTextTest(unittest.TestCase):
    """Where the text of a version comes from, without a database or Wikipedia."""

    def setUp(self):
        self.kept = []
        self.old = (db.ENV.get("EXACT_TEXT"), exact.keep, exact._paused_until)
        db.ENV["EXACT_TEXT"] = "on"
        exact.keep = lambda rev_id, body: self.kept.append((rev_id, body))
        exact._paused_until = 0.0

    def tearDown(self):
        db.ENV["EXACT_TEXT"], exact.keep, exact._paused_until = self.old

    def version(self, rev_id=20, text_rev_id=10):
        return {"rev_id": rev_id, "text_rev_id": text_rev_id, "body": "older copy"}

    def test_a_stored_revision_is_its_own_text(self):
        v = exact.fill(NoRows(), self.version(10, 10), ask=self.fail)
        self.assertEqual((v["text_from"], v["body"]), ("own", "older copy"))

    def test_a_missing_text_is_asked_for_once_and_kept(self):
        v = exact.fill(NoRows(), self.version(), ask=lambda rev_id: f"exact text of {rev_id}")
        self.assertEqual((v["text_from"], v["body"]), ("fetched", "exact text of 20"))
        self.assertEqual(self.kept, [(20, "exact text of 20")])

    def test_offline_falls_back_and_stops_asking_for_a_while(self):
        def down(rev_id):
            raise OSError("no route")
        with contextlib.redirect_stderr(io.StringIO()) as log:
            v = exact.fill(NoRows(), self.version(), ask=down)
        self.assertIn("no route", log.getvalue())
        self.assertEqual((v["text_from"], v["text_why"], v["body"]), ("older", "offline", "older copy"))
        again = exact.fill(NoRows(), self.version(), ask=self.fail)   # not asked: still in the pause
        self.assertEqual(again["text_why"], "offline")
        self.assertEqual(self.kept, [])

    def test_a_hidden_revision_keeps_the_stored_copy(self):
        v = exact.fill(NoRows(), self.version(), ask=lambda rev_id: None)
        self.assertEqual((v["text_from"], v["text_why"]), ("older", "hidden"))

    def test_switched_off_never_asks(self):
        db.ENV["EXACT_TEXT"] = "off"
        v = exact.fill(NoRows(), self.version(), ask=self.fail)
        self.assertEqual((v["text_from"], v["text_why"]), ("older", "off"))

    def test_the_note_says_which_text_is_on_show(self):
        day = dt.datetime(2009, 10, 10)
        exact_note = views.render_notes({"rev_id": 20, "text_from": "fetched", "text_date": day})
        self.assertIn("exact text of revision 20", exact_note)
        older = views.render_notes({"rev_id": 20, "text_from": "older", "text_why": "offline", "text_date": day})
        self.assertIn("stored copy from 10 Oct 2009", older)
        self.assertIn("could not be reached", older)


class ErrorPageTest(unittest.TestCase):
    """A failure gives a plain page. The reason stays in the terminal."""

    def get(self, failure):
        old = server.render_page

        def broken(params):
            raise failure
        server.render_page = broken
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.handle_request)
        thread.start()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/", timeout=10)
            self.fail("an error status was expected")
        except urllib.error.HTTPError as answer:
            return answer.code, answer.read().decode("utf-8")
        finally:
            thread.join()
            httpd.server_close()
            server.render_page = old

    def test_the_reason_is_not_sent_to_the_browser(self):
        with contextlib.redirect_stderr(io.StringIO()) as log:
            status, page = self.get(ValueError("secret detail"))
        self.assertEqual(status, 500)
        self.assertNotIn("secret detail", page)
        self.assertIn("secret detail", log.getvalue())

    def test_a_database_error_is_named_as_one(self):
        try:
            import pymysql
        except ImportError:
            self.skipTest("PyMySQL is not installed")
        with contextlib.redirect_stderr(io.StringIO()):
            status, page = self.get(pymysql.err.OperationalError(2003, "Can't connect to 10.0.0.9"))
        self.assertEqual(status, 503)
        self.assertIn("The database did not answer", page)
        self.assertNotIn("10.0.0.9", page)

    def test_other_paths_are_not_found(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.handle_request)
        thread.start()
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/etc/passwd", timeout=10)
            self.assertEqual(caught.exception.code, 404)
        finally:
            thread.join()
            httpd.server_close()


class DatabaseTest(unittest.TestCase):
    """The page must show the same revision as a direct AS OF query."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = db.connect()
        except Exception as exc:  # no driver or no database: skip, do not fail
            raise unittest.SkipTest(f"database not reachable: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_rabat_on_1_jan_2010(self):
        v = db.version_at(self.conn, 57400, dt.date(2010, 1, 1))
        with self.conn.cursor() as cur:
            cur.execute("SELECT rev_id FROM article_period "
                        "WHERE page_id = 57400 AND valid_from <= '2010-01-01 23:59:59.999999' "
                        "AND valid_to > '2010-01-01 23:59:59.999999'")
            self.assertEqual(v["rev_id"], cur.fetchone()["rev_id"])
        self.assertTrue(v["body"])

    def test_before_the_first_edit_there_is_nothing(self):
        self.assertIsNone(db.version_at(self.conn, 57400, dt.date(2001, 6, 1)))

    def test_the_page_renders(self):
        html = server.render_page({"city": ["57400"], "date": ["2010-01-01"], "compare": ["2020-01-01"]})
        self.assertIn("Rabat", html)
        self.assertIn("FOR SYSTEM_TIME AS OF TIMESTAMP", html)
        self.assertIn('class="sbs"', html)
        changes = server.render_page({"city": ["57400"], "date": ["2010-01-01"],
                                      "compare": ["2020-01-01"], "view": ["changes"]})
        self.assertIn('class="diff"', changes)

    def test_the_header_counts_the_loaded_articles(self):
        """45 with the full data, 3 with the sample: the page says what is loaded."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM page")
            n = cur.fetchone()["n"]
        self.assertIn(f"The Wikipedia articles of {n} Moroccan cities", server.render_page({}))
        self.assertIn("The Wikipedia articles of Moroccan cities", views.layout("Error", ""))

    def test_under_the_hood_agrees_with_the_period_table(self):
        v = db.version_at(self.conn, 57400, dt.date(2010, 1, 1))
        self.assertEqual(v["period_rev"], v["rev_id"])
        self.assertEqual(v["next"]["row_start"], v["row_end"])
        self.assertLessEqual(v["prev"]["row_start"], v["row_start"])
        html = server.render_page({"city": ["57400"], "date": ["2010-01-01"]})
        self.assertIn("It opened the other 18.", html)
        a = v["analyze"]["tables"]["a"]
        # every Rabat version that ended after the moment is read through the key:
        # 1,432 on the 26 Oct 2026 snapshot, more with newer data
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM article FOR SYSTEM_TIME ALL "
                        "WHERE page_id = 57400 AND row_end > '2010-01-01 23:59:59.999999'")
            self.assertEqual(a["r_rows"], cur.fetchone()["n"])
        self.assertIn("row_start <=", a["condition"])
        self.assertEqual(v["versions"], 447)

    def test_the_session_can_travel_without_as_of(self):
        """SET system_versioning_asof gives the same answer as AS OF, and prunes the same."""
        v = db.version_at(self.conn, 57400, dt.date(2010, 1, 1))
        self.assertEqual(v["session_rev"], v["rev_id"])
        self.assertEqual(len(v["session_partitions"]), len(v["partitions"]))
        with self.conn.cursor() as cur:  # and the setting did not leak out of version_at
            cur.execute("SELECT @@system_versioning_asof AS v")
            self.assertEqual(cur.fetchone()["v"], "DEFAULT")
        html = server.render_page({"city": ["57400"], "date": ["2010-01-01"]})
        self.assertIn("SET</b> @@system_versioning_asof", html)
        self.assertIn("and the same 18 partitions opened", html)

    def test_the_first_row_shortcut_agrees_and_reads_one_row(self):
        """ORDER BY row_end LIMIT 1 finds the same revision as AS OF from a single row."""
        for day in (dt.date(2005, 6, 1), dt.date(2010, 1, 1), dt.date(2026, 6, 1)):
            v = db.version_at(self.conn, 57400, day)
            self.assertEqual(v["first_rev"], v["rev_id"], day)
            self.assertEqual(v["first_rows"], 1, day)
            self.assertGreater(v["analyze"]["tables"]["a"]["r_rows"], v["first_rows"], day)
        html = server.render_page({"city": ["57400"], "date": ["2005-06-01"]})
        self.assertIn("A shorter way", html)
        self.assertIn("It read 1 row where", html)

    def test_edit_wars_come_from_the_edit_comments(self):
        days = db.edit_wars(self.conn, 57400)
        self.assertTrue(days)
        self.assertGreaterEqual(days[0]["reverts"], days[-1]["reverts"])
        for d in days:
            self.assertGreaterEqual(d["reverts"], 2)
            self.assertGreaterEqual(d["edits"], d["reverts"])
        html = server.render_page({"city": ["57400"], "date": ["2010-01-01"]})
        self.assertIn('class="wars"', html)
        self.assertIn(f'date={days[0]["day"].isoformat()}', html)

    def test_page_shows_pictures_tables_and_the_theme_switch(self):
        html = server.render_page({"city": ["57400"], "date": ["2026-10-01"]})
        self.assertIn('<figure class="img">', html)
        self.assertIn('<div class="gallery">', html)
        self.assertIn("Special:FilePath/Morocco_-_Kasbah_of_the_Udayas.jpg", html)
        self.assertIn("<th>Population (2014)</th>", html)
        self.assertIn('<button class="theme"', html)

    def test_unknown_city_falls_back_to_rabat(self):
        html = server.render_page({"city": ["999"], "date": ["2010-01-01"]})
        self.assertIn("<title>Rabat, 1 Jan 2010", html)

    def test_the_partitions_come_from_the_server(self):
        parts = db.partitions(self.conn)
        self.assertEqual(parts[-1]["ends_before"], "CURRENT")
        self.assertGreaterEqual(len(parts), 27)
        html = server.render_page({"city": ["57400"], "date": ["2010-01-01"]})
        self.assertIn(f'style="--parts:{len(parts)}"', html)
        self.assertIn(f"of the {len(parts)} partitions", html)

    def test_the_page_user_can_only_read(self):
        """Even on a connection that is not read only, the page's user is refused."""
        import pymysql
        conn = db.connect(readonly=False)
        try:
            with conn.cursor() as cur:
                for statement in ("UPDATE article SET bytes = 0 WHERE page_id = 57400",
                                  "DELETE HISTORY FROM article",
                                  "DELETE FROM exact_text",
                                  "INSERT INTO revision_text (rev_id, page_id, body) VALUES (1, 1, 'x')"):
                    with self.assertRaises(pymysql.err.OperationalError, msg=statement) as caught:
                        cur.execute(statement)
                    self.assertEqual(caught.exception.args[0], 1142, statement)
        finally:
            conn.close()

    def set_aside(self, *rev_ids):
        """Takes the texts of these revisions out of exact_text for the length
        of one test and puts them back afterwards, so a text the page fetched
        for real is neither in the way nor lost. As root: the page's user may
        not delete."""
        import pymysql

        def root():
            return pymysql.connect(host=db.ENV.get("DB_HOST", "127.0.0.1"), port=int(db.ENV.get("DB_PORT", "3307")),
                                   user="root", password=db.ENV.get("MARIADB_ROOT_PASSWORD", ""),
                                   database=db.ENV.get("DB_NAME", "timemachine"), autocommit=True)

        conn = root()
        with conn.cursor() as cur:
            cur.execute("SELECT rev_id, body, fetched_at FROM exact_text WHERE rev_id IN (%s)"
                        % ", ".join(["%s"] * len(rev_ids)), rev_ids)
            kept = cur.fetchall()
            cur.executemany("DELETE FROM exact_text WHERE rev_id = %s", [(r,) for r in rev_ids])
        conn.close()

        def put_back():
            conn = root()
            with conn.cursor() as cur:
                cur.executemany("DELETE FROM exact_text WHERE rev_id = %s", [(r,) for r in rev_ids])
                cur.executemany("INSERT INTO exact_text (rev_id, body, fetched_at) VALUES (%s, %s, %s)", kept)
            conn.close()
        self.addCleanup(put_back)

    def exact_stand_in(self, *rev_ids):
        """Wikipedia is replaced by a stand-in. What it leaves in exact_text is
        removed again afterwards, and what was there before comes back."""
        self.set_aside(*rev_ids)
        asked = []

        def ask(rev_id):
            asked.append(rev_id)
            return f"The exact text of revision {rev_id}, as the test wrote it.\n\nA second paragraph."

        old = (db.ENV.get("EXACT_TEXT"), exact.ask_wikipedia, exact._paused_until)

        def restore():
            db.ENV["EXACT_TEXT"], exact.ask_wikipedia, exact._paused_until = old
        db.ENV["EXACT_TEXT"], exact.ask_wikipedia, exact._paused_until = "on", ask, 0.0
        self.addCleanup(restore)
        return asked

    def test_the_exact_text_is_fetched_once_kept_and_shown(self):
        v = db.version_at(self.conn, 57400, dt.date(2010, 1, 1))
        self.assertNotEqual(v["text_rev_id"], v["rev_id"])       # not one of the quarterly texts
        asked = self.exact_stand_in(v["rev_id"])
        html = server.render_page({"city": ["57400"], "date": ["2010-01-01"]})
        self.assertIn(f"The exact text of revision {v['rev_id']}, as the test wrote it.", html)
        self.assertIn(f"This is the exact text of revision {v['rev_id']}", html)
        again = server.render_page({"city": ["57400"], "date": ["2010-01-01"]})
        self.assertIn(f"The exact text of revision {v['rev_id']}, as the test wrote it.", again)
        self.assertEqual(asked, [v["rev_id"]])                    # the second view read exact_text
        fresh = db.connect()      # self.conn still reads its older snapshot
        try:
            self.assertEqual(exact.fill(fresh, dict(v))["text_from"], "kept")
        finally:
            fresh.close()

    def test_two_dates_in_one_quarter_are_compared_on_their_exact_texts(self):
        first = db.version_at(self.conn, 57400, dt.date(2010, 1, 20))
        second = db.version_at(self.conn, 57400, dt.date(2010, 3, 20))
        self.assertEqual(first["text_rev_id"], second["text_rev_id"])   # the same stored copy
        self.assertNotEqual(first["rev_id"], second["rev_id"])
        params = {"city": ["57400"], "date": ["2010-01-20"], "compare": ["2010-03-20"]}
        self.set_aside(first["rev_id"], second["rev_id"])
        without = server.render_page(params)                             # exact texts off, none kept
        self.assertIn("nothing to compare here", without)
        self.exact_stand_in(first["rev_id"], second["rev_id"])
        html = server.render_page(params)
        self.assertIn("Compared on the exact texts of both revisions", html)
        self.assertIn(f"<del>{first['rev_id']},</del>", html)
        self.assertIn(f"<ins>{second['rev_id']},</ins>", html)


if __name__ == "__main__":
    unittest.main()
