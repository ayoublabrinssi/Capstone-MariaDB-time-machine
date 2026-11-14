-- Bitemporal on real Wikipedia data: hiding a reverted edit, and still
-- knowing what the database said before.
--
-- On 26 April 2018 at 14:46 UTC an edit to Marrakesh (rev 838361314) was
-- live for about 19 hours before it was reverted. Suppose a reader-facing
-- service wants to skip reverted edits: for that period it should show the
-- revision before it instead. That is a correction of the application-time
-- period, made today. article_period is also system-versioned, so the server
-- keeps the period as it was before the correction, and three questions have
-- an answer:
--   * what was live on Wikipedia at 20:00 that day      (system time of article)
--   * what the service shows for 20:00 that day         (application time, corrected)
--   * what the service showed before the correction     (system time of article_period)
--
-- Works on article_period itself, inside a transaction that is rolled back
-- at the end, so the loaded data stays as it was and the file can be run
-- again and again. Needs the full data (Marrakesh is not in the sample).
--   scripts/db.sh -t < sql/examples/wikipedia_correction.sql
USE timemachine;
SET time_zone = '+00:00';

-- The two clocks of article_period, before anything is changed:
-- valid_from is Wikipedia's time, row_start is when this database learned it.
SELECT MIN(valid_from) AS first_valid_from, MAX(valid_from) AS last_valid_from,
       MIN(row_start) AS learned_from, MAX(row_start) AS learned_until,
       COUNT(*) AS periods
FROM article_period FOR SYSTEM_TIME ALL;

-- The reverted edit and the revision before it
SELECT page_id INTO @page FROM page WHERE title = 'Marrakesh';
SELECT valid_from, valid_to INTO @bad_from, @bad_to
FROM article_period WHERE page_id = @page AND rev_id = 838361314;
SELECT rev_id INTO @good_rev
FROM article_period WHERE page_id = @page AND valid_to = @bad_from;

SELECT SLEEP(1) INTO @pause;          -- so "before" and "after" differ in system time
SET @before_fix = NOW(6);
SELECT SLEEP(1) INTO @pause;

START TRANSACTION;

-- The correction: for that period only, show the good revision.
-- FOR PORTION OF updates exactly that slice of time, nothing else.
UPDATE article_period FOR PORTION OF valid_time FROM @bad_from TO @bad_to
SET rev_id = @good_rev
WHERE page_id = @page AND rev_id = 838361314;

SET @moment = '2018-04-26 20:00:00';

SELECT 'live on Wikipedia' AS question, a.rev_id, a.editor
FROM article FOR SYSTEM_TIME AS OF TIMESTAMP @moment a
WHERE a.page_id = @page
UNION ALL
SELECT 'our service today', ap.rev_id, NULL
FROM article_period ap
WHERE ap.page_id = @page AND ap.valid_from <= @moment AND ap.valid_to > @moment
UNION ALL
SELECT 'our service before the fix', ap.rev_id, NULL
FROM article_period FOR SYSTEM_TIME AS OF TIMESTAMP @before_fix ap
WHERE ap.page_id = @page AND ap.valid_from <= @moment AND ap.valid_to > @moment;

-- The full trail of the correction: the old row is kept, closed at the
-- moment of the UPDATE. Its row_start is the time of the load.
SELECT rev_id, valid_from, valid_to, row_start, row_end
FROM article_period FOR SYSTEM_TIME ALL
WHERE page_id = @page AND valid_from <= @moment AND valid_to > @moment
ORDER BY row_start;

-- Both clocks in one question: which periods of Marrakesh did the database
-- describe differently before the fix and after it?
SELECT COUNT(*) AS periods_changed_by_the_fix
FROM article_period FOR SYSTEM_TIME AS OF TIMESTAMP @before_fix old
JOIN article_period new_ ON new_.page_id = old.page_id AND new_.valid_from = old.valid_from
WHERE old.page_id = @page AND old.rev_id <> new_.rev_id;

ROLLBACK;

-- After the rollback the table is as loaded: the reverted edit is back and
-- no trace of the correction is left in system time.
SELECT (SELECT rev_id FROM article_period
        WHERE page_id = @page AND valid_from <= @moment AND valid_to > @moment) AS our_service_after_rollback,
       (SELECT COUNT(*) FROM article_period FOR SYSTEM_TIME ALL) AS periods;
