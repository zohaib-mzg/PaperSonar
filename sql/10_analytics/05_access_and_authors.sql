-- =============================================================================
-- PaperSonar Phase 3 - Q09/Q10 access and author activity (READ-ONLY)
-- =============================================================================
-- Purpose: Answer the Phase 1 access and author-activity questions from the
--          published corpus.
--          Q09 How does open access availability vary by topic and year.
--          Q10 Which authors have repeated activity in a selected direction.
-- Inputs: PROJECT_REPORTING.VW_RESEARCH_OUTPUT, VW_CITATION_SNAPSHOT,
--         PROJECT_DW.BRIDGE_OUTPUT_AUTHOR, DIM_AUTHOR.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/01_queries/Q09_open_access_by_topic.csv and
--          docs/phase3/evidence/01_queries/Q10_repeat_author_activity.csv.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: Q09 uses the latest observed snapshot date; Q10 uses 2021-2025
--             and an optional category filter (NULL means every topic).
-- Cost: scans VW_RESEARCH_OUTPUT and the author bridge.
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Q09 - How does open access availability vary by topic and year
-- Decision. Estimate how accessible a reading direction will be.
-- Measure. At one snapshot date divide observed open-access works by works
--         with known access status. Display unknown-status share separately.
-- Analysis. Slice by primary topic, year and work type.
-- Limit. Availability reflects the observation date, not necessarily
--        availability on publication day.
-- ---------------------------------------------------------------------------
WITH snapshot_dates AS (
  SELECT MAX(snapshot.SNAPSHOT_DATE) AS SNAPSHOT_DATE
  FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_SNAPSHOT snapshot
),
cohort AS (
  SELECT
    output.OUTPUT_SK,
    output.CATEGORY_KEY,
    output.CATEGORY_LABEL,
    output.PUBLICATION_YEAR,
    output.OUTPUT_TYPE_NAME,
    output.ACCESS_STATUS_NAME
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.CATEGORY_KEY <> 'unclassified'
),
observed AS (
  SELECT
    snapshot.OUTPUT_SK,
    snapshot.SOURCE_NAME,
    snapshot.OA_IS_OA
  FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_SNAPSHOT snapshot
  JOIN snapshot_dates dates
    ON dates.SNAPSHOT_DATE = snapshot.SNAPSHOT_DATE
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY snapshot.OUTPUT_SK
    ORDER BY CASE snapshot.SOURCE_NAME
               WHEN 'OPENALEX' THEN 1
               WHEN 'CROSSREF' THEN 2
               WHEN 'ARXIV' THEN 3
               WHEN 'DATACITE' THEN 4
               WHEN 'ZENODO' THEN 5
               ELSE 9
             END,
             snapshot.SOURCE_NAME
  ) = 1
)
SELECT
  cohort.CATEGORY_KEY,
  cohort.CATEGORY_LABEL,
  cohort.PUBLICATION_YEAR,
  cohort.OUTPUT_TYPE_NAME,
  dates.SNAPSHOT_DATE,
  COUNT(DISTINCT cohort.OUTPUT_SK) AS COHORT_SIZE,
  COUNT(DISTINCT IFF(cohort.ACCESS_STATUS_NAME <> 'Unknown', cohort.OUTPUT_SK, NULL))
    AS WORKS_WITH_KNOWN_ACCESS,
  COUNT(DISTINCT IFF(cohort.ACCESS_STATUS_NAME = 'Unknown', cohort.OUTPUT_SK, NULL))
    AS WORKS_WITH_UNKNOWN_ACCESS,
  COUNT(DISTINCT IFF(observed.OA_IS_OA, cohort.OUTPUT_SK, NULL)) AS OPEN_ACCESS_WORKS,
  ROUND(
    COUNT(DISTINCT IFF(observed.OA_IS_OA, cohort.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT IFF(cohort.ACCESS_STATUS_NAME <> 'Unknown', cohort.OUTPUT_SK, NULL)), 0),
    6
  ) AS OPEN_ACCESS_SHARE_KNOWN_STATUS,
  ROUND(
    COUNT(DISTINCT IFF(cohort.ACCESS_STATUS_NAME = 'Unknown', cohort.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT cohort.OUTPUT_SK), 0),
    6
  ) AS UNKNOWN_ACCESS_SHARE,
  MAX(observed.SOURCE_NAME) AS SCOPE_SOURCE,
  CURRENT_DATE() AS RETRIEVED_ON
