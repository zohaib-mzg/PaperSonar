-- =============================================================================
-- PaperSonar Phase 3 - taxonomy vocabulary mining (READ-ONLY)
-- =============================================================================
-- Purpose: Provide the measured vocabulary that Phase 3 WP1 needs to expand the
--          taxonomy: which native taxonomy values the published corpus actually
--          carries, how often, and what the currently unclassified outputs look
--          like. The mined values become REF_TAXONOMY_MAP rows and keyword rules.
-- Inputs: database PAPERSONAR (silver, DW, reference, audit schemas).
-- Outputs: result sets only; save each block as sanitized CSV under
--          docs/phase3/evidence/00_taxonomy/.
-- Idempotent: Yes - SELECT only. Safe to re-run.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: none (all queries are self-contained).
-- Cost: V3 and V5 scan published titles; run them on WH_PAPERSONAR_ELT outside
--        peak time. The other blocks are cheap.
-- Notes:   Run blocks in order. Each block is self-contained.
-- =============================================================================

-- ============================================================================
-- SECTION V - VOCABULARY MINING FOR TAXONOMY EXPANSION
-- ============================================================================

-- V0. Published outputs used as the mining corpus ----------------------------
-- The published-batches filter matches the reporting views exactly.
WITH published_output AS (
  SELECT fact.OUTPUT_SK, fact.OUTPUT_BK, fact.LAST_BATCH_ID, fact.PUBLICATION_YEAR
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = fact.LAST_BATCH_ID
  )
),
primary_observation AS (
  SELECT
    crosswalk.OUTPUT_BK,
    observation.SOURCE_NAME,
    observation.TITLE_NORMALIZED,
    observation.TOPICS
  FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK crosswalk
  JOIN PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION observation
    ON observation.SOURCE_NAME = crosswalk.SOURCE_NAME
   AND observation.ENTITY_NAME = crosswalk.ENTITY_NAME
   AND observation.SOURCE_RECORD_ID = crosswalk.SOURCE_RECORD_ID
   AND observation.RECORD_HASH = crosswalk.RECORD_HASH
   AND observation.BATCH_ID = crosswalk.BATCH_ID
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = crosswalk.BATCH_ID
  )
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY crosswalk.OUTPUT_BK
    ORDER BY PAPERSONAR.PROJECT_SILVER.FN_SOURCE_PRIORITY(observation.SOURCE_NAME),
             observation.INGESTED_AT DESC
  ) = 1
)
SELECT source_name,
       COUNT(*)                    AS OUTPUTS,
       COUNT_IF(topics IS NOT NULL) AS WITH_TOPICS,
       ROUND(COUNT_IF(topics IS NOT NULL) / COUNT(*), 4) AS TOPIC_COVERAGE
FROM primary_observation
GROUP BY source_name
ORDER BY OUTPUTS DESC;

-- V1. Native taxonomy values per source (the REF_TAXONOMY_MAP candidates) ----
-- One row per distinct native value with the number of outputs carrying it.
-- Rank the rows inside each source to find the dominant vocabulary.
WITH published_output AS (
  SELECT DISTINCT fact.OUTPUT_SK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = fact.LAST_BATCH_ID
  )
),
primary_observation AS (
  SELECT crosswalk.OUTPUT_BK, observation.SOURCE_NAME, observation.TOPICS
  FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK crosswalk
  JOIN PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION observation
    ON observation.SOURCE_NAME = crosswalk.SOURCE_NAME
   AND observation.ENTITY_NAME = crosswalk.ENTITY_NAME
   AND observation.SOURCE_RECORD_ID = crosswalk.SOURCE_RECORD_ID
   AND observation.RECORD_HASH = crosswalk.RECORD_HASH
   AND observation.BATCH_ID = crosswalk.BATCH_ID
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = crosswalk.BATCH_ID
  )
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY crosswalk.OUTPUT_BK
    ORDER BY PAPERSONAR.PROJECT_SILVER.FN_SOURCE_PRIORITY(observation.SOURCE_NAME),
             observation.INGESTED_AT DESC
  ) = 1
),
topic_value AS (
  SELECT primary_observation.SOURCE_NAME,
         primary_observation.OUTPUT_BK,
         LOWER(
           TRIM(
             COALESCE(
               topic.value:name::STRING,
               topic.value:subject::STRING,
               topic.value::STRING,
               ''
             )
           )
         ) AS TOPIC_VALUE
  FROM primary_observation,
       LATERAL FLATTEN(input => primary_observation.TOPICS) topic
)
SELECT SOURCE_NAME,
       TOPIC_VALUE,
       COUNT(DISTINCT OUTPUT_BK) AS OUTPUTS,
       DENSE_RANK() OVER (
         PARTITION BY SOURCE_NAME ORDER BY COUNT(DISTINCT OUTPUT_BK) DESC
       ) AS FREQUENCY_RANK
FROM topic_value
WHERE TOPIC_VALUE <> ''
GROUP BY SOURCE_NAME, TOPIC_VALUE
ORDER BY SOURCE_NAME, OUTPUTS DESC, TOPIC_VALUE;

-- V2. Current categorization coverage per source (the DQ-009 baseline) ------
WITH published_output AS (
  SELECT fact.OUTPUT_SK, fact.LAST_BATCH_ID
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = fact.LAST_BATCH_ID
  )
)
SELECT
  batch.SOURCE_NAME,
  COUNT(DISTINCT fact.OUTPUT_SK) AS OUTPUTS,
  COUNT(DISTINCT IFF(bridge.CATEGORY_KEY <> 'unclassified', fact.OUTPUT_SK, NULL)) AS CATEGORIZED,
  ROUND(
    COUNT(DISTINCT IFF(bridge.CATEGORY_KEY <> 'unclassified', fact.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT fact.OUTPUT_SK), 0),
    4
  ) AS COVERAGE_RATIO
