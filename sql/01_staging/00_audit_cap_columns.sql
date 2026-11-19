-- =============================================================================
-- Purpose: Add the capped-window audit columns to existing deployments.
-- Inputs: PAPERSONAR.PROJECT_AUDIT schema from 00_setup.
-- Outputs: BATCH.IS_CAPPED and PUBLISHED_BATCH.IS_CAPPED.
-- Idempotent: Yes - ADD COLUMN IF NOT EXISTS is safe to redeploy.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata only; no table rebuild or backfill.
-- =============================================================================
-- The normal deployment skips 00_setup, so fresh columns must be added here as
-- well as in the one-time setup DDL. A TRUE value means the extractor stopped at
-- its configured max_records before the source window was exhausted. Publication
-- uses this flag to withhold watermark advancement.

ALTER TABLE PAPERSONAR.PROJECT_AUDIT.BATCH
  ADD COLUMN IF NOT EXISTS IS_CAPPED BOOLEAN DEFAULT FALSE;

ALTER TABLE PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH
  ADD COLUMN IF NOT EXISTS IS_CAPPED BOOLEAN DEFAULT FALSE;
