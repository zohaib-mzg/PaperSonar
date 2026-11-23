-- =============================================================================
-- PaperSonar Public API - verification worksheet (ADDITIVE)
-- =============================================================================
-- Purpose: Verify that the public role can read approved views and not base tables.
-- Inputs: The VW_PUBLIC_* views created in 01_public_views.sql.
-- Outputs: Manual verification result sets; no persisted output.
-- Idempotent: Yes - SELECT and SHOW only.
-- Owner: PAPERSONAR_PUBLIC_RO for the first section; an administrator for the last.
-- Parameters: None.
-- Cost: small COUNT(*) scans over published public views.
-- Deploy: manual worksheet run after grants.
-- =============================================================================
-- Expected: approved views return rows; base-table queries fail.

USE ROLE PAPERSONAR_PUBLIC_RO;
USE WAREHOUSE WH_PAPERSONAR_PUBLIC;

SELECT COUNT(*) AS TOPIC_YEAR_ROWS
FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_YEAR;
SELECT COUNT(*) AS CITATION_ROWS
FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_CITATIONS;
SELECT COUNT(*) AS INTERSECTION_ROWS
FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_INTERSECTIONS;
SELECT COUNT(*) AS INSTITUTION_ROWS
FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_INSTITUTION_TOPIC;
SELECT COUNT(*) AS AUTHOR_ROWS
FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_AUTHOR_ACTIVITY;
SELECT COUNT(*) AS VENUE_ROWS
FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_VENUE_TOPIC;
SELECT COUNT(*) AS ACCESS_ROWS
FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_ACCESS_TOPIC;
SELECT COUNT(*) AS SEARCH_ROWS
FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_OUTPUT_SEARCH;
SELECT * FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_DATA_STATUS;
SELECT * FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_CORPUS_SUMMARY;

-- These must FAIL. If any succeeds, stop and revoke access.
-- SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_RESEARCH_OUTPUT;
-- SELECT COUNT(*) FROM PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK;
-- SELECT COUNT(*) FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT;

-- Administrative verification (run with an administrative role, not the app).
SHOW GRANTS TO ROLE PAPERSONAR_PUBLIC_RO;
SHOW GRANTS TO USER SVC_PAPERSONAR_PUBLIC;
DESC USER SVC_PAPERSONAR_PUBLIC;
