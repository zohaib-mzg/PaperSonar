-- =============================================================================
-- Purpose: Widen the text columns that DataCite records overflowed, so the
--          silver and dimension stages no longer abort a batch on a legitimate
--          long value. DataCite returns multi-valued publication dates
--          ("2022-05-23/2022-06-05/...") and free-text subject strings far
--          longer than the original widths.
-- Inputs: PROJECT_SILVER.SLV_SOURCE_OBSERVATION, PROJECT_STAGING.STG_DIM_TOPIC,
--         PROJECT_DW.DIM_TOPIC, PROJECT_DW.DIMENSION_KEY_MAP.
-- Outputs: Wider PUBLICATION_DATE_RAW, TOPIC_NAME, TOPIC_KEY and BUSINESS_KEY.
-- Idempotent: Yes - SET DATA TYPE to the same width is a no-op.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata-only column widening.
-- =============================================================================

ALTER TABLE IF EXISTS PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION
  ALTER COLUMN PUBLICATION_DATE_RAW SET DATA TYPE VARCHAR(4000);

ALTER TABLE IF EXISTS PAPERSONAR.PROJECT_STAGING.STG_DIM_TOPIC
  ALTER COLUMN TOPIC_NAME SET DATA TYPE VARCHAR(4000);

ALTER TABLE IF EXISTS PAPERSONAR.PROJECT_STAGING.STG_DIM_TOPIC
  ALTER COLUMN TOPIC_KEY SET DATA TYPE VARCHAR(1000);

ALTER TABLE IF EXISTS PAPERSONAR.PROJECT_DW.DIM_TOPIC
  ALTER COLUMN TOPIC_NAME SET DATA TYPE VARCHAR(4000);

ALTER TABLE IF EXISTS PAPERSONAR.PROJECT_DW.DIMENSION_KEY_MAP
  ALTER COLUMN BUSINESS_KEY SET DATA TYPE VARCHAR(1000);
