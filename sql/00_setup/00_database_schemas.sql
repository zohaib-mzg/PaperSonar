-- =============================================================================
-- Purpose: Create the PaperSonar Phase 2 database and the seven approved schemas.
-- Inputs: A role allowed to create databases (ACCOUNTADMIN during initial setup).
-- Outputs: PAPERSONAR, PROJECT_STAGING, PROJECT_BRONZE, PROJECT_SILVER,
--          PROJECT_DW, PROJECT_REPORTING, PROJECT_AUDIT, PROJECT_REF.
-- Idempotent: Yes - CREATE ... IF NOT EXISTS only; never CREATE OR REPLACE.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata operation only; no warehouse compute.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS PAPERSONAR
  COMMENT = 'PaperSonar research intelligence warehouse - Phase 2 strict ELT';

CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_STAGING
  COMMENT = 'Transient load boundary: VARIANT payload plus load metadata';

CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_BRONZE
  COMMENT = 'Permanent append-only source observations';

CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_SILVER
  COMMENT = 'Typed, standardized, deduplicated canonical records and crosswalk';

CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_DW
  COMMENT = 'Kimball star schema: dimensions, facts and bridges';

CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_REPORTING
  COMMENT = 'Read-only business views and publication registry access';

CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_AUDIT
  COMMENT = 'Batch lifecycle, manifest, watermark, DQ, quarantine and lineage';

CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_REF
  COMMENT = 'Taxonomy, keyword rules, expected keys and DQ rule reference data';
