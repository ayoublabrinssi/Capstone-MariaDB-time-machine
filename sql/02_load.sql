-- Loads data/load/*.tsv (made by fetch/prepare.py) into the schema.
-- The files are mounted read-only at /data/load inside the container.
USE timemachine;
SET time_zone = '+00:00';

LOAD DATA INFILE '/data/load/page.tsv' INTO TABLE page;
LOAD DATA INFILE '/data/load/revision_text.tsv' INTO TABLE revision_text;

-- History rows with their real start and end times. Without this setting
-- MariaDB refuses to write row_start / row_end: system time normally comes
-- from the server clock only.
SET @@system_versioning_insert_history = 1;
LOAD DATA INFILE '/data/load/article_history.tsv' INTO TABLE article
  (page_id, rev_id, editor, comment, bytes, text_rev_id, row_start, row_end);
-- Current rows: real start time, open end.
LOAD DATA INFILE '/data/load/article_current.tsv' INTO TABLE article
  (page_id, rev_id, editor, comment, bytes, text_rev_id, row_start);
SET @@system_versioning_insert_history = 0;

-- Application-time periods. Ordinary insert: row_start = now.
LOAD DATA INFILE '/data/load/article_period.tsv' INTO TABLE article_period
  (page_id, rev_id, bytes, valid_from, valid_to);

SELECT 'page' AS loaded, COUNT(*) AS `rows` FROM page
UNION ALL SELECT 'revision_text', COUNT(*) FROM revision_text
UNION ALL SELECT 'article (current)', COUNT(*) FROM article
UNION ALL SELECT 'article (all versions)', COUNT(*) FROM article FOR SYSTEM_TIME ALL
UNION ALL SELECT 'article_period', COUNT(*) FROM article_period;
