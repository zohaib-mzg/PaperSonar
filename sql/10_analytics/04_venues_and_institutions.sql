-- =============================================================================
-- PaperSonar Phase 3 - Q06/Q07/Q08 venues and institutions (READ-ONLY)
-- =============================================================================
-- Purpose: Answer the Phase 1 venue and institution questions from the
--          published corpus.
--          Q06 Which venues regularly publish the selected topics.
--          Q07 Which institutions contribute to each topic.
--          Q08 How concentrated is institutional participation.
-- Inputs: PROJECT_REPORTING.VW_RESEARCH_OUTPUT, PROJECT_DW bridge tables,
--         DIM_INSTITUTION, DIM_CATEGORY, PROJECT_AUDIT.PUBLISHED_BATCH.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/01_queries/Q06_venues_by_topic.csv,
--          docs/phase3/evidence/01_queries/Q07_institution_contribution.csv and
--          docs/phase3/evidence/01_queries/Q08_institution_concentration.csv.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: year window 2021-2025 (Q06/Q07/Q08) and the top-5 window for
--             the concentration ratio (Q08).
-- Cost: bridge joins over about 265k outputs and 600k author links.
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================
-- Institution credit follows the Phase 1 rule: institutions are deduplicated
-- per output before the weight is assigned, and one output contributes a total
-- of 1.0 split evenly across its distinct institutions.

-- ---------------------------------------------------------------------------
-- Q06 - Which venues regularly publish the selected topics
-- Decision. Build a venue reading list.
-- Measure. Count distinct admitted works by primary venue and primary topic
--         for 2021 to 2025. Display missing venue share.
-- Analysis. Drill topic to venue to work.
-- Limit. Primary source is one indexed location and may be a repository. This
--        does not rank venue quality.
-- ---------------------------------------------------------------------------
WITH venue_topic AS (
  SELECT
    output.CATEGORY_KEY,
    output.CATEGORY_LABEL,
    output.VENUE_NAME,
    COUNT(DISTINCT output.OUTPUT_SK) AS WORKS
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.CATEGORY_KEY <> 'unclassified'
    AND output.PUBLICATION_YEAR BETWEEN 2021 AND 2025
  GROUP BY 1, 2, 3
)
SELECT
  venue_topic.CATEGORY_KEY,
  venue_topic.CATEGORY_LABEL,
  venue_topic.VENUE_NAME,
  venue_topic.WORKS,
  SUM(venue_topic.WORKS) OVER (PARTITION BY venue_topic.CATEGORY_KEY) AS TOPIC_WORKS_2021_2025,
  ROUND(
    venue_topic.WORKS / NULLIF(SUM(venue_topic.WORKS) OVER (PARTITION BY venue_topic.CATEGORY_KEY), 0),
    6
  ) AS SHARE_OF_TOPIC_WORKS,
  CURRENT_DATE() AS RETRIEVED_ON
FROM venue_topic
ORDER BY venue_topic.CATEGORY_KEY, venue_topic.WORKS DESC;

-- ---------------------------------------------------------------------------
-- Q06 companion - missing venue share over the same eligible population
-- ---------------------------------------------------------------------------
SELECT
  output.CATEGORY_KEY,
  output.CATEGORY_LABEL,
  COUNT(DISTINCT output.OUTPUT_SK) AS TOPIC_WORKS,
  COUNT(DISTINCT IFF(output.VENUE_NAME IS NULL OR output.VENUE_NAME = 'Unknown',
                     output.OUTPUT_SK, NULL)) AS WORKS_WITHOUT_VENUE,
  ROUND(
    COUNT(DISTINCT IFF(output.VENUE_NAME IS NULL OR output.VENUE_NAME = 'Unknown',
                       output.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT output.OUTPUT_SK), 0),
    6
  ) AS MISSING_VENUE_SHARE,
  CURRENT_DATE() AS RETRIEVED_ON
FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
WHERE output.CATEGORY_KEY <> 'unclassified'
  AND output.PUBLICATION_YEAR BETWEEN 2021 AND 2025
GROUP BY 1, 2
ORDER BY MISSING_VENUE_SHARE DESC, TOPIC_WORKS DESC;

