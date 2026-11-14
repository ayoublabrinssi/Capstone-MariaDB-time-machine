-- Tests for the time machine. Run with scripts/test.sh after scripts/install.sh.
-- Each check prints "ok" or "not ok", one line each.
-- A check is known by its number in that output (ok 1 to ok 40), here and in the README.
-- The AS OF checks come from data/load/expected_as_of.tsv, which fetch/prepare.py
-- computes in Python from the raw JSON, without MariaDB.
USE timemachine;
SET time_zone = '+00:00';

CREATE OR REPLACE TEMPORARY TABLE expected (
  page_id INT, at DATETIME, rev_id BIGINT
);
LOAD DATA INFILE '/data/load/expected_as_of.tsv' INTO TABLE expected;

CREATE OR REPLACE TEMPORARY TABLE result (n INT AUTO_INCREMENT PRIMARY KEY, ok BOOL, name VARCHAR(200));

DELIMITER //
CREATE OR REPLACE PROCEDURE check_that(IN passed BOOL, IN what VARCHAR(200))
  INSERT INTO result (ok, name) VALUES (COALESCE(passed, FALSE), what) //

-- Runs every expected row through FOR SYSTEM_TIME AS OF, with the moment and
-- the article passed as parameters, and counts the differences.
CREATE OR REPLACE PROCEDURE as_of_mismatches(OUT bad INT, OUT total INT)
BEGIN
  DECLARE done BOOL DEFAULT FALSE;
  DECLARE p INT; DECLARE t DATETIME; DECLARE want BIGINT;
  DECLARE cur CURSOR FOR SELECT page_id, at, rev_id FROM expected;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
  SET bad = 0, total = 0;
  PREPARE q FROM 'SELECT rev_id INTO @got FROM article FOR SYSTEM_TIME AS OF TIMESTAMP ? WHERE page_id = ?';
  OPEN cur;
  read_loop: LOOP
    FETCH cur INTO p, t, want;
    IF done THEN LEAVE read_loop; END IF;
    SET @got = NULL, @t = t, @p = p;
    EXECUTE q USING @t, @p;
    SET total = total + 1;
    IF @got IS NULL OR @got <> want THEN SET bad = bad + 1; END IF;
  END LOOP;
  CLOSE cur;
  DEALLOCATE PREPARE q;
END //

-- The same walk with the first-row query: read the key (page_id, row_end) in
-- order from the moment, stop at the first row, keep it if it had started.
CREATE OR REPLACE PROCEDURE first_row_mismatches(OUT bad INT, OUT total INT)
BEGIN
  DECLARE done BOOL DEFAULT FALSE;
  DECLARE p INT; DECLARE t DATETIME; DECLARE want BIGINT;
  DECLARE cur CURSOR FOR SELECT page_id, at, rev_id FROM expected;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
  SET bad = 0, total = 0;
  PREPARE q FROM 'SELECT rev_id INTO @got FROM (SELECT rev_id, row_start FROM article FOR SYSTEM_TIME ALL
                  WHERE page_id = ? AND row_end > ? ORDER BY row_end LIMIT 1) AS v WHERE v.row_start <= ?';
  OPEN cur;
  read_loop: LOOP
    FETCH cur INTO p, t, want;
    IF done THEN LEAVE read_loop; END IF;
    SET @got = NULL, @t = t, @p = p;
    EXECUTE q USING @p, @t, @t;
    SET total = total + 1;
    IF @got IS NULL OR @got <> want THEN SET bad = bad + 1; END IF;
  END LOOP;
  CLOSE cur;
  DEALLOCATE PREPARE q;
END //

-- Expects one statement to fail with one error number.
CREATE OR REPLACE PROCEDURE expect_error(IN stmt TEXT, IN errno INT, IN what VARCHAR(200))
BEGIN
  DECLARE got INT DEFAULT 0;
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN GET DIAGNOSTICS CONDITION 1 got = MYSQL_ERRNO; END;
  SET @stmt = stmt;
  PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;
  CALL check_that(got = errno, CONCAT(what, ' (error ', got, ', expected ', errno, ')'));
END //
DELIMITER ;

-- Checks 1 to 5. The load. scripts/test.sh sets @articles to the number of titles in the
--    article list that was loaded: 45, or 3 for the sample.
SET @articles = COALESCE(@articles, 45);
CALL check_that((SELECT COUNT(*) FROM page) = @articles, CONCAT(@articles, ' articles in page, as in the article list'));
CALL check_that((SELECT COUNT(*) FROM article) = @articles, 'one current row per article');
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL) = (SELECT SUM(revisions) FROM page),
  'every revision is a row of article (current + history)');