FROM cohort
CROSS JOIN snapshot_dates dates
LEFT JOIN observed
  ON observed.OUTPUT_SK = cohort.OUTPUT_SK
GROUP BY 1, 2, 3, 4, 5
ORDER BY cohort.CATEGORY_KEY, cohort.PUBLICATION_YEAR, cohort.OUTPUT_TYPE_NAME;

-- ---------------------------------------------------------------------------
-- Q10 - Which authors have repeated activity in a selected direction
-- Decision. Prepare an expert shortlist for manual review.
-- Measure. Count distinct admitted works per source author identifier over
--         2021 to 2025, with latest publication year.
-- Analysis. Drill topic to author to work.
-- Limit. Names do not identify people reliably. Use OpenAlex ID and ORCID
--        where supplied. This is activity, not an expertise certification.
-- ---------------------------------------------------------------------------
WITH params AS (
  SELECT 'ai-ml'::VARCHAR AS CATEGORY_FILTER,  -- change to NULL for every topic
         2021 AS YEAR_FROM,
         2025 AS YEAR_TO
),
published_output AS (
  SELECT DISTINCT fact.OUTPUT_SK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  JOIN PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    ON published.BATCH_ID = fact.LAST_BATCH_ID
),
output_category AS (
  SELECT
    bridge.OUTPUT_SK,
    bridge.CATEGORY_KEY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
  JOIN published_output output
    ON output.OUTPUT_SK = bridge.OUTPUT_SK
  WHERE bridge.IS_PRIMARY
    AND bridge.CATEGORY_KEY <> 'unclassified'
),
output_year AS (
  SELECT
    fact.OUTPUT_SK,
    fact.PUBLICATION_YEAR
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  JOIN published_output output
    ON output.OUTPUT_SK = fact.OUTPUT_SK
  WHERE fact.PUBLICATION_YEAR BETWEEN 2021 AND 2025
),
author_output AS (
  SELECT
    author_bridge.OUTPUT_SK,
    author_bridge.AUTHOR_KEY,
    author_bridge.SOURCE_NAME
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_AUTHOR author_bridge
  JOIN published_output output
    ON output.OUTPUT_SK = author_bridge.OUTPUT_SK
)
SELECT
  output_category.CATEGORY_KEY,
  category.LABEL                                   AS CATEGORY_LABEL,
  author_output.AUTHOR_KEY,
  author.AUTHOR_NAME,
  author.ORCID,
  MAX(author_output.SOURCE_NAME)                   AS SOURCE_NAME,
  COUNT(DISTINCT author_output.OUTPUT_SK)          AS DISTINCT_WORKS,
  MIN(output_year.PUBLICATION_YEAR)                AS FIRST_PUBLICATION_YEAR,
  MAX(output_year.PUBLICATION_YEAR)                AS LATEST_PUBLICATION_YEAR,
  CURRENT_DATE() AS RETRIEVED_ON
FROM author_output
JOIN output_year
  ON output_year.OUTPUT_SK = author_output.OUTPUT_SK
JOIN output_category
  ON output_category.OUTPUT_SK = author_output.OUTPUT_SK
JOIN PAPERSONAR.PROJECT_DW.DIM_AUTHOR author
  ON author.AUTHOR_KEY = author_output.AUTHOR_KEY
 AND author.IS_CURRENT
JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY category
  ON category.CATEGORY_KEY = output_category.CATEGORY_KEY
CROSS JOIN params
WHERE (params.CATEGORY_FILTER IS NULL OR output_category.CATEGORY_KEY = params.CATEGORY_FILTER)
GROUP BY 1, 2, 3, 4, 5
ORDER BY DISTINCT_WORKS DESC, author_output.AUTHOR_KEY;
