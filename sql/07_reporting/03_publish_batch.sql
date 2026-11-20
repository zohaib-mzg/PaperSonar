-- =============================================================================
-- Purpose: Publication gate. Publish the active batch only when DQ has run and
--          no CRITICAL rule failed; advance the source watermark only when the
--          window was not capped by max_records.
-- Inputs: CURRENT_BATCH, DQ_RESULT, BATCH, SOURCE_WATERMARK.
-- Outputs: PUBLISHED_BATCH row, BATCH status PUBLISHED, watermark update for
--          complete windows, LINEAGE_EVENT.
-- Idempotent: Yes - MERGE on BATCH_ID and repeatable watermark update.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None.
-- Cost: Small metadata statements only.
-- =============================================================================
-- A missing DQ result set blocks publication. Publication never infers success
-- from the absence of failures. A capped batch is published for visibility but
-- never advances the watermark, because part of its window was not read.

CREATE OR REPLACE PROCEDURE PAPERSONAR.PROJECT_REPORTING.SP_PUBLISH_BATCH()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  batch_id           VARCHAR DEFAULT NULL;
  source_name        VARCHAR;
  entity_name        VARCHAR;
  extraction_mode    VARCHAR;
  window_start       DATE;
  window_end         DATE;
  dq_checks          NUMBER DEFAULT 0;
  expected_checks    NUMBER DEFAULT 0;
  critical_failures  NUMBER DEFAULT 0;
  total_failures     NUMBER DEFAULT 0;
  is_capped          BOOLEAN DEFAULT FALSE;
  resume_cursor      VARCHAR;
  publish_result     VARCHAR DEFAULT 'PUBLISHED';