CALL check_that((SELECT COUNT(*) FROM article_period) = (SELECT SUM(revisions) FROM page),
  'every revision has an application-time period');
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL a
                 LEFT JOIN revision_text t ON t.rev_id = a.text_rev_id WHERE t.rev_id IS NULL) = 0,
  'every version points at stored text');

-- Checks 6 to 8. The timestamps are Wikipedia's, not the load time
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL WHERE row_start >= row_end) = 0,
  'every version has row_start < row_end');
CALL check_that((SELECT COUNT(*) FROM article a JOIN page p USING (page_id)
                 WHERE a.row_start <> p.last_edit) = 0,
  'current row starts at the last Wikipedia edit, not at load time');
CALL check_that((SELECT MIN(row_start) FROM article FOR SYSTEM_TIME ALL) = (SELECT MIN(first_edit) FROM page)
                AND (SELECT MIN(first_edit) FROM page) < '2006-01-01',
  CONCAT('history starts at the first Wikipedia edit, ', (SELECT DATE(MIN(first_edit)) FROM page)));

-- Checks 9 and 10. AS OF gives the revision that was live at that moment
CALL as_of_mismatches(@bad, @total);
CALL check_that(@bad = 0 AND @total = (SELECT COUNT(*) FROM expected),
  CONCAT('AS OF matches Python for ', @total, ' moments (', @bad, ' wrong)'));
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2001-01-01 00:00:00') = 0,
  'AS OF before the first edit returns nothing');

-- Check 11. The application-time period agrees with system time
CALL check_that((SELECT COUNT(*) FROM expected e
                 LEFT JOIN article_period ap ON ap.page_id = e.page_id
                      AND ap.valid_from <= e.at AND ap.valid_to > e.at
                 WHERE ap.rev_id IS NULL OR ap.rev_id <> e.rev_id) = 0,
  'application-time lookup gives the same revision as AS OF');

-- Checks 12 to 14. What the server refuses (documented limits)
CALL expect_error(
  'INSERT INTO article_period (page_id, rev_id, valid_from, valid_to) SELECT page_id, 1, ''2010-01-01'', ''2010-02-01'' FROM page LIMIT 1',
  1062, 'WITHOUT OVERLAPS refuses a second live revision');
CALL expect_error('ALTER TABLE article ADD COLUMN lang CHAR(2)', 4119,
  'ALTER on a versioned table is refused by default');
CALL expect_error(
  'INSERT INTO article (page_id, rev_id, text_rev_id, row_start) VALUES (1, 1, 1, ''2010-01-01'')',
  1906, 'row_start cannot be written without system_versioning_insert_history');

