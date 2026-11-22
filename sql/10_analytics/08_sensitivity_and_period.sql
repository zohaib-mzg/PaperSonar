-- =============================================================================
-- PaperSonar Phase 3 - Q13/Q14 counting sensitivity and elapsed period (READ-ONLY)
-- =============================================================================
-- Purpose: Answer the Phase 1 sensitivity and period questions from the
--          published corpus.
--          Q13 How sensitive is an opportunity shortlist to the counting
--               method.
--          Q14 How does the current partial year compare with the same elapsed
--               period last year.
-- Inputs: PROJECT_REPORTING.VW_RESEARCH_OUTPUT, PROJECT_DW bridge tables,
--         PROJECT_AUDIT.PUBLISHED_BATCH.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/01_queries/Q13_counting_sensitivity.csv and
--          docs/phase3/evidence/01_queries/Q14_partial_year_comparison.csv.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: Q13 uses a 30-work low-volume threshold; Q14 uses a common
--             month/day cutoff and the two comparison years. Both are visible
--             in the result.
-- Cost: scans VW_RESEARCH_OUTPUT and the topic bridge.
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Q13 - How sensitive is an opportunity shortlist to the counting method
-- Decision. See whether a recommendation survives reasonable analytical
--          choices.
-- Measure. Compare rankings using primary-topic counts and equal fractional
--         topic allocation, with and without low-volume groups.
-- Analysis. Inspect rank changes and supporting work lists.
-- Limit. Differences describe method sensitivity. No automatic confidence
--        score or discovery claim is assigned.
-- ---------------------------------------------------------------------------
WITH params AS (
  SELECT 30 AS LOW_VOLUME_THRESHOLD
),
published_output AS (
  SELECT DISTINCT fact.OUTPUT_SK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  JOIN PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    ON published.BATCH_ID = fact.LAST_BATCH_ID
),
assignment AS (
  SELECT DISTINCT
    bridge.OUTPUT_SK,
    bridge.CATEGORY_KEY,
    bridge.IS_PRIMARY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
  JOIN published_output output
    ON output.OUTPUT_SK = bridge.OUTPUT_SK
  WHERE bridge.CATEGORY_KEY <> 'unclassified'
),
assignment_count AS (
  SELECT
    assignment.OUTPUT_SK,
    COUNT(*) AS ASSIGNMENTS
  FROM assignment
  GROUP BY 1
),
method_counts AS (
  SELECT
    assignment.CATEGORY_KEY,
    COUNT(DISTINCT IFF(assignment.IS_PRIMARY, assignment.OUTPUT_SK, NULL)) AS PRIMARY_COUNT,
    SUM(1.0 / assignment_count.ASSIGNMENTS)                              AS FRACTIONAL_COUNT,
    COUNT(DISTINCT assignment.OUTPUT_SK)                                  AS ANY_ASSIGNMENT_WORKS
  FROM assignment
  JOIN assignment_count
    ON assignment_count.OUTPUT_SK = assignment.OUTPUT_SK
  GROUP BY 1
),
ranked AS (
  SELECT
    method_counts.*,
    ROW_NUMBER() OVER (ORDER BY PRIMARY_COUNT DESC, CATEGORY_KEY)     AS PRIMARY_RANK,
    ROW_NUMBER() OVER (ORDER BY FRACTIONAL_COUNT DESC, CATEGORY_KEY)  AS FRACTIONAL_RANK,
    ROW_NUMBER() OVER (ORDER BY ANY_ASSIGNMENT_WORKS DESC, CATEGORY_KEY) AS ALL_ASSIGNMENT_RANK
  FROM method_counts
)
SELECT
  ranked.CATEGORY_KEY,
  category.LABEL                                   AS CATEGORY_LABEL,
  ranked.PRIMARY_COUNT,
  ranked.FRACTIONAL_COUNT,
  ranked.ANY_ASSIGNMENT_WORKS,
  ranked.PRIMARY_RANK,
  ranked.FRACTIONAL_RANK,
  ranked.ALL_ASSIGNMENT_RANK,
  ranked.PRIMARY_RANK - ranked.FRACTIONAL_RANK      AS RANK_SHIFT,
  IFF(ranked.PRIMARY_COUNT < (SELECT LOW_VOLUME_THRESHOLD FROM params),
      'LOW_VOLUME', 'STABLE_VOLUME')               AS VOLUME_BAND,
  IFF(ranked.PRIMARY_COUNT < (SELECT LOW_VOLUME_THRESHOLD FROM params),
      NULL, ranked.PRIMARY_RANK - ranked.FRACTIONAL_RANK) AS RANK_SHIFT_EXCLUDING_LOW_VOLUME,
  CURRENT_DATE() AS RETRIEVED_ON
