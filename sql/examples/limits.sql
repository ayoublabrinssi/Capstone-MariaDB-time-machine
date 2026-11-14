-- Where system versioning stops. Each step asks the server one thing and
-- prints what it answered: what it refuses, what it accepts without checking,
-- and what it does in a way that is easy to guess wrong. Found while loading
-- 25 years of Wikipedia history into a feature made to record from today on.
-- Works on scratch tables (limit_*) and drops them at the end.
--   scripts/db.sh -t < sql/examples/limits.sql
USE timemachine;
SET time_zone = '+00:00';

DELIMITER //
-- Runs one statement and prints the server's answer as a row, so a refusal
-- shows up in order in the output instead of stopping the file.
CREATE OR REPLACE PROCEDURE try(IN what VARCHAR(80), IN stmt TEXT)
BEGIN
  DECLARE answer VARCHAR(300) DEFAULT 'accepted';
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN
      GET DIAGNOSTICS CONDITION 1 @errno = MYSQL_ERRNO, @msg = MESSAGE_TEXT;
      IF answer = 'accepted' THEN SET answer = CONCAT('error ', @errno, ': ', @msg); END IF;
    END;
  SET @stmt = stmt;
  PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;
  SELECT what AS tried, answer AS server_said;
END //
DELIMITER ;

CREATE OR REPLACE TABLE limit_t (
  id INT NOT NULL PRIMARY KEY,
  v  INT,
  row_start TIMESTAMP(6) AS ROW START INVISIBLE,
  row_end   TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)
) WITH SYSTEM VERSIONING;

-- 1. Which dates can be imported. System time is a TIMESTAMP, so history
--    cannot start before 1970-01-01 00:00:01 UTC. A table of kings or of land
--    titles needs application time (DATE or DATETIME columns) instead.
--    The future is accepted, and a version must start before it ends.
SET @@system_versioning_insert_history = 1;
CALL try('version from 1969',
  "INSERT INTO limit_t (id, v, row_start, row_end) VALUES (1, 1, '1969-06-01 00:00:00', '1980-01-01 00:00:00')");
CALL try('version from 1970-01-01 00:00:00',
  "INSERT INTO limit_t (id, v, row_start, row_end) VALUES (1, 1, '1970-01-01 00:00:00', '1980-01-01 00:00:00')");
CALL try('version from 1970-01-01 00:00:01',
  "INSERT INTO limit_t (id, v, row_start, row_end) VALUES (1, 1, '1970-01-01 00:00:01', '1980-01-01 00:00:00')");
CALL try('version from 2030 to 2031',
  "INSERT INTO limit_t (id, v, row_start, row_end) VALUES (2, 1, '2030-01-01 00:00:00', '2031-01-01 00:00:00')");
CALL try('version that ends before it starts',
  "INSERT INTO limit_t (id, v, row_start, row_end) VALUES (3, 1, '2020-01-01 00:00:00', '2019-01-01 00:00:00')");