-- Check 15. Partitions: history is spread by year, not in one partition
CALL check_that((SELECT COUNT(*) FROM information_schema.PARTITIONS
                 WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article' AND TABLE_ROWS > 0) >= 20,
  'history is spread over the yearly partitions');

-- Checks 16 and 17. The session can travel without AS OF in the query
SET @@system_versioning_asof = '2010-01-01 23:59:59.999999';
SELECT rev_id INTO @via_session FROM article WHERE page_id = 57400;
SET @@system_versioning_asof = DEFAULT;
CALL check_that(@via_session = (SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2010-01-01 23:59:59.999999'
                                WHERE page_id = 57400),
  'system_versioning_asof gives the same revision as AS OF');
CALL check_that(@@system_versioning_asof = 'DEFAULT' AND (SELECT COUNT(*) FROM article) = (SELECT COUNT(*) FROM page),
  'system_versioning_asof is back to DEFAULT, every article is current again');

-- Checks 18 to 20. Retention on a copy: DELETE HISTORY keeps the current rows and newer history
CREATE OR REPLACE TEMPORARY TABLE kept AS
  SELECT COUNT(*) AS n FROM article FOR SYSTEM_TIME ALL WHERE row_end >= '2010-01-01';
CREATE OR REPLACE TABLE article_retention LIKE article;
SET @@system_versioning_insert_history = 1;
INSERT INTO article_retention (page_id, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end)
  SELECT page_id, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end FROM article FOR SYSTEM_TIME ALL;
SET @@system_versioning_insert_history = 0;
DELETE HISTORY FROM article_retention BEFORE SYSTEM_TIME '2010-01-01 00:00:00';
CALL check_that((SELECT COUNT(*) FROM article_retention FOR SYSTEM_TIME ALL) = (SELECT n FROM kept)
                AND (SELECT COUNT(*) FROM article_retention) = (SELECT COUNT(*) FROM page),
  'DELETE HISTORY removes only the versions that ended before the moment');
CALL expect_error('ALTER TABLE article_retention DROP PARTITION p0', 0,
  'DROP PARTITION of the oldest year works without changing alter_history');
CALL expect_error('ALTER TABLE article_retention DROP PARTITION p10', 4116,
  'only the oldest partitions can be dropped');
DROP TABLE article_retention;

-- Check 21. The versions of an article form one unbroken line. Nothing in the server
--    checks this for imported history (see checks 26 and 27), so the loader is tested.
CALL check_that((SELECT COUNT(*) FROM (
                   SELECT row_end, LEAD(row_start) OVER (PARTITION BY page_id ORDER BY row_end) AS next_start
                   FROM article FOR SYSTEM_TIME ALL) v
                 WHERE next_start IS NOT NULL AND next_start <> row_end) = 0,
  'no two versions of an article overlap and there are no gaps');

-- Checks 22 and 23. The first-row query: same answer as AS OF without reading every later version
CALL first_row_mismatches(@bad, @total);
CALL check_that(@bad = 0 AND @total = (SELECT COUNT(*) FROM expected),
  CONCAT('first-row query matches Python for ', @total, ' moments (', @bad, ' wrong)'));
CALL check_that((SELECT COUNT(*) FROM (SELECT rev_id, row_start FROM article FOR SYSTEM_TIME ALL
                   WHERE page_id = 57400 AND row_end > '2001-01-01 00:00:00' ORDER BY row_end LIMIT 1) v
                 WHERE v.row_start <= '2001-01-01 00:00:00') = 0,
  'first-row query before the first edit returns nothing');

-- Checks 24 to 34. The edges of system time, on a scratch table (sql/examples/limits.sql shows them one by one)
CREATE OR REPLACE TABLE limit_check (
  id INT NOT NULL PRIMARY KEY, v INT,
  row_start TIMESTAMP(6) AS ROW START INVISIBLE, row_end TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)) WITH SYSTEM VERSIONING;
SET @@system_versioning_insert_history = 1;
CALL expect_error(
  'INSERT INTO limit_check (id, v, row_start, row_end) VALUES (1, 1, ''1969-06-01 00:00:00'', ''1980-01-01 00:00:00'')',
  1292, 'history cannot start before 1970');
CALL expect_error(
  'INSERT INTO limit_check (id, v, row_start, row_end) VALUES (3, 1, ''2020-01-01 00:00:00'', ''2019-01-01 00:00:00'')',
  4112, 'a version cannot end before it starts');
CALL expect_error(
  'INSERT INTO limit_check (id, v, row_start, row_end) VALUES (4, 1, ''2020-01-01 00:00:00'', ''2021-01-01 00:00:00''), (4, 2, ''2020-06-01 00:00:00'', ''2022-01-01 00:00:00'')',
  0, 'imported versions that overlap are accepted');
SET @@system_versioning_insert_history = 0;
CALL check_that((SELECT COUNT(*) FROM limit_check FOR SYSTEM_TIME AS OF TIMESTAMP '2020-09-01 00:00:00' WHERE id = 4) = 2,
  'and AS OF then returns two rows for one primary key');
INSERT INTO limit_check (id, v) VALUES (10, 1);
UPDATE limit_check SET v = 1 WHERE id = 10;
CALL check_that((SELECT COUNT(*) FROM limit_check FOR SYSTEM_TIME ALL WHERE id = 10) = 2,
  'an UPDATE that changes nothing still makes a version');
CALL expect_error('TRUNCATE TABLE limit_check', 4137, 'TRUNCATE is refused on a versioned table');
CREATE OR REPLACE TABLE limit_check_trx (
  id INT NOT NULL PRIMARY KEY, v INT,
  row_start BIGINT UNSIGNED AS ROW START INVISIBLE, row_end BIGINT UNSIGNED AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)) WITH SYSTEM VERSIONING;