FROM published_output fact
JOIN PAPERSONAR.PROJECT_AUDIT.BATCH batch
  ON batch.BATCH_ID = fact.LAST_BATCH_ID
LEFT JOIN PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
  ON bridge.OUTPUT_SK = fact.OUTPUT_SK
 AND bridge.IS_PRIMARY
GROUP BY batch.SOURCE_NAME
ORDER BY OUTPUTS DESC;

-- V3. [SCAN] Current primary-category distribution of the published corpus ---
SELECT category.CATEGORY_KEY,
       category.LABEL,
       COUNT(*) AS OUTPUTS
FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
JOIN PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  ON fact.OUTPUT_SK = bridge.OUTPUT_SK
JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY category
  ON category.CATEGORY_SK = bridge.CATEGORY_SK
WHERE bridge.IS_PRIMARY
  AND EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = fact.LAST_BATCH_ID
  )
GROUP BY category.CATEGORY_KEY, category.LABEL
ORDER BY OUTPUTS DESC;

-- V4. [SCAN] Most frequent title tokens of currently unclassified outputs ---
-- These tokens drive the keyword-rule expansion.
WITH unclassified_output AS (
  SELECT fact.OUTPUT_SK, fact.OUTPUT_BK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  LEFT JOIN PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
    ON bridge.OUTPUT_SK = fact.OUTPUT_SK
   AND bridge.IS_PRIMARY
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = fact.LAST_BATCH_ID
  )
    AND (bridge.CATEGORY_KEY IS NULL OR bridge.CATEGORY_KEY = 'unclassified')
),
primary_observation AS (
  SELECT crosswalk.OUTPUT_BK, observation.TITLE_NORMALIZED
  FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK crosswalk
  JOIN PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION observation
    ON observation.SOURCE_NAME = crosswalk.SOURCE_NAME
   AND observation.ENTITY_NAME = crosswalk.ENTITY_NAME
   AND observation.SOURCE_RECORD_ID = crosswalk.SOURCE_RECORD_ID
   AND observation.RECORD_HASH = crosswalk.RECORD_HASH
   AND observation.BATCH_ID = crosswalk.BATCH_ID
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = crosswalk.BATCH_ID
  )
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY crosswalk.OUTPUT_BK
    ORDER BY PAPERSONAR.PROJECT_SILVER.FN_SOURCE_PRIORITY(observation.SOURCE_NAME),
             observation.INGESTED_AT DESC
  ) = 1
),
token AS (
  SELECT unclassified_output.OUTPUT_SK, LOWER(token.value) AS TOKEN
  FROM unclassified_output
  JOIN primary_observation
    ON primary_observation.OUTPUT_BK = unclassified_output.OUTPUT_BK
  CROSS JOIN LATERAL FLATTEN(
    input => SPLIT_REGEX_TABLE(primary_observation.TITLE_NORMALIZED, '[^A-Za-z0-9]+')
  ) token
  WHERE LENGTH(token.value) >= 4
)
SELECT TOKEN,
       COUNT(DISTINCT OUTPUT_SK) AS OUTPUTS
FROM token
GROUP BY TOKEN
ORDER BY OUTPUTS DESC, TOKEN;

-- V5. [SCAN] Sample titles of unclassified outputs (rule design evidence) -----
-- Deterministic sample: one row per hash bucket, sorted by title.
WITH unclassified_output AS (
  SELECT fact.OUTPUT_SK, fact.OUTPUT_BK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  LEFT JOIN PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
    ON bridge.OUTPUT_SK = fact.OUTPUT_SK
   AND bridge.IS_PRIMARY
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = fact.LAST_BATCH_ID
  )
    AND (bridge.CATEGORY_KEY IS NULL OR bridge.CATEGORY_KEY = 'unclassified')
),
primary_observation AS (
  SELECT crosswalk.OUTPUT_BK, observation.SOURCE_NAME, observation.TITLE_NORMALIZED,
         observation.TOPICS
  FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK crosswalk
  JOIN PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION observation
    ON observation.SOURCE_NAME = crosswalk.SOURCE_NAME
   AND observation.ENTITY_NAME = crosswalk.ENTITY_NAME
   AND observation.SOURCE_RECORD_ID = crosswalk.SOURCE_RECORD_ID
   AND observation.RECORD_HASH = crosswalk.RECORD_HASH
   AND observation.BATCH_ID = crosswalk.BATCH_ID
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = crosswalk.BATCH_ID
  )
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY crosswalk.OUTPUT_BK
    ORDER BY PAPERSONAR.PROJECT_SILVER.FN_SOURCE_PRIORITY(observation.SOURCE_NAME),
             observation.INGESTED_AT DESC
  ) = 1
)
SELECT SOURCE_NAME,
       TITLE_NORMALIZED,
       TOPICS
FROM primary_observation
WHERE OUTPUT_BK IN (SELECT OUTPUT_BK FROM unclassified_output)
ORDER BY TITLE_NORMALIZED
LIMIT 200;

-- V6. Native taxonomy values that already carry a category mapping -----------
-- Confirms whether REF_TAXONOMY_MAP is populated and what it covers.
SELECT SOURCE_NAME,
       CATEGORY_KEY,
       MAPPING_VERSION,
       IS_ACTIVE,
       COUNT(*) AS MAPPINGS
FROM PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP
GROUP BY SOURCE_NAME, CATEGORY_KEY, MAPPING_VERSION, IS_ACTIVE
ORDER BY SOURCE_NAME, MAPPINGS DESC;
