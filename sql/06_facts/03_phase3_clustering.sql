-- =============================================================================
-- PaperSonar Phase 3 - WP5 clustering change (MANUAL, MEASURED FIRST)
-- =============================================================================
-- Purpose: Apply, and if necessary roll back, the clustering keys that the
--          Phase 3 measurement justifies on the hot access paths.
-- Inputs: PROJECT_DW.FACT_RESEARCH_OUTPUT, PROJECT_DW.FACT_OUTPUT_RELATION,
--         PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY.
-- Outputs: clustering keys on three tables, or the rollback of them.
-- Idempotent: Yes - a clustering key is replaced, not stacked, and
--             DROP CLUSTERING KEY restores the cluster-free layout.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: The change is applied only after the baseline measurement in
--             sql/10_analytics/10_optimization_benchmark.sql has been saved.
--             Re-clustering is a physical rewrite that consumes credits, so
--             the measured benefit has to be larger than the measured cost.
-- Cost: re-clustering rewrites the affected tables. FACT_OUTPUT_RELATION
--       holds about 1.8m rows, BRIDGE_OUTPUT_TOPIC_CATEGORY about 0.9m rows
--       and FACT_RESEARCH_OUTPUT about 0.3m rows.
-- Deploy: manual - the change is a measured experiment, not a default.
-- =============================================================================
-- MEASUREMENT ORDER
--   1. Run sql/10_analytics/10_optimization_benchmark.sql and save the
--      before artefacts (BENCH1..BENCH4 plan, analyze and result files).
--   2. Run the clustering statement below.
--   3. Wait until the tables are re-clustered (SHOW TABLES reports the
--      clustering key; the rewrite finishes in the background).
--   4. Run the benchmark again and save the after artefacts.
--   5. Keep the clustering keys only if the measured execution time or bytes
--      scanned improved on the hot statements. Otherwise run the rollback
--      statement at the end of this file.
--
-- WHY THESE KEYS
--   FACT_RESEARCH_OUTPUT on (PUBLICATION_YEAR, SOURCE_NAME): every analytical
--   statement filters by publication year and groups by source. Clustering
--   orders the rows so the year predicate prunes micro-partitions instead of
--   reading them.
--   FACT_OUTPUT_RELATION on (RELATION_TYPE, OUTPUT_SK): the citation flow
--   filters on the relation type and joins on the output key.
--   BRIDGE_OUTPUT_TOPIC_CATEGORY on (OUTPUT_SK, CATEGORY_KEY): the topic
--   intersection statement joins the bridge to itself on the output key.
--
-- The baseline layout is cluster-free on purpose: with a corpus of this size
-- the pruning benefit has to be proven, not assumed.

ALTER TABLE PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT
  CLUSTER BY (PUBLICATION_YEAR, SOURCE_NAME);

ALTER TABLE PAPERSONAR.PROJECT_DW.FACT_OUTPUT_RELATION
  CLUSTER BY (RELATION_TYPE, OUTPUT_SK);

ALTER TABLE PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY
  CLUSTER BY (OUTPUT_SK, CATEGORY_KEY);

-- Verification: the clustering key is visible in SHOW TABLES.
SHOW TABLES LIKE 'FACT_RESEARCH_OUTPUT' IN SCHEMA PAPERSONAR.PROJECT_DW;
SHOW TABLES LIKE 'FACT_OUTPUT_RELATION' IN SCHEMA PAPERSONAR.PROJECT_DW;
SHOW TABLES LIKE 'BRIDGE_OUTPUT_TOPIC_CATEGORY' IN SCHEMA PAPERSONAR.PROJECT_DW;

-- ---------------------------------------------------------------------------
-- ROLLBACK (run only when the measurement does not justify the change)
-- ---------------------------------------------------------------------------
-- ALTER TABLE PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT DROP CLUSTERING KEY;
-- ALTER TABLE PAPERSONAR.PROJECT_DW.FACT_OUTPUT_RELATION DROP CLUSTERING KEY;
-- ALTER TABLE PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY DROP CLUSTERING KEY;
