# PaperSonar — Post-Phase 2 Integration, SQL Engineering, and Hardening Instructions

**Document purpose:** Give the implementation agent a clear, testable checklist to run after completing the Phase 2 implementation pack.

**Project rule:** Snowflake is the required production data warehouse. SQL is a core part of PaperSonar, not an optional add-on. Python may collect and orchestrate data, but warehouse structures, loading, transformations, data-quality checks, and analytical models must make proper use of Snowflake SQL.

**Scope boundary:** This document audits and hardens Phase 2 only. Do not start Phase 3, add unrelated features, or silently replace the required warehouse with another database.

---

## 1. Required agent behavior

1. Read the repository, project documentation, and every Phase 2 instruction file before changing anything.
2. Compare the implementation with the requirements in this document and the Phase 2 pack.
3. Make changes in small, reviewable steps. Preserve working Phase 1 behavior.
4. Do not claim a requirement is complete unless implementation and tests provide evidence.
5. Do not invent files, environment variables, schemas, source capabilities, or successful live runs.
6. If a required service or credential is unavailable, document the exact blocker and provide a safe test that does not need live credentials.
7. Never enable paid cloud resources, create paid services, or incur costs without explicit approval.
8. Keep Phase 3 out of scope until Phase 2 is complete, validated, documented, and explicitly approved.

## 2. Architecture that must be preserved

PaperSonar collects scholarly and research metadata from these free sources:

- OpenAlex
- Crossref
- arXiv
- DataCite
- Zenodo

Use each source's documented API behavior and terms. Do not assume that every source supports the same filters, sorting, cursor, or update timestamp. Record the source-specific strategy in documentation.

Expected flow:

1. **Source adapters:** communicate with APIs, handle pagination, limits, retries, and response parsing.
2. **Ingestion/orchestration layer:** coordinates historical backfill and incremental runs; records run status and checkpoints.
3. **Raw landing and provenance:** preserve the original response or a sufficiently complete raw representation, source identity, retrieval time, and run metadata.
4. **Snowflake SQL warehouse:** stores validated raw/staging data and canonical, deduplicated records; performs SQL-based merges and transformations.
5. **Data quality and analytics:** SQL checks, modeled tables/views, and documented analytical queries.
6. **Automation:** GitHub Actions supports scheduled and manual runs, using repository secrets and safe concurrency controls.

Python and SQL have different jobs. Python is suitable for API calls, pagination, retries, parsing, and orchestration. Snowflake SQL must be used for warehouse DDL, data loading/merging, transformations, data quality, and analytics. Do not replace the SQL warehouse layer with Python-only in-memory transformations.

## 3. Required repository audit

Before editing, identify and document:

- Current directory and module structure.
- Existing Phase 1 components and tests that must continue to work.
- Source adapters and their pagination/incremental strategies.
- Snowflake connection and configuration approach.
- SQL schema/migration files, if present.
- Raw, staging, canonical, dimension, fact, bridge, and audit/run tables that actually exist.
- Checkpoint/watermark storage and update logic.
- GitHub Actions workflows and secret names referenced by the code.
- Unit, integration, and end-to-end test commands.
- Missing or conflicting requirements.

Create a requirement-to-evidence matrix with columns: requirement, implementation location, test/evidence, status (`PASS`, `FAIL`, or `BLOCKED`), and remaining work. Do not mark an item `PASS` based only on documentation.

## 4. Snowflake and SQL are mandatory

### 4.1 Warehouse connection and configuration

- Use Snowflake as the production warehouse.
- Read credentials from environment variables or the approved secret mechanism. Never commit credentials, tokens, private keys, or `.env` files containing secrets.
- Validate required configuration early and give clear, safe error messages that do not expose secret values.
- Keep local configuration examples free of real credentials.
- Pin and document required client-library versions where appropriate.
- Provide a clear setup path for a Snowflake account with suitable access.
- Do not silently fall back to a different database if Snowflake configuration is absent or connection fails.
- If free Snowflake access or credentials are unavailable, report live warehouse validation as `BLOCKED`; continue with mocks, unit tests, SQL review, and any available dry-run checks. Do not create paid resources.

### 4.2 SQL artifacts and schema management

Use explicit, reviewable Snowflake SQL for the warehouse. Include versioned DDL or migrations for the tables, views, and constraints/checks the project needs. The exact objects should follow the actual data model; do not create arbitrary tables merely to satisfy a checklist.

At minimum, review whether the design has appropriate SQL structures for:

