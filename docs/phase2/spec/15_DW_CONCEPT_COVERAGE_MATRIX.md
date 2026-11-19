# Data Warehousing Concept Coverage Matrix

| Concept | Phase 2 implementation | Location | Status/notes |
|---|---|---|---|
| OLTP vs OLAP | Explain operational source vs analytical warehouse; no OLAP analytics queries | 00, 01, 09 | Design rationale only |
| ETL vs ELT | Raw extract/upload then SQL transforms in Snowflake | 03–07 | Binding ELT architecture |
| Medallion architecture | Staging, bronze, silver, DW, reporting | 01, 06–10 | Implement |
| Staging | Explicit VARIANT payload and load metadata | 06 | No schema inference |
| Bronze history | Append-only source observations and insert-only MERGE | 06 | Implement |
| Silver cleaning | Typed values, standardization, dedupe, quarantine | 07 | Set-based SQL |
| Star schema | Fact and conformed dimensions | 09 | Implement |
| Conformed dimensions | Shared source/date/output/category/etc. dimensions | 09 | Implement |
| Role-playing date | Publication, update, snapshot date keys | 09 | Implement where used |
| Junk dimension | Access/status flags in `DIM_ACCESS_STATUS` or justified mini-dimension | 09 | Align to dictionary |
| Degenerate dimension | Source record or external identifiers in fact where appropriate | 09 | Document rationale |
| Bridges | Output-author and output-category relations | 09 | Implement |
| Factless facts | Relations without numeric measures when justified | 09 | Optional by model need |
| Periodic snapshot | Citation count by output/source/snapshot date | 09 | Implement if source supports it |
| Surrogate keys | Numeric keys for every dimension | 09 | Stable across reruns |
| Natural/business keys | Source and canonical identifiers | 09 | MERGE match keys |
| SCD Type 1 | Nonhistorical attributes | 09 | Implement where justified |
| SCD Type 2 | Author/affiliation, venue, topic history where justified | 09 | Effective dating and current-row DQ |
| SCD Type 3 | Limited previous/current attributes only if justified | 09 | Do not add without requirement |
| Late-arriving data | Inferred member and deferred fact repair | 09 | Audited |
| Unknown members | Reserved Unknown/Not Applicable keys | 09 | Consistent policy |
| Watermarks | Per source/entity checkpoint | 03, 05, 13 | Advance after bronze commit |
| Full and incremental load | Same adapter, different windows | 03, 17 | Demonstrate both |
| Idempotency | Stable files, manifest, COPY history, bronze MERGE, grain keys | 03, 06, 13 | Rerun test |
| MERGE INTO | Insert-only bronze and upserts in silver/DW | 06, 07, 09 | Deduplicate source first |
| Explicit schema | Explicit DDL; no INFER_SCHEMA | 01, 06, 07 | Mandatory |
| Data quality | Completeness, validity, uniqueness, integrity, accuracy | 11 | Publication gate |
| Quarantine | Rejected rows with reason codes | 07, 11, 13 | No silent drops |
| Reconciliation | Counts interpreted by layer/grain | 11 | Explain differences |
| Audit/lineage | Manifest, watermarks, run log, crosswalk, query IDs | 13 | Implement |
| Indexing equivalent | Clustering and Search Optimization | 12 | Selective, cost-justified |
| Partitioning equivalent | Snowflake micro-partitions and optional clustering | 12 | No manual partitions |
| Views | Basic semantic views | 10 | Implement |
| Materialized view | One physical-design demo if supported | 10, 12 | VERIFY edition/limitations |
| Dynamic table | One physical-design demo if supported | 10, 12 | VERIFY availability/cost |
| Streams and tasks | Change capture where useful; task graph orchestration | 05, 13 | VERIFY task-stage integration |
| Time Travel/clone | Recovery and development safety | 02, 12 | VERIFY retention/availability |
| RBAC | Loader, transformer, reporter, admin | 02 | Least privilege |
| Cost control | Resource monitor, XS warehouse, budget, run ledger | 02, 12 | Before compute |
| Schema drift | Expected-key registry and drift audit | 06, 11 | Required keys can block batch |
| Categorization | Source taxonomy, weighted rules, optional Cortex | 08 | Cortex OFF by default |
| PostgreSQL concepts | Mapped to Snowflake features | 01, 12 | No PostgreSQL dependency |
| Advanced analytics | Excluded | 00 | Phase 3 only |
| Dashboard/reporting insights | Excluded | 00 | Phase 3 only |

## References
- Snowflake tasks: https://docs.snowflake.com/en/user-guide/tasks-intro
- Snowflake clustering: https://docs.snowflake.com/en/user-guide/tables-clustering-micropartitions
- Snowflake constraints: https://docs.snowflake.com/en/sql-reference/constraints
- Kimball dimensional modeling: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/
