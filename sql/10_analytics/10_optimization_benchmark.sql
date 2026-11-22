-- =============================================================================
-- PaperSonar Phase 3 - WP5 optimization benchmark (READ-ONLY)
-- =============================================================================
-- Purpose: Provide the four representative statements whose runtime, bytes
--          scanned and partition pruning are measured before and after the
--          Phase 3 clustering change, so the change is justified by evidence
--          instead of by habit.
-- Inputs: PROJECT_REPORTING.VW_RESEARCH_OUTPUT, PROJECT_REPORTING
--         .VW_CITATION_SNAPSHOT, PROJECT_DW facts and bridges,
--         PROJECT_AUDIT.PUBLISHED_BATCH.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/03_optimization/BENCH1_before.csv ...
--          BENCH4_after.csv, the matching BENCHn_plan_before.json,
--          BENCHn_plan_after.json and BENCHn_analyze_before.txt,
--          BENCHn_analyze_after.txt.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: the year window 2021-2025 and the suppression thresholds
--             100 / 5 come from the Phase 1 question definitions and are
--             repeated here so the benchmark runs the same statement that the
--             business query runs.
-- Cost: BENCH2 and BENCH3 are the expensive statements in the project. Run
--       them on WH_PAPERSONAR_ELT and record the credits shown in the query
--       profile, not only the elapsed time.
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================
-- HOW TO MEASURE (per benchmark, in this order)
--   1. EXPLAIN USING JSON <statement>   -> save the plan as
--      BENCHn_plan_before.json  (it carries bytes scanned and partitions
--      scanned / pruned).
--   2. EXPLAIN ANALYZE <statement>      -> save the text plan as
--      BENCHn_analyze_before.txt  (it carries the execution time).
--   3. <statement>                      -> save the result as
--      BENCHn_before.csv.
-- Run every statement of a benchmark in one session so the warehouse state is
-- the same for the before and the after measurement. Do not edit the
-- statement: the measured statement must be the deployed statement.
--
-- The baseline is measured on the cluster-free layout, the after measurement
-- is measured after sql/06_facts/03_phase3_clustering.sql has been applied
-- and the tables have been re-clustered.

-- ---------------------------------------------------------------------------
-- BENCH1 - topic growth scan (Q01)
-- Two passes over the published output view: one to count the corpus per
-- year, one to count the works per topic and year. This is the statement the
-- BI page 1 runs, so it is the one that has to stay fast.
-- ---------------------------------------------------------------------------
WITH corpus_year AS (
  SELECT
    output.PUBLICATION_YEAR,
    COUNT(DISTINCT output.OUTPUT_SK) AS CORPUS_WORKS
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  GROUP BY 1
),
topic_year AS (
  SELECT
    output.CATEGORY_KEY,
    output.PUBLICATION_YEAR,
    COUNT(DISTINCT output.OUTPUT_SK) AS WORKS
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.CATEGORY_KEY <> 'unclassified'
    AND output.PUBLICATION_YEAR IN (2023, 2025)
  GROUP BY 1, 2
)
SELECT
  topic_year.CATEGORY_KEY,
  topic_year.PUBLICATION_YEAR,
  topic_year.WORKS,
  corpus_year.CORPUS_WORKS,
  ROUND(topic_year.WORKS / NULLIF(corpus_year.CORPUS_WORKS, 0), 6) AS SHARE_OF_CORPUS
FROM topic_year
JOIN corpus_year
  ON corpus_year.PUBLICATION_YEAR = topic_year.PUBLICATION_YEAR
ORDER BY topic_year.WORKS DESC;

-- ---------------------------------------------------------------------------
-- BENCH2 - topic intersection self-join (Q05)
-- The self-join over the category assignment is the heaviest statement in
-- the project: the bridge holds one row per output and category, and the
-- join is repeated for both endpoints.
-- ---------------------------------------------------------------------------
WITH published_output AS (
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
  SELECT assignment.CATEGORY_KEY, COUNT(DISTINCT assignment.OUTPUT_SK) AS PARENT_WORKS
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
  pair.CATEGORY_B,
  pair.JOINT_WORKS,
  parent_a.PARENT_WORKS AS PARENT_A_WORKS,
  parent_b.PARENT_WORKS AS PARENT_B_WORKS
FROM pair
JOIN parent_count parent_a
  ON parent_a.CATEGORY_KEY = pair.CATEGORY_A
JOIN parent_count parent_b
  ON parent_b.CATEGORY_KEY = pair.CATEGORY_B
WHERE parent_a.PARENT_WORKS >= 100
  AND parent_b.PARENT_WORKS >= 100
  AND pair.JOINT_WORKS >= 5
ORDER BY pair.JOINT_WORKS DESC;

-- ---------------------------------------------------------------------------
-- BENCH3 - directed topic citation flow (Q11)
-- Joins the relation fact to the category bridge on both endpoints. The
-- relation fact is the largest table in the model (about 1.8m rows).
-- ---------------------------------------------------------------------------
WITH published_output AS (
  SELECT DISTINCT fact.OUTPUT_SK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  JOIN PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    ON published.BATCH_ID = fact.LAST_BATCH_ID
),
primary_category AS (
  SELECT bridge.OUTPUT_SK, bridge.CATEGORY_KEY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
  JOIN published_output output
    ON output.OUTPUT_SK = bridge.OUTPUT_SK
  WHERE bridge.IS_PRIMARY
    AND bridge.CATEGORY_KEY <> 'unclassified'
),
citing_output AS (
  SELECT
    relation.OUTPUT_SK        AS CITING_OUTPUT_SK,
    relation.TARGET_OUTPUT_SK AS CITED_OUTPUT_SK,
    fact.PUBLICATION_YEAR     AS CITING_YEAR
  FROM PAPERSONAR.PROJECT_DW.FACT_OUTPUT_RELATION relation
  JOIN PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
    ON fact.OUTPUT_SK = relation.OUTPUT_SK
  JOIN published_output citing
    ON citing.OUTPUT_SK = relation.OUTPUT_SK
  JOIN published_output cited
    ON cited.OUTPUT_SK = relation.TARGET_OUTPUT_SK
  WHERE relation.RELATION_TYPE = 'REFERENCES'
    AND relation.TARGET_OUTPUT_SK IS NOT NULL
)
SELECT
  citing_category.CATEGORY_KEY      AS CITING_TOPIC,
  cited_category.CATEGORY_KEY       AS CITED_TOPIC,
  COUNT(*)                          AS CITATION_PAIRS,
  COUNT(DISTINCT citing.CITING_OUTPUT_SK) AS CITING_OUTPUTS,
  COUNT(DISTINCT citing.CITED_OUTPUT_SK)  AS CITED_OUTPUTS
FROM citing_output citing
JOIN primary_category citing_category
  ON citing_category.OUTPUT_SK = citing.CITING_OUTPUT_SK
JOIN primary_category cited_category
  ON cited_category.OUTPUT_SK = citing.CITED_OUTPUT_SK
GROUP BY 1, 2
ORDER BY CITATION_PAIRS DESC;

-- ---------------------------------------------------------------------------
-- BENCH4 - the heaviest reporting view (VW_RESEARCH_COMMUNITY)
-- The BI page 3 view: the author bridge joined to the institution bridge and
-- to the primary category of every published work.
-- ---------------------------------------------------------------------------
SELECT COUNT(*) AS COMMUNITY_ROWS
FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_COMMUNITY;
