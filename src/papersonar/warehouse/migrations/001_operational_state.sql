-- 001_operational_state.sql
-- PaperSonar Phase 2 operational state and staging.
-- Non-destructive: every object uses IF NOT EXISTS. Never resets shared environments.
-- Raw payloads are stored durably in the internal stage PROJECT_OPS.RAW_STAGE
-- (GitHub runner disk is never the sole raw copy); metadata/checksums live in
-- PROJECT_OPS.RAW_BATCH. Schemas follow the course contract:
-- project_staging / project_dw / project_reporting, plus PROJECT_OPS.

CREATE SCHEMA IF NOT EXISTS PROJECT_OPS;
CREATE SCHEMA IF NOT EXISTS PROJECT_STAGING;
CREATE SCHEMA IF NOT EXISTS PROJECT_DW;
CREATE SCHEMA IF NOT EXISTS PROJECT_REPORTING;

CREATE STAGE IF NOT EXISTS PROJECT_OPS.RAW_STAGE
  COMMENT = 'Immutable raw source payloads (append-only, checksummed in PROJECT_OPS.RAW_BATCH)';

-- ---------------------------------------------------------------------------
-- Runs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PROJECT_OPS.ETL_RUN (
  RUN_ID              STRING        NOT NULL,
  MODE                STRING        NOT NULL, -- backfill|sync|validate|load|full|replay
  STARTED_AT          TIMESTAMP_TZ  NOT NULL,
  FINISHED_AT         TIMESTAMP_TZ,
  STATUS              STRING        NOT NULL, -- started|succeeded|partial|failed|cancelled
  GIT_COMMIT          STRING,
  CONFIG_CHECKSUM     STRING,
  CODE_VERSION        STRING,
  SOURCE_STATUSES     VARIANT,
  RAW_ROWS            NUMBER DEFAULT 0,
  STAGING_ROWS        NUMBER DEFAULT 0,
  QUARANTINED_ROWS    NUMBER DEFAULT 0,
  WAREHOUSE_ROWS      NUMBER DEFAULT 0,
  RETRY_COUNT         NUMBER DEFAULT 0,
  QUALITY_GATE_RESULT STRING,
  ERROR_SUMMARY       STRING,
  CONSTRAINT PK_ETL_RUN PRIMARY KEY (RUN_ID)
)
COMMENT = 'One ETL/pipeline execution. Statuses: started, succeeded, partial, failed, cancelled.';

-- ---------------------------------------------------------------------------
-- Per-source incremental state (independent watermarks; never shared)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PROJECT_OPS.SOURCE_SYNC_STATE (
  SOURCE_NAME              STRING        NOT NULL,
  STREAM_NAME              STRING        NOT NULL, -- partition/stream/window id
  SYNC_MODE                STRING,               -- backfill|sync|reconciliation
  WINDOW_START             STRING,
  WINDOW_END               STRING,
  CURSOR_OR_TOKEN          STRING,               -- in-progress pagination state (run-scoped)
  LAST_SUCCESSFUL_WATERMARK STRING,
  LAST_ATTEMPT_AT          TIMESTAMP_TZ,
  LAST_SUCCESS_AT          TIMESTAMP_TZ,
  LAST_RUN_ID              STRING,
  STATUS                   STRING,               -- idle|running|succeeded|partial|failed
  PAGES_COMPLETED          NUMBER DEFAULT 0,
  RECORDS_SEEN             NUMBER DEFAULT 0,
  RECORDS_WRITTEN          NUMBER DEFAULT 0,
  RECORDS_QUARANTINED      NUMBER DEFAULT 0,
  ERROR_CODE               STRING,
  ERROR_SUMMARY            STRING,
  CONFIG_CHECKSUM          STRING,
  UPDATED_AT               TIMESTAMP_TZ,
  CONSTRAINT PK_SOURCE_SYNC_STATE PRIMARY KEY (SOURCE_NAME, STREAM_NAME)
)
COMMENT = 'Durable per-source/per-stream checkpoint. Watermark advances only after a complete, validated window.';

