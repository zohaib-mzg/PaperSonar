# Snowflake Setup, Security, and Cost

## 1. Verify account before compute
The project brief assumes a 30-day, $400-credit no-cost trial. Confirm actual expiry, balance, edition, region, and feature access. Verify task graphs, Git repository integration, key-pair auth, Time Travel, cloning, Search Optimization, materialized views, and dynamic tables before relying on them. Do not infer access from signup choices.

## 2. Database and schemas
Create `PAPERSONAR` and the seven schemas from `01_ARCHITECTURE_AND_NAMING.md`. Use `CREATE ... IF NOT EXISTS`; avoid `CREATE OR REPLACE` for production data objects. DDL belongs in `sql/00_setup/`.

```sql
-- Purpose: Create Phase 2 namespace.
-- Inputs: ADMIN role.
-- Outputs: Database and schemas.
-- Idempotent: Yes.
-- Owner: PAPERSONAR_ADMIN.
-- Parameters: None.
-- Cost: Metadata operation; no transformation warehouse workload expected.
CREATE DATABASE IF NOT EXISTS PAPERSONAR;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_STAGING;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_BRONZE;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_SILVER;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_DW;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_REPORTING;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_AUDIT;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_REF;
```

## 3. RBAC
Roles:
- `PAPERSONAR_LOADER`: stage upload and required manifest registration only.
- `PAPERSONAR_TRANSFORMER`: execute task graph and required transformations.
- `PAPERSONAR_REPORTER`: SELECT only from approved reporting objects.
- `PAPERSONAR_ADMIN`: controlled setup, grants, warehouse and resource controls.

Do not grant ACCOUNTADMIN to automation. Minimize ownership privileges and review inherited grants. Verify task, stage, Git integration, and resource-monitor privilege requirements against current Snowflake docs.

## 4. Authentication and network
Use a dedicated non-human service user and key-pair authentication where supported. Private keys and passphrases belong only in GitHub Secrets. Never log secrets or commit keys. Rotate credentials on suspected exposure. External APIs are called from GitHub Actions, not Snowflake SQL; the trial is assumed to lack outbound external network access. A network policy is optional only after checking GitHub runner IP implications.

## 5. Warehouse
Start with one user-managed XS warehouse, initially suspended, auto-resume enabled, auto-suspend 60 seconds, and bounded statement timeout. Validate syntax and values in the target account before applying.

```sql
-- Purpose: Initial ELT compute.
-- Inputs: ADMIN role; verified account limits.
-- Outputs: WH_PAPERSONAR_ELT.
-- Idempotent: Yes for creation; changes require reviewed migration.
-- Owner: PAPERSONAR_ADMIN.
-- Parameters: Warehouse settings are configuration.
-- Cost: XS compute only while running; monitor every run.
CREATE WAREHOUSE IF NOT EXISTS WH_PAPERSONAR_ELT
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  STATEMENT_TIMEOUT_IN_SECONDS = 1800;
```

User-managed XS is the default because compute choice and usage are visible. Serverless tasks are an alternative only after confirming availability and estimating cost. Do not run both designs concurrently for normal processing.

## 6. Resource monitor and budget
Configure and test a resource monitor before enabling compute. Verify supported quota scope, warning actions, and suspension behavior. Monitor charges not necessarily covered by a warehouse monitor.

Initial planning allocation (adjust to actual balance):
- Setup and smoke tests: 10%
- Backfill: 35%
- Transformation and DQ: 25%
- CI and acceptance: 10%
- Recovery reserve: 20%

Record query IDs, task durations, credits, rows processed, failures, and cost per 1,000 rows. Label estimates separately from measured usage. Cortex is OFF by default.

## 7. Dev/prod and rollback
Use a development database/schema and zero-copy clone where appropriate. Clone storage and compute are not assumed free. Apply versioned additive DDL; do not overwrite the only production copy. Verify Time Travel and retention settings. Keep evidence outside temporary objects.

## 8. Trial-expiry plan
Day 1: verify account and cost controls. Days 2–3: source-to-stage smoke test. Days 4–7: first useful backfill and incremental proof. Days 8–14: dimensions/facts/DQ. Days 15–20: remaining sources and semantic layer. Days 21–24: acceptance. Days 25–27: fixes and Parquet exports. Days 28–29: capture live evidence. Day 30: final access check. Adapt to actual expiry; do not wait until the last day.

## 9. Pause procedure
Disable GitHub cron; stop new extraction; suspend/disable task graph using supported controls; suspend warehouse when safe; inspect nonterminal batches; preserve audit logs. Verify suspension semantics for all graph tasks.

## Acceptance
- Schemas and roles exist.
- Loader cannot modify dimensions/facts.
- Reporter is read-only.
- Key-pair auth works without log leakage.
- Warehouse timeout and auto-suspend work.
- Resource monitor behavior is evidenced.
- Trial expiry and credits are recorded.
- Clone/test deployment and backup export are tested.

## References
- Warehouses: https://docs.snowflake.com/en/user-guide/warehouses
- Resource monitors: https://docs.snowflake.com/en/user-guide/resource-monitors
- Key-pair authentication: https://docs.snowflake.com/en/user-guide/key-pair-auth
- Access control: https://docs.snowflake.com/en/user-guide/security-access-control-overview
- Cloning: https://docs.snowflake.com/en/user-guide/object-clone
- Time Travel: https://docs.snowflake.com/en/user-guide/data-time-travel
- Search Optimization: https://docs.snowflake.com/en/user-guide/search-optimization-service
- Materialized views: https://docs.snowflake.com/en/user-guide/views-materialized
- Dynamic tables: https://docs.snowflake.com/en/user-guide/dynamic-tables-intro
