-- =============================================================================
-- Purpose: Add the DQ_RESULT.NOTE column that records why a rule was skipped.
-- Inputs: PROJECT_AUDIT.DQ_RESULT.
-- Outputs: NOTE column (VARCHAR) on DQ_RESULT.
-- Idempotent: Yes - ADD COLUMN IF NOT EXISTS.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata only.
-- =============================================================================
-- A re-categorization run does not re-process the raw ingestion layer, so the
-- ingestion reconciliation rules (DQ-001, DQ-002) cannot be evaluated again.
-- They are recorded as SKIPPED with this note instead of being reported as
-- failures, and the note keeps the reason visible in the DQ evidence.

ALTER TABLE PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
  ADD COLUMN IF NOT EXISTS NOTE VARCHAR(1000);

COMMENT ON COLUMN PAPERSONAR.PROJECT_AUDIT.DQ_RESULT.NOTE IS
  'Reason a rule was skipped, or NULL when the rule was evaluated';