-- ---------------------------------------------------------------------------
-- Raw batch registry (payload bytes live in PROJECT_OPS.RAW_STAGE)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PROJECT_OPS.RAW_BATCH (
  BATCH_ID            STRING        NOT NULL,
  RUN_ID              STRING        NOT NULL,
  SOURCE_NAME         STRING        NOT NULL,
  STREAM_NAME         STRING,
  WINDOW_START        STRING,
  WINDOW_END          STRING,
  PAGE_SEQ            NUMBER,
  PAGE_CURSOR         STRING,
  RETRIEVED_AT_UTC    TIMESTAMP_TZ  NOT NULL,
  HTTP_STATUS         NUMBER,
  PAYLOAD_STAGE_PATH  STRING        NOT NULL,
  PAYLOAD_SHA256      STRING        NOT NULL,
  RECORDS_SEEN        NUMBER,
  PARSER_VERSION      STRING        NOT NULL,
  SCHEMA_VERSION      STRING        NOT NULL,
  COMPLETE            BOOLEAN       DEFAULT FALSE,
  REQUEST_DESCRIPTOR  VARIANT,
  CONSTRAINT PK_RAW_BATCH PRIMARY KEY (BATCH_ID)
)
COMMENT = 'Append-only raw batch registry. A batch is COMPLETE only after every page is durable and validated.';

-- ---------------------------------------------------------------------------
-- Staging: one row per source-record content version (history preserved)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PROJECT_STAGING.STG_WORK_RECORD (
  STAGING_ID         STRING        NOT NULL,
  RUN_ID             STRING        NOT NULL,
  BATCH_ID           STRING        NOT NULL,
  SOURCE_NAME        STRING        NOT NULL,
  SOURCE_RECORD_ID   STRING        NOT NULL,
  SOURCE_UPDATED_AT  TIMESTAMP_TZ,
  DOI_RAW            STRING,
  DOI_NORMALIZED     STRING,
  TITLE              STRING,
  TITLE_NORMALIZED   STRING,
  PUBLICATION_DATE   DATE,
  PUBLICATION_YEAR   NUMBER,
  WORK_TYPE          STRING,
  VENUE_NAME         STRING,
  OA_IS_OA           BOOLEAN,
  OA_STATUS          STRING,
  CITED_BY_COUNT     NUMBER,
  REFERENCED_WORKS   ARRAY,
  TOPICS             ARRAY,
  AUTHORSHIPS        ARRAY,
  RELATED_IDENTIFIERS ARRAY,
  PAYLOAD_SHA256     STRING        NOT NULL,
  PARSER_VERSION     STRING        NOT NULL,
  SCHEMA_VERSION     STRING        NOT NULL,
  VALIDATION_STATUS  STRING        NOT NULL, -- accepted|quarantined
  VALIDATION_REASON  STRING,
  INGESTED_AT        TIMESTAMP_TZ  NOT NULL,
  CONSTRAINT PK_STG_WORK_RECORD PRIMARY KEY (SOURCE_NAME, SOURCE_RECORD_ID, PAYLOAD_SHA256)
)
COMMENT = 'Source-record content versions. Same content re-upserts in place; changed content appends a new version.';

-- ---------------------------------------------------------------------------
-- Quarantine: rejected/conflicting records with stable reason codes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PROJECT_STAGING.STG_QUARANTINE (
  QUARANTINE_ID     STRING        NOT NULL,
  RUN_ID            STRING        NOT NULL,
  BATCH_ID          STRING,
  SOURCE_NAME       STRING        NOT NULL,
  SOURCE_RECORD_ID  STRING,
  REASON_CODE       STRING        NOT NULL, -- missing_source_id|invalid_date|malformed_identifier|conflicting_doi|...
  DETAIL            STRING,
  FIRST_SEEN_AT     TIMESTAMP_TZ  NOT NULL,
  LAST_SEEN_AT      TIMESTAMP_TZ  NOT NULL,
  RESOLUTION_STATUS STRING        NOT NULL DEFAULT 'open', -- open|resolved|accepted|discarded
  CONSTRAINT PK_STG_QUARANTINE PRIMARY KEY (QUARANTINE_ID)
)
COMMENT = 'Quarantined records. Never silently discarded; reason codes are queryable.';
