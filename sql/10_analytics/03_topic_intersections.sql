-- =============================================================================
-- PaperSonar Phase 3 - Q05 sparse topic intersections (READ-ONLY)
-- =============================================================================
-- Purpose: Answer the Phase 1 topic-intersection question from the published
--          corpus.
--          Q05 Which topic intersections are sparsely represented but supported
--               by substantial parent topics.
-- Inputs: PROJECT_DW.FACT_RESEARCH_OUTPUT, BRIDGE_OUTPUT_TOPIC_CATEGORY,
--         PROJECT_AUDIT.PUBLISHED_BATCH.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/01_queries/Q05_topic_intersections.csv.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: year window 2021-2025 and the suppression thresholds (100 works
--             per parent, 5 joint works per pair) stated in the Phase 1
--             definition.
-- Cost: self-join over the output/category bridge; run on WH_PAPERSONAR_ELT.
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================
-- The published-batches filter is written out here because the topic bridge is
-- not exposed through a reporting view yet (WP4 adds the view). It matches
-- the publication contract used by the reporting views exactly.

-- ---------------------------------------------------------------------------
-- Q05 - Which topic intersections are sparsely represented but supported by
--       substantial parent topics
-- Decision. Identify candidates for manual literature review.
-- Measure. For each unordered pair of supplied topics count distinct
--         co-assigned works. Display each parent count, joint count and
--         joint / smaller parent count for 2021 to 2025.
-- Analysis. Compare pairs and inspect their actual papers.
-- Limit. Require each parent to have at least 100 works and the pair to have
--        at least 5. Sparse tagging is a prompt for review, not proof of a
--        scientific gap.
-- ---------------------------------------------------------------------------
WITH params AS (
  SELECT 2021 AS YEAR_FROM,
         2025 AS YEAR_TO,
         100 AS MIN_PARENT_WORKS,
         5   AS MIN_JOINT_WORKS
),
published_output AS (
  SELECT DISTINCT fact.OUTPUT_SK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  JOIN PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    ON published.BATCH_ID = fact.LAST_BATCH_ID
),
output_year AS (
  SELECT fact.OUTPUT_SK, fact.PUBLICATION_YEAR
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  JOIN published_output output
    ON output.OUTPUT_SK = fact.OUTPUT_SK
),
assignment AS (
  SELECT DISTINCT
    output_year.OUTPUT_SK,
    bridge.CATEGORY_KEY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
  JOIN output_year
    ON output_year.OUTPUT_SK = bridge.OUTPUT_SK
  WHERE bridge.CATEGORY_KEY <> 'unclassified'
    AND output_year.PUBLICATION_YEAR BETWEEN 2021 AND 2025
),
parent_count AS (
  SELECT
    assignment.CATEGORY_KEY,
    COUNT(DISTINCT assignment.OUTPUT_SK) AS PARENT_WORKS
  FROM assignment
  GROUP BY 1
),
pair AS (
  SELECT
    left_side.CATEGORY_KEY  AS CATEGORY_A,
    right_side.CATEGORY_KEY AS CATEGORY_B,
    COUNT(DISTINCT left_side.OUTPUT_SK) AS JOINT_WORKS
  FROM assignment left_side
  JOIN assignment right_side
    ON right_side.OUTPUT_SK = left_side.OUTPUT_SK
   AND right_side.CATEGORY_KEY > left_side.CATEGORY_KEY
  GROUP BY 1, 2
)
SELECT
  pair.CATEGORY_A,
  parent_dim_a.LABEL            AS CATEGORY_A_LABEL,
  pair.CATEGORY_B,
  parent_dim_b.LABEL            AS CATEGORY_B_LABEL,
  parent_a.PARENT_WORKS       AS PARENT_A_WORKS,
  parent_b.PARENT_WORKS       AS PARENT_B_WORKS,
  pair.JOINT_WORKS,
  ROUND(
    pair.JOINT_WORKS / NULLIF(LEAST(parent_a.PARENT_WORKS, parent_b.PARENT_WORKS), 0),
    4
  ) AS JOINT_TO_SMALLER_PARENT,
  (SELECT MIN_PARENT_WORKS FROM params) AS MIN_PARENT_WORKS,
  (SELECT MIN_JOINT_WORKS FROM params)   AS MIN_JOINT_WORKS,
  'REPORTABLE' AS PAIR_STATUS,
  CURRENT_DATE() AS RETRIEVED_ON
FROM pair
JOIN parent_count parent_a
  ON parent_a.CATEGORY_KEY = pair.CATEGORY_A
JOIN parent_count parent_b
  ON parent_b.CATEGORY_KEY = pair.CATEGORY_B
JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY parent_dim_a
  ON parent_dim_a.CATEGORY_KEY = pair.CATEGORY_A
JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY parent_dim_b
  ON parent_dim_b.CATEGORY_KEY = pair.CATEGORY_B
WHERE parent_a.PARENT_WORKS >= 100
  AND parent_b.PARENT_WORKS >= 100
  AND pair.JOINT_WORKS >= 5
ORDER BY JOINT_TO_SMALLER_PARENT DESC, pair.JOINT_WORKS DESC;
