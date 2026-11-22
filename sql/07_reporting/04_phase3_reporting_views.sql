-- =============================================================================
-- PaperSonar Phase 3 - WP4 reporting views (DEPLOYABLE)
-- =============================================================================
-- Purpose: Create the five Phase 3 reporting views named by the course
--          matrix and grant read access to PAPERSONAR_REPORTER:
--            VW_TOPIC_GROWTH          category x publication year
--            VW_OUTPUT_COVERAGE       source x year x output type
--            VW_CITATION_COHORTS      output x citation snapshot date
--            VW_TOPIC_INTERSECTIONS   category pair
--            VW_RESEARCH_COMMUNITY    institution x category
-- Inputs: PROJECT_DW facts, dimensions and bridges; PROJECT_AUDIT
--         .PUBLISHED_BATCH; the Phase 2 reporting views.
-- Outputs: five SECURE views in PROJECT_REPORTING plus the reporter grants.
-- Idempotent: Yes - CREATE OR REPLACE SECURE VIEW and GRANT are repeatable.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None. The publication contract is applied inside every view.
-- Cost: query-time only; the views read the existing facts and bridges.
-- =============================================================================
-- Every view exposes published data only. A bridge row is visible when its
-- BATCH_ID is in PROJECT_AUDIT.PUBLISHED_BATCH; an output row is visible
-- when its LAST_BATCH_ID is published. Nothing staged, quarantined or
-- unpublished is counted.
--
-- The views are the BI layer: they carry the grain, the labels and the
-- denominators, so a Power BI page never has to re-derive a measure.

-- ---------------------------------------------------------------------------
-- VW_TOPIC_GROWTH - category x publication year (BI page 1, Q01/Q02)
-- Grain: one row per category per publication year.
-- The 'unclassified' category is kept in the view and flagged, so the
-- coverage of the corpus is visible in the same table as the growth
-- ranking. The two share columns use different denominators: the corpus
-- share divides by every published work of the year, the classified share
-- divides by the classified works of the year.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE SECURE VIEW PAPERSONAR.PROJECT_REPORTING.VW_TOPIC_GROWTH AS
WITH classified AS (
  SELECT
    output.OUTPUT_SK,
    output.CATEGORY_KEY,
    output.CATEGORY_LABEL,
    output.PUBLICATION_YEAR
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.PUBLICATION_YEAR IS NOT NULL
),
topic_year AS (
  SELECT
    classified.CATEGORY_KEY,
    MAX(classified.CATEGORY_LABEL) AS CATEGORY_LABEL,
    classified.PUBLICATION_YEAR,
    COUNT(DISTINCT classified.OUTPUT_SK) AS WORKS
  FROM classified
  GROUP BY 1, 3
),
corpus_year AS (
  SELECT
    classified.PUBLICATION_YEAR,
    COUNT(DISTINCT classified.OUTPUT_SK) AS CORPUS_WORKS,
    COUNT(DISTINCT IFF(classified.CATEGORY_KEY <> 'unclassified', classified.OUTPUT_SK, NULL))
      AS CLASSIFIED_WORKS
  FROM classified
  GROUP BY 1
)
SELECT
  topic_year.CATEGORY_KEY,
  topic_year.CATEGORY_LABEL,
  topic_year.PUBLICATION_YEAR,
  topic_year.WORKS,
  corpus_year.CORPUS_WORKS,
  corpus_year.CLASSIFIED_WORKS,
  ROUND(topic_year.WORKS / NULLIF(corpus_year.CORPUS_WORKS, 0), 6) AS SHARE_OF_CORPUS,
  ROUND(topic_year.WORKS / NULLIF(corpus_year.CLASSIFIED_WORKS, 0), 6)
    AS SHARE_OF_CLASSIFIED_CORPUS,
  IFF(topic_year.CATEGORY_KEY = 'unclassified', TRUE, FALSE) AS IS_COVERAGE_CATEGORY,
  CURRENT_DATE() AS RETRIEVED_ON
FROM topic_year
JOIN corpus_year
  ON corpus_year.PUBLICATION_YEAR = topic_year.PUBLICATION_YEAR;

