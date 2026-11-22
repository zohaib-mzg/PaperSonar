-- =============================================================================
-- PaperSonar Phase 3 - Q03/Q04 citation impact and gains (READ-ONLY)
-- =============================================================================
-- Purpose: Answer the Phase 1 citation questions from the published corpus.
--          Q03 Which topics have high citation impact within comparable
--               publication cohorts.
--          Q04 Which publications gained citations between two observations.
-- Inputs: PROJECT_REPORTING.VW_CITATION_SNAPSHOT, VW_RESEARCH_OUTPUT.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/01_queries/Q03_citation_impact.csv and
--          docs/phase3/evidence/01_queries/Q04_citation_gains.csv.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: Q03 uses the latest observed snapshot date; Q04 uses the two
--             latest observed snapshot dates. Both are discovered from the
--             data and echoed in the result, so the result is self-describing.
-- Cost: scans VW_CITATION_SNAPSHOT (about 266k rows) once per query.
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================
-- Citation counts are never summed across sources: the snapshot fact is one
-- row per output/source/date, and the reporting view exposes one source per
-- row. Each query states which source scope it uses.

-- ---------------------------------------------------------------------------
-- Q03 - Which topics have high citation impact within comparable publication
--       cohorts
-- Decision. Prioritize a reading shortlist without favoring older work.
-- Measure. At one snapshot date, median cited_by_count within publication year
--         and work type. Report cohort size and missing counts.
-- Analysis. Dice by topic, publication year and type.
-- Limit. Use one observation date. Citation counts do not establish research
--        quality or causation.
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
    output.CITED_BY_COUNT AS FACT_CITED_BY_COUNT
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.CATEGORY_KEY <> 'unclassified'
),
observed AS (
  SELECT
    snapshot.OUTPUT_SK,
    snapshot.SOURCE_NAME,
    snapshot.SNAPSHOT_DATE,
    snapshot.CITED_BY_COUNT
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
  COUNT(DISTINCT observed.OUTPUT_SK) AS COHORT_WITH_SNAPSHOT,
  COUNT(DISTINCT IFF(observed.OUTPUT_SK IS NULL, cohort.OUTPUT_SK, NULL)) AS COHORT_MISSING_SNAPSHOT,
  MEDIAN(observed.CITED_BY_COUNT) AS MEDIAN_CITED_BY,
  MIN(observed.CITED_BY_COUNT) AS MIN_CITED_BY,
  MAX(observed.CITED_BY_COUNT) AS MAX_CITED_BY,
  MAX(observed.SOURCE_NAME) AS SCOPE_SOURCE,
  CURRENT_DATE() AS RETRIEVED_ON
FROM cohort
CROSS JOIN snapshot_dates dates
LEFT JOIN observed
  ON observed.OUTPUT_SK = cohort.OUTPUT_SK
GROUP BY 1, 2, 3, 4, 5
ORDER BY cohort.CATEGORY_KEY, cohort.PUBLICATION_YEAR, cohort.OUTPUT_TYPE_NAME;

-- ---------------------------------------------------------------------------
-- Q04 - Which publications gained citations between two observations
-- Decision. Monitor papers that merit a fresh review.
-- Measure. Difference between the same work's citation counts at two
--         successfully observed dates. Rank positive changes and display
--         negative revisions separately.
-- Analysis. Drill to publication title and DOI.
-- Limit. Only works present at both dates qualify. Snapshot differences begin
--        with local collection, not publication.
-- ---------------------------------------------------------------------------
WITH snapshot_dates AS (
  SELECT snapshot.SNAPSHOT_DATE
  FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_SNAPSHOT snapshot
  GROUP BY 1
),
chosen_dates AS (
  SELECT
    MAX(SNAPSHOT_DATE) AS LATE_DATE,
    (SELECT MAX(SNAPSHOT_DATE)
     FROM snapshot_dates
     WHERE SNAPSHOT_DATE < (SELECT MAX(SNAPSHOT_DATE) FROM snapshot_dates)) AS EARLY_DATE
  FROM snapshot_dates
),
early AS (
  SELECT snapshot.OUTPUT_SK, snapshot.SOURCE_NAME, snapshot.CITED_BY_COUNT
  FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_SNAPSHOT snapshot
  JOIN chosen_dates dates
    ON dates.EARLY_DATE = snapshot.SNAPSHOT_DATE
),
late AS (
  SELECT snapshot.OUTPUT_SK, snapshot.SOURCE_NAME, snapshot.CITED_BY_COUNT
  FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_SNAPSHOT snapshot
  JOIN chosen_dates dates
    ON dates.LATE_DATE = snapshot.SNAPSHOT_DATE
),
change AS (
  SELECT
    early.OUTPUT_SK,
    early.SOURCE_NAME,
    early.CITED_BY_COUNT AS EARLY_CITED_BY,
    late.CITED_BY_COUNT   AS LATE_CITED_BY,
    late.CITED_BY_COUNT - early.CITED_BY_COUNT AS CITATION_CHANGE
  FROM early
  JOIN late
    ON late.OUTPUT_SK = early.OUTPUT_SK
   AND late.SOURCE_NAME = early.SOURCE_NAME
)
SELECT
  change.OUTPUT_SK,
  output.OUTPUT_BK,
  output.DOI_NORMALIZED,
  output.CATEGORY_KEY,
  output.CATEGORY_LABEL,
  output.PUBLICATION_YEAR,
  output.VENUE_NAME,
  change.SOURCE_NAME,
  change.EARLY_CITED_BY,
  change.LATE_CITED_BY,
  change.CITATION_CHANGE,
  (SELECT EARLY_DATE FROM chosen_dates) AS EARLY_DATE,
  (SELECT LATE_DATE  FROM chosen_dates) AS LATE_DATE,
  IFF(change.CITATION_CHANGE > 0, 'GAIN', 'REVISION') AS CHANGE_KIND,
  CURRENT_DATE() AS RETRIEVED_ON
FROM change
JOIN PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  ON output.OUTPUT_SK = change.OUTPUT_SK
ORDER BY change.CITATION_CHANGE DESC, change.OUTPUT_SK;
