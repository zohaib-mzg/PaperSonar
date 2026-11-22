-- =============================================================================
-- PaperSonar - account housekeeping (ADMINISTRATIVE, RUN BY HAND)
-- =============================================================================
-- Purpose: Close the abandoned batch, stop the service user from running with
--          administrative rights by default, and remove the two warehouses the
--          project does not use, so the trial credits are only spent on
--          WH_PAPERSONAR_ELT.
-- Inputs: PROJECT_AUDIT.BATCH, PROJECT_AUDIT.DQ_RESULT, account users, roles
--         and warehouses.
-- Outputs: one batch row moved to FAILED, the stale DQ rows of that batch
--          removed, the service user defaults changed, PAPERSONAR_WH dropped
--          and COMPUTE_WH suspended.
-- Idempotent: Yes - every statement is written so that running it twice
--             changes nothing the second time.
-- Owner: PAPERSONAR_ADMIN (or ACCOUNTADMIN for the account-level objects).
-- Parameters: none.
-- Cost: no warehouse time beyond the metadata statements.
-- Deploy: manual - administrative statements, never run by the deployment
--         client. sql/00_setup is skipped by the deployment client anyway.
-- =============================================================================
-- Run the statements in the order below. Read the comment above each one
-- before running it: two of them change access rights.

-- ---------------------------------------------------------------------------
-- 1. Close the abandoned Crossref batch.
--
-- BATCH_70CEE97747ED6A70D3E40411 stopped in EXTRACTING on 2026-11-20 with
-- four manifest file mismatches (DQ-001). It was never transformed and never
-- published, but it still sits in the batch table as an open work item and
-- its stale DQ-009 result still shows a PASS from 2026-11-20, which would
-- misreport a batch that never had a category. Closing it removes the false
-- signal from every batch report.
-- ---------------------------------------------------------------------------
UPDATE PAPERSONAR.PROJECT_AUDIT.BATCH
   SET STATUS = 'FAILED',
       FINISHED_AT = CURRENT_TIMESTAMP(),
       ERROR_SUMMARY = 'Manual close: extraction stopped with four manifest file '
                       || 'mismatches (DQ-001); the batch was never transformed '
                       || 'and was never published',
       UPDATED_AT = CURRENT_TIMESTAMP()
 WHERE BATCH_ID = 'BATCH_70CEE97747ED6A70D3E40411'
   AND STATUS = 'EXTRACTING';

DELETE FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
 WHERE BATCH_ID = 'BATCH_70CEE97747ED6A70D3E40411';

-- Verification
SELECT BATCH_ID, SOURCE_NAME, STATUS, ERROR_SUMMARY, FINISHED_AT
FROM PAPERSONAR.PROJECT_AUDIT.BATCH
WHERE BATCH_ID = 'BATCH_70CEE97747ED6A70D3E40411';

-- ---------------------------------------------------------------------------
-- 2. Make the service user boring by default.
--
-- The default role and default warehouse of a user apply to every session
-- that does not set them. A service user that defaults to an administrative
-- role and to a running warehouse is the opposite of boring.
-- ---------------------------------------------------------------------------
ALTER USER SVC_PAPERSONAR SET DEFAULT_ROLE = 'PAPERSONAR_LOADER';
ALTER USER SVC_PAPERSONAR SET DEFAULT_WAREHOUSE = 'WH_PAPERSONAR_ELT';

-- ---------------------------------------------------------------------------
-- 3. Decide about the administrative grant. READ THIS BEFORE RUNNING.
--
-- The deployment workflow logs in as the secret SNOWFLAKE_USER and assumes
-- the secret SNOWFLAKE_DEPLOY_ROLE, which is PAPERSONAR_ADMIN. If that login
-- user is SVC_PAPERSONAR, revoking PAPERSONAR_ADMIN from it stops every
-- deployment from working.
--
-- Run this first and read the grantee names:
--
--   SHOW GRANTS OF ROLE PAPERSONAR_ADMIN;
--
-- 3a. SVC_PAPERSONAR is NOT the deployment user -> revoke the grant:
--
-- REVOKE ROLE PAPERSONAR_ADMIN FROM USER SVC_PAPERSONAR;
--
-- 3b. SVC_PAPERSONAR IS the deployment user -> do NOT revoke. The grant has
--     to stay for the pipeline to run, and step 2 is then the whole
--     least-privilege improvement that is possible without a second login
--     user. Record the decision in docs/phase2/IMPLEMENTATION_STATUS.md.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 4. Remove the unused warehouse and stop the account default one.
--
-- PAPERSONAR_WH was created in Phase 1 and superseded by WH_PAPERSONAR_ELT;
-- nothing references it. COMPUTE_WH is the Snowflake account default
-- warehouse: the project never uses it, but it was left running by the
-- account provisioning and it consumes credits while it is running.
-- ---------------------------------------------------------------------------
DROP WAREHOUSE IF EXISTS PAPERSONAR_WH;

ALTER WAREHOUSE COMPUTE_WH SUSPEND;

-- Verification
SHOW WAREHOUSES;

-- ---------------------------------------------------------------------------
-- 5. Final check.
-- ---------------------------------------------------------------------------
SELECT BATCH_ID, SOURCE_NAME, STATUS
FROM PAPERSONAR.PROJECT_AUDIT.BATCH
ORDER BY CREATED_AT;

SHOW GRANTS OF ROLE PAPERSONAR_ADMIN;
