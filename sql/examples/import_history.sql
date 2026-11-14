-- How to load history you already have into a system-versioned table.
-- A recipe on invented data: the price of three products since 2019. The
-- Wikipedia load (sql/02_load.sql) is the same five steps on 31,179 rows.
-- docs/import-tutorial.md explains each step.
--   scripts/db.sh -t < sql/examples/import_history.sql
USE timemachine;
SET time_zone = '+00:00';   -- the times below are UTC; say so before loading

-- The source: a plain change log, one row per price change.
CREATE OR REPLACE TABLE price_log (
  product    VARCHAR(20)  NOT NULL,
  price      DECIMAL(8,2) NOT NULL,
  changed_at DATETIME     NOT NULL,
  PRIMARY KEY (product, changed_at)
);
INSERT INTO price_log VALUES
  ('tea',    12.00, '2019-03-01 09:00:00'), ('tea',    13.50, '2021-06-15 09:00:00'),
  ('tea',    15.00, '2024-01-10 09:00:00'),
  ('sugar',   7.00, '2019-03-01 09:00:00'), ('sugar',   8.00, '2022-09-01 09:00:00'),
  ('mint',    2.00, '2020-05-20 09:00:00');

-- Step 1. Name the two system columns. A table made with only
--         WITH SYSTEM VERSIONING has them too, but they cannot be written.
-- Step 2. Make the yearly partitions up front, from before the oldest change
--         to today. AUTO alone would put all imported rows in one partition,
--         because it only follows the server clock. AUTO still adds the
--         partitions for the years to come.
CREATE OR REPLACE TABLE price (
  product   VARCHAR(20)  NOT NULL PRIMARY KEY,
  price     DECIMAL(8,2) NOT NULL,
  row_start TIMESTAMP(6) AS ROW START INVISIBLE,
  row_end   TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)
) WITH SYSTEM VERSIONING
  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2019-01-01 00:00:00' AUTO PARTITIONS 9;

-- Step 3. Open the switch for this session only and write both columns.
--         A version ends when the next change of the same product starts.
SET @@system_versioning_insert_history = 1;

INSERT INTO price (product, price, row_start, row_end)
SELECT product, price, changed_at, next_change
FROM (SELECT product, price, changed_at,
             LEAD(changed_at) OVER (PARTITION BY product ORDER BY changed_at) AS next_change
      FROM price_log) AS steps
WHERE next_change IS NOT NULL;

-- Step 4. The current rows: the last change of each product. Give row_start
--         only; the server sets row_end to "still live".
INSERT INTO price (product, price, row_start)
SELECT product, price, changed_at
FROM (SELECT product, price, changed_at,
             LEAD(changed_at) OVER (PARTITION BY product ORDER BY changed_at) AS next_change
      FROM price_log) AS steps
WHERE next_change IS NULL;

SET @@system_versioning_insert_history = 0;

-- Step 5. Check what the server did not: with the switch on it accepts
--         versions that overlap. Both counts must be right before you trust
--         AS OF: every change is a version, and each version ends exactly
--         where the next one starts.
SELECT (SELECT COUNT(*) FROM price_log) AS changes,
       (SELECT COUNT(*) FROM price FOR SYSTEM_TIME ALL) AS versions,
       (SELECT COUNT(*) FROM (SELECT row_end,
                 LEAD(row_start) OVER (PARTITION BY product ORDER BY row_end) AS next_start
               FROM price FOR SYSTEM_TIME ALL) AS v
        WHERE next_start IS NOT NULL AND next_start <> row_end) AS overlaps_or_gaps;

-- The past is there, with the real dates.
SELECT product, price FROM price FOR SYSTEM_TIME AS OF TIMESTAMP '2020-01-01 00:00:00' ORDER BY product;
SELECT product, price FROM price FOR SYSTEM_TIME AS OF TIMESTAMP '2023-01-01 00:00:00' ORDER BY product;

-- And the versions sit in the partition of the year they ended.
ANALYZE TABLE price;
SELECT PARTITION_NAME, TABLE_ROWS FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'price' AND TABLE_ROWS > 0;

-- From here on the table is an ordinary versioned table: a change made today
-- is stamped by the server clock and joins the imported history.
UPDATE price SET price = 16.00 WHERE product = 'tea';
SELECT product, price, row_start > '2026-01-01' AS stamped_by_the_server
FROM price FOR SYSTEM_TIME ALL WHERE product = 'tea' ORDER BY row_end;

-- For a key with a long history, a question about an old date reads every
-- later version. This reads one row instead (query 13 in sql/queries.sql).
SELECT price FROM (SELECT price, row_start FROM price FOR SYSTEM_TIME ALL
                   WHERE product = 'tea' AND row_end > '2020-01-01 00:00:00'
                   ORDER BY row_end LIMIT 1) AS v
WHERE v.row_start <= '2020-01-01 00:00:00';

DROP TABLE price, price_log;
