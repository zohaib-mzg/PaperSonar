-- =============================================================================
-- Purpose: Create the five bronze current-state tables. Bronze is the
--          source-of-truth layer: raw payload plus latest-observation provenance.
-- Inputs: PROJECT_BRONZE schema.
-- Outputs: BRZ_OPENALEX_WORK, BRZ_CROSSREF_WORK, BRZ_ARXIV_RECORD,
--          BRZ_DATACITE_DOI, BRZ_ZENODO_RECORD.
-- Idempotent: Yes - CREATE TABLE IF NOT EXISTS only.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata only. One row per source record id.
-- =============================================================================
-- Bronze is current-state, keyed by (source, entity, source record id). A
-- re-observed payload updates the existing row in place; historical versions
-- remain evidenced by BATCH_MANIFEST and LINEAGE_EVENT.

CREATE TABLE IF NOT EXISTS PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK (
  SOURCE_NAME      VARCHAR(50)   NOT NULL,
  ENTITY_NAME      VARCHAR(50)   NOT NULL,
  SOURCE_RECORD_ID VARCHAR(1000) NOT NULL,
  BATCH_ID         VARCHAR(64)   NOT NULL,
  WINDOW_START     DATE,
  WINDOW_END       DATE,
  RECORD_HASH      VARCHAR(64)   NOT NULL,
  CHECKSUM         VARCHAR(64),
  INGESTED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
  FILE_NAME        VARCHAR(1000),
  PAYLOAD          VARIANT       NOT NULL
)
COMMENT = 'Current-state OpenAlex work observations, one row per work id';

CREATE TABLE IF NOT EXISTS PAPERSONAR.PROJECT_BRONZE.BRZ_CROSSREF_WORK (
  SOURCE_NAME      VARCHAR(50)   NOT NULL,
  ENTITY_NAME      VARCHAR(50)   NOT NULL,
  SOURCE_RECORD_ID VARCHAR(1000) NOT NULL,
  BATCH_ID         VARCHAR(64)   NOT NULL,
  WINDOW_START     DATE,
  WINDOW_END       DATE,
  RECORD_HASH      VARCHAR(64)   NOT NULL,
  CHECKSUM         VARCHAR(64),
  INGESTED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
  FILE_NAME        VARCHAR(1000),
  PAYLOAD          VARIANT       NOT NULL
)
COMMENT = 'Current-state Crossref work observations, one row per DOI/URL';

CREATE TABLE IF NOT EXISTS PAPERSONAR.PROJECT_BRONZE.BRZ_ARXIV_RECORD (
  SOURCE_NAME      VARCHAR(50)   NOT NULL,
  ENTITY_NAME      VARCHAR(50)   NOT NULL,
  SOURCE_RECORD_ID VARCHAR(1000) NOT NULL,
  BATCH_ID         VARCHAR(64)   NOT NULL,
  WINDOW_START     DATE,
  WINDOW_END       DATE,
  RECORD_HASH      VARCHAR(64)   NOT NULL,
  CHECKSUM         VARCHAR(64),
  INGESTED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
  FILE_NAME        VARCHAR(1000),
  PAYLOAD          VARIANT       NOT NULL
)
COMMENT = 'Current-state arXiv OAI records; metadata XML preserved in PAYLOAD';

CREATE TABLE IF NOT EXISTS PAPERSONAR.PROJECT_BRONZE.BRZ_DATACITE_DOI (
  SOURCE_NAME      VARCHAR(50)   NOT NULL,
  ENTITY_NAME      VARCHAR(50)   NOT NULL,
  SOURCE_RECORD_ID VARCHAR(1000) NOT NULL,
  BATCH_ID         VARCHAR(64)   NOT NULL,
  WINDOW_START     DATE,
  WINDOW_END       DATE,
  RECORD_HASH      VARCHAR(64)   NOT NULL,
  CHECKSUM         VARCHAR(64),
  INGESTED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
  FILE_NAME        VARCHAR(1000),
  PAYLOAD          VARIANT       NOT NULL
)
COMMENT = 'Current-state DataCite DOI observations, one row per DOI';

CREATE TABLE IF NOT EXISTS PAPERSONAR.PROJECT_BRONZE.BRZ_ZENODO_RECORD (
  SOURCE_NAME      VARCHAR(50)   NOT NULL,
  ENTITY_NAME      VARCHAR(50)   NOT NULL,
  SOURCE_RECORD_ID VARCHAR(1000) NOT NULL,
  BATCH_ID         VARCHAR(64)   NOT NULL,
  WINDOW_START     DATE,
  WINDOW_END       DATE,
  RECORD_HASH      VARCHAR(64)   NOT NULL,
  CHECKSUM         VARCHAR(64),
  INGESTED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
  FILE_NAME        VARCHAR(1000),
  PAYLOAD          VARIANT       NOT NULL
)
COMMENT = 'Current-state Zenodo OAI records; DataCite XML preserved in PAYLOAD';
