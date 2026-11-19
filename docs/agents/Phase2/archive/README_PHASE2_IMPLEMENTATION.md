# PaperSonar Phase 2 Implementation Pack

## Purpose

This pack is the implementation contract for Phase 2 of PaperSonar. It defines the required work, implementation order, verification checks, and hard stopping boundary. The agent must inspect the actual repository before editing and preserve working code unless a documented migration is necessary.

**Important:** These files are specifications, not proof that the repository already implements the described features. The agent must report actual repository state, tests, and live-run evidence.

## Required reading order

1. `00_REPOSITORY_AUDIT_AND_PHASE_BOUNDARY.md`
2. `01_TARGET_ARCHITECTURE_AND_REQUIREMENTS.md`
3. `02_SOURCE_CONNECTORS_AND_INCREMENTAL_LOADING.md`
4. `03_RAW_STAGING_CANONICAL_MODEL.md`
5. `04_DIMENSIONAL_WAREHOUSE_AND_SQL.md`
6. `05_ORCHESTRATION_RETRIES_AND_RECOVERY.md`
7. `06_SNOWFLAKE_SETUP_AND_GITHUB_ACTIONS.md`
8. `07_TESTING_DATA_QUALITY_AND_ACCEPTANCE.md`
9. `08_SECURITY_COSTS_AND_OPERATIONS.md`
10. `09_AGENT_EXECUTION_PLAN_AND_STOP_RULES.md`
11. `10_SOURCE_AND_RUNTIME_CONFIGURATION_REFERENCE.md`

## Non-negotiable requirements

- **Snowflake is mandatory** as the Phase 2 production warehouse. It is not a selectable or replaceable production target.
- GitHub Actions must connect to Snowflake securely and run scheduled incremental ingestion automatically, with manual dispatch for controlled backfill/recovery.
- Use only free/open-source libraries, public metadata access, and a no-cost Snowflake offer/credits if available. Snowflake is a commercial service and permanent free availability cannot be guaranteed. Never activate paid resources. If no no-cost Snowflake access is available, report deployment/acceptance as **BLOCKED**; do not substitute another database.
- Unit tests may use fixtures and a mocked Snowflake adapter. Production ingestion, warehouse loads, and Phase 2 acceptance require Snowflake connectivity and a real smoke test.
- Do not commit credentials, tokens, private keys, `.env` files, or secrets.
- Approved sources are exactly OpenAlex, Crossref, arXiv, DataCite, and Zenodo. Do not add a sixth source.
- Collect permitted metadata only; do not store full paper PDFs or copyrighted full text.
- Implement source-specific synchronization, idempotent upserts, durable checkpoints, provenance, retries, quarantine, and recovery.
- Never advance a checkpoint until the corresponding source window has been fully and durably processed in Snowflake and required raw/manifests are persisted.
- Do not invent data counts, successful runs, test results, or source capabilities.
- Phase 3 is out of scope: no Power BI dashboard, web app, product features, research-gap scoring product, or new sources.

## Definition of Phase 2 complete

Phase 2 is complete only when: (1) all five source adapters work; (2) historical backfill and recurring sync are separate; (3) each source's incremental limitations are documented; (4) raw payloads and manifests are traceable; (5) canonicalization, deduplication, quarantine, and provenance work; (6) the approved dimensional model is created and loadable in Snowflake; (7) retries, checkpoints, idempotency, and warehouse integrity are tested; (8) GitHub Actions connects to Snowflake and the scheduled/manual workflow is verified; (9) a real Snowflake smoke test and acceptance checks pass; and (10) the agent stops before Phase 3. If the Snowflake account cannot be accessed at no cost, the agent must report the blocked acceptance criteria clearly and must not claim Phase 2 is complete.

## Repository reconciliation

Before modifying anything, list the repository tree, inspect existing documentation and DDL, identify languages/frameworks, read current tests, and map every requirement to files and tests. If an artifact is absent, create it. If a similar artifact exists, update it in place and preserve useful history.
