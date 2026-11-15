-- A walk through system-versioned tables on 45 Moroccan city articles.
-- Read-only: run it as often as you like. Made for the full data: on the
-- sample (Rabat, Ifrane, Asilah) the queries about other cities return nothing.
--
--   scripts/db.sh -t < sql/queries.sql
--
-- Every query names the feature it shows. The README explains the schema.
USE timemachine;
SET time_zone = '+00:00';   -- all times in this database are UTC


-- 1. The present. A versioned table reads like any other table:
--    only the current rows are visible.
SELECT p.title, a.rev_id, a.editor, a.bytes, a.row_start AS live_since
FROM article a JOIN page p USING (page_id)
WHERE p.title IN ('Rabat', 'Casablanca', 'Marrakesh');


-- 2. FOR SYSTEM_TIME AS OF: Rabat as it stood on 1 January 2005.
--    No revision table, no "WHERE date <= ... ORDER BY ... LIMIT 1".
SELECT p.title, a.rev_id, a.editor, a.bytes, LEFT(t.body, 300) AS text_start
FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2005-01-01 00:00:00' a
JOIN page p USING (page_id)
JOIN revision_text t ON t.rev_id = a.text_rev_id
WHERE p.title = 'Rabat';


-- 3. AS OF on every article at once: the size of all 45 articles
--    on 1 January of 2006, 2016 and today.
SELECT p.title,
       old.bytes AS bytes_2006, mid.bytes AS bytes_2016, now.bytes AS bytes_today
FROM page p
LEFT JOIN article FOR SYSTEM_TIME AS OF TIMESTAMP '2006-01-01 00:00:00' old USING (page_id)
LEFT JOIN article FOR SYSTEM_TIME AS OF TIMESTAMP '2016-01-01 00:00:00' mid USING (page_id)
JOIN article now USING (page_id)
ORDER BY now.bytes DESC
LIMIT 10;


-- 4. FOR SYSTEM_TIME BETWEEN: every version of Rabat that was live
--    at some point during the week of 13 January 2020.
SELECT a.rev_id, a.editor, a.bytes, a.row_start, a.row_end, LEFT(a.comment, 60) AS comment
FROM article FOR SYSTEM_TIME BETWEEN TIMESTAMP '2020-01-13 00:00:00' AND TIMESTAMP '2020-01-20 00:00:00' a
JOIN page p USING (page_id)
WHERE p.title = 'Rabat'
ORDER BY a.row_start;

--    FROM ... TO is the same range without its last instant. A version that
--    starts exactly at the end of the range is in BETWEEN and not in FROM ... TO.
--    Here the range ends at the exact moment of an edit to Rabat.
SELECT a.row_start INTO @edit
FROM article FOR SYSTEM_TIME ALL a JOIN page p USING (page_id)
WHERE p.title = 'Rabat' AND a.row_start >= '2020-01-13 00:00:00'
ORDER BY a.row_start LIMIT 1;
SELECT @edit AS range_ends_at_this_edit,
       (SELECT COUNT(*) FROM article FOR SYSTEM_TIME BETWEEN TIMESTAMP '2020-01-13 00:00:00' AND TIMESTAMP @edit a
        JOIN page p USING (page_id) WHERE p.title = 'Rabat') AS versions_between,
       (SELECT COUNT(*) FROM article FOR SYSTEM_TIME FROM TIMESTAMP '2020-01-13 00:00:00' TO TIMESTAMP @edit a
        JOIN page p USING (page_id) WHERE p.title = 'Rabat') AS versions_from_to;


-- 5. FOR SYSTEM_TIME ALL: the full history as a time series.
--    Edits per year on Rabat, with the largest size reached that year.
SELECT YEAR(a.row_start) AS year, COUNT(*) AS edits, MAX(a.bytes) AS largest_bytes
FROM article FOR SYSTEM_TIME ALL a JOIN page p USING (page_id)
WHERE p.title = 'Rabat'
GROUP BY year ORDER BY year;


-- 6. How long a version stayed live. The shortest-lived versions are
--    usually vandalism that was reverted within minutes.
SELECT p.title, a.rev_id, a.editor,
       TIMESTAMPDIFF(SECOND, a.row_start, a.row_end) AS seconds_live,
       LEFT(a.comment, 50) AS comment
FROM article FOR SYSTEM_TIME ALL a JOIN page p USING (page_id)
WHERE a.row_end < NOW()               -- history rows only
ORDER BY seconds_live, a.rev_id      -- rev_id settles ties, so the list is the same every run
LIMIT 5;


-- 7. The editors behind the history: most edits over all 45 articles.
SELECT a.editor, COUNT(*) AS edits, COUNT(DISTINCT a.page_id) AS articles
FROM article FOR SYSTEM_TIME ALL a
WHERE a.editor IS NOT NULL
GROUP BY a.editor ORDER BY edits DESC
LIMIT 10;


-- 8. Two dates, one article: what changed between 2010 and 2020?
--    (The page in app/ shows the full diff.)
SELECT '1 Jan 2010' AS as_of, a.rev_id, a.bytes, a.row_start
FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2010-01-01 00:00:00' a JOIN page p USING (page_id)
WHERE p.title = 'Rabat'
UNION ALL
SELECT '1 Jan 2020', a.rev_id, a.bytes, a.row_start
FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2020-01-01 00:00:00' a JOIN page p USING (page_id)
WHERE p.title = 'Rabat';


