"""Tests for the download and the preparation, with no network and no
database: small made-up histories in a temporary folder.

    python3 -m unittest discover -s tests      (or scripts/test.sh)
"""
import contextlib
import gzip
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "fetch"))

import fetch  # noqa: E402
import prepare  # noqa: E402


def rev(revid, timestamp, size=100, user="A", comment="edit"):
    return {"revid": revid, "timestamp": timestamp, "size": size, "user": user, "comment": comment}


HISTORY = [
    rev(1, "2020-01-10T08:00:00Z"),
    rev(2, "2020-02-01T09:30:00Z", 150),
    rev(3, "2020-05-05T10:00:00Z", 120, comment="a tab\there"),
    rev(4, "2021-01-01T00:00:00Z", 300, user=None),
]


class SampleTest(unittest.TestCase):
    def test_period_key(self):
        self.assertEqual(fetch.period_key("2020-05-05T10:00:00Z", "quarter"), "2020-Q2")
        self.assertEqual(fetch.period_key("2020-05-05T10:00:00Z", "month"), "2020-05")
        self.assertEqual(fetch.period_key("2020-05-05T10:00:00Z", "year"), "2020")

    def test_first_revision_of_each_quarter_plus_the_latest(self):
        ids = [r["revid"] for r in fetch.pick_sample(HISTORY, "quarter")]
        self.assertEqual(ids, [1, 3, 4])

    def test_the_latest_is_added_when_it_does_not_open_a_period(self):
        ids = [r["revid"] for r in fetch.pick_sample(HISTORY[:2], "quarter")]
        self.assertEqual(ids, [1, 2])
        self.assertEqual([r["revid"] for r in fetch.pick_sample(HISTORY, "year")], [1, 4])
        self.assertEqual(fetch.pick_sample([], "quarter"), [])

    def test_file_names_have_no_slash(self):
        self.assertEqual(fetch.file_name("AC/DC"), "AC_DC.json")


class FilesTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = pathlib.Path(folder.name)

    def write(self, name, doc):
        path = self.dir / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def test_snapshot_file_gives_the_last_revision_and_the_count(self):
        path = self.dir / "snapshot.tsv"
        path.write_text("# title\tpage\tlast\tlast edit\trevisions\n"
                        "Rabat\t57400\t1382098700\t2026-10-26T16:17:34Z\t1878\n\n", encoding="utf-8")
        self.assertEqual(fetch.read_snapshot(str(path)), {"Rabat": (1382098700, 1878)})

    def test_titles_skip_comments_and_blank_lines(self):
        path = self.dir / "articles.txt"
        path.write_text("# cities\nRabat\n\n  Fez, Morocco  \n", encoding="utf-8")
        self.assertEqual(fetch.read_titles(str(path)), ["Rabat", "Fez, Morocco"])

    def test_a_file_on_disk_is_kept_only_when_it_is_the_data_asked_for(self):
        fixed = self.write("fixed.json", {"revisions": HISTORY, "snapshot": True})
        newest = self.write("newest.json", {"revisions": HISTORY, "snapshot": False})
        self.assertTrue(fetch.keep(fixed, 4))        # stops at the snapshot revision
        self.assertFalse(fetch.keep(fixed, 3))       # stops somewhere else
        self.assertFalse(fetch.keep(fixed, None))    # newest asked, fixed on disk
        self.assertTrue(fetch.keep(newest, None))

    def test_manifest_lists_what_is_on_disk(self):
        self.write("Rabat.json", {"pageid": 7, "title": "Rabat", "revisions": HISTORY,
                                  "sample": [{"revid": 1}, {"revid": 4}], "fetched_at": "now"})
        out = self.dir / "manifest.json"
        with contextlib.redirect_stdout(io.StringIO()):
            fetch.write_manifest(["Rabat", "Missing"], str(self.dir), str(out))
        manifest = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(list(manifest), ["Rabat"])
        self.assertEqual((manifest["Rabat"]["revisions"], manifest["Rabat"]["sampled"]), (4, 2))
        self.assertEqual(manifest["Rabat"]["last"], "2021-01-01T00:00:00Z")