-- ---------------------------------------------------------------------------
-- VW_OUTPUT_COVERAGE - source x year x output type (BI page 1, Q12)
-- Grain: one row per primary source per publication year per output type.
-- Every coverage ratio states its denominator, and the unknown share is a
-- separate column instead of being folded into the numerator.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE SECURE VIEW PAPERSONAR.PROJECT_REPORTING.VW_OUTPUT_COVERAGE AS
WITH base AS (
  SELECT
    output.OUTPUT_SK,
    output.PRIMARY_SOURCE_NAME,
    output.PUBLICATION_YEAR,
    output.OUTPUT_TYPE_NAME,
    output.CATEGORY_KEY,
    output.DOI_NORMALIZED,
    output.VENUE_NAME,
    output.ACCESS_STATUS_NAME
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
)
SELECT
  base.PRIMARY_SOURCE_NAME,
  base.PUBLICATION_YEAR,
  base.OUTPUT_TYPE_NAME,
  COUNT(DISTINCT base.OUTPUT_SK) AS OUTPUTS,
  COUNT(DISTINCT IFF(base.CATEGORY_KEY <> 'unclassified', base.OUTPUT_SK, NULL))
    AS CATEGORIZED_OUTPUTS,
  ROUND(
    COUNT(DISTINCT IFF(base.CATEGORY_KEY <> 'unclassified', base.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT base.OUTPUT_SK), 0), 6) AS CATEGORY_COVERAGE_RATIO,
  COUNT(DISTINCT IFF(base.DOI_NORMALIZED IS NULL OR base.DOI_NORMALIZED = '', base.OUTPUT_SK, NULL))
    AS OUTPUTS_WITHOUT_DOI,
  COUNT(DISTINCT IFF(base.VENUE_NAME IS NULL OR base.VENUE_NAME = '', base.OUTPUT_SK, NULL))
    AS OUTPUTS_WITHOUT_VENUE,
  COUNT(DISTINCT IFF(base.ACCESS_STATUS_NAME IS NULL OR base.ACCESS_STATUS_NAME = '',
                     base.OUTPUT_SK, NULL)) AS OUTPUTS_WITHOUT_ACCESS_STATUS,
  ROUND(
    COUNT(DISTINCT IFF(base.ACCESS_STATUS_NAME IS NOT NULL AND base.ACCESS_STATUS_NAME <> '',
                       base.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT base.OUTPUT_SK), 0), 6) AS KNOWN_ACCESS_RATIO,
  CURRENT_DATE() AS RETRIEVED_ON
FROM base
GROUP BY 1, 2, 3;

-- ---------------------------------------------------------------------------
-- VW_CITATION_COHORTS - output x citation snapshot date (BI page 2, Q03/Q04)
-- Grain: one row per published output per citation snapshot date.
-- The observation date is carried on the row so a reader never mixes two
-- snapshot dates inside one comparison, and the publication year and the
-- primary category travel with the output so a cohort can be cut by year or
-- by topic without a second join.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE SECURE VIEW PAPERSONAR.PROJECT_REPORTING.VW_CITATION_COHORTS AS
SELECT
  snapshot.OUTPUT_SK,
  snapshot.OUTPUT_BK,
  snapshot.SNAPSHOT_DATE,
  snapshot.SNAPSHOT_DATE_KEY,
  snapshot.CITED_BY_COUNT,
  snapshot.OA_STATUS,
  snapshot.ACCESS_STATUS_NAME,
  output.PUBLICATION_YEAR,
  output.CATEGORY_KEY,
  output.CATEGORY_LABEL,
  output.PRIMARY_SOURCE_NAME,
  output.OUTPUT_TYPE_NAME,
  CURRENT_DATE() AS RETRIEVED_ON
FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_SNAPSHOT snapshot
JOIN PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  ON output.OUTPUT_SK = snapshot.OUTPUT_SK;

