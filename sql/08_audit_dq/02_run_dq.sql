-- =============================================================================
-- Purpose: Run the versioned DQ suite for the active batch, persist every
--          observed value, and return PASS only when no CRITICAL rule failed.
-- Inputs: CURRENT_BATCH, manifest/staging/bronze/silver/fact/dimension tables,
--         QUARANTINE_RECORD, SCHEMA_DRIFT_LOG, SOURCE_WATERMARK, REF_DQ_RULE.
-- Outputs: DQ_RESULT rows, LINEAGE_EVENT row.
-- Idempotent: Yes - the batch's DQ rows are replaced on every run.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None.
-- Cost: Bounded scans of the active batch; XS warehouse compute.
-- =============================================================================
-- DQ-009 and DQ-010 are directional checks (observed >= threshold and observed
-- <= threshold respectively). Every other rule passes only when the observed
-- defect count is zero. WARNING failures are recorded and never block.

CREATE OR REPLACE PROCEDURE PAPERSONAR.PROJECT_AUDIT.SP_RUN_DQ()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  batch_id           VARCHAR DEFAULT NULL;
  critical_failures  NUMBER DEFAULT 0;
  total_failures     NUMBER DEFAULT 0;
  republish_mode     BOOLEAN DEFAULT FALSE;
  published_rows     NUMBER DEFAULT 0;
