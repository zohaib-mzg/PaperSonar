-- =============================================================================
-- Purpose: Score every output touched by the active batch against the versioned
--          keyword taxonomy and the native source taxonomy mappings, apply
--          auditable overrides, and write one primary category plus secondary
--          candidates to the staging bridge.
-- Inputs: SLV_OUTPUT_CROSSWALK, SLV_SOURCE_OBSERVATION, REF_CATEGORY_KEYWORD,
--         REF_TAXONOMY_MAP, CATEGORY_OVERRIDE, CURRENT_BATCH.
-- Outputs: STG_OUTPUT_CATEGORY rows for the batch.
-- Idempotent: Yes - batch rows are deleted and rebuilt deterministically.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None.
-- Cost: Title/rule cross join is bounded by outputs touched by one batch.
-- =============================================================================
-- Native taxonomy values are read as structured parts: the topic display name,
-- the OpenAlex domain, subfield and field names, and the plain source value
-- for sources that publish a flat string (arXiv category codes, Zenodo
-- subjects). Every part is a separate candidate value, so the curated
-- REF_TAXONOMY_MAP can name the value it actually means.
--
-- Matching is boundary aware. A pattern must start on a word boundary, so
-- "cultural" cannot match "agricultural" and "art" cannot match "plant".
-- Patterns of four characters or fewer must match a whole word; longer
-- patterns match a word-initial stem.
--
-- Ranking order: operator override (1000) > native source taxonomy match >
-- keyword/topic score > unclassified default. A native taxonomy value is a
-- curated label supplied by the source, so it outranks a keyword hit. Within
-- the native taxonomy method the most specific part wins: a topic display name
-- outranks a subfield, a subfield outranks a field, and a field outranks a
-- domain.

CREATE OR REPLACE PROCEDURE PAPERSONAR.PROJECT_STAGING.SP_CATEGORIZE_BATCH()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  batch_id VARCHAR DEFAULT NULL;
  scored_rows NUMBER DEFAULT 0;
  taxonomy_version VARCHAR DEFAULT 'v2';
