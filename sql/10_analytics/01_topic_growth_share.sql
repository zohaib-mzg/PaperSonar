-- =============================================================================
-- PaperSonar Phase 3 - Q01/Q02 topic growth and share (READ-ONLY)
-- =============================================================================
-- Purpose: Answer the Phase 1 topic questions from the published corpus.
--          Q01 Which selected topics grew most between 2023 and 2025.
--          Q02 Which topics are expanding their share of the retained corpus.
-- Inputs: PROJECT_REPORTING.VW_RESEARCH_OUTPUT (published outputs only),
--         PROJECT_DW.DIM_CATEGORY.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/01_queries/Q01_topic_growth.csv and
--          docs/phase3/evidence/01_queries/Q02_topic_share.csv.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: Q01 uses years 2023 and 2025 and a 30-work suppression threshold;
--             both are stated in the Phase 1 definition and repeated in the
--             query so the SQL and the requirement text cannot drift.
-- Cost: scans VW_RESEARCH_OUTPUT once per query (about 265k rows).
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================
-- The reporting view already enforces the publication contract: only outputs
-- whose LAST_BATCH_ID is in PROJECT_AUDIT.PUBLISHED_BATCH are visible.
-- "Admitted works" therefore means published works, not staged or quarantined
-- records.

-- ---------------------------------------------------------------------------
-- Q01 - Which selected topics grew most between 2023 and 2025
-- Decision. Choose a direction for a deeper review.
-- Measure. Distinct admitted works by primary topic and publication year.
--         Compare 2023 and 2025 counts and a two-year CAGR where both counts
--         are positive.
-- Analysis. Compare topic > subfield > field and year. Show counts next to
--         percentages.
-- Limit. Suppress growth rankings when either endpoint has fewer than 30
--        works. This is a proposed reporting threshold.
-- ---------------------------------------------------------------------------
WITH params AS (
  SELECT 2023 AS YEAR_FROM,
         2025 AS YEAR_TO,
         30   AS MIN_WORKS
),
topic_year AS (
  SELECT
    output.CATEGORY_KEY,
    output.CATEGORY_LABEL,
    category.PARENT_KEY             AS PARENT_CATEGORY_KEY,
    parent.LABEL                    AS PARENT_CATEGORY_LABEL,
    grandparent.LABEL               AS FIELD_CATEGORY_LABEL,
    output.PUBLICATION_YEAR,
    COUNT(DISTINCT output.OUTPUT_SK) AS WORKS
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY category
    ON category.CATEGORY_KEY = output.CATEGORY_KEY
  LEFT JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY parent
    ON parent.CATEGORY_KEY = category.PARENT_KEY
  LEFT JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY grandparent
    ON grandparent.CATEGORY_KEY = parent.PARENT_KEY
  WHERE output.CATEGORY_KEY <> 'unclassified'
    AND output.PUBLICATION_YEAR IN (2023, 2025)
  GROUP BY 1, 2, 3, 4, 5, 6
),
endpoints AS (
  SELECT
    CATEGORY_KEY,
    CATEGORY_LABEL,
    PARENT_CATEGORY_KEY,
    PARENT_CATEGORY_LABEL,
    FIELD_CATEGORY_LABEL,
    SUM(IFF(PUBLICATION_YEAR = 2023, WORKS, 0)) AS WORKS_2023,
    SUM(IFF(PUBLICATION_YEAR = 2025, WORKS, 0)) AS WORKS_2025
  FROM topic_year
  GROUP BY 1, 2, 3, 4, 5
)
SELECT
  endpoints.CATEGORY_KEY,
  endpoints.CATEGORY_LABEL,
  endpoints.PARENT_CATEGORY_KEY,
  endpoints.PARENT_CATEGORY_LABEL,
  endpoints.FIELD_CATEGORY_LABEL,
  endpoints.WORKS_2023,
  endpoints.WORKS_2025,
  endpoints.WORKS_2025 - endpoints.WORKS_2023 AS ABSOLUTE_GROWTH,
  ROUND(endpoints.WORKS_2025 / NULLIF(endpoints.WORKS_2023, 0), 4) AS GROWTH_RATIO,
  CASE
    WHEN endpoints.WORKS_2023 < 30 OR endpoints.WORKS_2025 < 30 THEN 'SUPPRESSED_LT_30'
    WHEN endpoints.WORKS_2023 = 0 OR endpoints.WORKS_2025 = 0     THEN 'NO_CAGR'
    ELSE 'REPORTABLE'
  END AS GROWTH_STATUS,
  CASE
    WHEN endpoints.WORKS_2023 < 30 OR endpoints.WORKS_2025 < 30
      OR endpoints.WORKS_2023 = 0 OR endpoints.WORKS_2025 = 0
      THEN NULL
    ELSE ROUND(POWER(endpoints.WORKS_2025 / endpoints.WORKS_2023, 1.0 / 2) - 1, 4)
  END AS CAGR_2023_2025,
  (SELECT MIN_WORKS FROM params) AS SUPPRESSION_THRESHOLD,
  CURRENT_DATE() AS RETRIEVED_ON
