-- 004: STG_WORK_RECORD.PUBLICATION_DATE DATE -> STRING
--
-- Sources (e.g. Crossref) often give partial dates such as '2002' or '2002-05'.
-- staging.py preserves them as text (YYYY, YYYY-MM or YYYY-MM-DD), and the
-- dimensional tables already store PUBLICATION_DATE as STRING, so the staging
-- column must be text as well. Snowflake cannot change DATE to STRING in place,
-- so: add a text column, copy existing values, drop the old column, rename.

ALTER TABLE PROJECT_STAGING.STG_WORK_RECORD ADD COLUMN PUBLICATION_DATE_TXT STRING;

UPDATE PROJECT_STAGING.STG_WORK_RECORD
SET PUBLICATION_DATE_TXT = TO_VARCHAR(PUBLICATION_DATE);

ALTER TABLE PROJECT_STAGING.STG_WORK_RECORD DROP COLUMN PUBLICATION_DATE;

ALTER TABLE PROJECT_STAGING.STG_WORK_RECORD RENAME COLUMN PUBLICATION_DATE_TXT TO PUBLICATION_DATE;