SET @@system_versioning_insert_history = 1;
CALL expect_error('INSERT INTO limit_check_trx (id, v, row_start, row_end) VALUES (1, 1, 100, 200)',
  1906, 'history cannot be imported into a table versioned by transaction id');
SET @@system_versioning_insert_history = 0;
CALL expect_error(
  'CREATE TABLE limit_check_part (id INT NOT NULL PRIMARY KEY, row_start BIGINT UNSIGNED AS ROW START INVISIBLE, row_end BIGINT UNSIGNED AS ROW END INVISIBLE, PERIOD FOR SYSTEM_TIME (row_start, row_end)) WITH SYSTEM VERSIONING PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR PARTITIONS 3',
  4110, 'and such a table cannot be partitioned by SYSTEM_TIME');
CREATE OR REPLACE TABLE limit_check_views (id INT NOT NULL PRIMARY KEY, body VARCHAR(20),
  views INT WITHOUT SYSTEM VERSIONING) WITH SYSTEM VERSIONING;
INSERT INTO limit_check_views VALUES (1, 'text', 0);
UPDATE limit_check_views SET views = views + 1;
CALL check_that((SELECT COUNT(*) FROM limit_check_views FOR SYSTEM_TIME ALL) = 1,
  'a column WITHOUT SYSTEM VERSIONING changes without making a version');
CREATE OR REPLACE TABLE limit_check_clock (id INT NOT NULL PRIMARY KEY, v INT) WITH SYSTEM VERSIONING;
SET @@timestamp = UNIX_TIMESTAMP('2019-03-01 00:00:00'); INSERT INTO limit_check_clock VALUES (1, 1);
SET @@timestamp = UNIX_TIMESTAMP('2021-06-01 00:00:00'); UPDATE limit_check_clock SET v = 2;
SET @@timestamp = UNIX_TIMESTAMP('2024-01-15 00:00:00'); UPDATE limit_check_clock SET v = 3;
SET @@timestamp = DEFAULT;
CALL check_that((SELECT COUNT(*) FROM limit_check_clock FOR SYSTEM_TIME ALL) = 3
                AND (SELECT v FROM limit_check_clock FOR SYSTEM_TIME AS OF TIMESTAMP '2020-01-01 00:00:00') = 1
                AND (SELECT v FROM limit_check_clock FOR SYSTEM_TIME AS OF TIMESTAMP '2022-01-01 00:00:00') = 2,
  'a replay with SET @@timestamp lets the server write past history itself');
SET @@timestamp = UNIX_TIMESTAMP('2020-01-01 00:00:00'); UPDATE limit_check_clock SET v = 4;
SET @@timestamp = DEFAULT;
CALL check_that((SELECT COUNT(*) FROM limit_check_clock FOR SYSTEM_TIME ALL) = 3
                AND (SELECT COUNT(*) FROM limit_check_clock FOR SYSTEM_TIME ALL WHERE v = 3) = 0
                AND (SELECT COUNT(*) FROM limit_check_clock FOR SYSTEM_TIME AS OF TIMESTAMP '2020-06-01 00:00:00') = 2,
  'one step back with the clock loses a version and leaves an overlap, with no error');
DROP TABLE IF EXISTS limit_check, limit_check_trx, limit_check_part, limit_check_views, limit_check_clock;

-- Checks 35 and 36. After the import the server keeps the history itself: one UPDATE on
--     article today, inside a transaction that is rolled back.
SET @versions = (SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL WHERE page_id = 57400);
SET @last_rev = (SELECT rev_id FROM article WHERE page_id = 57400);
SET @before_edit = NOW(6);
DO SLEEP(0.01);
START TRANSACTION;
UPDATE article SET rev_id = rev_id + 1, comment = 'test edit' WHERE page_id = 57400;
SET @during = (SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL WHERE page_id = 57400);
SET @closed = (SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL
               WHERE page_id = 57400 AND rev_id = @last_rev AND row_end > @before_edit AND row_end <= NOW(6));
SET @then = (SELECT rev_id FROM article FOR SYSTEM_TIME AS OF TIMESTAMP @before_edit WHERE page_id = 57400);
ROLLBACK;
CALL check_that(@during = @versions + 1 AND @closed = 1 AND @then = @last_rev,
  'an UPDATE today makes the server close the imported row and keep it as history');
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL WHERE page_id = 57400) = @versions
                AND (SELECT rev_id FROM article WHERE page_id = 57400) = @last_rev,
  'and the rollback leaves the loaded history untouched');

