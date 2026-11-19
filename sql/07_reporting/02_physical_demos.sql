-- =============================================================================
-- Purpose: Optional physical-design demonstrations (materialized view and
--          dynamic table). These are NOT applied by the default deploy.
-- Inputs: PROJECT_DW fact tables.
-- Outputs: MV_CITATION_BY_DAY, DT_SOURCE_OBSERVATION_DAILY.
-- Idempotent: Yes - IF NOT EXISTS; manual execution only.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Background refresh consumes credits; enable only after reviewing the
--       trial edition and credit balance.
-- =============================================================================
-- Deploy: manual
-- VERIFY: dynamic tables require a supported Snowflake edition and a dedicated
-- warehouse. Materialized views have SQL restrictions and do not support every
-- join/aggregate pattern. Run each statement manually in the target account and
-- keep these objects out of the default deployment.
--
-- The baseline physical design is: cluster-free XS ELT, micro-partition pruning
-- from batch/window predicates, and secure reporting views. Add these objects
-- only when query latency evidence justifies the background cost.

CREATE MATERIALIZED VIEW IF NOT EXISTS PAPERSONAR.PROJECT_REPORTING.MV_CITATION_BY_DAY
  COMMENT = 'Optional: daily citation totals by source; manual deployment only'
AS
SELECT
  SNAPSHOT_DATE_KEY,
  SOURCE_NAME,
  COUNT(*) AS OUTPUT_COUNT,
  SUM(CITED_BY_COUNT) AS TOTAL_CITATIONS
FROM PAPERSONAR.PROJECT_DW.FACT_CITATION_SNAPSHOT
GROUP BY SNAPSHOT_DATE_KEY, SOURCE_NAME;

CREATE DYNAMIC TABLE IF NOT EXISTS PAPERSONAR.PROJECT_REPORTING.DT_SOURCE_OBSERVATION_DAILY
  TARGET_LAG = '1 hour'
  WAREHOUSE = WH_PAPERSONAR_ELT
  COMMENT = 'Optional: daily observation counts by source; manual deployment only'
AS
SELECT
  TO_DATE(INGESTED_AT) AS OBSERVATION_DATE,
  SOURCE_NAME,
  COUNT(*) AS OBSERVATION_COUNT
FROM PAPERSONAR.PROJECT_DW.FACT_OUTPUT_SOURCE_OBSERVATION
GROUP BY TO_DATE(INGESTED_AT), SOURCE_NAME;