BEGIN
  SELECT BATCH_ID INTO :batch_id
  FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH
  LIMIT 1;

  IF (batch_id IS NULL) THEN
    RETURN 'NO_BATCH';
  END IF;

  SELECT COUNT(*) INTO :dq_checks
  FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
  WHERE BATCH_ID = :batch_id;

  SELECT COUNT(*) INTO :expected_checks
  FROM PAPERSONAR.PROJECT_REF.REF_DQ_RULE
  WHERE IS_ACTIVE;

  IF (dq_checks = 0) THEN
    RETURN 'BLOCKED_NO_DQ';
  END IF;

  IF (dq_checks < expected_checks) THEN
    UPDATE PAPERSONAR.PROJECT_AUDIT.BATCH
       SET STATUS = 'FAILED',
           FINISHED_AT = CURRENT_TIMESTAMP(),
           ERROR_SUMMARY = 'Publication blocked: only ' || :dq_checks ||
                           ' of ' || :expected_checks || ' DQ rules ran',
           UPDATED_AT = CURRENT_TIMESTAMP()
     WHERE BATCH_ID = :batch_id;
    RETURN 'BLOCKED_INCOMPLETE_DQ';
  END IF;

  SELECT
    COUNT_IF(SEVERITY = 'CRITICAL' AND STATUS = 'FAIL'),
    COUNT_IF(STATUS = 'FAIL')
    INTO :critical_failures, :total_failures
  FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
  WHERE BATCH_ID = :batch_id;

  IF (critical_failures > 0) THEN
    UPDATE PAPERSONAR.PROJECT_AUDIT.BATCH
       SET STATUS = 'FAILED',
           FINISHED_AT = CURRENT_TIMESTAMP(),
           ERROR_SUMMARY = 'Publication blocked by ' || :critical_failures ||
                           ' critical DQ failure(s)',
           UPDATED_AT = CURRENT_TIMESTAMP()
     WHERE BATCH_ID = :batch_id;
    RETURN 'BLOCKED_DQ';
  END IF;

  SELECT SOURCE_NAME, ENTITY_NAME, EXTRACTION_MODE, WINDOW_START, WINDOW_END,
         IS_CAPPED, CURSOR_END
    INTO :source_name, :entity_name, :extraction_mode, :window_start, :window_end,
         :is_capped, :resume_cursor
  FROM PAPERSONAR.PROJECT_AUDIT.BATCH
  WHERE BATCH_ID = :batch_id;

  MERGE INTO PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH t
  USING (
    SELECT
      :batch_id AS BATCH_ID,
      CURRENT_USER() AS PUBLISHED_BY,
      'critical_failures=0;total_failures=' || :total_failures AS DQ_SUMMARY,
      COALESCE(:is_capped, FALSE) AS IS_CAPPED
  ) s
  ON t.BATCH_ID = s.BATCH_ID
  WHEN MATCHED THEN UPDATE SET
    t.DQ_SUMMARY = s.DQ_SUMMARY,
    t.IS_CAPPED = s.IS_CAPPED,
    t.PUBLISHED_AT = CURRENT_TIMESTAMP()
  WHEN NOT MATCHED THEN INSERT
    (BATCH_ID, PUBLISHED_AT, PUBLISHED_BY, DQ_SUMMARY, IS_CAPPED)
    VALUES (s.BATCH_ID, CURRENT_TIMESTAMP(), s.PUBLISHED_BY, s.DQ_SUMMARY, s.IS_CAPPED);

  UPDATE PAPERSONAR.PROJECT_AUDIT.BATCH
     SET STATUS = 'PUBLISHED',
         FINISHED_AT = CURRENT_TIMESTAMP(),
         UPDATED_AT = CURRENT_TIMESTAMP()
   WHERE BATCH_ID = :batch_id;

  IF (COALESCE(:is_capped, FALSE)) THEN
    -- Publish the partial data for visibility, but do not claim the window is
    -- complete. Advance only to the window start and store the first unread
    -- cursor so the next run resumes the exact same logical window.
    MERGE INTO PAPERSONAR.PROJECT_AUDIT.SOURCE_WATERMARK t
    USING (
      SELECT
        :source_name AS SOURCE_NAME,
        :entity_name AS ENTITY_NAME,
        TO_VARCHAR(:window_start) AS WATERMARK_VALUE,
        :window_start AS WINDOW_START,
        :window_end AS WINDOW_END,
        :resume_cursor AS CURSOR,
        :batch_id AS LAST_BATCH_ID
    ) s
    ON t.SOURCE_NAME = s.SOURCE_NAME AND t.ENTITY_NAME = s.ENTITY_NAME
    WHEN MATCHED THEN UPDATE SET
      t.WATERMARK_VALUE = TO_VARCHAR(GREATEST(
        COALESCE(TRY_TO_DATE(t.WATERMARK_VALUE), TO_DATE('1900-01-01')),
        COALESCE(TRY_TO_DATE(s.WATERMARK_VALUE), TO_DATE('1900-01-01'))
      )),
      t.WINDOW_START = s.WINDOW_START,
      t.WINDOW_END = s.WINDOW_END,
      t.CURSOR = s.CURSOR,
      t.LAST_BATCH_ID = s.LAST_BATCH_ID,
      t.LAST_SUCCESS_AT = CURRENT_TIMESTAMP(),
      t.STATUS = 'CAPPED',
      t.UPDATED_AT = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT
      (SOURCE_NAME, ENTITY_NAME, WATERMARK_VALUE, WINDOW_START, WINDOW_END,
       OVERLAP_DAYS, CURSOR, LAST_BATCH_ID, LAST_SUCCESS_AT, STATUS, UPDATED_AT)
      VALUES (s.SOURCE_NAME, s.ENTITY_NAME, s.WATERMARK_VALUE, s.WINDOW_START,
              s.WINDOW_END, 0, s.CURSOR, s.LAST_BATCH_ID, CURRENT_TIMESTAMP(),
              'CAPPED', CURRENT_TIMESTAMP());
    publish_result := 'PUBLISHED_CAPPED';
  ELSE
    -- Incremental windows are updated-date windows, so WINDOW_END is a valid
    -- updated-date watermark. A full backfill window is a publication-date
    -- window; using its WINDOW_END would move the change-feed watermark years
    -- backwards. Stamp a full backfill with the publication date instead.
    MERGE INTO PAPERSONAR.PROJECT_AUDIT.SOURCE_WATERMARK t
    USING (
      SELECT
        :source_name AS SOURCE_NAME,
        :entity_name AS ENTITY_NAME,
        TO_VARCHAR(
          IFF(UPPER(:extraction_mode) = 'FULL', CURRENT_DATE(), :window_end)
        ) AS WATERMARK_VALUE,
        :window_start AS WINDOW_START,
        :window_end AS WINDOW_END,
        :batch_id AS LAST_BATCH_ID
    ) s
    ON t.SOURCE_NAME = s.SOURCE_NAME AND t.ENTITY_NAME = s.ENTITY_NAME
    WHEN MATCHED THEN UPDATE SET
      t.WATERMARK_VALUE = TO_VARCHAR(GREATEST(
        COALESCE(TRY_TO_DATE(t.WATERMARK_VALUE), TO_DATE('1900-01-01')),
        COALESCE(TRY_TO_DATE(s.WATERMARK_VALUE), TO_DATE('1900-01-01'))
      )),
      t.WINDOW_START = s.WINDOW_START,
      t.WINDOW_END = s.WINDOW_END,
      t.CURSOR = NULL,
      t.LAST_BATCH_ID = s.LAST_BATCH_ID,
      t.LAST_SUCCESS_AT = CURRENT_TIMESTAMP(),
      t.STATUS = 'PUBLISHED',
      t.UPDATED_AT = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT
      (SOURCE_NAME, ENTITY_NAME, WATERMARK_VALUE, WINDOW_START, WINDOW_END,
       OVERLAP_DAYS, CURSOR, LAST_BATCH_ID, LAST_SUCCESS_AT, STATUS, UPDATED_AT)
      VALUES (s.SOURCE_NAME, s.ENTITY_NAME, s.WATERMARK_VALUE, s.WINDOW_START,
              s.WINDOW_END, 0, NULL, s.LAST_BATCH_ID, CURRENT_TIMESTAMP(),
              'PUBLISHED', CURRENT_TIMESTAMP());
  END IF;

  MERGE INTO PAPERSONAR.PROJECT_AUDIT.LINEAGE_EVENT t
  USING (
    SELECT
      SHA2(:batch_id || '|REPORTING|PUBLISH', 256) AS EVENT_ID,
      :batch_id AS BATCH_ID,
      'REPORTING' AS LAYER,
      'PUBLISHED_BATCH' AS OBJECT_NAME,
      'PUBLISH' AS EVENT_TYPE,
      (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
        WHERE BATCH_ID = :batch_id) AS INPUT_COUNT,
      1 AS OUTPUT_COUNT
  ) s
  ON t.EVENT_ID = s.EVENT_ID
  WHEN MATCHED THEN UPDATE SET
    t.INPUT_COUNT = s.INPUT_COUNT,
    t.OUTPUT_COUNT = s.OUTPUT_COUNT,
    t.EVENT_AT = CURRENT_TIMESTAMP()
  WHEN NOT MATCHED THEN INSERT
    (EVENT_ID, BATCH_ID, LAYER, OBJECT_NAME, EVENT_TYPE, INPUT_COUNT,
     OUTPUT_COUNT, EVENT_AT)
    VALUES (s.EVENT_ID, s.BATCH_ID, s.LAYER, s.OBJECT_NAME, s.EVENT_TYPE,
            s.INPUT_COUNT, s.OUTPUT_COUNT, CURRENT_TIMESTAMP());

  RETURN :publish_result;
END;
$$;

COMMENT ON PROCEDURE PAPERSONAR.PROJECT_REPORTING.SP_PUBLISH_BATCH()
  IS 'Fail-closed publication gate; watermark advances only for complete windows';
