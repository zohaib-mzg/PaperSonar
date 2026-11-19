-- =============================================================================
-- Purpose: Define the explicit JSON file format and internal stages used for raw
--          gzip NDJSON payloads and versioned SQL deployment.
-- Inputs: PAPERSONAR database and PROJECT_STAGING schema.
-- Outputs: FF_NDJSON_GZ, RAW_STAGE, SQL_STAGE.
-- Idempotent: Yes - CREATE ... IF NOT EXISTS.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata only; storage is billed by staged bytes.
-- =============================================================================
-- VERIFY: confirm current COPY/JSON file-format options and internal-stage
-- behaviour against https://docs.snowflake.com/en/sql-reference/sql/create-file-format

CREATE FILE FORMAT IF NOT EXISTS PAPERSONAR.PROJECT_STAGING.FF_NDJSON_GZ
  TYPE = JSON
  COMPRESSION = GZIP
  STRIP_OUTER_ARRAY = FALSE
  STRIP_NULL_VALUES = FALSE
  REPLACE_INVALID_CHARACTERS = FALSE
  IGNORE_UTF8_ERRORS = FALSE
  COMMENT = 'One JSON object per line, gzip-compressed, no schema inference';

CREATE STAGE IF NOT EXISTS PAPERSONAR.PROJECT_STAGING.RAW_STAGE
  FILE_FORMAT = PAPERSONAR.PROJECT_STAGING.FF_NDJSON_GZ
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Immutable raw extraction payloads (gzip NDJSON)';

CREATE STAGE IF NOT EXISTS PAPERSONAR.PROJECT_STAGING.SQL_STAGE
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Versioned SQL deployment files executed with EXECUTE IMMEDIATE FROM';

-- The format and stages are account-level setup objects. Grant access so a
-- deploy or task-owner role other than their creator can use them.
GRANT USAGE ON FILE FORMAT PAPERSONAR.PROJECT_STAGING.FF_NDJSON_GZ
  TO ROLE PAPERSONAR_ADMIN;
GRANT USAGE ON FILE FORMAT PAPERSONAR.PROJECT_STAGING.FF_NDJSON_GZ
  TO ROLE PAPERSONAR_LOADER;
GRANT USAGE ON FILE FORMAT PAPERSONAR.PROJECT_STAGING.FF_NDJSON_GZ
  TO ROLE PAPERSONAR_TRANSFORMER;
