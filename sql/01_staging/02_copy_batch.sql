-- =============================================================================
-- Purpose: COPY one claimed batch from the internal raw stage into the matching
--          staging table and record per-file load reconciliation.
-- Inputs: PROJECT_AUDIT.CURRENT_BATCH, BATCH_MANIFEST (status REGISTERED/LOADED).
-- Outputs: five STG_* tables, FILE_LOAD_LOG rows, manifest status LOADED.
-- Idempotent: Yes - staging rows for the batch are deleted first and COPY uses
--            FORCE = TRUE so a replay reloads the same deterministic files.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None - the active batch comes from CURRENT_BATCH.
-- Cost: One COPY per registered file; XS warehouse compute.
-- =============================================================================
-- VERIFY: validate COPY metadata-column syntax, FORCE behaviour and internal
-- stage path handling in the target account before the first live run.

CREATE OR REPLACE PROCEDURE PAPERSONAR.PROJECT_STAGING.SP_COPY_BATCH()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  batch_id      VARCHAR DEFAULT NULL;
  table_name    VARCHAR;
  copy_sql      VARCHAR;
  staged_rows   NUMBER DEFAULT 0;
  source_name   VARCHAR;
  entity_name   VARCHAR;
  file_name     VARCHAR;
  manifest_rows NUMBER;
  manifest_files RESULTSET;
BEGIN
  SELECT BATCH_ID INTO :batch_id
  FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH
  LIMIT 1;

  IF (batch_id IS NULL) THEN
    RETURN 'NO_BATCH';
  END IF;

  -- Assign the resultset after batch_id is known. A cursor declared with
  -- :batch_id in the DECLARE block is bound before the SELECT INTO runs.
  manifest_files := (
    SELECT SOURCE_NAME, ENTITY_NAME, FILE_NAME, RECORD_COUNT
    FROM PAPERSONAR.PROJECT_AUDIT.BATCH_MANIFEST
    WHERE BATCH_ID = :batch_id
      AND STATUS IN ('REGISTERED', 'LOADED')
    ORDER BY FILE_NAME
  );

  -- Transient layer: clear this batch so COPY is a full, repeatable reload.
  DELETE FROM PAPERSONAR.PROJECT_STAGING.STG_OPENALEX_WORK WHERE BATCH_ID = :batch_id;
  DELETE FROM PAPERSONAR.PROJECT_STAGING.STG_CROSSREF_WORK WHERE BATCH_ID = :batch_id;
  DELETE FROM PAPERSONAR.PROJECT_STAGING.STG_ARXIV_RECORD WHERE BATCH_ID = :batch_id;
  DELETE FROM PAPERSONAR.PROJECT_STAGING.STG_DATACITE_DOI WHERE BATCH_ID = :batch_id;
  DELETE FROM PAPERSONAR.PROJECT_STAGING.STG_ZENODO_RECORD WHERE BATCH_ID = :batch_id;

  FOR rec IN manifest_files DO
    -- Cursor row fields are procedural values. Copy them to locals before
    -- using them in SQL statements or dynamic SQL.
    source_name := rec.SOURCE_NAME;
    entity_name := rec.ENTITY_NAME;
    file_name := rec.FILE_NAME;
    manifest_rows := rec.RECORD_COUNT;

    IF (NOT REGEXP_LIKE(
          file_name,
          '^[a-z0-9_]+/[a-z0-9_]+/[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}-[0-9]{2}-[0-9]{2}/part-[0-9]{6}-[0-9a-f]{12}[.]ndjson[.]gz$'
        )) THEN
      RETURN 'INVALID_STAGE_PATH';
    END IF;

    table_name := CASE UPPER(source_name)
      WHEN 'OPENALEX' THEN 'STG_OPENALEX_WORK'
      WHEN 'CROSSREF' THEN 'STG_CROSSREF_WORK'
      WHEN 'ARXIV'    THEN 'STG_ARXIV_RECORD'
      WHEN 'DATACITE' THEN 'STG_DATACITE_DOI'
      WHEN 'ZENODO'   THEN 'STG_ZENODO_RECORD'
      ELSE NULL
    END;

    IF (table_name IS NULL) THEN
      CONTINUE;
    END IF;

    copy_sql :=
      'COPY INTO PAPERSONAR.PROJECT_STAGING.' || table_name ||
      ' (PAYLOAD, FILE_NAME, FILE_ROW_NUMBER, BATCH_ID, LOADED_AT) ' ||
      'FROM (SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, ''' || :batch_id ||
      ''', CURRENT_TIMESTAMP()::TIMESTAMP_NTZ ' ||
      'FROM @PAPERSONAR.PROJECT_STAGING.RAW_STAGE/' || file_name || ') ' ||
      'FILE_FORMAT = (TYPE = JSON COMPRESSION = GZIP STRIP_OUTER_ARRAY = FALSE ' ||
      'STRIP_NULL_VALUES = FALSE REPLACE_INVALID_CHARACTERS = FALSE ' ||
      'IGNORE_UTF8_ERRORS = FALSE) ' ||
      'ON_ERROR = ''ABORT_STATEMENT'' FORCE = TRUE';
    EXECUTE IMMEDIATE :copy_sql;
    staged_rows := SQLROWCOUNT;

    MERGE INTO PAPERSONAR.PROJECT_AUDIT.FILE_LOAD_LOG t
    USING (
      SELECT :batch_id || ':' || :file_name AS FILE_LOAD_ID,
             :batch_id AS BATCH_ID, :source_name AS SOURCE_NAME,
             :entity_name AS ENTITY_NAME, :file_name AS FILE_NAME,
             :staged_rows AS STAGED_ROWS, :manifest_rows AS MANIFEST_ROWS
    ) s
    ON t.FILE_LOAD_ID = s.FILE_LOAD_ID
    WHEN MATCHED THEN UPDATE SET
      t.STAGED_ROWS = s.STAGED_ROWS,
      t.MANIFEST_ROWS = s.MANIFEST_ROWS,
      t.STATUS = IFF(s.STAGED_ROWS = s.MANIFEST_ROWS, 'MATCH', 'MISMATCH'),
      t.LOADED_AT = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT
      (FILE_LOAD_ID, BATCH_ID, SOURCE_NAME, ENTITY_NAME, FILE_NAME,
       STAGED_ROWS, MANIFEST_ROWS, STATUS, LOADED_AT)
      VALUES (s.FILE_LOAD_ID, s.BATCH_ID, s.SOURCE_NAME, s.ENTITY_NAME,
              s.FILE_NAME, s.STAGED_ROWS, s.MANIFEST_ROWS,
              IFF(s.STAGED_ROWS = s.MANIFEST_ROWS, 'MATCH', 'MISMATCH'),
              CURRENT_TIMESTAMP());

    UPDATE PAPERSONAR.PROJECT_AUDIT.BATCH_MANIFEST
       SET STATUS = 'LOADED', LOADED_AT = CURRENT_TIMESTAMP()
     WHERE BATCH_ID = :batch_id AND FILE_NAME = :file_name;
  END FOR;

  RETURN 'COPIED';
END;
$$;

COMMENT ON PROCEDURE PAPERSONAR.PROJECT_STAGING.SP_COPY_BATCH()
  IS 'COPY the active batch from RAW_STAGE into staging with per-file reconciliation';