-- 2. Imported history is not checked for overlaps. Two versions of the same
--    key that cover the same months are both accepted, and AS OF then returns
--    two rows for one primary key. The loader has to get this right itself
--    (tests/tests.sql checks it for article). The same two rows in an
--    application-time table with WITHOUT OVERLAPS are refused by the server.
CALL try('two overlapping versions of id 4',
  "INSERT INTO limit_t (id, v, row_start, row_end) VALUES
     (4, 1, '2020-01-01 00:00:00', '2021-01-01 00:00:00'),
     (4, 2, '2020-06-01 00:00:00', '2022-01-01 00:00:00')");
SET @@system_versioning_insert_history = 0;

SELECT id, v, row_start, row_end
FROM limit_t FOR SYSTEM_TIME AS OF TIMESTAMP '2020-09-01 00:00:00' WHERE id = 4;

CREATE OR REPLACE TABLE limit_period (
  id INT NOT NULL,
  v  INT,
  valid_from DATETIME NOT NULL,
  valid_to   DATETIME NOT NULL,
  PERIOD FOR valid_time (valid_from, valid_to),
  PRIMARY KEY (id, valid_time WITHOUT OVERLAPS)
);
CALL try('the same two rows with WITHOUT OVERLAPS',
  "INSERT INTO limit_period VALUES
     (4, 1, '2020-01-01 00:00:00', '2021-01-01 00:00:00'),
     (4, 2, '2020-06-01 00:00:00', '2022-01-01 00:00:00')");

-- 3. Which time a version gets. Inside a transaction each statement stamps
--    its rows with its own time: not the BEGIN, not the COMMIT. Every step is
--    kept, so a transaction with two updates leaves two history rows, and
--    AS OF can land between them on a value that was never committed alone.
INSERT INTO limit_t (id, v) VALUES (10, 1);
SELECT SLEEP(1) INTO @pause;
BEGIN;
SET @begin = NOW(6);
SELECT SLEEP(1) INTO @pause;
UPDATE limit_t SET v = 2 WHERE id = 10;
SELECT SLEEP(1) INTO @pause;
SET @between = NOW(6);
SELECT SLEEP(1) INTO @pause;
UPDATE limit_t SET v = 3 WHERE id = 10;
SELECT SLEEP(1) INTO @pause;
SET @before_commit = NOW(6);
COMMIT;

SELECT v,
       row_start > @begin AND row_start < @before_commit AS stamped_inside_the_transaction,
       ROUND(TIMESTAMPDIFF(MICROSECOND, @begin, row_start) / 1e6) AS seconds_after_begin
FROM limit_t FOR SYSTEM_TIME ALL WHERE id = 10 ORDER BY row_end;

SELECT v AS value_between_the_two_updates
FROM limit_t FOR SYSTEM_TIME AS OF TIMESTAMP @between WHERE id = 10;

-- 4. An UPDATE that changes nothing still makes a new version.
SELECT COUNT(*) INTO @before FROM limit_t FOR SYSTEM_TIME ALL WHERE id = 10;
UPDATE limit_t SET v = 3 WHERE id = 10;
SELECT @before AS versions_before, COUNT(*) AS versions_after_same_value_update
FROM limit_t FOR SYSTEM_TIME ALL WHERE id = 10;

--    The other way round: a column declared WITHOUT SYSTEM VERSIONING can
--    change as often as it likes and no version is made. That is the place
--    for a counter or a "last seen" time next to data whose history matters.
CREATE OR REPLACE TABLE limit_views (
  id    INT NOT NULL PRIMARY KEY,
  body  VARCHAR(20),
  views INT WITHOUT SYSTEM VERSIONING
) WITH SYSTEM VERSIONING;
INSERT INTO limit_views VALUES (1, 'text', 0);
UPDATE limit_views SET views = views + 1;
UPDATE limit_views SET views = views + 1;
SELECT COUNT(*) AS versions_after_two_updates_of_views FROM limit_views FOR SYSTEM_TIME ALL;
UPDATE limit_views SET body = 'new text';
SELECT COUNT(*) AS versions_after_one_update_of_body FROM limit_views FOR SYSTEM_TIME ALL;

-- 5. TRUNCATE is refused: history can only go through DELETE HISTORY or a
--    dropped partition (sql/examples/retention.sql).
CALL try('TRUNCATE TABLE', "TRUNCATE TABLE limit_t");

-- 6. Time zones. row_start is stored in UTC and shown in the session time
--    zone, and an AS OF literal is read in the session time zone too. The
--    same literal in two sessions can mean two different moments.
SET time_zone = '+00:00';
SELECT 'session +00:00' AS zone, row_start,
       (SELECT COUNT(*) FROM limit_t FOR SYSTEM_TIME AS OF TIMESTAMP '2020-01-01 00:30:00' WHERE id = 4) AS rows_as_of_0030
FROM limit_t FOR SYSTEM_TIME ALL WHERE id = 4 AND v = 1;
SET time_zone = '+01:00';
SELECT 'session +01:00' AS zone, row_start,
       (SELECT COUNT(*) FROM limit_t FOR SYSTEM_TIME AS OF TIMESTAMP '2020-01-01 00:30:00' WHERE id = 4) AS rows_as_of_0030
FROM limit_t FOR SYSTEM_TIME ALL WHERE id = 4 AND v = 1;
SET time_zone = '+00:00';

-- 7. The other kind of versioning. With BIGINT row_start and row_end the
--    server stores transaction ids instead of times and looks the times up in
--    mysql.transaction_registry. A transaction then counts as one moment: it
--    leaves one history row whatever it did inside, and AS OF a time inside
--    it gives the value from before it began. The price: no partitioning by
--    SYSTEM_TIME and no import of history, so it could not hold Wikipedia.
CREATE OR REPLACE TABLE limit_trx (
  id INT NOT NULL PRIMARY KEY,
  v  INT,
  row_start BIGINT UNSIGNED AS ROW START INVISIBLE,
  row_end   BIGINT UNSIGNED AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)
) WITH SYSTEM VERSIONING;

CALL try('transaction ids + PARTITION BY SYSTEM_TIME',
  "CREATE TABLE limit_trx_part (
     id INT NOT NULL PRIMARY KEY,
     row_start BIGINT UNSIGNED AS ROW START INVISIBLE,
     row_end   BIGINT UNSIGNED AS ROW END INVISIBLE,
     PERIOD FOR SYSTEM_TIME (row_start, row_end)
   ) WITH SYSTEM VERSIONING PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR PARTITIONS 3");
SET @@system_versioning_insert_history = 1;
CALL try('transaction ids + imported history',
  "INSERT INTO limit_trx (id, v, row_start, row_end) VALUES (1, 1, 100, 200)");
SET @@system_versioning_insert_history = 0;

INSERT INTO limit_trx (id, v) VALUES (10, 1);
SELECT SLEEP(1) INTO @pause;
BEGIN;
UPDATE limit_trx SET v = 2 WHERE id = 10;
SELECT SLEEP(1) INTO @pause;
SET @between = NOW(6);
SELECT SLEEP(1) INTO @pause;
UPDATE limit_trx SET v = 3 WHERE id = 10;
COMMIT;

SELECT COUNT(*) AS versions_stored,
       (SELECT v FROM limit_trx FOR SYSTEM_TIME AS OF TIMESTAMP @between WHERE id = 10) AS value_between_the_two_updates,
       (SELECT v FROM limit_trx WHERE id = 10) AS value_now
FROM limit_trx FOR SYSTEM_TIME ALL WHERE id = 10;

-- 8. The session clock. A session may set its own time with SET @@timestamp
--    (unless the server runs with secure_timestamp, see
--    scripts/trust_check.sh), and the server stamps versions with it. That is
--    a second way to load a past: replay the changes in order and let the
--    server write the history, with no row_start in any statement. It only
--    works forwards. One step back in time is accepted without a word: the
--    version that was current is lost (its end would come before its start,
--    so no history row is written), and the new version overlaps older ones.
CREATE OR REPLACE TABLE limit_clock (
  item VARCHAR(10) NOT NULL PRIMARY KEY,
  mad  DECIMAL(6,2)
) WITH SYSTEM VERSIONING;
SET @@timestamp = UNIX_TIMESTAMP('2019-03-01 00:00:00'); INSERT INTO limit_clock VALUES ('tea', 10.00);
SET @@timestamp = UNIX_TIMESTAMP('2021-06-01 00:00:00'); UPDATE limit_clock SET mad = 12.50;
SET @@timestamp = UNIX_TIMESTAMP('2024-01-15 00:00:00'); UPDATE limit_clock SET mad = 14.00;
SELECT 'replayed in order' AS history, mad, row_start, row_end
FROM limit_clock FOR SYSTEM_TIME ALL ORDER BY row_start;

SET @@timestamp = UNIX_TIMESTAMP('2020-01-01 00:00:00');
CALL try('UPDATE with the clock set back to 2020', "UPDATE limit_clock SET mad = 11.00");
SET @@timestamp = DEFAULT;
SELECT 'after one step back' AS history, mad, row_start, row_end
FROM limit_clock FOR SYSTEM_TIME ALL ORDER BY row_start;
SELECT COUNT(*) AS rows_as_of_mid_2020
FROM limit_clock FOR SYSTEM_TIME AS OF TIMESTAMP '2020-06-01 00:00:00';

-- 9. AUTO partitions and an imported past. AUTO adds a yearly partition when
--    the server clock needs one, never for the dates of imported rows. With
--    STARTS in the past and no PARTITIONS count, the table has one history
--    partition, and every imported version lands in it whatever year it ended
--    in. Nothing looks wrong yet. The first live UPDATE makes AUTO add the
--    missing years, the imported versions stay where they are, and from then
--    on AS OF skips the partition they sit in: a date that had an answer a
--    moment ago has none. CHECK TABLE finds the misplaced rows and REPAIR
--    TABLE moves them. sql/01_schema.sql avoids all of it by making the
--    partitions for every year before the load.
CREATE OR REPLACE TABLE limit_auto (
  item VARCHAR(10) NOT NULL PRIMARY KEY,
  mad  DECIMAL(6,2)
) WITH SYSTEM VERSIONING
  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2005-01-01 00:00:00' AUTO;
SET @@system_versioning_insert_history = 1;
INSERT INTO limit_auto (item, mad, row_start, row_end) VALUES
  ('tea', 10.00, '2005-03-01 00:00:00', '2009-07-01 00:00:00'),
  ('tea', 12.50, '2009-07-01 00:00:00', '2016-02-01 00:00:00'),
  ('tea', 14.00, '2016-02-01 00:00:00', '2023-10-01 00:00:00');
INSERT INTO limit_auto (item, mad, row_start) VALUES ('tea', 15.00, '2023-10-01 00:00:00');
SET @@system_versioning_insert_history = 0;
SELECT 'after the import' AS moment,
  (SELECT COUNT(*) FROM information_schema.PARTITIONS
   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'limit_auto') AS partitions,
  (SELECT COUNT(*) FROM limit_auto PARTITION (p0)) AS versions_in_p0,
  (SELECT mad FROM limit_auto FOR SYSTEM_TIME AS OF TIMESTAMP '2018-01-01 00:00:00') AS price_in_2018;

UPDATE limit_auto SET mad = 16.00;
SELECT 'after one live UPDATE' AS moment,
  (SELECT COUNT(*) FROM information_schema.PARTITIONS
   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'limit_auto') > 2 AS auto_added_partitions,
  (SELECT COUNT(*) FROM limit_auto PARTITION (p0)) AS versions_in_p0,
  (SELECT mad FROM limit_auto FOR SYSTEM_TIME AS OF TIMESTAMP '2018-01-01 00:00:00') AS price_in_2018;

CHECK TABLE limit_auto;
REPAIR TABLE limit_auto;
SELECT 'after REPAIR TABLE' AS moment,
  (SELECT COUNT(*) FROM limit_auto PARTITION (p0)) AS versions_in_p0,
  (SELECT mad FROM limit_auto FOR SYSTEM_TIME AS OF TIMESTAMP '2018-01-01 00:00:00') AS price_in_2018;

--    The loaded table has a partition for every year, so nothing is misplaced:
CHECK TABLE article;

DROP TABLE IF EXISTS limit_t, limit_period, limit_trx, limit_trx_part, limit_views, limit_clock, limit_auto;
DROP PROCEDURE try;
