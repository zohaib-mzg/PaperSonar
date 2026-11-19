# Audit, Metadata, and Lineage

## Required audit tables
Define explicit DDL in `sql/00_setup/`:
- `PROJECT_AUDIT.BATCH_MANIFEST`
- `PROJECT_AUDIT.SOURCE_WATERMARK`
- `PROJECT_AUDIT.RUN_LOG`
- `PROJECT_AUDIT.DQ_RESULT`
- `PROJECT_AUDIT.SCHEMA_DRIFT_LOG`
- `PROJECT_AUDIT.QUARANTINE_RECORD`
- `PROJECT_AUDIT.FILE_LOAD_LOG`
- `PROJECT_AUDIT.LINEAGE_EVENT`

Each table must have documented grain, key, retention, and access policy. Audit tables are permanent unless a specific retention decision is approved.

## Manifest grain
One row per source/entity/file/extraction unit. Store batch ID, source, entity, logical window, file name, checksum, compressed bytes, expected record count, cursor start/end, extraction start/end, status, and error summary. Do not store secrets.

## Watermark grain
One row per source/entity. Store committed watermark value, window start/end, overlap, cursor, last successful batch, last good checkpoint, status, updated timestamp, and optimistic version/claim fields if used.

A watermark may advance only after the bronze data for that checkpoint is durable. Replay after a partial failure must be safe.

## Run log
One row per pipeline run or stage execution. Include run ID, batch ID, task/stage, start/end, status, query ID if available, warehouse, input/output counts, error code/message, retry count, and implementation version.

## Lineage
Trace each canonical output to its source observations and files. Record the transformation version and match method. For each selected attribute, retain source/provenance where practical. Avoid storing full duplicate payloads in audit tables; bronze is the raw record store.

## Idempotency and concurrent processing
Use stable batch IDs, deterministic file names, checksums, and explicit states. A batch claim must prevent concurrent processing. If a task fails after committing one layer but before updating the manifest, replay must reconcile actual data and continue safely. Never use a manifest status alone as proof that a layer's data is correct.

## Recovery matrix
| Failure point | Recovery |
|---|---|
| API request | Retry from last confirmed cursor; keep batch incomplete |
| Upload | Re-upload deterministic file; verify checksum |
| Manifest insert | Reconcile stage/file and insert missing manifest row |
| COPY | Inspect COPY errors and load history; retry batch safely |
| Bronze MERGE | Rerun deduplicated insert-only MERGE |
| Watermark update | Reconcile committed bronze then advance checkpoint |
| Silver transform | Rerun batch-scoped SQL; preserve quarantine history |
| Dimension load | Reconcile business keys and surrogate keys before retry |
| Fact load | Re-run declared grain MERGE and orphan checks |
| DQ gate | Keep unpublished; fix cause and rerun checks |
| Gold refresh | Keep publication status closed until refresh succeeds |
| Finalizer | Compare table state and manifest, then rerun logging safely |

## Acceptance
- Every batch and task stage has an audit record.
- Watermark and manifest state transitions are traceable.
- File checksums and counts are recorded.
- Source-to-canonical lineage is queryable.
- Recovery tests prove safe replay.

## References
- Snowflake COPY INTO: https://docs.snowflake.com/en/sql-reference/sql/copy-into-table
- Snowflake streams: https://docs.snowflake.com/en/user-guide/streams-intro
- Snowflake tasks: https://docs.snowflake.com/en/user-guide/tasks-intro
- Snowflake query history: https://docs.snowflake.com/en/sql-reference/account-usage/query_history