FROM ranked
JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY category
  ON category.CATEGORY_KEY = ranked.CATEGORY_KEY
ORDER BY ranked.PRIMARY_RANK;

-- ---------------------------------------------------------------------------
-- Q14 - How does the current partial year compare with the same elapsed period
--       last year
-- Decision. Monitor recent activity without comparing a partial year to a
--          complete one.
-- Measure. Count works through a common month and day cutoff in 2025 and 2026
--         using source-reported dates. Show cutoff and retrieval date.
-- Analysis. Slice by topic and type, then drill by month.
-- Limit. Exclude unknown or year-only dates from elapsed-period comparisons.
--        Indexing delay remains a limitation.
-- ---------------------------------------------------------------------------
WITH params AS (
  SELECT 10 AS CUTOFF_MONTH,
         31 AS CUTOFF_DAY,
         2025 AS EARLY_YEAR,
         2026 AS LATE_YEAR
),
dated_output AS (
  SELECT
    output.OUTPUT_SK,
    output.CATEGORY_KEY,
    output.CATEGORY_LABEL,
    output.OUTPUT_TYPE_NAME,
    output.PUBLICATION_DATE,
    output.PUBLICATION_YEAR
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.PUBLICATION_DATE IS NOT NULL
    AND output.PUBLICATION_YEAR IN (2025, 2026)
),
eligible AS (
  SELECT
    dated_output.*,
    params.CUTOFF_MONTH,
    params.CUTOFF_DAY,
    params.EARLY_YEAR,
    params.LATE_YEAR,
    TO_DATE(TO_VARCHAR(dated_output.PUBLICATION_YEAR) || '-' ||
            RIGHT('0' || TO_VARCHAR(params.CUTOFF_MONTH), 2) || '-' ||
            RIGHT('0' || TO_VARCHAR(params.CUTOFF_DAY), 2)) AS CUTOFF_DATE
  FROM dated_output
  CROSS JOIN params
)
SELECT
  eligible.CATEGORY_KEY,
  eligible.CATEGORY_LABEL,
  eligible.OUTPUT_TYPE_NAME,
  eligible.CUTOFF_MONTH,
  eligible.CUTOFF_DAY,
  eligible.EARLY_YEAR,
  eligible.LATE_YEAR,
  COUNT(DISTINCT IFF(eligible.PUBLICATION_YEAR = eligible.EARLY_YEAR
                       AND eligible.PUBLICATION_DATE <= eligible.CUTOFF_DATE,
                     eligible.OUTPUT_SK, NULL)) AS WORKS_THROUGH_CUTOFF_EARLY_YEAR,
  COUNT(DISTINCT IFF(eligible.PUBLICATION_YEAR = eligible.LATE_YEAR
                       AND eligible.PUBLICATION_DATE <= eligible.CUTOFF_DATE,
                     eligible.OUTPUT_SK, NULL)) AS WORKS_THROUGH_CUTOFF_LATE_YEAR,
  COUNT(DISTINCT IFF(eligible.PUBLICATION_YEAR = eligible.EARLY_YEAR,
                     eligible.OUTPUT_SK, NULL)) AS WORKS_EARLY_YEAR_TOTAL,
  COUNT(DISTINCT IFF(eligible.PUBLICATION_YEAR = eligible.LATE_YEAR,
                     eligible.OUTPUT_SK, NULL)) AS WORKS_LATE_YEAR_TOTAL,
  ROUND(
    COUNT(DISTINCT IFF(eligible.PUBLICATION_YEAR = eligible.LATE_YEAR
                         AND eligible.PUBLICATION_DATE <= eligible.CUTOFF_DATE,
                       eligible.OUTPUT_SK, NULL))
    / NULLIF(COUNT(DISTINCT IFF(eligible.PUBLICATION_YEAR = eligible.EARLY_YEAR
                                  AND eligible.PUBLICATION_DATE <= eligible.CUTOFF_DATE,
                                eligible.OUTPUT_SK, NULL)), 0),
    6
  ) AS LATE_TO_EARLY_RATIO,
  (SELECT MAX(CUTOFF_DATE) FROM eligible) AS CUTOFF_DATE,
  CURRENT_DATE() AS RETRIEVED_ON
FROM eligible
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY eligible.CATEGORY_KEY, eligible.OUTPUT_TYPE_NAME;
