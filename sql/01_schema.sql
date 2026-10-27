-- Schema for the Wikipedia time machine. Developed on MariaDB 12.3.3.
--
-- Two clocks, two tables (README, "How time is modelled"):
--
--   article         system-versioned. One current row per city. Every older
--                   revision is a history row whose row_start / row_end are
--                   the REAL Wikipedia edit times, written once at import with
--                   system_versioning_insert_history. Read the past with
--                   FOR SYSTEM_TIME AS OF.
--
--   article_period  application-time period (valid_from, valid_to) = the same
--                   real edit times, as ordinary data, PLUS system versioning
--                   with the real load time. This one can be corrected later
--                   (UPDATE ... FOR PORTION OF) and still answers "what did
--                   the database say before the correction?". Bitemporal.
--
-- The text itself lives in revision_text, written once and never changed,
-- the way Wikipedia keeps revisions and text in separate tables.
-- All times are UTC.

CREATE DATABASE IF NOT EXISTS timemachine CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE timemachine;
SET time_zone = '+00:00';

DROP TABLE IF EXISTS article, article_period, revision_text, page;

-- One row per city article. Plain table.
CREATE TABLE page (
  page_id    INT          NOT NULL PRIMARY KEY,
  title      VARCHAR(255) NOT NULL UNIQUE,
  revisions  INT          NOT NULL,
  first_edit DATETIME     NOT NULL,
  last_edit  DATETIME     NOT NULL
);

-- Wikitext of the sampled revisions (first revision of each quarter, plus the
-- latest). Immutable, so not versioned.
CREATE TABLE revision_text (
  rev_id  BIGINT     NOT NULL PRIMARY KEY,
  page_id INT        NOT NULL,
  body    MEDIUMTEXT NOT NULL,
  KEY (page_id)
);

-- The time machine. System time = Wikipedia time.
-- Partitioned by the year a version ENDED (that is how SYSTEM_TIME partitions
-- work): p0 = versions replaced in 2001, ..., p25 = replaced in 2026,
-- pn = the current versions. The partitions are created up front because
-- AUTO alone puts imported history into one partition (README, limits).
-- AUTO stays on, so a new yearly partition is added as time goes on.
CREATE TABLE article (
  page_id     INT          NOT NULL PRIMARY KEY,
  rev_id      BIGINT       NOT NULL,
  editor      VARCHAR(255),
  comment     TEXT,
  bytes       INT,
  text_rev_id BIGINT       NOT NULL COMMENT 'stored text shown for this revision, see revision_text',
  row_start   TIMESTAMP(6) AS ROW START INVISIBLE,
  row_end     TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)
) WITH SYSTEM VERSIONING
  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2001-01-01 00:00:00' AUTO PARTITIONS 27;

-- Bitemporal: application time = Wikipedia time (data we may correct),
-- system time = when this database learned it.
-- WITHOUT OVERLAPS: two revisions of one article can never be live at once.
CREATE TABLE article_period (
  page_id    INT         NOT NULL,
  rev_id     BIGINT      NOT NULL,
  bytes      INT,
  valid_from DATETIME(6) NOT NULL,
  valid_to   DATETIME(6) NOT NULL,
  PERIOD FOR valid_time (valid_from, valid_to),
  PRIMARY KEY (page_id, valid_time WITHOUT OVERLAPS),
  KEY (rev_id)
) WITH SYSTEM VERSIONING;
