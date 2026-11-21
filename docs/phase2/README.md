# Phase 2 Documentation Index

**Current implementation:** strict ELT against the Nov 18 Phase 2 specification
pack. Python extracts/uploads raw gzip NDJSON; Snowflake performs all SQL
transforms, DQ gating and publication.

## Start here

0. [NEXT_STEPS.md](NEXT_STEPS.md) — short handoff checklist: GitHub-only
   scheduling, secrets/variable, one-time Snowflake setup, and verification.
0. [PIPELINE_FLOW_GUIDE.md](PIPELINE_FLOW_GUIDE.md) — plain-language full data
   flow: when incremental runs happen, where data lands, and how SQL runs.
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
- `sql/99_tests/01_acceptance.sql`, `02_phase2_verification.sql`,
  `03_phase2_closeout.sql`
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

Phase 2 is **closed with known limits** as of 2026-11-22. Live Snowflake
evidence exists for:

- the OpenAlex full backfill —
  [evidence/2026-11-19-openalex-full-load.md](evidence/2026-11-19-openalex-full-load.md);
- the multi-source closeout (OpenAlex, Crossref, arXiv and Zenodo published
  with `critical_failures=0`, the 12-rule DQ gate live on every batch, the
  model populated, plus the two defects found and fixed) —
  [evidence/2026-11-22-live-verification.md](evidence/2026-11-22-live-verification.md).

Still open, and deliberately not claimed as accepted:

- incremental OpenAlex requires a Member+/Partner daily-sync plan (HTTP 403
  today); the zero-record path is unit-tested only;
- the DataCite backlog replays one window per run after the oversize-text fix;
- categorization coverage is 4–6% against the 60% DQ-009 target — Phase 3
  work package WP1;
- account housekeeping (service-user defaults, one stuck batch, unused
  warehouse) — listed in the closeout evidence §10.

Do not read mocked/unit test success as warehouse acceptance for anything
that is not listed above. Further evidence must be captured under
`docs/phase2/evidence/` after an authorized account run.
