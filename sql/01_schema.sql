-- Schema for the Wikipedia time machine. MariaDB 12.3.3.
-- One row per revision of an article, with two clocks:
--   valid_from / valid_to  = when this text was the live article on Wikipedia
--                            (application-time period, our data)
--   row_start / row_end    = when OUR database inserted or replaced the row
--                            (system-time period, kept by MariaDB)
-- Week 2 finishes this file (partitions, indexes, the JPTrack example).

CREATE DATABASE IF NOT EXISTS timemachine;
USE timemachine;

CREATE TABLE IF NOT EXISTS article (
  page_id    INT          NOT NULL,
  title      VARCHAR(255) NOT NULL,
  rev_id     BIGINT       NOT NULL,
  editor     VARCHAR(255),
  comment    TEXT,
  bytes      INT,
  body       MEDIUMTEXT,
  valid_from DATETIME(6)  NOT NULL,
  valid_to   DATETIME(6)  NOT NULL,
  PERIOD FOR valid_time (valid_from, valid_to),
  PRIMARY KEY (page_id, valid_time WITHOUT OVERLAPS),
  KEY (title)
) WITH SYSTEM VERSIONING;
