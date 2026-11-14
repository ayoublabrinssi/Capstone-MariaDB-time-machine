-- After the import, the table lives on. The 25 years in article were written
-- once with system_versioning_insert_history. From then on the server keeps
-- the history itself, the way the feature is meant to be used: an UPDATE is
-- all it takes. This file makes one edit to Rabat today and watches what the
-- server does, then takes it back, so the loaded data stays as it was. The
-- last part moves the clock of a scratch copy forward to watch AUTO add
-- partitions as the years pass.
--   scripts/db.sh -t < sql/examples/live_edit.sql
USE timemachine;
SET time_zone = '+00:00';

-- 1. Before: the current row, and the number of versions of Rabat.
SELECT rev_id, editor, bytes, row_start FROM article WHERE page_id = 57400;
SELECT COUNT(*) AS versions_before FROM article FOR SYSTEM_TIME ALL WHERE page_id = 57400;

SELECT SLEEP(1) INTO @pause;
SET @a_moment_ago = NOW(6);
SELECT SLEEP(1) INTO @pause;

-- 2. A new edit arrives. No switch, no row_start in the statement.
START TRANSACTION;
UPDATE article
SET rev_id = rev_id + 1, editor = 'Example', comment = 'an edit made today', bytes = bytes + 120
WHERE page_id = 57400;

-- 3. The server closed the old row and opened a new one at the same instant.
--    The old row is the last one imported; its end is no longer the far
--    future but the moment of the UPDATE, taken from the server clock.
SELECT rev_id, editor, row_start, row_end
FROM article FOR SYSTEM_TIME ALL
WHERE page_id = 57400
ORDER BY row_end DESC LIMIT 2;

-- 4. Both moments can be asked for at once.
SELECT 'a moment ago' AS asked, rev_id, editor
FROM article FOR SYSTEM_TIME AS OF TIMESTAMP @a_moment_ago WHERE page_id = 57400
UNION ALL
SELECT 'now', rev_id, editor FROM article WHERE page_id = 57400;

-- 5. The closed row moved out of pn, the partition of current rows, into the
--    partition of the year it ended in.
SELECT PARTITION_NAME, PARTITION_DESCRIPTION AS ends_before
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article'
  AND PARTITION_DESCRIPTION > NOW() AND PARTITION_DESCRIPTION <> 'CURRENT'
ORDER BY PARTITION_ORDINAL_POSITION LIMIT 1;
EXPLAIN PARTITIONS
SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP @a_moment_ago WHERE page_id = 57400;

-- 6. Take the edit back. The history row goes with it.
ROLLBACK;
SELECT rev_id, editor, bytes, row_start FROM article WHERE page_id = 57400;
SELECT COUNT(*) AS versions_after FROM article FOR SYSTEM_TIME ALL WHERE page_id = 57400;

-- 7. AUTO, watched. article has one partition per year up to the current
--    year. A scratch copy with the same partitions gets one edit "in March
--    2028": the session clock is moved with SET @@timestamp, which a session
--    may do unless the server runs with secure_timestamp (see
--    scripts/trust_check.sh). The server adds the missing years by itself.
CREATE OR REPLACE TABLE article_later LIKE article;
INSERT INTO article_later (page_id, rev_id, editor, comment, bytes, text_rev_id)
SELECT page_id, rev_id, editor, comment, bytes, text_rev_id FROM article WHERE page_id = 57400;

SELECT COUNT(*) AS partitions_before FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article_later';

SET @@timestamp = UNIX_TIMESTAMP('2028-03-01 12:00:00');
UPDATE article_later SET rev_id = rev_id + 1, comment = 'an edit in March 2028' WHERE page_id = 57400;
SET @@timestamp = DEFAULT;

SELECT COUNT(*) AS partitions_after FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article_later';
SELECT PARTITION_NAME, PARTITION_DESCRIPTION AS ends_before, TABLE_ROWS
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article_later'
ORDER BY PARTITION_ORDINAL_POSITION DESC LIMIT 4;

DROP TABLE article_later;
