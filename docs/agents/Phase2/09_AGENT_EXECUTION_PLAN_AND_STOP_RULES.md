# 09. Agent Execution Plan and Stop Rules

## Instruction to implementation agent

Implement Phase 2 in the existing PaperSonar repository. Treat this pack as the contract and inspect the actual repository before editing. Do not ask the user to decide matters already settled here. Snowflake is mandatory for production; never add a production fallback to another database. If access to a no-cost Snowflake account is unavailable, continue deterministic implementation/tests where possible, but mark live acceptance as BLOCKED.

## Implementation order

### Step 0: Audit and baseline
- Inspect repository tree, current architecture, source connectors, SQL/DDL, tests, workflow files, and documentation.
- Run existing tests and capture actual baseline results.
- Create/update `docs/phase2/REPOSITORY_AUDIT.md`.
- Map each requirement to code, test, and documentation.
- Stop only if the repository is inaccessible or destructive changes would be unavoidable.

### Step 1: Configuration and runtime
- Add typed configuration and `.env.example` with placeholders only.
- Fix the production target to Snowflake; reject other targets in production.
- Add secret-safe logging, `.gitignore` rules, and startup validation.
- Keep unit tests runnable with a mocked Snowflake adapter, but never imply that mocks prove production connectivity.

### Step 2: Snowflake operational state
- Implement run, source checkpoint/state, batch/manifest, and quarantine tables in Snowflake.
- Add versioned, repeatable migrations; do not use destructive resets.
- Test transaction and checkpoint behavior, including failure rollback/unchanged checkpoint.

### Step 3: Raw persistence
- Add raw payload writer and manifest writer.
- Make each page/window durable before marking it complete.
- Add hashes, source identifiers, retrieval timestamps, parser/schema versions, and run IDs.
- Use durable storage; GitHub runner disk must not be the sole copy.

### Step 4: Source adapters
Implement OpenAlex, Crossref, arXiv, DataCite, and Zenodo in that order. Use fixtures and source-specific pagination.
- OpenAlex: cursor backfill plus bounded free reconciliation; document its coverage limitation.
- Crossref: index-date windows plus cursor.
- arXiv: OAI-PMH datestamp windows and resumption tokens.
- DataCite: OAI-PMH and/or verified updated-date REST query.
- Zenodo: OAI-PMH, including expired-token recovery.
- Verify official docs and record a source capability matrix with links and verification date.

### Step 5: Staging and canonicalization
- Normalize DOI and dates, preserve source crosswalks, apply documented field precedence, and quarantine conflicts.
- Test cross-source duplicates and conflicting metadata.

### Step 6: Snowflake dimensional warehouse
- Reconcile actual DDL with the approved model and dictionary.
- Create dimensions, facts, and bridges using Snowflake-compatible migrations.
- Implement `MERGE`-based idempotent loaders and integrity checks.
- Keep documented grain; do not silently change approved grain.

### Step 7: Orchestration and recovery
- Implement `backfill`, `sync`, `validate`, `load`, and safe replay modes.
- Add retry/backoff, partial-run semantics, structured summaries, and failure recovery.
- A source checkpoint advances only after its complete window is durably committed to the required storage and warehouse stages.

### Step 8: Snowflake live integration
- Implement secure supported authentication, connection handling, migrations, and smoke tests.
- Verify permissions, idempotency, transaction boundaries, and one end-to-end sample load.
- If credentials/account access are unavailable, mark live verification BLOCKED; do not substitute another database.

### Step 9: GitHub Actions automation
- Add scheduled and manual workflows with least privilege, concurrency control, timeout, secret validation, and job summary.
- Run deterministic tests before ingestion.
- Scheduled workflow calls `sync`, never full `backfill`.
- Persist checkpoints/manifests durably in Snowflake and ensure raw data follows the approved durable storage design.
- Do not enable a schedule until configuration and cost safeguards are reviewed.

### Step 10: Quality gates
- Run deterministic tests without network access.
- Run live Snowflake smoke tests and small API checks only when credentials, access, and limits permit.
- Test idempotency, pagination/resumption, forced failures, checkpoint behavior, and warehouse integrity.
- Generate an acceptance report with real outputs.

### Step 11: Documentation
Update root README and docs with setup, configuration, backfill vs sync, source capability matrix, Snowflake migrations, GitHub Actions secrets, recovery/replay, limitations, commands, and actual implementation status.

## Implementation quality rules

- Use small, reviewable modules and clear names. Keep source-specific code separate.
- Never hardcode credentials or query secrets.
- Pin/bound dependencies and update lock files when applicable.
- Never disable tests or weaken checks to make CI pass.
- Never run full historical backfill in routine CI.
- Do not delete raw batches during retry.
- No destructive database reset in shared or Snowflake environments.
- Provide migrations and rollback notes.
- Unit tests may mock Snowflake; production acceptance may not be based on mocks alone.
- Every command needs help text and documented examples.
- Do not claim an API was verified unless official docs were checked or a test was actually run.

## Mandatory completion report

Report: changed files; actual architecture; status for each source; exact incremental strategy and limits; commands and real test results; record counts only if measured; idempotency/failure recovery evidence; Snowflake live status; GitHub Actions workflow status; required secrets still needed; known limitations and unmet criteria; and confirmation Phase 3 was not started.

Use `PASS`, `FAIL`, `BLOCKED`, or `NOT TESTED` for each acceptance criterion. If Snowflake live access is missing, do not declare Phase 2 accepted.

## Hard stop rule

Stop immediately after Phase 2 work and its acceptance report are complete, or after clearly reporting that acceptance is blocked by unavailable mandatory Snowflake access. Do not begin Phase 3. Do not create Power BI dashboards, publish reports, build a web application, add sources, or implement product features. End with the exact statement:

**“Phase 2 implementation has stopped at the defined boundary. Phase 3 has not been started.”**
