# Phase 2 Report Outlines

## A. Data Cleaning Report
Generate from actual `PROJECT_AUDIT` data and reproducible SQL queries. Do not fabricate counts or examples.

1. Project scope and run/batch IDs.
2. Source inventory and windows.
3. Extracted and staged counts.
4. Standardization rules: whitespace, Unicode, case, DOI, title, date, language, country.
5. Type conversions and failed conversions.
6. Duplicate handling: exact source duplicates vs cross-source identity matches.
7. Canonical identity strategy and match confidence.
8. Attribute survivorship and source provenance.
9. Category mapping and unclassified outcomes.
10. Quarantine counts by reason code.
11. Before/after examples using real records that may be safely shown.
12. Limitations, licensing notes, and known data gaps.

Required tables:
- Layer counts per source/entity/batch.
- Rejection counts per reason.
- Identity matches by method.
- Categorization coverage by method/version.

## B. Data Quality Report
1. Execution summary and publication decision.
2. DQ rule inventory, severity, and version.
3. Completeness and validity results.
4. Uniqueness and SCD2 current-row checks.
5. Fact/bridge integrity and orphan counts.
6. Reconciliation across layers, with explanations for grain differences.
7. Freshness and watermark status.
8. Volume anomalies and schema drift.
9. Category coverage and evaluation sample summary.
10. Citation-count caveats and source-specific values.
11. Failures, remediation, and rerun results.
12. Acceptance evidence links and query IDs.

Required summary fields: batch ID, run ID, query/task IDs, check timestamp, observed value, threshold, pass/fail, severity, publication status.

## Generation rule
Reports must be produced from actual SQL query results and audit tables. If a live run is unavailable, label the report as a template or local test result; do not claim live acceptance.

## References
- Snowflake query history: https://docs.snowflake.com/en/sql-reference/account-usage/query_history
- Snowflake tasks: https://docs.snowflake.com/en/user-guide/tasks-intro
