-- =============================================================================
-- Purpose: Score every output touched by the active batch against the versioned
--          keyword taxonomy, apply auditable overrides, and write one primary
--          category plus secondary candidates to the staging bridge.
-- Inputs: SLV_OUTPUT_CROSSWALK, SLV_SOURCE_OBSERVATION, REF_CATEGORY_KEYWORD,
--         CATEGORY_OVERRIDE, CURRENT_BATCH.
-- Outputs: STG_OUTPUT_CATEGORY rows for the batch.
-- Idempotent: Yes - batch rows are deleted and rebuilt deterministically.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None.
-- Cost: Title/rule cross join is bounded by outputs touched by one batch.
-- =============================================================================
-- Short patterns (<= 4 characters) require token boundaries so "rag" does not
-- match "storage". Patterns are normalized with the same title normalizer used
-- for silver, so punctuation differences do not change the score.

CREATE OR REPLACE PROCEDURE PAPERSONAR.PROJECT_STAGING.SP_CATEGORIZE_BATCH()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  batch_id VARCHAR DEFAULT NULL;
  scored_rows NUMBER DEFAULT 0;
BEGIN
  SELECT BATCH_ID INTO :batch_id
  FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH
  LIMIT 1;

  IF (batch_id IS NULL) THEN
    RETURN 'NO_BATCH';
  END IF;

  DELETE FROM PAPERSONAR.PROJECT_STAGING.STG_OUTPUT_CATEGORY WHERE BATCH_ID = :batch_id;

  INSERT INTO PAPERSONAR.PROJECT_STAGING.STG_OUTPUT_CATEGORY (
    BATCH_ID, OUTPUT_BK, CATEGORY_KEY, SCORE, CATEGORY_RANK, IS_PRIMARY,
    METHOD, TAXONOMY_VERSION, CREATED_AT
  )
  WITH src AS (
    SELECT
      c.OUTPUT_BK,
      o.TITLE_NORMALIZED,
      o.TOPICS
    FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK c
    JOIN PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION o
      ON o.SOURCE_NAME = c.SOURCE_NAME
     AND o.ENTITY_NAME = c.ENTITY_NAME
     AND o.SOURCE_RECORD_ID = c.SOURCE_RECORD_ID
     AND o.RECORD_HASH = c.RECORD_HASH
     AND o.BATCH_ID = c.BATCH_ID
    WHERE c.BATCH_ID = :batch_id
    QUALIFY ROW_NUMBER() OVER (
      PARTITION BY c.OUTPUT_BK
      ORDER BY PAPERSONAR.PROJECT_SILVER.FN_SOURCE_PRIORITY(o.SOURCE_NAME),
               o.INGESTED_AT DESC
    ) = 1
  ),
  rules AS (
    SELECT
      CATEGORY_KEY,
      FIELD_NAME,
      BASE_WEIGHT,
      PAPERSONAR.PROJECT_SILVER.FN_NORMALIZE_TITLE(PATTERN) AS PATTERN
    FROM PAPERSONAR.PROJECT_REF.REF_CATEGORY_KEYWORD
    WHERE IS_ACTIVE
    QUALIFY ROW_NUMBER() OVER (
      PARTITION BY CATEGORY_KEY, FIELD_NAME,
                   PAPERSONAR.PROJECT_SILVER.FN_NORMALIZE_TITLE(PATTERN)
      ORDER BY RULE_ID
    ) = 1
  ),
  title_matches AS (
    SELECT
      s.OUTPUT_BK,
      k.CATEGORY_KEY,
      SUM(k.BASE_WEIGHT * 3) AS SCORE
    FROM src s
    JOIN rules k
      ON k.FIELD_NAME = 'title'
     AND (
       (LENGTH(k.PATTERN) <= 4 AND CONTAINS(' ' || s.TITLE_NORMALIZED || ' ', ' ' || k.PATTERN || ' '))
       OR (LENGTH(k.PATTERN) > 4 AND CONTAINS(s.TITLE_NORMALIZED, k.PATTERN))
     )
    GROUP BY s.OUTPUT_BK, k.CATEGORY_KEY
  ),
  topic_tokens AS (
    SELECT
      s.OUTPUT_BK,
      LOWER(
        COALESCE(
          t.value:name::STRING,
          t.value:subject::STRING,
          t.value::STRING,
          ''
        )
      ) AS TOKEN
    FROM src s,
    LATERAL FLATTEN(input => s.TOPICS) t
  ),
  topic_matches AS (
    SELECT
      tt.OUTPUT_BK,
      k.CATEGORY_KEY,
      SUM(k.BASE_WEIGHT * 2) AS SCORE
    FROM topic_tokens tt
    JOIN rules k
      ON k.FIELD_NAME = 'keywords'
     AND CONTAINS(tt.TOKEN, k.PATTERN)
    GROUP BY tt.OUTPUT_BK, k.CATEGORY_KEY
  ),
  keyword_scores AS (
    SELECT OUTPUT_BK, CATEGORY_KEY, SUM(SCORE) AS SCORE
    FROM (
      SELECT OUTPUT_BK, CATEGORY_KEY, SCORE FROM title_matches
      UNION ALL
      SELECT OUTPUT_BK, CATEGORY_KEY, SCORE FROM topic_matches
    )
    GROUP BY OUTPUT_BK, CATEGORY_KEY
  ),
  override_scores AS (
    SELECT
      overrides.OUTPUT_BK,
      overrides.CATEGORY_KEY,
      1000 AS SCORE,
      'OVERRIDE' AS METHOD,
      0 AS PRIORITY
    FROM PAPERSONAR.PROJECT_REF.CATEGORY_OVERRIDE overrides
    JOIN src s ON s.OUTPUT_BK = overrides.OUTPUT_BK
    WHERE overrides.IS_ACTIVE
  ),
  combined AS (
    SELECT OUTPUT_BK, CATEGORY_KEY, SCORE, METHOD, PRIORITY FROM override_scores
    UNION ALL
    SELECT OUTPUT_BK, CATEGORY_KEY, SCORE, 'KEYWORD', 1 FROM keyword_scores
  ),
  ranked AS (
    SELECT
      OUTPUT_BK,
      CATEGORY_KEY,
      SCORE,
      METHOD,
      ROW_NUMBER() OVER (
        PARTITION BY OUTPUT_BK
        ORDER BY PRIORITY, SCORE DESC, CATEGORY_KEY
      ) AS CATEGORY_RANK
    FROM combined
  ),
  unclassified AS (
    SELECT
      s.OUTPUT_BK,
      'unclassified' AS CATEGORY_KEY,
      0 AS SCORE,
      'DEFAULT' AS METHOD,
      1 AS CATEGORY_RANK
    FROM src s
    WHERE NOT EXISTS (
      SELECT 1 FROM combined c WHERE c.OUTPUT_BK = s.OUTPUT_BK
    )
  )
  SELECT
    :batch_id,
    assignments.OUTPUT_BK,
    assignments.CATEGORY_KEY,
    assignments.SCORE,
    assignments.CATEGORY_RANK,
    IFF(assignments.CATEGORY_RANK = 1, TRUE, FALSE),
    assignments.METHOD,
    'v1',
    CURRENT_TIMESTAMP()
  FROM (
    SELECT OUTPUT_BK, CATEGORY_KEY, SCORE, METHOD, CATEGORY_RANK FROM ranked
    UNION ALL
    SELECT OUTPUT_BK, CATEGORY_KEY, SCORE, METHOD, CATEGORY_RANK FROM unclassified
  ) assignments;

  scored_rows := SQLROWCOUNT;
  RETURN 'CATEGORIZED:' || scored_rows;
END;
$$;

COMMENT ON PROCEDURE PAPERSONAR.PROJECT_STAGING.SP_CATEGORIZE_BATCH()
  IS 'Deterministic weighted taxonomy scoring plus auditable overrides';
