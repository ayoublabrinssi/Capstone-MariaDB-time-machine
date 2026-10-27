-- Tests for the time machine. Run with scripts/test.sh after scripts/install.sh.
-- Each check prints "ok" or "not ok", one line each.
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

-- 1. The load
CALL check_that((SELECT COUNT(*) FROM page) = 45, '45 articles in page');
CALL check_that((SELECT COUNT(*) FROM article) = 45, 'one current row per article');
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL) = (SELECT SUM(revisions) FROM page),
  'every revision is a row of article (current + history)');
CALL check_that((SELECT COUNT(*) FROM article_period) = (SELECT SUM(revisions) FROM page),
  'every revision has an application-time period');
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL a
                 LEFT JOIN revision_text t ON t.rev_id = a.text_rev_id WHERE t.rev_id IS NULL) = 0,
  'every version points at stored text');

-- 2. The timestamps are Wikipedia's, not the load time
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME ALL WHERE row_start >= row_end) = 0,
  'every version has row_start < row_end');
CALL check_that((SELECT COUNT(*) FROM article a JOIN page p USING (page_id)
                 WHERE a.row_start <> p.last_edit) = 0,
  'current row starts at the last Wikipedia edit, not at load time');
CALL check_that((SELECT MIN(row_start) FROM article FOR SYSTEM_TIME ALL) < '2002-01-01',
  'history reaches back to 2001');

-- 3. AS OF gives the revision that was live at that moment
CALL as_of_mismatches(@bad, @total);
CALL check_that(@bad = 0 AND @total = (SELECT COUNT(*) FROM expected),
  CONCAT('AS OF matches Python for ', @total, ' moments (', @bad, ' wrong)'));
CALL check_that((SELECT COUNT(*) FROM article FOR SYSTEM_TIME AS OF TIMESTAMP '2001-01-01 00:00:00') = 0,
  'AS OF before the first edit returns nothing');

-- 4. The application-time period agrees with system time
CALL check_that((SELECT COUNT(*) FROM expected e
                 LEFT JOIN article_period ap ON ap.page_id = e.page_id
                      AND ap.valid_from <= e.at AND ap.valid_to > e.at
                 WHERE ap.rev_id IS NULL OR ap.rev_id <> e.rev_id) = 0,
  'application-time lookup gives the same revision as AS OF');

-- 5. What the server refuses (documented limits)
CALL expect_error(
  'INSERT INTO article_period (page_id, rev_id, valid_from, valid_to) SELECT page_id, 1, ''2010-01-01'', ''2010-02-01'' FROM page LIMIT 1',
  1062, 'WITHOUT OVERLAPS refuses a second live revision');
CALL expect_error('ALTER TABLE article ADD COLUMN lang CHAR(2)', 4119,
  'ALTER on a versioned table is refused by default');
CALL expect_error(
  'INSERT INTO article (page_id, rev_id, text_rev_id, row_start) VALUES (1, 1, 1, ''2010-01-01'')',
  1906, 'row_start cannot be written without system_versioning_insert_history');

-- 6. Partitions: history is spread by year, not in one partition
CALL check_that((SELECT COUNT(*) FROM information_schema.PARTITIONS
                 WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME = 'article' AND TABLE_ROWS > 0) >= 20,
  'history is spread over the yearly partitions');

SELECT CONCAT(IF(ok, 'ok ', 'not ok '), n, ' - ', name) AS tap FROM result ORDER BY n;
DROP PROCEDURE check_that; DROP PROCEDURE as_of_mismatches; DROP PROCEDURE expect_error;
