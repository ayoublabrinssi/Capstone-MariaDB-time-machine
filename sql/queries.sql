-- A walk through system-versioned tables on 45 Moroccan city articles.
-- Read-only: run it as often as you like.
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


-- 4. FOR SYSTEM_TIME BETWEEN: every version of Casablanca that was live
--    at some point during the first week of March 2020.
SELECT a.rev_id, a.editor, a.bytes, a.row_start, a.row_end, LEFT(a.comment, 60) AS comment
FROM article FOR SYSTEM_TIME BETWEEN TIMESTAMP '2020-03-01 00:00:00' AND TIMESTAMP '2020-03-08 00:00:00' a
JOIN page p USING (page_id)
WHERE p.title = 'Casablanca'
ORDER BY a.row_start;


-- 5. FOR SYSTEM_TIME ALL: the full history as a time series.
--    Edits per year on Rabat, with the size at the end of each year.
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
ORDER BY seconds_live
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
WHERE p.title = 'Tangier'
UNION ALL
SELECT '1 Jan 2020', a.rev_id, a.bytes, a.row_start
FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2020-01-01 00:00:00' a JOIN page p USING (page_id)
WHERE p.title = 'Tangier';


-- 9. Partitions by SYSTEM_TIME: history rows sit in the partition of the
--    year their version ended, current rows in pn.
SELECT PARTITION_NAME, PARTITION_DESCRIPTION AS ends_before, TABLE_ROWS
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article';

--    Pruning: a query on a recent moment reads only the newest partitions.
--    A query on an old moment cannot skip the newer ones, because a version
--    that ENDED in 2020 may have STARTED before 2005. See the README.
EXPLAIN PARTITIONS SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2026-06-01 00:00:00';
EXPLAIN PARTITIONS SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2005-06-01 00:00:00';


-- 10. The same question with the application-time period instead:
--     an ordinary WHERE on valid_from / valid_to. Same answer as query 2.
SELECT p.title, ap.rev_id, ap.bytes, ap.valid_from, ap.valid_to
FROM article_period ap JOIN page p USING (page_id)
WHERE p.title = 'Rabat'
  AND ap.valid_from <= '2005-01-01 00:00:00' AND ap.valid_to > '2005-01-01 00:00:00';
