# Phase 2 Implementation Status

**Status date:** 2026-11-19
**Scope:** Nov 18 Phase 2 specification pack, strict ELT architecture.
**Code state:** implemented at repository level.
**Live acceptance state:** **PARTIAL** — the OpenAlex full backfill is live-proven through
`PUBLISHED`; incremental OpenAlex remains blocked by the Member+/Partner daily-sync
plan. See [evidence/2026-11-19-openalex-full-load.md](evidence/2026-11-19-openalex-full-load.md).

## Architectural contract

- Python performs extraction and upload only: raw gzip NDJSON shards, deterministic batch IDs, checksums, manifest registration, and `PUT` to the internal stage.
- Python does not clean fields, assign surrogate keys, deduplicate records, categorize, or transform business data.
- Snowflake SQL performs staging COPY, bronze current-state upsert, silver projection/identity, categorization, dimensions, facts, DQ, and publication.
- Seven schemas: `PROJECT_STAGING`, `PROJECT_BRONZE`, `PROJECT_SILVER`, `PROJECT_DW`, `PROJECT_REPORTING`, `PROJECT_AUDIT`, `PROJECT_REF`.
- Five sources only: OpenAlex, Crossref, arXiv, DataCite, Zenodo.
- No `INFER_SCHEMA`; every table has explicit DDL.
- Bronze is current-state by source record id. Dimensions are never truncated. Watermarks advance only after publication.
- Critical DQ failure blocks publication. Malformed/oversize/invalid records are quarantined, never silently dropped.

## Implemented artifacts

| Area | Files |
|---|---|
| Extraction | `src/extract/{base,http,oai,openalex,crossref,arxiv,datacite,zenodo,registry}.py` |
| Runner/deploy | `src/runner/{config,windows,snowflake,extract_run,cli}.py` |
| Contracts | `config/sources.yml`, `config/taxonomy.yml`, `config/quality_rules.yml` |
| Setup/security/cost | `sql/00_setup/00..06_*.sql` |
| Staging/bronze | `sql/01_staging/`, `sql/02_bronze/` |
| Silver/identity | `sql/03_silver/00_udfs.sql`, `01_slv_tables.sql`, `02_transform_batch.sql` |
| Categorization | `sql/04_categorization/` |
| Dimensions/facts | `sql/05_dimensions/`, `sql/06_facts/` |
| Reporting/publication | `sql/07_reporting/` |
| DQ gate | `sql/08_audit_dq/` |
| Task graph | `sql/09_tasks/01_batch_control.sql`, `02_task_graph.sql` |
| Acceptance queries | `sql/99_tests/01_acceptance.sql` |
| CI | `.github/workflows/extract-load.yml`, `.github/workflows/deploy-ci.yml` |
| Tests | `tests/unit/`, `tests/sql/test_sql_contracts.py` |

The old `src/papersonar/` package remains in place. The old `phase2.yml` workflow is renamed `legacy-phase2.yml.disabled` so it cannot run alongside the new pipeline. No old source file has been deleted.

## Verification matrix

| Check | Result | Evidence |
|---|---|---|
| Ruff on `src` and `tests` | PASS | local run |
| Python unit/integration tests | PASS | `python -m pytest tests -q` (`219 passed`) |
| SQL static contracts | PASS | `tests/sql/test_sql_contracts.py` (`11 passed`) |
| Dry-run shard writing | PASS | unit tests with fake HTTP |
| Live SQL deployment | PASS | full-load run; inline JSON file format for COPY |
| Live COPY/procedure execution | PASS | `168725` staging rows; 5/5 `FILE_LOAD_LOG` rows `MATCH` |
| Task graph execution/history | PASS | root through finalizer; batch `PUBLISHED` |
| Task graph auto-resume after deploy | PASS | `SHOW TASKS`: all 10 tasks `started` |
| DQ gate live demonstration | PASS | 12 rules; `critical_failures=0`, 2 warnings |
| Bronze current-state uniqueness | PASS | `168725` rows / `168725` ids / `0` duplicates |
| Dimension >= 100 / fact >= 10,000 | PASS | `168725` outputs and citation snapshots |
| Full backfill live run | PASS | `BATCH_07D9668D4CBED88D815D30CA`; 5 files; `168725` records; `CURSOR_END=NULL`; `ERROR_SUMMARY=NULL` |
| Incremental live run | **BLOCKED** | `from_updated_date` returns HTTP 403; Member+/Partner plan required |
| Zero-record path | PARTIAL | unit-tested only; no live incremental request possible |
| Force push preparation | **NOT PREPARED** | no `phase1-final` tag, no backup branch, no authorization |

All live rows above are backed by
[evidence/2026-11-19-openalex-full-load.md](evidence/2026-11-19-openalex-full-load.md).

## Commands