- Raw source payloads and ingestion provenance.
- Staging and validation.
- Canonical research records.
- Source-to-record identity mapping.
- Ingestion run history and error records.
- Per-source incremental checkpoints/watermarks.
- Required dimensions, facts, bridge tables, or analytical views, according to the documented warehouse model.

Use explicit column definitions and data types. Avoid relying on automatic schema inference as the only schema-management method. Document how schema changes are reviewed and deployed.

### 4.3 SQL loading, merging, and transformations

- Use Snowflake SQL for repeatable warehouse-side loading and transformations.
- Use `MERGE` or an equally safe, documented SQL upsert pattern for canonical records where appropriate.
- Deduplicate staged input before a `MERGE` so that multiple source rows cannot create ambiguous updates.
- Define deterministic match keys and conflict-resolution rules. Prefer stable source namespace plus source record ID; use normalized DOI as a cross-source matching signal when present, not as an assumption that every record has one.
- Preserve source provenance and raw data rather than overwriting the only copy with a normalized record.
- Make rerunning the same input safe and idempotent.
- Handle missing fields and source-specific differences explicitly.
- Keep SQL readable, version-controlled, and covered by tests or documented validation queries.

### 4.4 SQL quality and analytics

Provide executable, documented Snowflake SQL checks for applicable rules, including:

- Required identifiers are not null or blank.
- Source identity keys are unique at the intended grain.
- Duplicate staging rows are detected or removed before merge.
- Canonical record counts and source counts can be reconciled.
- Invalid or malformed DOI values are flagged where DOI is expected.
- Run outcomes, rejected records, and ingestion errors are measurable.
- Checkpoint values do not advance past records that have not been durably written and validated.

Provide a small set of useful analytical SQL queries or views that demonstrate the warehouse is genuinely queryable. Examples may include publication counts by year/source, research topics over time, organization output, and dataset/software links where the available source fields support them. Clearly label queries that depend on fields not yet populated.

### 4.5 SQL performance and safe operations

- Use query profiles and Snowflake query history when account permissions allow.
- Avoid unnecessary full-table rewrites during incremental runs.
- Use sensible batch sizes and avoid one-row-at-a-time warehouse writes where a batch approach is supported.
- Consider clustering or other optimization only when measured data volume and query profiles justify it; do not add costly optimization by default.
- Document transaction boundaries and recovery behavior for related warehouse writes.
- Never log credentials or raw sensitive configuration.
- Do not assume a primary key or unique constraint alone prevents duplicates in every Snowflake table; enforce the required behavior in loading logic and validation.

## 5. Historical backfill and incremental loading

The system must support an initial historical load and later incremental synchronization for each source.

For every source, document:

- Supported historical range and API limits.
- Pagination mechanism and termination conditions.
- Incremental filter or cursor, if the API supports one.
- Whether the source provides a reliable updated/created timestamp.
- Overlap window or other approach for late-arriving/updated records.
- Deduplication and stable identity rules.
- Rate limits, retry policy, and backoff behavior.
- Checkpoint storage, advancement rules, and recovery behavior.
- Known limitations and how they are tested.

Important rules:

1. Do not invent a cursor or claim an API supports one without evidence.
2. Use source-specific checkpoints; do not share one global watermark across all sources.
3. Save progress only after the corresponding records are durably written and validation succeeds.
4. Use an overlap window when suitable, then rely on idempotent upserts to tolerate repeated records.
5. On failure, resume from a safe checkpoint without skipping records.
6. Handle pagination loops, empty pages, malformed responses, timeouts, rate limits, and transient server errors.
7. If a source cannot reliably expose updates, document a safe fallback such as bounded rechecks or periodic reconciliation; state its cost and coverage limits.
8. Record attempted, fetched, accepted, rejected, inserted, updated, unchanged, and failed counts where the source and pipeline can measure them.
9. Make dry-run behavior explicit and ensure it cannot advance production checkpoints.
10. Test the initial load and subsequent incremental run separately.

## 6. Data identity, provenance, and change tracking

- Store source name/namespace and source record ID.
- Store DOI when supplied, using documented normalization for matching.
- Preserve original source values and retrieval metadata.
- Track first-seen and last-seen timestamps when supported by the data model.
- Track source update time separately from ingestion time.
- Keep a clear rule for which source wins when fields conflict; do not silently discard alternate source values.
- Record enough run metadata to explain where a canonical value came from.
- Ensure deleted, withdrawn, or corrected records are handled according to documented source capabilities; do not infer deletions from a missing page alone.

## 7. GitHub Actions automation

Review or implement workflows for both scheduled runs and manual dispatch, subject to repository configuration and user-approved cost limits.

Required safeguards:

- Credentials are stored in GitHub Secrets or an approved secret store, not committed to workflow files.
- Workflow permissions are minimal.
- Concurrency controls prevent overlapping runs from corrupting checkpoint state.
- Jobs have sensible timeouts and use retry logic in the application.
- Failures produce a clear non-zero result and useful logs without exposing secrets.
- Manual runs support safe parameters where needed, such as source selection or backfill mode, with validation.
- Scheduled runs are incremental by default; a full historical backfill must not run accidentally on every schedule.
- Workflow documentation explains required secrets, setup, manual execution, and how to diagnose failures.
- Do not claim scheduled automation is operational until workflow configuration and a successful authorized run are evidenced.

## 8. Testing requirements

Use the repository's actual test framework and conventions. Add or update tests for:

### Source adapters
- Pagination and normal termination.
- Empty pages and malformed responses.
- Retryable versus non-retryable errors.
- Rate limiting and backoff.
- Duplicate records and missing optional fields.
- Incremental filters/cursors and overlap windows where supported.

### Pipeline safety
- Rerunning the same batch does not create duplicates.
- Failed writes do not advance checkpoints.
- A restart resumes from the last safe checkpoint.
- Partial failures are recorded and recoverable.
- Source-specific watermarks remain independent.
- Dry runs do not change production data or checkpoints.

### SQL and Snowflake
- SQL DDL/migrations are present and reviewed.
- Staging deduplication happens before merge.
- Merge logic is deterministic and idempotent.
- SQL data-quality queries return expected results on controlled test data.
- Integration tests use Snowflake only when valid credentials and access are available.
- Without credentials, report the live integration test as `BLOCKED`, not `PASS`; use mocks or isolated unit tests for the remaining checks.

### Automation
- Workflow syntax and configuration are validated.
- Scheduled mode defaults to incremental sync.
- Manual inputs are validated.
- Secrets are referenced safely.
- Failures are visible and do not silently report success.

## 9. Documentation and operational handover

Update documentation based on what the repository actually implements:

- Architecture and data-flow diagram.
- Source capability matrix for all five APIs.
- Setup and configuration instructions.
- Snowflake account/schema setup and SQL deployment order.
- Table/view descriptions and data grain.
- Historical backfill and incremental sync behavior.
- Checkpoint and recovery rules.
- GitHub Actions setup and manual/scheduled operation.
- Test commands and their actual results.
- Known limitations, blocked checks, and next steps.
- Cost safeguards and any operations that require explicit approval.

Keep the architecture documentation consistent with the implementation. If a feature is not implemented, label it `NOT IMPLEMENTED` or `BLOCKED`; do not describe it as complete.

## 10. Required final report from the agent

At completion, produce a report with:

1. Repository audit summary.
2. Files added, changed, and removed.
3. Requirement-to-evidence matrix.
4. SQL artifacts created or improved and what each does.
5. Source-by-source historical and incremental behavior.
6. Tests run, commands used, and real outcomes.
7. GitHub Actions validation and execution status.
8. Snowflake live integration status (`PASS`, `FAIL`, or `BLOCKED`) with reason.
9. Known defects, limitations, and follow-up work.
10. Confirmation that Phase 3 was not started.

Every claim must be supported by file paths, test output, or other direct evidence. Separate successful local tests from live Snowflake tests.

## 11. Completion gate

Phase 2 is complete only when all applicable requirements have evidence and no critical data-integrity issue remains. Any unavailable external credential must be clearly marked `BLOCKED`, not hidden or falsely passed.

Before stopping, verify:

- [ ] All five source adapters follow documented, tested behavior.
- [ ] Historical and incremental paths are distinct and tested.
- [ ] Watermarks are source-specific and advance only after durable validated writes.
- [ ] Retry, resume, and idempotency behavior is tested.
- [ ] Raw payload and provenance are preserved.
- [ ] Snowflake is the only production warehouse target.
- [ ] SQL DDL/migrations, merge/upsert logic, transformations, quality checks, and analytical queries are version-controlled and reviewed.
- [ ] No Python-only replacement of the warehouse SQL layer has been introduced.
- [ ] GitHub Actions supports scheduled incremental runs and safe manual runs.
- [ ] Secrets and cost safeguards are in place.
- [ ] Documentation matches the actual implementation.
- [ ] Phase 1 behavior and tests remain intact.
- [ ] Phase 3 has not been started.
- [ ] A final evidence-based report is delivered.

**Stop condition:** Once the Phase 2 audit, implementation hardening, tests, documentation, and report are complete, stop and wait for explicit user approval. Do not proceed to Phase 3 automatically.