-- ---------------------------------------------------------------------------
-- VW_TOPIC_INTERSECTIONS - category pair (BI page 2, Q05/Q11)
-- Grain: one row per unordered category pair.
-- A pair means "these two topics are assigned to the same work", so every
-- category of a work is admitted here, primary and secondary alike. The
-- Phase 1 thresholds are applied in the view: a pair needs at least 100
-- parent works and at least 5 joint works to be reportable.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE SECURE VIEW PAPERSONAR.PROJECT_REPORTING.VW_TOPIC_INTERSECTIONS AS
WITH output_category AS (
  SELECT
    bridge.OUTPUT_SK,
    bridge.CATEGORY_KEY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
  WHERE bridge.CATEGORY_KEY <> 'unclassified'
    AND EXISTS (
      SELECT 1
      FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
      WHERE published.BATCH_ID = bridge.BATCH_ID
    )
),
pair AS (
  SELECT
    left_side.OUTPUT_SK,
    left_side.CATEGORY_KEY AS CATEGORY_KEY_A,
    right_side.CATEGORY_KEY AS CATEGORY_KEY_B
  FROM output_category left_side
  JOIN output_category right_side
    ON right_side.OUTPUT_SK = left_side.OUTPUT_SK
   AND right_side.CATEGORY_KEY > left_side.CATEGORY_KEY
),
parent AS (
  SELECT CATEGORY_KEY, COUNT(DISTINCT OUTPUT_SK) AS PARENT_WORKS
  FROM output_category
  GROUP BY 1
)
SELECT
  pair.CATEGORY_KEY_A,
  pair.CATEGORY_KEY_B,
  COUNT(DISTINCT pair.OUTPUT_SK) AS JOINT_WORKS,
  parent_a.PARENT_WORKS AS PARENT_WORKS_A,
  parent_b.PARENT_WORKS AS PARENT_WORKS_B,
  ROUND(
    COUNT(DISTINCT pair.OUTPUT_SK) / NULLIF(LEAST(parent_a.PARENT_WORKS, parent_b.PARENT_WORKS), 0),
    6) AS JOINT_TO_SMALLER_PARENT_RATIO,
  IFF(
    parent_a.PARENT_WORKS >= 100 AND parent_b.PARENT_WORKS >= 100
    AND COUNT(DISTINCT pair.OUTPUT_SK) >= 5,
    TRUE, FALSE) AS IS_REPORTABLE,
  100 AS MIN_PARENT_WORKS,
  5   AS MIN_JOINT_WORKS,
  CURRENT_DATE() AS RETRIEVED_ON
FROM pair
JOIN parent parent_a
  ON parent_a.CATEGORY_KEY = pair.CATEGORY_KEY_A
JOIN parent parent_b
  ON parent_b.CATEGORY_KEY = pair.CATEGORY_KEY_B
GROUP BY 1, 2, 4, 5;

-- ---------------------------------------------------------------------------
-- VW_RESEARCH_COMMUNITY - institution x category (BI page 3, Q07/Q08/Q10)
-- Grain: one row per institution per category per publication year.
-- A work is credited to an institution through its authors. The credit is
-- fractional when a work has several institutions, so the sum of the credit
-- column is the number of works in the cell rather than the number of author
-- affiliations. Institutions that are not known are excluded from the ranking
-- and flagged instead, so they are visible but never counted as a partner.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE SECURE VIEW PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_COMMUNITY AS
WITH published_output AS (
  SELECT
    output.OUTPUT_SK,
    output.CATEGORY_KEY,
    output.CATEGORY_LABEL,
    output.PUBLICATION_YEAR
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.CATEGORY_KEY <> 'unclassified'
),
output_institution AS (
  SELECT DISTINCT
    author_bridge.OUTPUT_SK,
    institution_bridge.INSTITUTION_SK,
    institution_bridge.INSTITUTION_KEY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_AUTHOR author_bridge
  JOIN PAPERSONAR.PROJECT_DW.BRIDGE_AUTHOR_INSTITUTION institution_bridge
    ON institution_bridge.AUTHOR_SK = author_bridge.AUTHOR_SK
  WHERE EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = author_bridge.BATCH_ID
  )
    AND EXISTS (
      SELECT 1
      FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
      WHERE published.BATCH_ID = institution_bridge.BATCH_ID
    )
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
  credit.INSTITUTION_SK,
  credit.INSTITUTION_KEY,
  institution.INSTITUTION_NAME,
  institution.COUNTRY_CODE,
  published_output.CATEGORY_KEY,
  published_output.CATEGORY_LABEL,
  published_output.PUBLICATION_YEAR,
  COUNT(DISTINCT credit.OUTPUT_SK) AS WORKS,
  ROUND(SUM(credit.OUTPUT_CREDIT), 4) AS FRACTIONAL_CREDIT,
  IFF(institution.IS_UNKNOWN, TRUE, FALSE) AS IS_UNKNOWN_INSTITUTION,
  CURRENT_DATE() AS RETRIEVED_ON
FROM credit
JOIN published_output
  ON published_output.OUTPUT_SK = credit.OUTPUT_SK
JOIN PAPERSONAR.PROJECT_DW.DIM_INSTITUTION institution
  ON institution.INSTITUTION_SK = credit.INSTITUTION_SK
GROUP BY 1, 2, 3, 4, 5, 6, 7, 10
ORDER BY 5, 7, FRACTIONAL_CREDIT DESC;

GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_TOPIC_GROWTH
  TO ROLE PAPERSONAR_REPORTER;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_OUTPUT_COVERAGE
  TO ROLE PAPERSONAR_REPORTER;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_CITATION_COHORTS
  TO ROLE PAPERSONAR_REPORTER;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_TOPIC_INTERSECTIONS
  TO ROLE PAPERSONAR_REPORTER;
GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_COMMUNITY
  TO ROLE PAPERSONAR_REPORTER;
