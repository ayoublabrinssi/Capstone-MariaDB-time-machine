#!/usr/bin/env python3
"""Download Wikipedia revision histories for the time machine.

For every title in the article list:
  1. fetch the metadata of ALL revisions (id, time, user, size, comment);
  2. pick a sample of revisions for which the full wikitext is downloaded:
     the first revision of every quarter (or month, or year) plus the latest;
  3. write data/raw/<title>.json with both lists.

Only the standard library is used. The Wikipedia API asks for a User-Agent
that names the project and a contact, and for the maxlag parameter.

    python3 fetch/fetch.py --articles data/articles.txt --out data/raw
    python3 fetch/fetch.py --every year --limit 3      # quick small run
    python3 fetch/fetch.py --snapshot data/snapshot.tsv  # stop where the 26 Oct 2026 data stops
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = ("mariadb-time-machine/0.1 (student project, Constructor University; "
              "https://github.com/ayoublabrinssi)")


def api(params, retries=5):
    """One GET on the API, with maxlag and simple retries."""
    params = dict(params, format="json", formatversion="2", maxlag="5")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
        except (urllib.error.URLError, TimeoutError) as e:
            error = e
            wait = 2 ** attempt
            print(f"    network error ({e}), retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if "error" in data and data["error"].get("code") == "maxlag":
            time.sleep(5)
            continue
        if "error" in data:
            raise RuntimeError(data["error"])
        return data
    raise SystemExit(f"\nWikipedia did not answer after {retries} tries (last error: {error}).\n"
                     "Its servers may be busy or under maintenance. Try again in a few minutes:\n"
                     "the articles already downloaded are kept.")


def all_revisions(title, end_revid=None):
    """Metadata of every revision, oldest first. Follows redirects.
    With end_revid, stops at that revision (included)."""
    revs, page, cont = [], None, {}
    end = {"rvendid": str(end_revid)} if end_revid else {}
    while True:
        data = api({"action": "query", "prop": "revisions", "titles": title,
                    "redirects": "1", "rvprop": "ids|timestamp|user|size|comment",
                    "rvlimit": "max", "rvdir": "newer", **end, **cont})
        page = data["query"]["pages"][0]
        if page.get("missing"):
            raise RuntimeError(f"no such article: {title}")
        revs.extend(page.get("revisions", []))
        cont = data.get("continue")
        if not cont:
            break
    return page["pageid"], page["title"], revs


def period_key(ts, every):
    y, m = ts[:4], int(ts[5:7])
    if every == "year":
        return y
    if every == "month":
        return f"{y}-{m:02d}"
    return f"{y}-Q{(m - 1) // 3 + 1}"


def pick_sample(revs, every):
    """First revision of each period, plus the latest one."""
    seen, sample = set(), []
    for r in revs:
        k = period_key(r["timestamp"], every)
        if k not in seen:
            seen.add(k)
            sample.append(r)
    if revs and (not sample or sample[-1]["revid"] != revs[-1]["revid"]):
        sample.append(revs[-1])
    return sample


def fetch_content(revids):
    """Wikitext for a list of revision ids, 50 per request."""
    out = {}
    for i in range(0, len(revids), 50):
        chunk = revids[i:i + 50]
        data = api({"action": "query", "prop": "revisions",
                    "revids": "|".join(str(x) for x in chunk),
                    "rvprop": "ids|content", "rvslots": "main"})
        for page in data["query"]["pages"]:
            for r in page.get("revisions", []):
                slot = r["slots"]["main"]
                out[r["revid"]] = slot.get("content", "")
        time.sleep(0.5)
    return out


def read_snapshot(path):
    """data/snapshot.tsv: title, page id, last revision id, last edit, revisions."""
    snap = {}
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if ln.strip() and not ln.startswith("#"):
                title, _, last, _, count = ln.rstrip("\n").split("\t")
                snap[title] = (int(last), int(count))
    return snap


def read_titles(path):
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--articles", default="data/articles.txt")
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--every", choices=["month", "quarter", "year"], default="quarter",
                    help="download the text of the first revision of each period")
    ap.add_argument("--limit", type=int, default=0, help="only the first N titles")
    ap.add_argument("--force", action="store_true", help="refetch existing files")
    ap.add_argument("--snapshot", metavar="FILE",
                    help="stop each article at the last revision listed in FILE "
                         "(data/snapshot.tsv: the data the tests and results were made on)")
    a = ap.parse_args()
    snap = read_snapshot(a.snapshot) if a.snapshot else {}

    titles = read_titles(a.articles)
    if a.limit:
        titles = titles[:a.limit]
    os.makedirs(a.out, exist_ok=True)
    manifest_path = os.path.join(a.out, "manifest.json")

    for n, title in enumerate(titles, 1):
        path = os.path.join(a.out, file_name(title))
        end_revid, expected = snap.get(title, (None, None))
        if a.snapshot and end_revid is None:
            print(f"[{n}/{len(titles)}] {title}: not in {a.snapshot}, fetched up to today")
        if os.path.exists(path) and not a.force:
            if keep(path, end_revid):
                print(f"[{n}/{len(titles)}] {title}: already there, skipped")
                continue
            print(f"[{n}/{len(titles)}] {title}: other data on disk, fetching again")
        print(f"[{n}/{len(titles)}] {title}: revisions...", end="", flush=True)
        pageid, real_title, revs = all_revisions(title, end_revid)
        if expected is not None and len(revs) != expected:
            print(f"\n    NOTE: {len(revs)} revisions instead of {expected}; Wikipedia has hidden "
                  "or removed some since the snapshot", file=sys.stderr)
        sample = pick_sample(revs, a.every)
        print(f" {len(revs)} total, {len(sample)} with text...", end="", flush=True)
        texts = fetch_content([r["revid"] for r in sample])
        latest = texts.get(revs[-1]["revid"], "")
        if "{{disambiguation" in latest.lower() or latest.lstrip().upper().startswith("#REDIRECT"):
            print(f"\n    WARNING: {real_title} is a disambiguation or redirect page, "
                  "fix the title in the article list", file=sys.stderr)
        doc = {"pageid": pageid, "title": real_title, "requested_title": title,
               "every": a.every, "snapshot": bool(end_revid), "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "revisions": revs,
               "sample": [{"revid": r["revid"], "timestamp": r["timestamp"],
                           "text": texts.get(r["revid"], "")} for r in sample]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        print(f" saved ({os.path.getsize(path) // 1024} KB)")
    write_manifest(titles, a.out, manifest_path)


def keep(path, end_revid):
    """Is the file on disk already the data asked for? With a snapshot: it stops
    at the same revision. Without: it was fetched up to its day, not to a snapshot."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if end_revid:
        return doc["revisions"][-1]["revid"] == end_revid
    return doc.get("snapshot") is False


def file_name(title):
    return title.replace("/", "_") + ".json"


def write_manifest(titles, out, manifest_path):
    """Summary of what is on disk for the titles in the list, rebuilt every run."""
    manifest = {}
    for title in titles:
        path = os.path.join(out, file_name(title))
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        revs = doc["revisions"]
        manifest[doc["title"]] = {"pageid": doc["pageid"], "file": file_name(title),
                                  "requested_title": title, "revisions": len(revs),
                                  "sampled": len(doc["sample"]),
                                  "first": revs[0]["timestamp"], "last": revs[-1]["timestamp"],
                                  "bytes_now": revs[-1].get("size", 0),
                                  "fetched_at": doc.get("fetched_at")}
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"Done. {len(manifest)} of {len(titles)} articles on disk, listed in {manifest_path}")


if __name__ == "__main__":
    main()
