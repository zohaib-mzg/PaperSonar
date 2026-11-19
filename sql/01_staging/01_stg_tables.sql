-- =============================================================================
-- Purpose: Create the five transient staging tables. Each holds one VARIANT
--          payload plus file/row/batch metadata; no transformations occur here.
-- Inputs: PROJECT_STAGING schema.
-- Outputs: STG_OPENALEX_WORK, STG_CROSSREF_WORK, STG_ARXIV_RECORD,
--          STG_DATACITE_DOI, STG_ZENODO_RECORD.
-- Idempotent: Yes - CREATE TABLE IF NOT EXISTS only.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata only; tables are transient and reloadable from the raw stage.
-- =============================================================================
-- No INFER_SCHEMA is used anywhere. The JSON file format is explicit and every
-- table below has an explicit VARIANT plus metadata contract.

CREATE TRANSIENT TABLE IF NOT EXISTS PAPERSONAR.PROJECT_STAGING.STG_OPENALEX_WORK (
  PAYLOAD         VARIANT       NOT NULL,
  FILE_NAME       VARCHAR(1000),
  FILE_ROW_NUMBER NUMBER(38,0),
  BATCH_ID        VARCHAR(64),
  LOADED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw OpenAlex work objects exactly as returned by the API';

CREATE TRANSIENT TABLE IF NOT EXISTS PAPERSONAR.PROJECT_STAGING.STG_CROSSREF_WORK (
  PAYLOAD         VARIANT       NOT NULL,
  FILE_NAME       VARCHAR(1000),
  FILE_ROW_NUMBER NUMBER(38,0),
  BATCH_ID        VARCHAR(64),
  LOADED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw Crossref work items exactly as returned by the API';

CREATE TRANSIENT TABLE IF NOT EXISTS PAPERSONAR.PROJECT_STAGING.STG_ARXIV_RECORD (
  PAYLOAD         VARIANT       NOT NULL,
  FILE_NAME       VARCHAR(1000),
  FILE_ROW_NUMBER NUMBER(38,0),
  BATCH_ID        VARCHAR(64),
  LOADED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw arXiv OAI record envelope with metadata XML preserved';

CREATE TRANSIENT TABLE IF NOT EXISTS PAPERSONAR.PROJECT_STAGING.STG_DATACITE_DOI (
  PAYLOAD         VARIANT       NOT NULL,
  FILE_NAME       VARCHAR(1000),
  FILE_ROW_NUMBER NUMBER(38,0),
  BATCH_ID        VARCHAR(64),
  LOADED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw DataCite JSON:API DOI objects';

CREATE TRANSIENT TABLE IF NOT EXISTS PAPERSONAR.PROJECT_STAGING.STG_ZENODO_RECORD (
  PAYLOAD         VARIANT       NOT NULL,
  FILE_NAME       VARCHAR(1000),
  FILE_ROW_NUMBER NUMBER(38,0),
  BATCH_ID        VARCHAR(64),
  LOADED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw Zenodo OAI record envelope with DataCite XML preserved';

CREATE TRANSIENT TABLE IF NOT EXISTS PAPERSONAR.PROJECT_STAGING.STG_OUTPUT_CATEGORY (
  BATCH_ID          VARCHAR(64)  NOT NULL,
  OUTPUT_BK         VARCHAR(300) NOT NULL,
  CATEGORY_KEY      VARCHAR(80)  NOT NULL,
  SCORE             NUMBER(18,4) DEFAULT 0,
  CATEGORY_RANK     NUMBER(38,0),
  IS_PRIMARY        BOOLEAN DEFAULT FALSE,
  METHOD            VARCHAR(20),
  TAXONOMY_VERSION  VARCHAR(20),
  CREATED_AT        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Rule-scored/override category assignments awaiting dimensional load';