BEGIN
  SELECT BATCH_ID INTO :batch_id
  FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH
  LIMIT 1;

  IF (batch_id IS NULL) THEN
    RETURN 'NO_BATCH';
  END IF;

  SELECT MAX(RULE_VERSION) INTO :taxonomy_version
  FROM PAPERSONAR.PROJECT_REF.REF_CATEGORY_KEYWORD;

  DELETE FROM PAPERSONAR.PROJECT_STAGING.STG_OUTPUT_CATEGORY WHERE BATCH_ID = :batch_id;

  INSERT INTO PAPERSONAR.PROJECT_STAGING.STG_OUTPUT_CATEGORY (
    BATCH_ID, OUTPUT_BK, CATEGORY_KEY, SCORE, CATEGORY_RANK, IS_PRIMARY,
    METHOD, TAXONOMY_VERSION, CREATED_AT
  )
  WITH src AS (
    SELECT
      c.OUTPUT_BK,
      o.SOURCE_NAME,
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
       OR (LENGTH(k.PATTERN) > 4 AND CONTAINS(' ' || s.TITLE_NORMALIZED || ' ', ' ' || k.PATTERN))
     )
    GROUP BY s.OUTPUT_BK, k.CATEGORY_KEY
  ),
  topic_names AS (
    SELECT
      s.OUTPUT_BK,
      s.SOURCE_NAME,
      CASE WHEN IS_OBJECT(t.value) THEN GET(t.value, 'display_name')::STRING END AS DISPLAY_NAME,
      CASE WHEN IS_OBJECT(t.value) THEN GET(GET(t.value, 'subfield'), 'display_name')::STRING END AS SUBFIELD_NAME,
      CASE WHEN IS_OBJECT(t.value) THEN GET(GET(t.value, 'field'), 'display_name')::STRING END AS FIELD_NAME,
      CASE WHEN IS_OBJECT(t.value) THEN GET(GET(t.value, 'domain'), 'display_name')::STRING END AS DOMAIN_NAME,
      t.value::STRING AS PLAIN_VALUE
    FROM src s,
      LATERAL FLATTEN(input => s.TOPICS) t
  ),
  topic_parts AS (
    SELECT
      n.OUTPUT_BK,
      n.SOURCE_NAME,
      part.value:level::NUMBER AS LEVEL,
      part.value:value::STRING AS RAW_VALUE
    FROM topic_names n,
      LATERAL FLATTEN(
        input => ARRAY_COMPACT([
          IFF(n.DISPLAY_NAME IS NOT NULL,
              OBJECT_CONSTRUCT('level', 4, 'value', n.DISPLAY_NAME), NULL),
          IFF(n.SUBFIELD_NAME IS NOT NULL,
              OBJECT_CONSTRUCT('level', 3, 'value', n.SUBFIELD_NAME), NULL),
          IFF(n.FIELD_NAME IS NOT NULL,
              OBJECT_CONSTRUCT('level', 2, 'value', n.FIELD_NAME), NULL),
          IFF(n.DOMAIN_NAME IS NOT NULL,
              OBJECT_CONSTRUCT('level', 1, 'value', n.DOMAIN_NAME), NULL),
          IFF(n.DISPLAY_NAME IS NULL,
              OBJECT_CONSTRUCT('level', 0, 'value', n.PLAIN_VALUE), NULL)
        ])
      ) part
  ),
  topic_tokens AS (
    SELECT
      tp.OUTPUT_BK,
      tp.SOURCE_NAME,
      LOWER(TRIM(tp.RAW_VALUE)) AS TOKEN,
      PAPERSONAR.PROJECT_SILVER.FN_NORMALIZE_TITLE(tp.RAW_VALUE) AS NORMALIZED_TOKEN,
      tp.LEVEL
    FROM topic_parts tp
    WHERE PAPERSONAR.PROJECT_SILVER.FN_NORMALIZE_TITLE(tp.RAW_VALUE) IS NOT NULL
  ),
  topic_matches AS (
    SELECT
      tt.OUTPUT_BK,
      k.CATEGORY_KEY,
      SUM(k.BASE_WEIGHT * 2) AS SCORE
    FROM topic_tokens tt
    JOIN rules k
      ON k.FIELD_NAME = 'keywords'
     AND (
       (LENGTH(k.PATTERN) <= 4 AND CONTAINS(' ' || tt.NORMALIZED_TOKEN || ' ', ' ' || k.PATTERN || ' '))
       OR (LENGTH(k.PATTERN) > 4 AND CONTAINS(' ' || tt.NORMALIZED_TOKEN || ' ', ' ' || k.PATTERN))
     )
    GROUP BY tt.OUTPUT_BK, k.CATEGORY_KEY
  ),
  taxonomy_matches AS (
    SELECT
      tt.OUTPUT_BK,
      m.CATEGORY_KEY,
      MAX(2 + tt.LEVEL) AS SCORE
    FROM topic_tokens tt
    JOIN (
      SELECT SOURCE_NAME,
             UPPER(TRIM(SOURCE_VALUE)) AS SOURCE_VALUE,
             CATEGORY_KEY
      FROM PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP
      WHERE IS_ACTIVE
    ) m
      ON m.SOURCE_NAME = UPPER(tt.SOURCE_NAME)
     AND m.SOURCE_VALUE = UPPER(TRIM(tt.TOKEN))
    GROUP BY tt.OUTPUT_BK, m.CATEGORY_KEY
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
    SELECT OUTPUT_BK, CATEGORY_KEY, SCORE, 'SOURCE_TAXONOMY', 1 FROM taxonomy_matches
    UNION ALL
    SELECT OUTPUT_BK, CATEGORY_KEY, SCORE, 'KEYWORD', 2 FROM keyword_scores
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
    :taxonomy_version,
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
