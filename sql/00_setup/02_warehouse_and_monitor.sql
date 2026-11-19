-- =============================================================================
-- Purpose: Create the single XS ELT warehouse and a resource monitor. Cost
--          controls must exist before any transformation compute is enabled.
-- Inputs: Administrative role.
-- Outputs: WH_PAPERSONAR_ELT, RM_PAPERSONAR_ELT and its monitor assignment.
-- Idempotent: Yes - creation is IF NOT EXISTS; ALTER is safe to repeat.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: CREDIT_QUOTA is a planning value. Adjust to the actual trial
--             balance before enabling scheduled runs.
-- Cost: XS compute only while a statement runs; auto-suspend is 60 seconds.
-- =============================================================================
-- VERIFY: confirm the actual trial credit balance, currency and resource-monitor
-- actions in the target account. Credit quotas are expressed in credits, not
-- dollars. Do not treat this planning value as the account's real balance.

CREATE WAREHOUSE IF NOT EXISTS WH_PAPERSONAR_ELT
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  STATEMENT_TIMEOUT_IN_SECONDS = 1800
  COMMENT = 'PaperSonar Phase 2 ELT compute - XS, bounded statements';

CREATE RESOURCE MONITOR IF NOT EXISTS RM_PAPERSONAR_ELT
  WITH CREDIT_QUOTA = 100
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 75 PERCENT DO NOTIFY
    ON 90 PERCENT DO SUSPEND
    ON 100 PERCENT DO SUSPEND_IMMEDIATE;

ALTER WAREHOUSE IF EXISTS WH_PAPERSONAR_ELT
  SET RESOURCE_MONITOR = RM_PAPERSONAR_ELT;
