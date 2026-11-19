-- =============================================================================
-- Purpose: Widen silver title columns. Source titles can reach OpenAlex's
--          5,000-character cap; the original VARCHAR(4000) definition made the
--          silver insert fail instead of storing the record.
-- Inputs: PROJECT_SILVER.SLV_SOURCE_OBSERVATION, SLV_RESEARCH_OUTPUT.
-- Outputs: Wider TITLE_RAW, TITLE_NORMALIZED and TITLE columns.
-- Idempotent: Yes - SET DATA TYPE to the same width is a no-op.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata-only column widening.
-- =============================================================================

ALTER TABLE IF EXISTS PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION
  ALTER COLUMN TITLE_RAW SET DATA TYPE VARCHAR(16000);

ALTER TABLE IF EXISTS PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION
  ALTER COLUMN TITLE_NORMALIZED SET DATA TYPE VARCHAR(16000);

ALTER TABLE IF EXISTS PAPERSONAR.PROJECT_SILVER.SLV_RESEARCH_OUTPUT
  ALTER COLUMN TITLE SET DATA TYPE VARCHAR(16000);
