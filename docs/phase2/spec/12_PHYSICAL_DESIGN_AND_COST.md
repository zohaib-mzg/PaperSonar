# Physical Design and Cost Optimization

## Scope
Implement structural readiness only. Query-plan/EXPLAIN comparisons, before-and-after benchmark reports, and advanced analytic tuning are Phase 3 and must not be implemented here.

## Snowflake equivalents
- Indexing: Snowflake does not use conventional user-managed B-tree indexes on standard tables. Evaluate clustering and Search Optimization Service for justified access patterns.
- Partitioning: Snowflake automatically manages micro-partitions. Do not manually partition tables as in some relational databases. Clustering can improve pruning for suitable large tables.
- Transient/permanent: use transient staging where recovery requirements permit; permanent bronze, silver, DW, audit, and reference data.
- Rollback: use Time Travel and zero-copy clones within verified retention and account limits.
- Bulk loading: stage compressed NDJSON and use COPY in batches.
- Merge: prefer idempotent MERGE for business-key upsert; compare alternatives only in Phase 3.
- Compute: XS warehouse initially, auto-suspend 60 seconds, bounded timeout.
- Dynamic tables/materialized views: demonstrations only if supported and justified.

## Implementation decisions
1. Keep staging transient because it is reloadable from raw files, but verify retention/recovery needs.
2. Keep bronze permanent because it preserves source observations and supports replay/audit.
3. Keep silver and DW permanent for stable canonical data and acceptance.
4. Add clustering only after identifying recurring selective filters and measuring table size/access pattern. Do not cluster every table by default.
5. Candidate clustering keys may include publication date or source ID for large tables, but are not mandatory without evidence.
6. Search Optimization is optional and must be limited to queries that benefit enough to justify its cost.
7. Use one small warehouse during initial implementation.
8. Bound task retries and prevent runaway loops.
9. Avoid repeated full backfills; use incremental windows after baseline.
10. Record query IDs, bytes scanned, duration, rows, and credits where available.

## Credit ledger
For each major run record warehouse, start/end, query/task IDs, credits if available, rows processed, and cost per 1,000 rows. Keep estimated and measured costs separate. Do not claim credits are saved unless the account usage evidence supports it.

## Acceptance
- Physical choices are documented and applied selectively.
- Staging recovery model is documented.
- Permanent history layers are preserved.
- Clustering/Search Optimization decisions include rationale and cost.
- No Phase 3 benchmarking deliverables are present.

## References
- Micro-partitions and clustering: https://docs.snowflake.com/en/user-guide/tables-clustering-micropartitions
- Search Optimization: https://docs.snowflake.com/en/user-guide/search-optimization-service
- Transient tables: https://docs.snowflake.com/en/user-guide/tables-temp-transient
- Time Travel: https://docs.snowflake.com/en/user-guide/data-time-travel
- Bulk load considerations: https://docs.snowflake.com/en/user-guide/data-load-considerations-load
