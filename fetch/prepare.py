#!/usr/bin/env python3
"""Turn the fetched JSON in data/raw/ into tab-separated files for LOAD DATA.

Reads the titles in data/articles.txt and writes data/load/:

  page.tsv              one row per article
  revision_text.tsv     the stored wikitext, one row per sampled revision
  article_history.tsv   every revision except the latest, with its real
                        start and end time (system-time history rows)
  article_current.tsv   the latest revision of each article (current rows)
  article_period.tsv    every revision with its application-time period
  expected_as_of.tsv    200 (article, moment, revision) checks for the tests,
                        computed here in Python, independently of MariaDB

Times are UTC, written as 'YYYY-MM-DD HH:MM:SS'. Only the standard library.

    python3 fetch/prepare.py
"""
import argparse
import bisect
import json
import os
import random
from datetime import datetime, timedelta, timezone

END_OF_TIME = "9999-12-31 00:00:00"   # open end of an application-time period


def ts(wiki_ts):
    """'2002-06-15T17:35:01Z' -> '2002-06-15 17:35:01'"""
    return wiki_ts.replace("T", " ").replace("Z", "")


def esc(value):
    """One field in the default LOAD DATA format (tab separated, backslash escapes)."""
    if value is None:
        return r"\N"
    s = str(value)
    return (s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
             .replace("\r", "\\r").replace("\0", "\\0"))


def write(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write("\t".join(esc(v) for v in row) + "\n")
    return len(rows)


def read_titles(path):
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--articles", default="data/articles.txt")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/load")
    ap.add_argument("--checks", type=int, default=200, help="number of AS OF checks for the tests")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    page, texts, history, current, period, all_revs = [], [], [], [], [], []
    for title in read_titles(a.articles):
        path = os.path.join(a.raw, title.replace("/", "_") + ".json")
        if not os.path.exists(path):
            raise SystemExit(f"missing {path}: run scripts/fetch.sh first")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        pid, revs = doc["pageid"], doc["revisions"]
        revs.sort(key=lambda r: (r["timestamp"], r["revid"]))
        sampled = sorted((s["timestamp"], s["revid"]) for s in doc["sample"])
        sampled_times = [t for t, _ in sampled]
        page.append((pid, doc["title"], len(revs), ts(revs[0]["timestamp"]), ts(revs[-1]["timestamp"])))
        for s in doc["sample"]:
            texts.append((s["revid"], pid, s.get("text", "")))
        for i, r in enumerate(revs):
            # the stored text closest before this revision (sampled once per quarter)
            k = bisect.bisect_right(sampled_times, r["timestamp"]) - 1
            text_rev = sampled[k][1]
            start = ts(r["timestamp"])
            end = ts(revs[i + 1]["timestamp"]) if i + 1 < len(revs) else None
            row = (pid, r["revid"], r.get("user"), r.get("comment"), r.get("size"), text_rev)
            if end is None:
                current.append(row + (start,))
            else:
                history.append(row + (start, end))
            period.append((pid, r["revid"], r.get("size"), start, end or END_OF_TIME))
            all_revs.append((pid, r["timestamp"], r["revid"]))

    # Independent expectations for the tests: at moment t, the article shows the
    # latest revision whose timestamp is <= t.
    rnd = random.Random(20261026)
    by_page = {}
    for pid, t, rid in all_revs:
        by_page.setdefault(pid, []).append((t, rid))
    checks = []
    pids = sorted(by_page)
    for _ in range(a.checks):
        pid = rnd.choice(pids)
        revs = by_page[pid]
        first = datetime.strptime(revs[0][0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        last = datetime.strptime(revs[-1][0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        span = (last - first).total_seconds() + 86400 * 30
        moment = first + timedelta(seconds=rnd.uniform(0, span))
        m = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
        k = bisect.bisect_right([t for t, _ in revs], m) - 1
        checks.append((pid, moment.strftime("%Y-%m-%d %H:%M:%S"), revs[k][1]))
    # plus the exact edges: one second before and exactly at a revision
    for pid in pids[:10]:
        revs = by_page[pid]
        t, rid = revs[len(revs) // 2]
        prev_rid = revs[len(revs) // 2 - 1][1]
        at = datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ")
        checks.append((pid, at.strftime("%Y-%m-%d %H:%M:%S"), rid))
        checks.append((pid, (at - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"), prev_rid))

    counts = {
        "page": write(os.path.join(a.out, "page.tsv"), page),
        "revision_text": write(os.path.join(a.out, "revision_text.tsv"), texts),
        "article_history": write(os.path.join(a.out, "article_history.tsv"), history),
        "article_current": write(os.path.join(a.out, "article_current.tsv"), current),
        "article_period": write(os.path.join(a.out, "article_period.tsv"), period),
        "expected_as_of": write(os.path.join(a.out, "expected_as_of.tsv"), checks),
    }
    for name, n in counts.items():
        print(f"{name:18} {n:7} rows")


if __name__ == "__main__":
    main()
