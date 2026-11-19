-- =============================================================================
-- Purpose: Create the SCD2 author dimension and the Type 1 institution
--          dimension. Author history is justified by affiliation/name changes.
-- Inputs: PROJECT_DW schema.
-- Outputs: SEQ_AUTHOR_SK, DIM_AUTHOR, DIM_INSTITUTION.
-- Idempotent: Yes - CREATE ... IF NOT EXISTS only.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata only.
-- =============================================================================
-- A new DIM_AUTHOR row is inserted only when the current hash changes. Facts
-- join the current row (IS_CURRENT = TRUE); history remains queryable.

CREATE SEQUENCE IF NOT EXISTS PAPERSONAR.PROJECT_DW.SEQ_AUTHOR_SK
  START = 1 INCREMENT = 1
  COMMENT = 'Surrogate key sequence for DIM_AUTHOR SCD2 versions';

CREATE TABLE IF NOT EXISTS PAPERSONAR.PROJECT_DW.DIM_AUTHOR (
  AUTHOR_SK       NUMBER(38,0) NOT NULL,
  AUTHOR_KEY      VARCHAR(500) NOT NULL,
  AUTHOR_NAME     VARCHAR(500),
  ORCID           VARCHAR(200),
  HASH_DIFF       VARCHAR(64),
  EFFECTIVE_FROM  TIMESTAMP_NTZ NOT NULL,
  EFFECTIVE_TO    TIMESTAMP_NTZ,
  IS_CURRENT      BOOLEAN NOT NULL DEFAULT TRUE,
  VERSION         NUMBER(38,0) NOT NULL DEFAULT 1,
  CONSTRAINT PK_DIM_AUTHOR PRIMARY KEY (AUTHOR_SK)
)
COMMENT = 'SCD2 author dimension; one current row per AUTHOR_KEY';

CREATE TABLE IF NOT EXISTS PAPERSONAR.PROJECT_DW.DIM_INSTITUTION (
  INSTITUTION_SK   NUMBER(38,0) NOT NULL,
  INSTITUTION_KEY  VARCHAR(500) NOT NULL,
  INSTITUTION_NAME VARCHAR(1000),
  COUNTRY_CODE     VARCHAR(10),
  IS_UNKNOWN       BOOLEAN DEFAULT FALSE,
  CONSTRAINT PK_DIM_INSTITUTION PRIMARY KEY (INSTITUTION_SK)
)
COMMENT = 'Type 1 institution dimension from source affiliation metadata';
