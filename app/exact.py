"""The exact text of one revision.

The load stores one text per article per quarter (table revision_text). When
the page shows a revision that is not one of those, it asks Wikipedia for
that one revision and keeps the answer in the table exact_text, so each
revision is asked for once. Offline, or with EXACT_TEXT=off in .env, the page
shows the stored quarterly copy and says so.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

import db

API = "https://en.wikipedia.org/w/api.php"
# The same name fetch/fetch.py gives: Wikipedia asks clients to say who they are.
USER_AGENT = ("mariadb-time-machine/0.1 (student project, Constructor University; "
              "https://github.com/ayoublabrinssi)")
TIMEOUT = 6     # seconds to wait for Wikipedia
PAUSE = 60      # seconds without asking again after it did not answer

STORED_SQL = "SELECT body FROM exact_text WHERE rev_id = %s"
KEEP_SQL = "INSERT IGNORE INTO exact_text (rev_id, body) VALUES (%s, %s)"

_paused_until = 0.0


def enabled():
    return db.ENV.get("EXACT_TEXT", "on").strip().lower() != "off"


def ask_wikipedia(rev_id):
    """The wikitext of one revision from the MediaWiki API, or None when
    Wikipedia hides it or no longer has it. Raises OSError or ValueError when
    Wikipedia cannot be reached or answers with something else than JSON."""
    query = urllib.parse.urlencode({
        "action": "query", "prop": "revisions", "revids": str(rev_id),
        "rvprop": "ids|content", "rvslots": "main", "format": "json", "formatversion": "2"})
    request = urllib.request.Request(API + "?" + query, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        data = json.load(answer)
    for page in data.get("query", {}).get("pages", []):
        for rev in page.get("revisions", []):
            if rev.get("revid") == rev_id:
                return rev.get("slots", {}).get("main", {}).get("content")
    return None


def stored(conn, rev_id):
    with conn.cursor() as cur:
        cur.execute(STORED_SQL, (rev_id,))
        row = cur.fetchone()
    return row["body"] if row else None


def keep(rev_id, body):
    """Writes one text into exact_text. The page's reading connection is read
    only, so this opens a second one for the single INSERT its user may do."""
    conn = db.connect(readonly=False)
    try:
        with conn.cursor() as cur:
            cur.execute(KEEP_SQL, (rev_id, body))
        conn.commit()
    finally:
        conn.close()


def fill(conn, v, ask=None):
    """Puts the exact text of version v into v["body"] when it can, and says
    in v["text_from"] where the text comes from:

      own      the stored text is this very revision
      kept     read from exact_text
      fetched  asked from Wikipedia just now, and kept
      older    the stored quarterly copy; v["text_why"] is off, offline or hidden
    """
    global _paused_until
    if v["text_rev_id"] == v["rev_id"]:
        v["text_from"] = "own"
        return v
    body = stored(conn, v["rev_id"])
    if body is not None:
        v["body"], v["text_from"] = body, "kept"
        return v
    v["text_from"] = "older"
    if not enabled():
        v["text_why"] = "off"
        return v
    if time.monotonic() < _paused_until:
        v["text_why"] = "offline"
        return v
    try:
        body = (ask or ask_wikipedia)(v["rev_id"])
    except (OSError, ValueError) as exc:
        print(f"exact text of {v['rev_id']}: Wikipedia did not answer ({exc})", file=sys.stderr)
        _paused_until = time.monotonic() + PAUSE
        v["text_why"] = "offline"
        return v
    if body is None:
        v["text_why"] = "hidden"
        return v
    v["body"], v["text_from"] = body, "fetched"
    try:
        keep(v["rev_id"], body)
    except Exception as exc:  # the text is still shown; it is asked for again next time
        print(f"exact text of {v['rev_id']}: could not be kept ({exc})", file=sys.stderr)
    return v