-- Check 37. Ranges: FROM ... TO leaves out a version that starts exactly at the end, BETWEEN keeps it
SET @edit = (SELECT row_start FROM article FOR SYSTEM_TIME ALL WHERE page_id = 57400 ORDER BY row_start LIMIT 1 OFFSET 100);
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME BETWEEN TIMESTAMP '2001-01-01 00:00:00' AND TIMESTAMP @edit
                 WHERE page_id = 57400) = 101
            AND (SELECT COUNT(*) FROM article FOR SYSTEM_TIME FROM TIMESTAMP '2001-01-01 00:00:00' TO TIMESTAMP @edit
                 WHERE page_id = 57400) = 100,
  'FROM ... TO stops one version before BETWEEN when the range ends at an edit');

-- Check 38. The page's user: it may read, and insert into exact_text. Nothing else.
CALL check_that((SELECT GROUP_CONCAT(PRIVILEGE_TYPE ORDER BY PRIVILEGE_TYPE) FROM information_schema.USER_PRIVILEGES
                 WHERE GRANTEE = "'timemachine_page'@'%'") = 'USAGE'
            AND (SELECT GROUP_CONCAT(CONCAT(TABLE_SCHEMA, ':', PRIVILEGE_TYPE) ORDER BY 1) FROM information_schema.SCHEMA_PRIVILEGES
                 WHERE GRANTEE = "'timemachine_page'@'%'") = 'timemachine:SELECT'
            AND (SELECT GROUP_CONCAT(CONCAT(TABLE_NAME, ':', PRIVILEGE_TYPE) ORDER BY 1) FROM information_schema.TABLE_PRIVILEGES
                 WHERE GRANTEE = "'timemachine_page'@'%'") = 'exact_text:INSERT',
  'the page user may SELECT in timemachine and INSERT into exact_text, nothing else');

-- Checks 39 and 40. AUTO partitions and an imported past (sql/examples/limits.sql, step 9).
--    With too few partitions the imported versions all sit in the first one.
--    One live UPDATE makes AUTO add the missing years, and AS OF then skips
--    the partition the old versions are in. The loaded table must not be in
--    that state: its partitions reach past its newest history row.
CREATE OR REPLACE TABLE t_auto (
  item VARCHAR(10) NOT NULL PRIMARY KEY,
  mad  DECIMAL(6,2)
) WITH SYSTEM VERSIONING
  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2005-01-01 00:00:00' AUTO;
SET @@system_versioning_insert_history = 1;
INSERT INTO t_auto (item, mad, row_start, row_end) VALUES
  ('tea', 10.00, '2005-03-01 00:00:00', '2009-07-01 00:00:00'),
  ('tea', 12.50, '2009-07-01 00:00:00', '2016-02-01 00:00:00'),
  ('tea', 14.00, '2016-02-01 00:00:00', '2023-10-01 00:00:00');
INSERT INTO t_auto (item, mad, row_start) VALUES ('tea', 15.00, '2023-10-01 00:00:00');
SET @@system_versioning_insert_history = 0;
SET @before = (SELECT mad FROM t_auto FOR SYSTEM_TIME AS OF TIMESTAMP '2018-01-01 00:00:00');
UPDATE t_auto SET mad = 16.00;
SET @after = (SELECT mad FROM t_auto FOR SYSTEM_TIME AS OF TIMESTAMP '2018-01-01 00:00:00');
CALL check_that(@before = 14.00 AND @after IS NULL
                AND (SELECT COUNT(*) FROM t_auto FOR SYSTEM_TIME ALL WHERE mad = 14.00) = 1,
  'with too few partitions, one live UPDATE after an import makes AS OF lose a version that is still stored');
DROP TABLE t_auto;
CALL check_that((SELECT MAX(row_end) FROM article FOR SYSTEM_TIME ALL WHERE row_end < NOW())
                < (SELECT MAX(PARTITION_DESCRIPTION) FROM information_schema.PARTITIONS
                   WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article' AND PARTITION_DESCRIPTION <> 'CURRENT'),
  'the partitions of article reach past its newest history row, so no version is misplaced');

SELECT CONCAT(IF(ok, 'ok ', 'not ok '), n, ' - ', name) AS tap FROM result ORDER BY n;
DROP PROCEDURE check_that; DROP PROCEDURE as_of_mismatches; DROP PROCEDURE first_row_mismatches;
DROP PROCEDURE expect_error;
