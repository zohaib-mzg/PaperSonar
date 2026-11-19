-- =============================================================================
-- Purpose: Create topic and category dimensions. Both are Type 1; topic history
--          is available through bronze/silver observations, so SCD2 is not
--          justified for the reporting grain.
-- Inputs: PROJECT_DW and PROJECT_REF schemas.
-- Outputs: DIM_TOPIC, DIM_CATEGORY.
-- Idempotent: Yes - CREATE TABLE IF NOT EXISTS only.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: Metadata only.
-- =============================================================================

CREATE TABLE IF NOT EXISTS PAPERSONAR.PROJECT_DW.DIM_TOPIC (
  TOPIC_SK    NUMBER(38,0)  NOT NULL,
  TOPIC_KEY   VARCHAR(500)  NOT NULL,
  SOURCE_NAME VARCHAR(50),
  TOPIC_ID    VARCHAR(200),
  TOPIC_NAME  VARCHAR(500),
  IS_UNKNOWN  BOOLEAN DEFAULT FALSE,
  CONSTRAINT PK_DIM_TOPIC PRIMARY KEY (TOPIC_SK)
)
COMMENT = 'Source topics/keywords normalized to stable business keys';

CREATE TABLE IF NOT EXISTS PAPERSONAR.PROJECT_DW.DIM_CATEGORY (
  CATEGORY_SK      NUMBER(38,0) NOT NULL,
  CATEGORY_KEY     VARCHAR(80)  NOT NULL,
  LABEL            VARCHAR(200),
  PARENT_KEY       VARCHAR(80),
  TAXONOMY_VERSION VARCHAR(20),
  IS_UNKNOWN       BOOLEAN DEFAULT FALSE,
  CONSTRAINT PK_DIM_CATEGORY PRIMARY KEY (CATEGORY_SK)
)
COMMENT = 'Internal taxonomy dimension; seeded from PROJECT_REF.REF_CATEGORY';