FROM endpoints
WHERE endpoints.WORKS_2023 > 0 OR endpoints.WORKS_2025 > 0
ORDER BY CAGR_2023_2025 DESC NULLS LAST, endpoints.WORKS_2025 DESC;

-- ---------------------------------------------------------------------------
-- Q02 - Which topics are expanding their share of the retained corpus
-- Decision. Separate broad corpus growth from a change in relative attention.
-- Measure. Topic primary-publication count divided by all admitted publications
--         in the same year. Report percentage-point change from 2023 to 2025.
-- Analysis. Slice by year and work type, then rank topics.
-- Limit. Shares describe the selected corpus, not all research worldwide.
-- ---------------------------------------------------------------------------
WITH corpus_year AS (
  SELECT
    output.PUBLICATION_YEAR,
    COUNT(DISTINCT output.OUTPUT_SK) AS CORPUS_WORKS,
    COUNT(DISTINCT IFF(output.CATEGORY_KEY <> 'unclassified', output.OUTPUT_SK, NULL))
      AS CORPUS_WORKS_CATEGORIZED
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  GROUP BY 1
),
topic_year AS (
  SELECT
    output.CATEGORY_KEY,
    output.CATEGORY_LABEL,
    output.PUBLICATION_YEAR,
    COUNT(DISTINCT output.OUTPUT_SK) AS WORKS
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.CATEGORY_KEY <> 'unclassified'
    AND output.PUBLICATION_YEAR IN (2023, 2025)
  GROUP BY 1, 2, 3
),
share AS (
  SELECT
    topic.CATEGORY_KEY,
    topic.CATEGORY_LABEL,
    topic.PUBLICATION_YEAR,
    topic.WORKS,
    corpus.CORPUS_WORKS,
    corpus.CORPUS_WORKS_CATEGORIZED,
    ROUND(topic.WORKS / NULLIF(corpus.CORPUS_WORKS, 0), 6) AS SHARE_OF_CORPUS,
    ROUND(topic.WORKS / NULLIF(corpus.CORPUS_WORKS_CATEGORIZED, 0), 6) AS SHARE_OF_CATEGORIZED_CORPUS
  FROM topic_year topic
  JOIN corpus_year corpus
    ON corpus.PUBLICATION_YEAR = topic.PUBLICATION_YEAR
),
endpoints AS (
  SELECT
    CATEGORY_KEY,
    CATEGORY_LABEL,
    MAX(IFF(PUBLICATION_YEAR = 2023, WORKS, 0))                       AS WORKS_2023,
    MAX(IFF(PUBLICATION_YEAR = 2025, WORKS, 0))                       AS WORKS_2025,
    MAX(IFF(PUBLICATION_YEAR = 2023, CORPUS_WORKS, 0))                AS CORPUS_WORKS_2023,
    MAX(IFF(PUBLICATION_YEAR = 2025, CORPUS_WORKS, 0))                AS CORPUS_WORKS_2025,
    MAX(IFF(PUBLICATION_YEAR = 2023, SHARE_OF_CORPUS, 0))            AS SHARE_2023,
    MAX(IFF(PUBLICATION_YEAR = 2025, SHARE_OF_CORPUS, 0))            AS SHARE_2025,
    MAX(IFF(PUBLICATION_YEAR = 2023, SHARE_OF_CATEGORIZED_CORPUS, 0)) AS SHARE_CATEGORIZED_2023,
    MAX(IFF(PUBLICATION_YEAR = 2025, SHARE_OF_CATEGORIZED_CORPUS, 0)) AS SHARE_CATEGORIZED_2025
  FROM share
  GROUP BY 1, 2
)
SELECT
  endpoints.CATEGORY_KEY,
  endpoints.CATEGORY_LABEL,
  endpoints.WORKS_2023,
  endpoints.WORKS_2025,
  endpoints.CORPUS_WORKS_2023,
  endpoints.CORPUS_WORKS_2025,
  ROUND(endpoints.SHARE_2023, 6) AS SHARE_2023,
  ROUND(endpoints.SHARE_2025, 6) AS SHARE_2025,
  ROUND((endpoints.SHARE_2025 - endpoints.SHARE_2023) * 100, 4) AS SHARE_CHANGE_PP,
  ROUND(endpoints.SHARE_CATEGORIZED_2023, 6) AS SHARE_OF_CATEGORIZED_2023,
  ROUND(endpoints.SHARE_CATEGORIZED_2025, 6) AS SHARE_OF_CATEGORIZED_2025,
  ROUND((endpoints.SHARE_CATEGORIZED_2025 - endpoints.SHARE_CATEGORIZED_2023) * 100, 4)
    AS SHARE_OF_CATEGORIZED_CHANGE_PP,
  CURRENT_DATE() AS RETRIEVED_ON
FROM endpoints
WHERE endpoints.WORKS_2023 > 0 OR endpoints.WORKS_2025 > 0
ORDER BY SHARE_CHANGE_PP DESC NULLS LAST, endpoints.WORKS_2025 DESC;
