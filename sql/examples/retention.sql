-- Forgetting history on purpose. System versioning keeps every version until
-- someone removes it, so a real deployment needs a retention rule. MariaDB
-- gives two tools, shown here on a copy of article:
--   * ALTER TABLE ... DROP PARTITION: throws away whole years at once, only
--     on a table partitioned by SYSTEM_TIME, oldest years first;
--   * DELETE HISTORY ... BEFORE SYSTEM_TIME: removes the versions that ENDED
--     before a moment, on any versioned table.
-- Both keep the current rows. Numbers (rows, bytes, time) are in
-- results/measurements.txt and docs/measurements.md.
--   scripts/db.sh -t < sql/examples/retention.sql
USE timemachine;
SET time_zone = '+00:00';

CREATE OR REPLACE TABLE article_copy LIKE article;
SET @@system_versioning_insert_history = 1;
INSERT INTO article_copy (page_id, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end)
SELECT page_id, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end
FROM article FOR SYSTEM_TIME ALL;
SET @@system_versioning_insert_history = 0;

SELECT 'before' AS step, COUNT(*) AS versions, MIN(row_end) AS oldest_end
FROM article_copy FOR SYSTEM_TIME ALL;

-- 1. The partition way: drop whole years. p0 holds the versions that ended
--    in 2001, p1 those of 2002, and so on. Only the oldest partitions can go
--    (dropping p9 while p0 exists gives error 4116), so retention means
--    "keep the last N years". The space goes back at once.
SELECT PARTITION_NAME, TABLE_ROWS FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article_copy'
  AND PARTITION_NAME IN ('p0', 'p1', 'p2');
ALTER TABLE article_copy DROP PARTITION p0, p1, p2;
SELECT 'after DROP PARTITION p0, p1, p2' AS step, COUNT(*) AS versions, MIN(row_end) AS oldest_end
FROM article_copy FOR SYSTEM_TIME ALL;

-- 2. The row way: forget every version that ended before 2010, whatever
--    the partitions. Current rows stay.
DELETE HISTORY FROM article_copy BEFORE SYSTEM_TIME '2010-01-01 00:00:00';

SELECT 'after DELETE HISTORY' AS step, COUNT(*) AS versions, MIN(row_end) AS oldest_end
FROM article_copy FOR SYSTEM_TIME ALL;
SELECT COUNT(*) AS current_rows FROM article_copy;

-- An old date now has no answer at all: the time machine stops at 2010.
SELECT COUNT(*) AS rows_as_of_2005
FROM article_copy FOR SYSTEM_TIME AS OF TIMESTAMP '2005-06-01 00:00:00';

-- 3. After DELETE HISTORY the space is not given back until the table is
--    rebuilt. OPTIMIZE is an ALTER, so a versioned table refuses it unless
--    told to keep history. The refusal is a status row, not an error.
OPTIMIZE TABLE article_copy;
SET @@system_versioning_alter_history = KEEP;
OPTIMIZE TABLE article_copy;
SET @@system_versioning_alter_history = ERROR;

DROP TABLE article_copy;
