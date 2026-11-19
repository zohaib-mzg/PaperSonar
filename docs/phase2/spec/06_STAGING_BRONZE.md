# Staging and Bronze Layer

## Staging contract
Staging is a transient load boundary. Each source/entity table contains a `VARIANT` payload plus load metadata. Define explicit JSON file formats and explicit table DDL. Do not use `INFER_SCHEMA`.

Example column contract:
| Column | Type | Purpose |
|---|---|---|
| `PAYLOAD` | VARIANT | Raw JSON object |
| `FILE_NAME` | VARCHAR | Source filename |
| `FILE_ROW_NUMBER` | NUMBER | Row position in file |
| `BATCH_ID` | VARCHAR | Batch lineage |
| `LOADED_AT` | TIMESTAMP_NTZ | UTC load timestamp |

Use an explicit JSON file format configured for NDJSON records. Validate how blank lines, malformed JSON, and oversized records are handled. Set COPY options deliberately and preserve load errors in audit.

Illustrative COPY skeleton:
```sql
-- Purpose: Load one registered source batch to staging.
-- Inputs: BATCH_ID and registered stage filenames.
-- Outputs: STG_<SOURCE>_<ENTITY>.
-- Idempotent: COPY behavior plus batch/file ledger; validate on rerun.
-- Owner: PAPERSONAR_TRANSFORMER.
-- Parameters: fixed source/entity and validated batch ID.
-- Cost: Warehouse compute; avoid duplicate file scans.
COPY INTO PAPERSONAR.PROJECT_STAGING.STG_OPENALEX_WORK
  (PAYLOAD, FILE_NAME, FILE_ROW_NUMBER, BATCH_ID, LOADED_AT)
FROM (
  SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER,
         '<validated-batch-id>', CURRENT_TIMESTAMP()::TIMESTAMP_NTZ
  FROM @PAPERSONAR.PROJECT_STAGING.RAW_STAGE
)
FILE_FORMAT = (FORMAT_NAME = PAPERSONAR.PROJECT_STAGING.FF_NDJSON)
ON_ERROR = 'ABORT_STATEMENT';
```
This is a pattern, not final executable SQL: use a fixed, validated file path/pattern per batch and verify COPY metadata-column syntax and parameterization against current Snowflake documentation. Do not interpolate arbitrary user input.

## Bronze contract
Bronze is permanent and current-state, keyed by (source, entity, source record id). Required metadata:
`SOURCE_NAME`, `ENTITY_NAME`, `SOURCE_RECORD_ID`, `BATCH_ID`, `WINDOW_START`, `WINDOW_END`, `RECORD_HASH`, `CHECKSUM`, `INGESTED_AT`, `FILE_NAME`, and raw `PAYLOAD`.

Store source payload without business transformations. `RECORD_HASH` must be deterministic over a documented canonical serialization of the raw object. Do not assume arbitrary JSON object key order is stable; define canonicalization in the extractor or compute a consistent hash in SQL. Python may calculate a checksum for file integrity, but may not alter the payload.

## Current-state MERGE
Bronze is a current-state table, not an append-only log. Deduplicate every MERGE
source to one row per `(SOURCE_NAME, ENTITY_NAME, SOURCE_RECORD_ID)` using a
deterministic `ROW_NUMBER()` ordered by file and row number. Re-fetched work
updates the existing row in place; it does not create a second observation.

```sql
MERGE INTO PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK t
USING (
  SELECT
    'OPENALEX' AS SOURCE_NAME,
    'WORK' AS ENTITY_NAME,
    REGEXP_REPLACE(s.PAYLOAD:id::STRING, '^https?://openalex[.]org/', '') AS SOURCE_RECORD_ID,
    s.BATCH_ID, b.WINDOW_START, b.WINDOW_END,
    SHA2(TO_JSON(s.PAYLOAD), 256) AS RECORD_HASH,
    m.CHECKSUM, s.FILE_NAME, s.PAYLOAD
  FROM PAPERSONAR.PROJECT_STAGING.STG_OPENALEX_WORK s
  JOIN PAPERSONAR.PROJECT_AUDIT.BATCH b ON b.BATCH_ID = s.BATCH_ID
  LEFT JOIN PAPERSONAR.PROJECT_AUDIT.BATCH_MANIFEST m
    ON m.BATCH_ID = s.BATCH_ID AND m.FILE_NAME = s.FILE_NAME
  WHERE s.BATCH_ID = :batch_id
    AND COALESCE(s.PAYLOAD:id::STRING, '') <> ''
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY REGEXP_REPLACE(s.PAYLOAD:id::STRING, '^https?://openalex[.]org/', '')
    ORDER BY s.FILE_NAME DESC, s.FILE_ROW_NUMBER DESC
  ) = 1
) s
ON t.SOURCE_NAME = s.SOURCE_NAME
AND t.ENTITY_NAME = s.ENTITY_NAME
AND t.SOURCE_RECORD_ID = s.SOURCE_RECORD_ID
WHEN MATCHED THEN UPDATE SET t.BATCH_ID = s.BATCH_ID,
  t.WINDOW_START = s.WINDOW_START, t.WINDOW_END = s.WINDOW_END,
  t.RECORD_HASH = s.RECORD_HASH, t.CHECKSUM = s.CHECKSUM,
  t.FILE_NAME = s.FILE_NAME, t.PAYLOAD = s.PAYLOAD,
  t.INGESTED_AT = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (...);
```
The snippet is a pattern: create the explicit metadata/hash projection and target
column list for each source table. Do not copy ellipses into executable SQL.
DQ-002 reconciles bronze observations to distinct staged
`(SOURCE_NAME, RECORD_KEY)` values, not to `RECORD_HASH`, so a re-fetch with
changed content is still one current-state observation.

COPY load history is an additional duplicate guard, not the long-term idempotency guarantee. `VERIFY:` confirm current Snowflake load-history retention and the often-cited 64-day behavior for the exact loading method.

## Schema drift
Compare payload object keys with the explicit expected-key reference for each source/entity. Log new and missing keys to `PROJECT_AUDIT.SCHEMA_DRIFT_LOG` with source, entity, batch, key name, drift type, and first-seen time. Missing optional fields are not automatically failures; required-field loss can fail the batch.

## Acceptance
- Explicit table DDL and file formats exist.
- No schema inference is used.
- Raw payload remains unchanged.
- Repeated COPY/MERGE does not duplicate logical observations.
- Drift is logged.
- Malformed/oversized rows are not silently discarded.
- Bronze history is preserved across full loads.

## References
- COPY INTO: https://docs.snowflake.com/en/sql-reference/sql/copy-into-table
- Semi-structured data: https://docs.snowflake.com/en/user-guide/semistructured-intro
- Query metadata: https://docs.snowflake.com/en/sql-reference/metadata
- MERGE: https://docs.snowflake.com/en/sql-reference/sql/merge
- QUALIFY: https://docs.snowflake.com/en/sql-reference/constructs/qualify