-- 9. Partitions by SYSTEM_TIME: history rows sit in the partition of the
--    year their version ended, current rows in pn.
SELECT PARTITION_NAME, PARTITION_DESCRIPTION AS ends_before, TABLE_ROWS
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article';

--    Pruning: a query on a recent moment reads only the newest partitions.
--    A query on an old moment cannot skip the newer ones, because a version
--    that ENDED in 2020 may have STARTED before 2005. See docs/details.md.
EXPLAIN PARTITIONS SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2026-06-01 00:00:00';
EXPLAIN PARTITIONS SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2005-06-01 00:00:00';


-- 10. The same question with the application-time period instead:
--     an ordinary WHERE on valid_from / valid_to. Same answer as query 2.
SELECT p.title, ap.rev_id, ap.bytes, ap.valid_from, ap.valid_to
FROM article_period ap JOIN page p USING (page_id)
WHERE p.title = 'Rabat'
  AND ap.valid_from <= '2005-01-01 00:00:00' AND ap.valid_to > '2005-01-01 00:00:00';

--     article_period has a second clock of its own. valid_from is Wikipedia's
--     time; row_start is system time, the moment this database learned the
--     row, which is the load. sql/examples/wikipedia_correction.sql uses both.
SELECT ap.rev_id, ap.valid_from AS true_on_wikipedia_from, ap.row_start AS known_to_this_database_since
FROM article_period ap JOIN page p USING (page_id)
WHERE p.title = 'Rabat'
  AND ap.valid_from <= '2005-01-01 00:00:00' AND ap.valid_to > '2005-01-01 00:00:00';


-- 11. No AS OF in the query at all: the session travels instead.
--     system_versioning_asof moves every query on a versioned table to that
--     moment, so a whole site could run "as of 2010" with one SET.
--     Same answer as query 2, and the partitions are pruned the same way.
SET @@system_versioning_asof = '2005-01-01 00:00:00';
SELECT p.title, a.rev_id, a.editor, a.bytes
FROM article a JOIN page p USING (page_id)
WHERE p.title = 'Rabat';
EXPLAIN PARTITIONS SELECT rev_id FROM article WHERE page_id = 57400;
SET @@system_versioning_asof = DEFAULT;   -- back to the server's setting, which is "now"


-- 12. Edit wars: the history as data. Days with the most reverts on one
--     article, read from the edit comments over the full history.
SELECT p.title, DATE(a.row_start) AS day, COUNT(*) AS edits, COUNT(DISTINCT a.editor) AS editors,
       SUM(a.comment LIKE 'Revert%' OR a.comment LIKE 'Undid%' OR a.comment LIKE 'rv%'
           OR a.comment LIKE '%revert%') AS reverts
FROM article FOR SYSTEM_TIME ALL a JOIN page p USING (page_id)
GROUP BY p.title, day
HAVING reverts >= 4
ORDER BY reverts DESC, edits DESC, day
LIMIT 10;


-- 13. The answer of query 2 from one row. AS OF reads every version of Rabat
--     that ended after the moment and keeps one. The versions of one article
--     never overlap, so the live one is the first that ended after the
--     moment: read the key (page_id, row_end) in order and stop there. The
--     outer WHERE drops the row when the article did not exist yet.
--     ANALYZE shows the rows each way reads (r_rows). Section 4 of
--     docs/measurements.md has the numbers for other dates and sizes.
SELECT p.title, v.rev_id, v.editor, v.bytes
FROM (SELECT page_id, rev_id, editor, bytes, row_start
      FROM article FOR SYSTEM_TIME ALL
      WHERE page_id = 57400 AND row_end > '2005-01-01 00:00:00'
      ORDER BY row_end LIMIT 1) AS v
JOIN page p USING (page_id)
WHERE v.row_start <= '2005-01-01 00:00:00';

ANALYZE SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2005-01-01 00:00:00' WHERE page_id = 57400;
ANALYZE SELECT rev_id FROM (SELECT rev_id, row_start FROM article FOR SYSTEM_TIME ALL
                            WHERE page_id = 57400 AND row_end > '2005-01-01 00:00:00'
                            ORDER BY row_end LIMIT 1) AS v
WHERE v.row_start <= '2005-01-01 00:00:00';

--     The longest history in this data is Casablanca. The same two ways:
SELECT p.title, p.revisions AS versions,
       (SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL a
        WHERE a.page_id = p.page_id AND a.row_end > '2005-01-01 00:00:00') AS rows_as_of_2005_has_to_read
FROM page p ORDER BY p.revisions DESC LIMIT 3;
SELECT page_id INTO @casablanca FROM page WHERE title = 'Casablanca';
ANALYZE SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2005-01-01 00:00:00' WHERE page_id = @casablanca;
ANALYZE SELECT rev_id FROM (SELECT rev_id, row_start FROM article FOR SYSTEM_TIME ALL
                            WHERE page_id = @casablanca AND row_end > '2005-01-01 00:00:00'
                            ORDER BY row_end LIMIT 1) AS v
WHERE v.row_start <= '2005-01-01 00:00:00';