BEGIN
  SELECT BATCH_ID INTO :batch_id
  FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH
  LIMIT 1;

  IF (batch_id IS NULL) THEN
    RETURN 'NO_BATCH';
  END IF;

  -- A batch that is already in PUBLISHED_BATCH is being re-categorized, not
  -- re-ingested. The ingestion reconciliation rules compare layers that this
  -- run did not produce, so they are recorded as SKIPPED with a reason instead
  -- of being reported as failures. They were evaluated when the batch was
  -- published the first time.
  SELECT COUNT(*) INTO :published_rows
  FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH
  WHERE BATCH_ID = :batch_id;

  republish_mode := :published_rows > 0;

  DELETE FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT WHERE BATCH_ID = :batch_id;

  INSERT INTO PAPERSONAR.PROJECT_AUDIT.DQ_RESULT (
    DQ_RESULT_ID, BATCH_ID, RULE_ID, RULE_VERSION, LAYER, SEVERITY,
    DESCRIPTION, OBSERVED_VALUE, THRESHOLD_VALUE, STATUS, QUERY_ID,
    CHECKED_AT, NOTE
  )
  SELECT
    :batch_id || ':' || checks.RULE_ID,
    :batch_id,
    checks.RULE_ID,
    COALESCE(rule.RULE_VERSION, 'v1'),
    checks.LAYER,
    COALESCE(rule.SEVERITY, 'WARNING'),
    COALESCE(rule.DESCRIPTION, checks.RULE_ID),
    checks.OBSERVED_VALUE,
    checks.THRESHOLD_VALUE,
    checks.STATUS,
    LAST_QUERY_ID(),
    CURRENT_TIMESTAMP(),
    CASE
      WHEN checks.STATUS = 'SKIPPED'
      THEN 'Not re-evaluated: this batch was published before and the raw '
           || 'ingestion layer was not re-processed in this run.'
      ELSE NULL
    END AS NOTE
  FROM (
    -- DQ-001: manifest vs staging per file ----------------------------------
    SELECT
      'DQ-001' AS RULE_ID,
      'STAGING' AS LAYER,
      IFF(:republish_mode, NULL, COUNT(*)) AS OBSERVED_VALUE,
      0 AS THRESHOLD_VALUE,
      IFF(:republish_mode, 'SKIPPED', IFF(COUNT(*) = 0, 'PASS', 'FAIL')) AS STATUS
    FROM PAPERSONAR.PROJECT_AUDIT.BATCH_MANIFEST manifest
    LEFT JOIN (
      SELECT FILE_NAME, COUNT(*) AS STAGED_ROWS
      FROM PAPERSONAR.PROJECT_STAGING.STG_OPENALEX_WORK
      WHERE BATCH_ID = :batch_id
      GROUP BY FILE_NAME
      UNION ALL
      SELECT FILE_NAME, COUNT(*)
      FROM PAPERSONAR.PROJECT_STAGING.STG_CROSSREF_WORK
      WHERE BATCH_ID = :batch_id
      GROUP BY FILE_NAME
      UNION ALL
      SELECT FILE_NAME, COUNT(*)
      FROM PAPERSONAR.PROJECT_STAGING.STG_ARXIV_RECORD
      WHERE BATCH_ID = :batch_id
      GROUP BY FILE_NAME
      UNION ALL
      SELECT FILE_NAME, COUNT(*)
      FROM PAPERSONAR.PROJECT_STAGING.STG_DATACITE_DOI
      WHERE BATCH_ID = :batch_id
      GROUP BY FILE_NAME
      UNION ALL
      SELECT FILE_NAME, COUNT(*)
      FROM PAPERSONAR.PROJECT_STAGING.STG_ZENODO_RECORD
      WHERE BATCH_ID = :batch_id
      GROUP BY FILE_NAME
    ) staged
      ON staged.FILE_NAME = manifest.FILE_NAME
    WHERE manifest.BATCH_ID = :batch_id
      AND COALESCE(staged.STAGED_ROWS, 0) <> manifest.RECORD_COUNT

    UNION ALL

    -- DQ-002: distinct staged observation keys vs bronze --------------------
    SELECT
      'DQ-002' AS RULE_ID,
      'BRONZE' AS LAYER,
      IFF(:republish_mode, NULL, staged_bronze.DIFFERENCE) AS OBSERVED_VALUE,
      0 AS THRESHOLD_VALUE,
      IFF(:republish_mode, 'SKIPPED',
          IFF(staged_bronze.DIFFERENCE = 0, 'PASS', 'FAIL')) AS STATUS
    FROM (
      SELECT ABS(
        (
          SELECT COUNT(*)
          FROM (
            SELECT DISTINCT SOURCE_NAME, RECORD_KEY
            FROM (
              SELECT
                'OPENALEX' AS SOURCE_NAME,
                REGEXP_REPLACE(
                  PAYLOAD:id::STRING, '^https?://openalex[.]org/', ''
                ) AS RECORD_KEY,
                SHA2(TO_JSON(PAYLOAD), 256) AS RECORD_HASH
              FROM PAPERSONAR.PROJECT_STAGING.STG_OPENALEX_WORK
              WHERE BATCH_ID = :batch_id
              UNION ALL
              SELECT
                'CROSSREF',
                COALESCE(PAYLOAD:DOI::STRING, PAYLOAD:URL::STRING),
                SHA2(TO_JSON(PAYLOAD), 256)
              FROM PAPERSONAR.PROJECT_STAGING.STG_CROSSREF_WORK
              WHERE BATCH_ID = :batch_id
              UNION ALL
              SELECT
                'ARXIV',
                PAYLOAD:identifier::STRING,
                SHA2(TO_JSON(PAYLOAD), 256)
              FROM PAPERSONAR.PROJECT_STAGING.STG_ARXIV_RECORD
              WHERE BATCH_ID = :batch_id
              UNION ALL
              SELECT
                'DATACITE',
                COALESCE(PAYLOAD:attributes.doi::STRING, PAYLOAD:id::STRING),
                SHA2(TO_JSON(PAYLOAD), 256)
              FROM PAPERSONAR.PROJECT_STAGING.STG_DATACITE_DOI
              WHERE BATCH_ID = :batch_id
              UNION ALL
              SELECT
                'ZENODO',
                PAYLOAD:identifier::STRING,
                SHA2(TO_JSON(PAYLOAD), 256)
              FROM PAPERSONAR.PROJECT_STAGING.STG_ZENODO_RECORD
              WHERE BATCH_ID = :batch_id
            )
            WHERE RECORD_KEY IS NOT NULL AND TRIM(RECORD_KEY) <> ''
          )
        )
        -
        (
          (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK
            WHERE BATCH_ID = :batch_id)
          + (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_BRONZE.BRZ_CROSSREF_WORK
              WHERE BATCH_ID = :batch_id)
          + (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_BRONZE.BRZ_ARXIV_RECORD
              WHERE BATCH_ID = :batch_id)
          + (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_BRONZE.BRZ_DATACITE_DOI
              WHERE BATCH_ID = :batch_id)
          + (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_BRONZE.BRZ_ZENODO_RECORD
              WHERE BATCH_ID = :batch_id)
        )
      ) AS DIFFERENCE
    ) staged_bronze

    UNION ALL

    -- DQ-003: silver observations vs crosswalk + unsupported-shape quarantine
    SELECT
      'DQ-003',
      'SILVER',
      ABS(
        (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION
          WHERE BATCH_ID = :batch_id)
        - (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK
            WHERE BATCH_ID = :batch_id)
        - (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_AUDIT.QUARANTINE_RECORD
            WHERE BATCH_ID = :batch_id AND REASON_CODE = 'UNSUPPORTED_SHAPE')
      ),
      0,
      IFF(
        ABS(
          (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION
            WHERE BATCH_ID = :batch_id)
          - (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK
              WHERE BATCH_ID = :batch_id)
          - (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_AUDIT.QUARANTINE_RECORD
              WHERE BATCH_ID = :batch_id AND REASON_CODE = 'UNSUPPORTED_SHAPE')
        ) = 0,
        'PASS',
        'FAIL'
      )

    UNION ALL

    -- DQ-004: duplicate canonical fact grain ---------------------------------
    SELECT
      'DQ-004',
      'DW',
      COUNT(*),
      0,
      IFF(COUNT(*) = 0, 'PASS', 'FAIL')
    FROM (
      SELECT OUTPUT_SK
      FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT
      GROUP BY OUTPUT_SK
      HAVING COUNT(*) > 1
      UNION ALL
      SELECT OUTPUT_SK
      FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY
      GROUP BY OUTPUT_SK, CATEGORY_KEY
      HAVING COUNT(*) > 1
    ) duplicates

    UNION ALL

    -- DQ-005: fact dimension orphans -----------------------------------------
    SELECT
      'DQ-005',
      'DW',
      COUNT(*),
      0,
      IFF(COUNT(*) = 0, 'PASS', 'FAIL')
    FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
    WHERE fact.LAST_BATCH_ID = :batch_id
      AND (
        (fact.PUBLICATION_DATE_SK <> 0 AND NOT EXISTS (
          SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_DATE dim
          WHERE dim.DATE_SK = fact.PUBLICATION_DATE_SK
        ))
        OR NOT EXISTS (
          SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_OUTPUT_TYPE dim
          WHERE dim.OUTPUT_TYPE_SK = fact.OUTPUT_TYPE_SK
        )
        OR NOT EXISTS (
          SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_VENUE dim
          WHERE dim.VENUE_SK = fact.VENUE_SK
        )
        OR NOT EXISTS (
          SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_ACCESS_STATUS dim
          WHERE dim.ACCESS_STATUS_SK = fact.ACCESS_STATUS_SK
        )
        OR NOT EXISTS (
          SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_SOURCE dim
          WHERE dim.SOURCE_SK = fact.SOURCE_SK
        )
      )

    UNION ALL

    -- DQ-006: bridge orphans --------------------------------------------------
    SELECT
      'DQ-006',
      'DW',
      (
        SELECT COUNT(*)
        FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_AUTHOR bridge
        WHERE bridge.BATCH_ID = :batch_id
          AND (
            NOT EXISTS (
              SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_AUTHOR dim
              WHERE dim.AUTHOR_SK = bridge.AUTHOR_SK
            )
            OR NOT EXISTS (
              SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIMENSION_KEY_MAP map
              WHERE map.DIMENSION_NAME = 'OUTPUT'
                AND map.SURROGATE_KEY = bridge.OUTPUT_SK
            )
          )
      )
      + (
        SELECT COUNT(*)
        FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
        WHERE bridge.BATCH_ID = :batch_id
          AND (
            NOT EXISTS (
              SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_CATEGORY dim
              WHERE dim.CATEGORY_SK = bridge.CATEGORY_SK
            )
            OR NOT EXISTS (
              SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIMENSION_KEY_MAP map
              WHERE map.DIMENSION_NAME = 'OUTPUT'
                AND map.SURROGATE_KEY = bridge.OUTPUT_SK
            )
          )
      )
      + (
        SELECT COUNT(*)
        FROM PAPERSONAR.PROJECT_DW.BRIDGE_AUTHOR_INSTITUTION bridge
        WHERE bridge.BATCH_ID = :batch_id
          AND (
            NOT EXISTS (
              SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_AUTHOR dim
              WHERE dim.AUTHOR_SK = bridge.AUTHOR_SK
            )
            OR NOT EXISTS (
              SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_INSTITUTION dim
              WHERE dim.INSTITUTION_SK = bridge.INSTITUTION_SK
            )
          )
      ),
      0,
      IFF(
        (
          SELECT COUNT(*)
          FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_AUTHOR bridge
          WHERE bridge.BATCH_ID = :batch_id
            AND (
              NOT EXISTS (
                SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_AUTHOR dim
                WHERE dim.AUTHOR_SK = bridge.AUTHOR_SK
              )
              OR NOT EXISTS (
                SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIMENSION_KEY_MAP map
                WHERE map.DIMENSION_NAME = 'OUTPUT'
                  AND map.SURROGATE_KEY = bridge.OUTPUT_SK
              )
            )
        )
        + (
          SELECT COUNT(*)
          FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
          WHERE bridge.BATCH_ID = :batch_id
            AND (
              NOT EXISTS (
                SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_CATEGORY dim
                WHERE dim.CATEGORY_SK = bridge.CATEGORY_SK
              )
              OR NOT EXISTS (
                SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIMENSION_KEY_MAP map
                WHERE map.DIMENSION_NAME = 'OUTPUT'
                  AND map.SURROGATE_KEY = bridge.OUTPUT_SK
              )
            )
        )
        + (
          SELECT COUNT(*)
          FROM PAPERSONAR.PROJECT_DW.BRIDGE_AUTHOR_INSTITUTION bridge
          WHERE bridge.BATCH_ID = :batch_id
            AND (
              NOT EXISTS (
                SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_AUTHOR dim
                WHERE dim.AUTHOR_SK = bridge.AUTHOR_SK
              )
              OR NOT EXISTS (
                SELECT 1 FROM PAPERSONAR.PROJECT_DW.DIM_INSTITUTION dim
                WHERE dim.INSTITUTION_SK = bridge.INSTITUTION_SK
              )
            )
        ) = 0,
        'PASS',
        'FAIL'
      )

    UNION ALL

    -- DQ-007: one current author row per business key -------------------------
    SELECT
      'DQ-007',
      'DW',
      COUNT(*),
      0,
      IFF(COUNT(*) = 0, 'PASS', 'FAIL')
    FROM (
      SELECT AUTHOR_KEY
      FROM PAPERSONAR.PROJECT_DW.DIM_AUTHOR
      WHERE IS_CURRENT
      GROUP BY AUTHOR_KEY
      HAVING COUNT(*) > 1
    ) duplicates

    UNION ALL

    -- DQ-008: invalid DOI quarantine visibility ------------------------------
    SELECT
      'DQ-008',
      'SILVER',
      COUNT(*),
      0,
      IFF(COUNT(*) = 0, 'PASS', 'FAIL')
    FROM PAPERSONAR.PROJECT_AUDIT.QUARANTINE_RECORD
    WHERE BATCH_ID = :batch_id AND REASON_CODE = 'INVALID_DOI'

    UNION ALL

    -- DQ-009: category coverage ratio ----------------------------------------
    SELECT
      'DQ-009',
      'CATEGORIZATION',
      coverage.COVERAGE_RATIO,
      0.60,
      IFF(coverage.COVERAGE_RATIO >= 0.60, 'PASS', 'FAIL')
    FROM (
      SELECT
        IFF(
          COUNT(DISTINCT crosswalk.OUTPUT_BK) = 0,
          1.0,
          COUNT(DISTINCT IFF(category.CATEGORY_KEY <> 'unclassified',
                            category.OUTPUT_BK, NULL))
          / COUNT(DISTINCT crosswalk.OUTPUT_BK)
        ) AS COVERAGE_RATIO
      FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK crosswalk
      LEFT JOIN PAPERSONAR.PROJECT_STAGING.STG_OUTPUT_CATEGORY category
        ON category.BATCH_ID = crosswalk.BATCH_ID
       AND category.OUTPUT_BK = crosswalk.OUTPUT_BK
       AND category.IS_PRIMARY
      WHERE crosswalk.BATCH_ID = :batch_id
    ) coverage

    UNION ALL

    -- DQ-010: watermark freshness --------------------------------------------
    SELECT
      'DQ-010',
      'AUDIT',
      COALESCE(
        DATEDIFF('hour', MAX(LAST_SUCCESS_AT), CURRENT_TIMESTAMP()),
        999999
      ),
      72,
      IFF(
        COALESCE(
          DATEDIFF('hour', MAX(LAST_SUCCESS_AT), CURRENT_TIMESTAMP()),
          999999
        ) <= 72,
        'PASS',
        'FAIL'
      )
    FROM PAPERSONAR.PROJECT_AUDIT.SOURCE_WATERMARK
    WHERE LAST_BATCH_ID = :batch_id

    UNION ALL

    -- DQ-011: required payload keys present ----------------------------------
    SELECT
      'DQ-011',
      'BRONZE',
      COUNT(*),
      0,
      IFF(COUNT(*) = 0, 'PASS', 'FAIL')
    FROM PAPERSONAR.PROJECT_AUDIT.SCHEMA_DRIFT_LOG
    WHERE BATCH_ID = :batch_id
      AND IS_REQUIRED
      AND DRIFT_TYPE = 'MISSING_REQUIRED'

    UNION ALL

    -- DQ-012: exactly one primary category per output ------------------------
    SELECT
      'DQ-012',
      'CATEGORIZATION',
      COUNT(*),
      0,
      IFF(COUNT(*) = 0, 'PASS', 'FAIL')
    FROM (
      SELECT touched.OUTPUT_BK
      FROM (
        SELECT DISTINCT OUTPUT_BK
        FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK
        WHERE BATCH_ID = :batch_id
      ) touched
      LEFT JOIN (
        SELECT OUTPUT_BK, COUNT(*) AS PRIMARY_COUNT
        FROM PAPERSONAR.PROJECT_STAGING.STG_OUTPUT_CATEGORY
        WHERE BATCH_ID = :batch_id AND IS_PRIMARY
        GROUP BY OUTPUT_BK
      ) category
        ON category.OUTPUT_BK = touched.OUTPUT_BK
      WHERE COALESCE(category.PRIMARY_COUNT, 0) <> 1
    ) invalid_primary
  ) checks
  LEFT JOIN PAPERSONAR.PROJECT_REF.REF_DQ_RULE rule
    ON rule.RULE_ID = checks.RULE_ID;

  SELECT
    COUNT_IF(SEVERITY = 'CRITICAL' AND STATUS = 'FAIL'),
    COUNT_IF(STATUS = 'FAIL')
    INTO :critical_failures, :total_failures
  FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
  WHERE BATCH_ID = :batch_id;

  MERGE INTO PAPERSONAR.PROJECT_AUDIT.LINEAGE_EVENT t
  USING (
    SELECT
      SHA2(:batch_id || '|AUDIT|DQ', 256) AS EVENT_ID,
      :batch_id AS BATCH_ID,
      'AUDIT' AS LAYER,
      'DQ_RESULT' AS OBJECT_NAME,
      'CHECK' AS EVENT_TYPE,
      12 AS INPUT_COUNT,
      (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
        WHERE BATCH_ID = :batch_id AND STATUS = 'PASS') AS OUTPUT_COUNT,
      OBJECT_CONSTRUCT(
        'critical_failures', :critical_failures,
        'total_failures', :total_failures
      ) AS DETAILS
  ) s
  ON t.EVENT_ID = s.EVENT_ID
  WHEN MATCHED THEN UPDATE SET
    t.INPUT_COUNT = s.INPUT_COUNT,
    t.OUTPUT_COUNT = s.OUTPUT_COUNT,
    t.DETAILS = s.DETAILS,
    t.EVENT_AT = CURRENT_TIMESTAMP()
  WHEN NOT MATCHED THEN INSERT
    (EVENT_ID, BATCH_ID, LAYER, OBJECT_NAME, EVENT_TYPE, INPUT_COUNT,
     OUTPUT_COUNT, DETAILS, EVENT_AT)
    VALUES (s.EVENT_ID, s.BATCH_ID, s.LAYER, s.OBJECT_NAME, s.EVENT_TYPE,
            s.INPUT_COUNT, s.OUTPUT_COUNT, s.DETAILS, CURRENT_TIMESTAMP());

  IF (critical_failures > 0) THEN
    RETURN 'FAIL';
  END IF;

  RETURN 'PASS';
END;
$$;

COMMENT ON PROCEDURE PAPERSONAR.PROJECT_AUDIT.SP_RUN_DQ()
  IS 'Run the 12-rule DQ suite and return PASS only without critical failures';
