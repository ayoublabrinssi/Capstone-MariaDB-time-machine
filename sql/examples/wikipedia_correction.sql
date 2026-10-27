-- Bitemporal on real Wikipedia data: hiding a reverted edit, and still
-- knowing what the database said before.
--
-- On 26 April 2018 at 14:46 UTC an edit to Marrakesh (rev 838361314) was
-- live for about 19 hours before it was reverted. Suppose a reader-facing
-- service wants to skip reverted edits: for that period it should show the
-- revision before it instead. That is a correction of the application-time
-- period, made today. System versioning keeps the period as it was before
-- the correction, so both questions have an answer:
--   * what was live on Wikipedia at 20:00 that day      (raw history)
--   * what our service shows for 20:00 that day         (corrected)
--   * what our service showed before the correction     (AS OF system time)
--
-- Works on a copy of the Marrakesh rows, so it can be run again and again.
--   scripts/db.sh -t < sql/examples/wikipedia_correction.sql
USE timemachine;
SET time_zone = '+00:00';

CREATE OR REPLACE TABLE reader_view (
  page_id    INT         NOT NULL,
  rev_id     BIGINT      NOT NULL,
  valid_from DATETIME(6) NOT NULL,
  valid_to   DATETIME(6) NOT NULL,
  PERIOD FOR valid_time (valid_from, valid_to),
  PRIMARY KEY (page_id, valid_time WITHOUT OVERLAPS)
) WITH SYSTEM VERSIONING;

INSERT INTO reader_view (page_id, rev_id, valid_from, valid_to)
SELECT ap.page_id, ap.rev_id, ap.valid_from, ap.valid_to
FROM article_period ap JOIN page p USING (page_id)
WHERE p.title = 'Marrakesh';

-- The reverted edit and the revision before it
SELECT valid_from, valid_to INTO @bad_from, @bad_to
FROM reader_view WHERE rev_id = 838361314;
SELECT rev_id INTO @good_rev
FROM reader_view WHERE valid_to = @bad_from;

SELECT SLEEP(1) INTO @pause;          -- so "before" and "after" differ in system time
SET @before_fix = NOW(6);
SELECT SLEEP(1) INTO @pause;

-- The correction: for that period only, show the good revision.
-- FOR PORTION OF updates exactly that slice of time, nothing else.
UPDATE reader_view FOR PORTION OF valid_time FROM @bad_from TO @bad_to
SET rev_id = @good_rev
WHERE rev_id = 838361314;

SET @moment = '2018-04-26 20:00:00';

SELECT 'live on Wikipedia' AS question, a.rev_id, a.editor
FROM article FOR SYSTEM_TIME AS OF TIMESTAMP @moment a JOIN page p USING (page_id)
WHERE p.title = 'Marrakesh'
UNION ALL
SELECT 'our service today', r.rev_id, NULL
FROM reader_view r
WHERE r.valid_from <= @moment AND r.valid_to > @moment
UNION ALL
SELECT 'our service before the fix', r.rev_id, NULL
FROM reader_view FOR SYSTEM_TIME AS OF TIMESTAMP @before_fix r
WHERE r.valid_from <= @moment AND r.valid_to > @moment;

-- The full trail of the correction: the old row is kept, closed at the
-- moment of the UPDATE.
SELECT rev_id, valid_from, valid_to, row_start, row_end
FROM reader_view FOR SYSTEM_TIME ALL
WHERE valid_from <= @moment AND valid_to > @moment
ORDER BY row_start;
