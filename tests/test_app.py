"""Tests for the page: the wikitext cleaner, the diff, the date input, and
one end-to-end check against the database (skipped when it is not running).

    python3 -m unittest discover -s tests      (or scripts/test.sh)
"""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "app"))

import server  # noqa: E402
import wikitext  # noqa: E402


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
    def test_editor_kind(self):
        self.assertEqual(server.editor_kind("SieBot"), "a bot")
        self.assertEqual(server.editor_kind("41.140.12.9"), "not logged in, an IP address")
        self.assertEqual(server.editor_kind("2601:206:8102:1640:99DF:15ED:8531:B675"), "not logged in, an IP address")
        self.assertEqual(server.editor_kind("El C"), "a registered editor")

    def test_span(self):
        self.assertEqual(server.span(dt.timedelta(hours=19)), "19 hours")
        self.assertEqual(server.span(dt.timedelta(days=26)), "26 days")
        self.assertEqual(server.span(dt.timedelta(days=800)), "2 years")


class DayTest(unittest.TestCase):
    today = dt.date(2026, 10, 27)

    def test_valid_day(self):
        self.assertEqual(server.parse_day("2010-01-01", self.today), dt.date(2010, 1, 1))

    def test_days_are_kept_in_range(self):
        self.assertEqual(server.parse_day("1990-05-01", self.today), dt.date(2001, 1, 1))
        self.assertEqual(server.parse_day("2099-01-01", self.today), self.today)

    def test_city_names_drop_the_disambiguation(self):
        self.assertEqual(server.city_name("Fez, Morocco"), "Fez")
        self.assertEqual(server.city_name("Rabat"), "Rabat")

    def test_bad_input_is_refused(self):
        for value in ["", "2010-13-01", "2010-1-1", "1 Jan 2010", "2010-01-01' OR 1=1"]:
            self.assertIsNone(server.parse_day(value, self.today), value)


class DatabaseTest(unittest.TestCase):
    """The page must show the same revision as a direct AS OF query."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = server.connect()
        except Exception as exc:  # no driver or no database: skip, do not fail
            raise unittest.SkipTest(f"database not reachable: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_rabat_on_1_jan_2010(self):
        v = server.version_at(self.conn, 57400, dt.date(2010, 1, 1))
        with self.conn.cursor() as cur:
            cur.execute("SELECT rev_id FROM article_period "
                        "WHERE page_id = 57400 AND valid_from <= '2010-01-01 23:59:59.999999' "
                        "AND valid_to > '2010-01-01 23:59:59.999999'")
            self.assertEqual(v["rev_id"], cur.fetchone()["rev_id"])
        self.assertTrue(v["body"])

    def test_before_the_first_edit_there_is_nothing(self):
        self.assertIsNone(server.version_at(self.conn, 57400, dt.date(2001, 6, 1)))

    def test_the_page_renders(self):
        html = server.render_page({"city": ["57400"], "date": ["2010-01-01"], "compare": ["2020-01-01"]})
        self.assertIn("Rabat", html)
        self.assertIn("FOR SYSTEM_TIME AS OF TIMESTAMP", html)
        self.assertIn('class="sbs"', html)
        changes = server.render_page({"city": ["57400"], "date": ["2010-01-01"],
                                      "compare": ["2020-01-01"], "view": ["changes"]})
        self.assertIn('class="diff"', changes)

    def test_under_the_hood_agrees_with_the_period_table(self):
        v = server.version_at(self.conn, 57400, dt.date(2010, 1, 1))
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


if __name__ == "__main__":
    unittest.main()