-- ---------------------------------------------------------------------------
-- Q07 - Which institutions contribute to each topic
-- Decision. Identify potential collaborators.
-- Measure. Sum institution allocation weights by primary topic and year. Show
--         distinct full publication counts alongside fractional credit.
-- Analysis. Roll institution to country and compare years.
-- Limit. Deduplicate institutions across authors before assigning weights.
--        Unknown affiliations form a visible coverage category.
-- ---------------------------------------------------------------------------
WITH published_output AS (
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
output_institution AS (
  SELECT DISTINCT
    author_bridge.OUTPUT_SK,
    institution_bridge.INSTITUTION_SK,
    institution_bridge.INSTITUTION_KEY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_AUTHOR author_bridge
  JOIN PAPERSONAR.PROJECT_DW.BRIDGE_AUTHOR_INSTITUTION institution_bridge
    ON institution_bridge.AUTHOR_SK = author_bridge.AUTHOR_SK
  JOIN published_output output
    ON output.OUTPUT_SK = author_bridge.OUTPUT_SK
),
credit AS (
  SELECT
    output_institution.OUTPUT_SK,
    output_institution.INSTITUTION_SK,
    output_institution.INSTITUTION_KEY,
    1.0 / COUNT(*) OVER (PARTITION BY output_institution.OUTPUT_SK) AS OUTPUT_CREDIT
  FROM output_institution
)
SELECT
  output_category.CATEGORY_KEY,
  category.LABEL                                   AS CATEGORY_LABEL,
  output_year.PUBLICATION_YEAR,
  credit.INSTITUTION_KEY,
  institution.INSTITUTION_NAME,
  institution.COUNTRY_CODE,
  institution.IS_UNKNOWN                           AS IS_UNKNOWN_INSTITUTION,
  ROUND(SUM(credit.OUTPUT_CREDIT), 4)              AS FRACTIONAL_CREDIT,
  COUNT(DISTINCT credit.OUTPUT_SK)                 AS DISTINCT_WORKS
FROM credit
JOIN output_year
  ON output_year.OUTPUT_SK = credit.OUTPUT_SK
JOIN output_category
  ON output_category.OUTPUT_SK = credit.OUTPUT_SK
JOIN PAPERSONAR.PROJECT_DW.DIM_INSTITUTION institution
  ON institution.INSTITUTION_SK = credit.INSTITUTION_SK
JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY category
  ON category.CATEGORY_KEY = output_category.CATEGORY_KEY
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY output_category.CATEGORY_KEY,
         output_year.PUBLICATION_YEAR,
         FRACTIONAL_CREDIT DESC;

-- ---------------------------------------------------------------------------
-- Q08 - How concentrated is institutional participation
-- Decision. Find topics dominated by a small set of institutions.
-- Measure. Largest five institutions' fractional credit divided by all
--         fractional institution credit within each primary topic.
-- Analysis. Dice by year, topic and country.
-- Limit. Compute the top five after filtering. Exclude unknown institutions
--        from ranking and disclose their publication share.
-- ---------------------------------------------------------------------------
WITH published_output AS (
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
output_institution AS (
  SELECT DISTINCT
    author_bridge.OUTPUT_SK,
    institution_bridge.INSTITUTION_SK,
    institution_bridge.INSTITUTION_KEY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_AUTHOR author_bridge
  JOIN PAPERSONAR.PROJECT_DW.BRIDGE_AUTHOR_INSTITUTION institution_bridge
    ON institution_bridge.AUTHOR_SK = author_bridge.AUTHOR_SK
  JOIN published_output output
    ON output.OUTPUT_SK = author_bridge.OUTPUT_SK
),
credit AS (
  SELECT
    output_institution.OUTPUT_SK,
    output_institution.INSTITUTION_SK,
    output_institution.INSTITUTION_KEY,
    1.0 / COUNT(*) OVER (PARTITION BY output_institution.OUTPUT_SK) AS OUTPUT_CREDIT
  FROM output_institution
),
institution_topic AS (
  SELECT
    output_category.CATEGORY_KEY,
    output_year.PUBLICATION_YEAR,
    credit.INSTITUTION_SK,
    credit.INSTITUTION_KEY,
    SUM(credit.OUTPUT_CREDIT) AS FRACTIONAL_CREDIT,
    COUNT(DISTINCT credit.OUTPUT_SK) AS DISTINCT_WORKS
  FROM credit
  JOIN output_year
    ON output_year.OUTPUT_SK = credit.OUTPUT_SK
  JOIN output_category
    ON output_category.OUTPUT_SK = credit.OUTPUT_SK
  GROUP BY 1, 2, 3, 4
),
classified AS (
  SELECT
    institution_topic.CATEGORY_KEY,
    institution_topic.PUBLICATION_YEAR,
    institution_topic.INSTITUTION_SK,
    institution_topic.INSTITUTION_KEY,
    institution_topic.FRACTIONAL_CREDIT,
    institution_topic.DISTINCT_WORKS,
    institution.IS_UNKNOWN
  FROM institution_topic
  JOIN PAPERSONAR.PROJECT_DW.DIM_INSTITUTION institution
    ON institution.INSTITUTION_SK = institution_topic.INSTITUTION_SK
  WHERE NOT institution.IS_UNKNOWN
),
ranked AS (
  SELECT
    classified.CATEGORY_KEY,
    classified.PUBLICATION_YEAR,
    classified.INSTITUTION_SK,
    classified.INSTITUTION_KEY,
    classified.FRACTIONAL_CREDIT,
    classified.DISTINCT_WORKS,
    classified.IS_UNKNOWN,
    SUM(classified.FRACTIONAL_CREDIT) OVER (
      PARTITION BY classified.CATEGORY_KEY, classified.PUBLICATION_YEAR
    ) AS TOPIC_CREDIT,
    ROW_NUMBER() OVER (
      PARTITION BY classified.CATEGORY_KEY, classified.PUBLICATION_YEAR
      ORDER BY classified.FRACTIONAL_CREDIT DESC, classified.INSTITUTION_KEY
    ) AS INSTITUTION_RANK
  FROM classified
),
unknown_share AS (
  SELECT
    institution_topic.CATEGORY_KEY,
    institution_topic.PUBLICATION_YEAR,
    SUM(IFF(institution.IS_UNKNOWN, institution_topic.FRACTIONAL_CREDIT, 0))
      AS UNKNOWN_CREDIT,
    SUM(institution_topic.FRACTIONAL_CREDIT) AS ALL_CREDIT
  FROM institution_topic
  JOIN PAPERSONAR.PROJECT_DW.DIM_INSTITUTION institution
    ON institution.INSTITUTION_SK = institution_topic.INSTITUTION_SK
  GROUP BY 1, 2
)
SELECT
  ranked.CATEGORY_KEY,
  ranked.PUBLICATION_YEAR,
  ranked.INSTITUTION_KEY,
  ranked.FRACTIONAL_CREDIT,
  ranked.DISTINCT_WORKS,
  ranked.INSTITUTION_RANK,
  ROUND(ranked.TOPIC_CREDIT, 4) AS TOPIC_CLASSIFIED_CREDIT,
  ROUND(
    SUM(IFF(ranked.INSTITUTION_RANK <= 5, ranked.FRACTIONAL_CREDIT, 0))
      OVER (PARTITION BY ranked.CATEGORY_KEY, ranked.PUBLICATION_YEAR)
      / NULLIF(ranked.TOPIC_CREDIT, 0),
    6
  ) AS TOP5_INSTITUTION_SHARE,
  ROUND(unknown_share.UNKNOWN_CREDIT / NULLIF(unknown_share.ALL_CREDIT, 0), 6)
    AS UNKNOWN_INSTITUTION_CREDIT_SHARE,
  CURRENT_DATE() AS RETRIEVED_ON
FROM ranked
JOIN unknown_share
  ON unknown_share.CATEGORY_KEY = ranked.CATEGORY_KEY
 AND unknown_share.PUBLICATION_YEAR = ranked.PUBLICATION_YEAR
WHERE ranked.INSTITUTION_RANK <= 5
ORDER BY ranked.CATEGORY_KEY, ranked.PUBLICATION_YEAR, ranked.INSTITUTION_RANK;
