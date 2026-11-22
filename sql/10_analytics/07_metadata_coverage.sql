-- =============================================================================
-- PaperSonar Phase 3 - Q12 metadata coverage weakness (READ-ONLY)
-- =============================================================================
-- Purpose: Answer the Phase 1 metadata-coverage question from the published
--          corpus.
--          Q12 Which comparisons are weakened by missing or unstable metadata.
-- Inputs: PROJECT_REPORTING.VW_RESEARCH_OUTPUT, PROJECT_DW bridge tables,
--         DIM_INSTITUTION, PROJECT_AUDIT.PUBLISHED_BATCH.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/01_queries/Q12_metadata_coverage.csv.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: year window 2021-2025.
-- Cost: scans VW_RESEARCH_OUTPUT and the author/institution bridges.
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================
-- Every rate is computed over its own eligible population and the eligible
-- population is returned next to it. Nulls are never converted into zero
-- citation counts, and a missing value is reported as missing.

-- ---------------------------------------------------------------------------
-- Q12 - Which comparisons are weakened by missing or unstable metadata
-- Decision. Avoid presenting unreliable rankings.
-- Measure. Missing DOI, primary topic, venue, institution and known access
--         percentages over their eligible work populations. Compare corpus
--         versions through archived outputs.
-- Analysis. Drill from a flagged topic to the affected records.
-- Limit. Do not turn nulls into zero citation counts. Failed refreshes must
--        not appear as changes.
-- ---------------------------------------------------------------------------
WITH published_output AS (
  SELECT DISTINCT fact.OUTPUT_SK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  JOIN PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    ON published.BATCH_ID = fact.LAST_BATCH_ID
),
output_with_institution AS (
  SELECT DISTINCT
    author_bridge.OUTPUT_SK,
    institution_bridge.INSTITUTION_SK
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_AUTHOR author_bridge
  JOIN PAPERSONAR.PROJECT_DW.BRIDGE_AUTHOR_INSTITUTION institution_bridge
    ON institution_bridge.AUTHOR_SK = author_bridge.AUTHOR_SK
  JOIN published_output output
    ON output.OUTPUT_SK = author_bridge.OUTPUT_SK
),
known_institution AS (
  SELECT DISTINCT
    output_with_institution.OUTPUT_SK,
    institution_bridge.INSTITUTION_SK
  FROM output_with_institution
  JOIN PAPERSONAR.PROJECT_DW.DIM_INSTITUTION institution
    ON institution.INSTITUTION_SK = output_with_institution.INSTITUTION_SK
  WHERE NOT institution.IS_UNKNOWN
)
SELECT
  output.CATEGORY_KEY,
  output.CATEGORY_LABEL,
  output.PUBLICATION_YEAR,
  COUNT(DISTINCT output.OUTPUT_SK) AS ELIGIBLE_WORKS,
  COUNT(DISTINCT IFF(output.DOI_NORMALIZED IS NULL, output.OUTPUT_SK, NULL)) AS MISSING_DOI,
  ROUND(
    COUNT(DISTINCT IFF(output.DOI_NORMALIZED IS NULL, output.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT output.OUTPUT_SK), 0), 6
  ) AS MISSING_DOI_SHARE,
  COUNT(DISTINCT IFF(output.CATEGORY_KEY IS NULL OR output.CATEGORY_KEY = 'unclassified',
                     output.OUTPUT_SK, NULL)) AS MISSING_PRIMARY_TOPIC,
  ROUND(
    COUNT(DISTINCT IFF(output.CATEGORY_KEY IS NULL OR output.CATEGORY_KEY = 'unclassified',
                       output.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT output.OUTPUT_SK), 0), 6
  ) AS MISSING_PRIMARY_TOPIC_SHARE,
  COUNT(DISTINCT IFF(output.VENUE_NAME IS NULL OR output.VENUE_NAME = 'Unknown',
                     output.OUTPUT_SK, NULL)) AS MISSING_VENUE,
  ROUND(
    COUNT(DISTINCT IFF(output.VENUE_NAME IS NULL OR output.VENUE_NAME = 'Unknown',
                       output.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT output.OUTPUT_SK), 0), 6
  ) AS MISSING_VENUE_SHARE,
  COUNT(DISTINCT IFF(known_institution.OUTPUT_SK IS NULL, output.OUTPUT_SK, NULL))
    AS MISSING_INSTITUTION,
  ROUND(
    COUNT(DISTINCT IFF(known_institution.OUTPUT_SK IS NULL, output.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT output.OUTPUT_SK), 0), 6
  ) AS MISSING_INSTITUTION_SHARE,
  COUNT(DISTINCT IFF(output.ACCESS_STATUS_NAME = 'Unknown', output.OUTPUT_SK, NULL))
    AS MISSING_ACCESS_STATUS,
  ROUND(
    COUNT(DISTINCT IFF(output.ACCESS_STATUS_NAME = 'Unknown', output.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT output.OUTPUT_SK), 0), 6
  ) AS MISSING_ACCESS_STATUS_SHARE,
  CURRENT_DATE() AS RETRIEVED_ON
FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
LEFT JOIN known_institution
  ON known_institution.OUTPUT_SK = output.OUTPUT_SK
WHERE output.PUBLICATION_YEAR BETWEEN 2021 AND 2025
GROUP BY 1, 2, 3
ORDER BY output.CATEGORY_KEY, output.PUBLICATION_YEAR;