```powershell
# Local checks
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m pytest tests -q

# Configuration without secrets
.venv\Scripts\python.exe -m runner.cli check

# Local extraction only (no Snowflake writes)
.venv\Scripts\python.exe -m runner.cli extract --source crossref --mode incremental --dry-run

# One-time OpenAlex full backfill (verified 2026-11-17..18)
.venv\Scripts\python.exe -m runner.cli extract --source openalex --mode full --from 2026-11-17 --until 2026-11-18 --no-task --json

# OpenAlex incremental requires Member+/Partner daily sync; do not use a publication-date fallback.

# One live source window, then trigger the graph (requires secrets)
.venv\Scripts\python.exe -m runner.cli extract --source crossref --mode incremental --no-task
.venv\Scripts\python.exe -m runner.cli trigger --drain

# Deploy SQL safely (review diff first)
.venv\Scripts\python.exe -m runner.cli deploy --sql-dir sql --yes
```

## Known `VERIFY:` items

These are marked in the SQL and require the target account/API:

1. `COPY INTO` was proven live with an inline JSON file format. Future setup should grant USAGE on `FF_NDJSON_GZ` to `PAPERSONAR_ADMIN`, `PAPERSONAR_LOADER` and `PAPERSONAR_TRANSFORMER` before relying on the named format: https://docs.snowflake.com/en/sql-reference/sql/copy-into-table
2. DataCite `updated:[...]` query syntax against the live API.
3. arXiv/Zenodo XML extraction with `REGEXP_SUBSTR_ALL(... 'e', 1)`.
4. `SHA2(TO_JSON(payload))` stability for staged VARIANT replay.
5. Task graph `FINALIZE` failed-child behavior was observed live. `CREATE OR REPLACE TASK` recreates tasks suspended; the deploy client resumes children before the root: https://docs.snowflake.com/en/sql-reference/sql/create-task
6. `EXECUTE TASK` for the configured deployment/trigger role was exercised live.
7. Materialized view/dynamic table edition support (manual-only file).
8. Actual trial credits, resource-monitor actions, and account features.
9. OpenAlex Member+/Partner entitlement for `from_updated_date`; the current plan returns HTTP 403. No publication-date fallback is used: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/filter-entity-lists

## Specification traceability

| Spec | Implementation |
|---|---|
| `00_README_PHASE2.md` | This status document and README update |
| `01_ARCHITECTURE_AND_NAMING.md` | `sql/00_setup/00_database_schemas.sql`, naming in all DDL |
| `02_SNOWFLAKE_SETUP_SECURITY_COST.md` | `sql/00_setup/01..03` |
| `03_SOURCES_AND_EXTRACTION.md` | `src/extract/`, `config/sources.yml` |
| `04_GITHUB_ACTIONS.md` | `.github/workflows/extract-load.yml`, `deploy-ci.yml` |
| `05_SNOWFLAKE_TASK_ORCHESTRATION.md` | `sql/09_tasks/` |
| `06_STAGING_BRONZE.md` | `sql/01_staging/`, `sql/02_bronze/` |
| `07_SILVER.md` | `sql/03_silver/` |
| `08_CATEGORIZATION.md` | `sql/04_categorization/`, `config/taxonomy.yml` |
| `09_DIMENSIONAL_MODEL_DW.md` | `sql/05_dimensions/`, `sql/06_facts/` |
| `10_GOLD_SEMANTIC_LAYER.md` | `sql/07_reporting/01_views.sql` |
| `11_DATA_QUALITY_RECONCILIATION.md` | `sql/08_audit_dq/`, `config/quality_rules.yml`, `sql/07_reporting/03_publish_batch.sql` |
| `12_PHYSICAL_DESIGN_AND_COST.md` | `sql/00_setup/02`, `sql/07_reporting/02_physical_demos.sql` (manual) |
| `13_AUDIT_METADATA_LINEAGE.md` | `sql/00_setup/04_audit_ddl.sql`, lineage merges in procedures |
| `14_ISSUES_RISKS_RESOLUTIONS.md` | Known `VERIFY:` list above |
| `15_DW_CONCEPT_COVERAGE_MATRIX.md` | Dimensions/facts/bridges in `sql/05` and `sql/06` |
| `16_REPO_STRUCTURE_FORCE_PUSH.md` | Pending: tag/backup/authorization not performed |
| `17_TESTING_ACCEPTANCE.md` | `tests/`, `sql/99_tests/01_acceptance.sql`; full-load live evidence in `evidence/2026-11-19-openalex-full-load.md` |
| `18_PHASE2_REPORT_OUTLINES.md` | Full backfill evidence available; other sources/incremental still pending |
| `19_IMPLEMENTATION_PLAN.md` | Implemented through build steps; full backfill live-proven, incremental blocked |

## Evidence policy

Live evidence must be saved under `docs/phase2/evidence/` with query IDs and timestamps. Do not record secrets, full private keys, or unsanitized account identifiers. Mocked tests must never be presented as live Snowflake acceptance.
