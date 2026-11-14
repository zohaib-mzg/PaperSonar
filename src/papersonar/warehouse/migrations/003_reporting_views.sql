-- 003_reporting_views.sql
-- PaperSonar PROJECT_REPORTING analytical views (SQL-first hardening layer).
--
-- Non-destructive: CREATE SCHEMA IF NOT EXISTS + CREATE VIEW IF NOT EXISTS.
-- Views read only from PROJECT_DW / PROJECT_OPS; no data is copied. They give
-- the warehouse a documented, queryable reporting surface consistent with the
-- dim/fact grains. Views are created even before data lands (zero-row results
-- until ingestion populates the warehouse).
--
-- NOTE: views are materialized only on real Snowflake. The mock warehouse
-- logs CREATE VIEW statements without evaluating them; reporting-view behavior
-- is therefore verified live (see acceptance report: BLOCKED items).

CREATE SCHEMA IF NOT EXISTS PROJECT_REPORTING;

-- Publications by publication year (grain: one row per publication year)
CREATE VIEW IF NOT EXISTS PROJECT_REPORTING.VW_PUBLICATION_BY_YEAR AS
SELECT
  PUBLICATION_YEAR                          AS PUB_YEAR,
  COUNT(*)                                  AS WORK_COUNT,
  SUM(CITED_BY_COUNT)                       AS CITED_BY_TOTAL,
  ROUND(AVG(CITED_BY_COUNT), 2)             AS CITED_BY_AVG
FROM PROJECT_DW.FACT_PUBLICATION
WHERE PUBLICATION_YEAR IS NOT NULL
GROUP BY PUBLICATION_YEAR;

-- Publications by winning source and open-access status (grain: source x OA)
-- FACT_PUBLICATION carries ACCESS_STATUS_KEY; the OA status name comes from
-- DIM_ACCESS_STATUS (fixed after live Snowflake flagged invalid identifier
-- 'OA_STATUS' on first execution).
CREATE VIEW IF NOT EXISTS PROJECT_REPORTING.VW_PUBLICATION_BY_SOURCE AS
SELECT
  F.SOURCE_PRIORITY                          AS SOURCE_NAME,
  COALESCE(A.ACCESS_STATUS_NAME, 'unknown')  AS OA_STATUS,
  COUNT(*)                                   AS WORK_COUNT,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY F.SOURCE_PRIORITY), 2) AS PCT_OF_SOURCE
FROM PROJECT_DW.FACT_PUBLICATION F
LEFT JOIN PROJECT_DW.DIM_ACCESS_STATUS A ON A.ACCESS_STATUS_KEY = F.ACCESS_STATUS_KEY
GROUP BY F.SOURCE_PRIORITY, A.ACCESS_STATUS_NAME;

-- Topic activity: canonical works per topic with publication-year span
-- (uses the topic bridge; topics from every source are source-qualified keys)
CREATE VIEW IF NOT EXISTS PROJECT_REPORTING.VW_TOPIC_ACTIVITY AS
SELECT
  T.TOPIC_NAME,
  T.SOURCE_NAME                    AS TOPIC_SOURCE,
  COUNT(DISTINCT B.WORK_KEY)       AS WORK_COUNT,
  MIN(F.PUBLICATION_YEAR)          AS FIRST_PUB_YEAR,
  MAX(F.PUBLICATION_YEAR)          AS LAST_PUB_YEAR
FROM PROJECT_DW.BRIDGE_WORK_TOPIC B
JOIN PROJECT_DW.DIM_TOPIC T ON T.TOPIC_KEY = B.TOPIC_KEY
LEFT JOIN PROJECT_DW.FACT_PUBLICATION F ON F.WORK_KEY = B.WORK_KEY
GROUP BY T.TOPIC_NAME, T.SOURCE_NAME;

