# Phase 2 Documentation Index

**Current implementation:** strict ELT against the Nov 18 Phase 2 specification
pack. Python extracts/uploads raw gzip NDJSON; Snowflake performs all SQL
transforms, DQ gating and publication.

## Start here

0. [NEXT_STEPS.md](NEXT_STEPS.md) — short handoff checklist: GitHub-only
   scheduling, secrets/variable, one-time Snowflake setup, and verification.
1. [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) — implemented artifacts,
   verification matrix, known `VERIFY:` items, and traceability to all 20 specs.
2. [spec/19_IMPLEMENTATION_PLAN.md](spec/19_IMPLEMENTATION_PLAN.md) — build order
   and dependencies.
3. [spec/17_TESTING_ACCEPTANCE.md](spec/17_TESTING_ACCEPTANCE.md) — required live
   evidence, explicitly separated from mocked tests.
4. [spec/05_SNOWFLAKE_TASK_ORCHESTRATION.md](spec/05_SNOWFLAKE_TASK_ORCHESTRATION.md)
   — task graph and failure/recovery contract.

## Current source-of-truth artifacts

- `config/sources.yml`, `config/taxonomy.yml`, `config/quality_rules.yml`
- `src/extract/`, `src/runner/`
- `sql/00_setup/` through `sql/09_tasks/`
- `sql/99_tests/01_acceptance.sql`
- `tests/sql/test_sql_contracts.py`
- `.github/workflows/extract-load.yml`, `.github/workflows/deploy-ci.yml`

## Historical documents (preserved, not current acceptance claims)

- [ACCEPTANCE_REPORT.md](ACCEPTANCE_REPORT.md) — earlier implementation results.
- [RUNBOOK.md](RUNBOOK.md) — account/secret setup is still useful; commands and
  object names may be stale.
- [PHASE2_DATA_DICTIONARY_ADDENDUM.md](PHASE2_DATA_DICTIONARY_ADDENDUM.md)
- [PHASE2_EVIDENCE_QUERIES.sql](PHASE2_EVIDENCE_QUERIES.sql)
- [SOURCE_CAPABILITY_MATRIX.md](SOURCE_CAPABILITY_MATRIX.md)
- [SURROGATE_KEY_MIGRATION.md](SURROGATE_KEY_MIGRATION.md)
- [REPOSITORY_AUDIT.md](REPOSITORY_AUDIT.md)
- [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md)

## Status boundary

Live Snowflake evidence exists for the OpenAlex full backfill:
[evidence/2026-11-19-openalex-full-load.md](evidence/2026-11-19-openalex-full-load.md).
Do not read mocked/unit test success as warehouse acceptance for other sources
or for incremental mode. OpenAlex incremental requires a Member+/Partner daily-sync
plan and currently returns HTTP 403; the zero-record path is unit-tested only.
Further evidence must be captured under `docs/phase2/evidence/` after an
authorized account run.
