-- The same idea in a fleet tracking app: which driver had which truck.
--
-- Based on JPTrack, a vehicle tracking platform in Morocco. The data here
-- is invented. A fleet app needs two answers that a plain table cannot give:
--   * who drove truck TRK-12 on 12 March           (application time)
--   * what did our records say before a correction (system time)
-- A bitemporal table answers both, and refuses impossible data on its own.
--
--   scripts/db.sh -t < sql/examples/fleet.sql
USE timemachine;

CREATE OR REPLACE TABLE assignment (
  vehicle    VARCHAR(10) NOT NULL,
  driver     VARCHAR(30) NOT NULL,
  valid_from DATE        NOT NULL,
  valid_to   DATE        NOT NULL,
  PERIOD FOR valid_time (valid_from, valid_to),
  -- one driver per truck at any moment
  UNIQUE (vehicle, valid_time WITHOUT OVERLAPS)
) WITH SYSTEM VERSIONING;

-- March plan, entered on day one
INSERT INTO assignment VALUES
  ('TRK-12', 'Karim',   '2026-03-01', '2026-04-01'),
  ('TRK-07', 'Youssef', '2026-03-01', '2026-03-10'),
  ('TRK-07', 'Sara',    '2026-03-10', '2026-04-01');

SELECT SLEEP(1) INTO @pause;
SET @before_fix = NOW(6);
SELECT SLEEP(1) INTO @pause;

-- A correction arrives later: Youssef drove TRK-12 from 10 to 15 March.
-- FOR PORTION OF splits Karim's row into three: before, the fix, after.
UPDATE assignment FOR PORTION OF valid_time FROM '2026-03-10' TO '2026-03-15'
SET driver = 'Youssef'
WHERE vehicle = 'TRK-12';

SELECT vehicle, driver, valid_from, valid_to
FROM assignment WHERE vehicle = 'TRK-12' ORDER BY valid_from;

-- Who drove TRK-12 on 12 March, today and before the correction
SELECT 'today' AS records, driver
FROM assignment
WHERE vehicle = 'TRK-12' AND valid_from <= '2026-03-12' AND valid_to > '2026-03-12'
UNION ALL
SELECT 'before the fix', driver
FROM assignment FOR SYSTEM_TIME AS OF TIMESTAMP @before_fix
WHERE vehicle = 'TRK-12' AND valid_from <= '2026-03-12' AND valid_to > '2026-03-12';

-- A second driver on the same truck at the same time is refused.
-- Expected: ERROR 1062 Duplicate entry 'TRK-12-2026-03-25-2026-03-20' ...
-- (MariaDB reports the period end before the start; see the README.)
INSERT INTO assignment VALUES ('TRK-12', 'Sara', '2026-03-20', '2026-03-25');