-- Open-access status distribution (grain: one row per OA status)
CREATE VIEW IF NOT EXISTS PROJECT_REPORTING.VW_OPENACCESS_STATUS AS
SELECT
  COALESCE(A.ACCESS_STATUS_NAME, 'unknown') AS ACCESS_STATUS,
  COUNT(*)                                   AS WORK_COUNT,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS PCT_OF_ALL
FROM PROJECT_DW.FACT_PUBLICATION F
LEFT JOIN PROJECT_DW.DIM_ACCESS_STATUS A ON A.ACCESS_STATUS_KEY = F.ACCESS_STATUS_KEY
GROUP BY A.ACCESS_STATUS_NAME;

-- Venue output (grain: one row per venue)
CREATE VIEW IF NOT EXISTS PROJECT_REPORTING.VW_VENUE_OUTPUT AS
SELECT
  V.VENUE_NAME,
  V.SOURCE_NAME                    AS VENUE_SOURCE,
  COUNT(*)                         AS WORK_COUNT,
  SUM(F.CITED_BY_COUNT)            AS CITED_BY_TOTAL
FROM PROJECT_DW.FACT_PUBLICATION F
JOIN PROJECT_DW.DIM_VENUE V ON V.VENUE_KEY = F.VENUE_KEY
GROUP BY V.VENUE_NAME, V.SOURCE_NAME;

-- Citation graph health: unresolved vs resolved edges per source
CREATE VIEW IF NOT EXISTS PROJECT_REPORTING.VW_CITATION_RESOLUTION AS
SELECT
  SOURCE_NAME,
  COUNT(*)                                                 AS CITATION_EDGES,
  SUM(IFF(CITED_WORK_KEY IS NOT NULL AND CITED_WORK_KEY <> '', 1, 0)) AS RESOLVED_EDGES,
  SUM(IFF(CITED_WORK_KEY IS NULL OR CITED_WORK_KEY = '', 1, 0))       AS UNRESOLVED_EDGES
FROM PROJECT_DW.FACT_CITATION
GROUP BY SOURCE_NAME;

-- Ingest run history (grain: one row per run)
CREATE VIEW IF NOT EXISTS PROJECT_REPORTING.VW_INGEST_RUN_HISTORY AS
SELECT
  RUN_ID,
  MODE,
  STATUS,
  STARTED_AT,
  FINISHED_AT,
  SOURCE_STATUSES,
  RAW_ROWS,
  STAGING_ROWS,
  QUARANTINED_ROWS,
  WAREHOUSE_ROWS,
  RETRY_COUNT,
  QUALITY_GATE_RESULT,
  ERROR_SUMMARY
FROM PROJECT_OPS.ETL_RUN;

-- Source sync health: last success and failed attempts per stream
-- (grain: one row per source stream; operational freshness monitoring)
CREATE VIEW IF NOT EXISTS PROJECT_REPORTING.VW_SOURCE_SYNC_HEALTH AS
SELECT
  SOURCE_NAME,
  STREAM_NAME,
  STATUS,
  LAST_SUCCESSFUL_WATERMARK,
  LAST_SUCCESS_AT,
  LAST_ATTEMPT_AT,
  ERROR_CODE,
  DATEDIFF('hour', LAST_SUCCESS_AT, CURRENT_TIMESTAMP()) AS HOURS_SINCE_SUCCESS
FROM PROJECT_OPS.SOURCE_SYNC_STATE;

-- Quarantine review queue summary (grain: reason code x source)
CREATE VIEW IF NOT EXISTS PROJECT_REPORTING.VW_QUARANTINE_SUMMARY AS
SELECT
  SOURCE_NAME,
  REASON_CODE,
  COUNT(*)                                   AS OPEN_ITEMS,
  MIN(FIRST_SEEN_AT)                         AS OLDEST_ITEM_AT
FROM PROJECT_STAGING.STG_QUARANTINE
WHERE RESOLUTION_STATUS = 'open'
GROUP BY SOURCE_NAME, REASON_CODE;
