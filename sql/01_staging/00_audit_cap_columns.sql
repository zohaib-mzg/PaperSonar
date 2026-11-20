-- =============================================================================
-- Purpose: Add the capped-window audit columns to existing deployments.
-- Inputs: PAPERSONAR.PROJECT_AUDIT schema from 00_setup.
-- Outputs: BATCH.IS_CAPPED and PUBLISHED_BATCH.IS_CAPPED.
-- Idempotent: Yes - the scripting guard only adds missing columns.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata only; no table rebuild or backfill.
-- =============================================================================
-- The normal deployment skips 00_setup, so fresh columns must be added here as
-- well as in the one-time setup DDL. A TRUE value means the extractor stopped at
-- its configured max_records before the source window was exhausted. Publication
-- uses this flag to withhold watermark advancement.
--
-- Snowflake reports "ambiguous column name IS_CAPPED" for ALTER TABLE ...
-- ADD COLUMN IF NOT EXISTS IS_CAPPED on some existing deployments, so use an
-- explicit INFORMATION_SCHEMA guard instead.

EXECUTE IMMEDIATE $$
BEGIN
  LET batch_column_count NUMBER := 0;
  LET published_column_count NUMBER := 0;

  SELECT COUNT(*) INTO batch_column_count
  FROM PAPERSONAR.INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = 'PROJECT_AUDIT'
    AND TABLE_NAME = 'BATCH'
    AND COLUMN_NAME = 'IS_CAPPED';

  IF (batch_column_count = 0) THEN
    ALTER TABLE PAPERSONAR.PROJECT_AUDIT.BATCH
      ADD COLUMN IS_CAPPED BOOLEAN DEFAULT FALSE;
  END IF;

  SELECT COUNT(*) INTO published_column_count
  FROM PAPERSONAR.INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = 'PROJECT_AUDIT'
    AND TABLE_NAME = 'PUBLISHED_BATCH'
    AND COLUMN_NAME = 'IS_CAPPED';

  IF (published_column_count = 0) THEN
    ALTER TABLE PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH
      ADD COLUMN IS_CAPPED BOOLEAN DEFAULT FALSE;
  END IF;
END;
$$;
