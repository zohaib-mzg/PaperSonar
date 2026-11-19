# Testing and Acceptance Specification

## Principle
Live Snowflake evidence is required. Mocked tests prove adapter logic, not warehouse acceptance. Capture SQL results, query IDs, task history, sanitized screenshots where needed, and report outputs in `docs/phase2/evidence/`.

## Requirement/evidence matrix
| Requirement | Evidence/query |
|---|---|
| Layer row counts | Counts by batch/source in staging, bronze, silver, DW |
| Dimensions >=100 | Count rows per dimension and total distinct business members |
| Facts >=10,000 | Count rows per declared fact grain; identify qualifying fact table |
| Zero orphans | Left-join every fact FK to its dimension; result must be 0 |
| Stable keys | Snapshot business-key-to-surrogate-key mapping, rerun same batch, compare |
| Idempotency | Run same batch twice; logical counts and keys unchanged |
| Incremental | Show watermark before/after, window, new observations, and published batch |
| Full load | Show full window and no bronze truncation |
| Task graph | Task history plus run log for each stage |
| DQ gate | Demonstrate critical failure prevents publication, then corrected success |
| Reconciliation | Report source/staging/bronze/silver/rejected/DW counts with grain explanation |
| Security | Role grants and reporter read-only test |
| Cost controls | Warehouse config, resource monitor, query/task usage evidence |

## Read-only acceptance query patterns
Row counts:
```sql
SELECT 'STAGING' AS LAYER, COUNT(*) AS ROW_COUNT
FROM PAPERSONAR.PROJECT_STAGING.STG_OPENALEX_WORK
UNION ALL
SELECT 'BRONZE', COUNT(*)
FROM PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK
UNION ALL
SELECT 'SILVER', COUNT(*)
FROM PAPERSONAR.PROJECT_SILVER.SLV_RESEARCH_OUTPUT;
```

Dimension target:
```sql
SELECT 'DIM_AUTHOR' AS OBJECT_NAME, COUNT(*) AS ROW_COUNT
FROM PAPERSONAR.PROJECT_DW.DIM_AUTHOR
UNION ALL
SELECT 'DIM_CATEGORY', COUNT(*)
FROM PAPERSONAR.PROJECT_DW.DIM_CATEGORY;
```

Fact target:
```sql
SELECT COUNT(*) AS FACT_ROWS
FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT;
```

Orphan check pattern:
```sql
SELECT COUNT(*) AS ORPHAN_ROWS
FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT f
LEFT JOIN PAPERSONAR.PROJECT_DW.DIM_OUTPUT_TYPE d
  ON f.OUTPUT_TYPE_KEY = d.OUTPUT_TYPE_KEY
WHERE d.OUTPUT_TYPE_KEY IS NULL;
```
Repeat for every FK, including bridges. These are patterns; align exact names to final DDL.

## Unit and integration tests
- Source pagination and cursor resume using mocked HTTP responses.
- 429/5xx retries and permanent 4xx handling.
- Deterministic filenames and checksums.
- Malformed and oversized record behavior.
- DOI/title/date normalization.
- Duplicate source record handling.
- MERGE-source deduplication.
- SCD2 change and unchanged-row behavior.
- Fact grain uniqueness and late-arriving dimension repair.
- Category positive/negative examples.
- DQ critical failure blocks publication.
- Rerun/recovery after each pipeline boundary.

## Acceptance run sequence
1. Verify setup and role grants.
2. Run one small source smoke test.
3. Run full mode for selected feasible historical windows.
4. Run the task graph and inspect each stage.
5. Run DQ and publish only if critical checks pass.
6. Repeat the same batch to prove idempotency.
7. Run incremental mode with overlap and show watermark movement.
8. Verify row targets and zero orphans.
9. Generate both reports.
10. Capture evidence and export required backups.

## References
- Snowflake query history: https://docs.snowflake.com/en/sql-reference/account-usage/query_history
- Snowflake task history: https://docs.snowflake.com/en/sql-reference/functions/task_history
- Snowflake constraints: https://docs.snowflake.com/en/sql-reference/constraints