class PrepareTest(unittest.TestCase):
    """prepare.py turns revisions into versions: each one ends when the next begins."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = pathlib.Path(folder.name)
        (self.dir / "articles.txt").write_text("Town\nVillage\n", encoding="utf-8")
        town = {"pageid": 7, "title": "Town", "revisions": list(reversed(HISTORY)),   # order must not matter
                "sample": [{"revid": 1, "timestamp": HISTORY[0]["timestamp"], "text": "first\ttext\nline two"},
                           {"revid": 3, "timestamp": HISTORY[2]["timestamp"], "text": "third"},
                           {"revid": 4, "timestamp": HISTORY[3]["timestamp"], "text": "latest"}]}
        village = {"pageid": 9, "title": "Village", "revisions": [rev(50, "2022-03-03T03:03:03Z")],
                   "sample": [{"revid": 50, "timestamp": "2022-03-03T03:03:03Z", "text": "only"}]}
        (self.dir / "Town.json").write_text(json.dumps(town), encoding="utf-8")
        with gzip.open(self.dir / "Village.json.gz", "wt", encoding="utf-8") as f:   # a gzipped file is read too
            json.dump(village, f)
        self.out = self.dir / "load"
        with contextlib.redirect_stdout(io.StringIO()):
            prepare.main(["--articles", str(self.dir / "articles.txt"), "--raw", str(self.dir),
                          "--out", str(self.out), "--checks", "40"])

    def rows(self, name):
        text = (self.out / name).read_text(encoding="utf-8")
        return [line.split("\t") for line in text.splitlines()]

    def test_helpers(self):
        self.assertEqual(prepare.ts("2002-06-15T17:35:01Z"), "2002-06-15 17:35:01")
        self.assertEqual(prepare.esc(None), r"\N")
        self.assertEqual(prepare.esc("a\tb\nc\\"), "a\\tb\\nc\\\\")

    def test_a_missing_article_stops_the_run(self):
        (self.dir / "articles.txt").write_text("Town\nNowhere\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            prepare.main(["--articles", str(self.dir / "articles.txt"), "--raw", str(self.dir),
                          "--out", str(self.out)])

    def test_pages(self):
        self.assertEqual(self.rows("page.tsv"), [
            ["7", "Town", "4", "2020-01-10 08:00:00", "2021-01-01 00:00:00"],
            ["9", "Village", "1", "2022-03-03 03:03:03", "2022-03-03 03:03:03"]])

    def test_history_rows_end_where_the_next_revision_starts(self):
        history = self.rows("article_history.tsv")
        self.assertEqual([(r[1], r[6], r[7]) for r in history], [
            ("1", "2020-01-10 08:00:00", "2020-02-01 09:30:00"),
            ("2", "2020-02-01 09:30:00", "2020-05-05 10:00:00"),
            ("3", "2020-05-05 10:00:00", "2021-01-01 00:00:00")])
        self.assertEqual(history[2][3], "a tab\\there")        # the comment, escaped for LOAD DATA

    def test_the_latest_revision_is_the_current_row(self):
        current = self.rows("article_current.tsv")
        self.assertEqual([(r[0], r[1], r[6]) for r in current],
                         [("7", "4", "2021-01-01 00:00:00"), ("9", "50", "2022-03-03 03:03:03")])
        self.assertEqual(current[0][2], r"\N")                 # a hidden editor is NULL
        self.assertEqual(len(current[0]), 7)                   # no end time

    def test_each_version_points_at_the_stored_text_at_or_before_it(self):
        pointer = {r[1]: r[5] for r in self.rows("article_history.tsv") + self.rows("article_current.tsv")}
        self.assertEqual(pointer, {"1": "1", "2": "1", "3": "3", "4": "4", "50": "50"})
        texts = self.rows("revision_text.tsv")
        self.assertEqual(texts[0], ["1", "7", "first\\ttext\\nline two"])
        self.assertEqual(len(texts), 4)

    def test_periods_cover_the_same_times_with_an_open_end(self):
        period = self.rows("article_period.tsv")
        self.assertEqual(period[0][3:], ["2020-01-10 08:00:00", "2020-02-01 09:30:00"])
        self.assertEqual(period[3][3:], ["2021-01-01 00:00:00", prepare.END_OF_TIME])
        self.assertEqual(len(period), 5)

    def test_expected_answers_are_the_latest_revision_at_or_before_the_moment(self):
        checks = self.rows("expected_as_of.tsv")
        # 40 random moments, then the exact edges: two for Town, one for
        # Village, which has a single revision and so nothing before it
        self.assertEqual(len(checks), 40 + 2 + 1)
        starts = {7: [(prepare.ts(r["timestamp"]), r["revid"]) for r in HISTORY],
                  9: [("2022-03-03 03:03:03", 50)]}
        for page_id, moment, rev_id in checks:
            live = [r for t, r in starts[int(page_id)] if t <= moment]
            self.assertEqual(int(rev_id), live[-1], (page_id, moment))
        self.assertIn(["7", "2020-05-05 10:00:00", "3"], checks)     # exactly at an edit
        self.assertIn(["7", "2020-05-05 09:59:59", "2"], checks)     # one second before it

if __name__ == "__main__":
    unittest.main()
