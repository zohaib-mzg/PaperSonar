# 06. Mandatory Snowflake Setup and GitHub Actions Automation

## 1. Non-negotiable deployment rule

Snowflake is the required production warehouse for PaperSonar Phase 2. The production pipeline must not support a PostgreSQL, SQLite, local-file, or other database fallback. Local deterministic tests may use fixtures and a mocked Snowflake adapter, but production ingestion, warehouse loading, and acceptance require a real Snowflake connection.

**Cost rule:** Use only a no-cost Snowflake trial, credits, or offer that is currently available to the account. Snowflake is not guaranteed to be permanently free. Do not activate paid resources, upgrade to a paid plan, or allow uncontrolled compute usage. If no no-cost account access is available or it expires, stop production deployment and report **BLOCKED**. Do not replace Snowflake with another database.

## 2. Account and resource setup

The user/account owner must create or access a Snowflake account under a currently available no-cost offer. The implementation agent must verify current Snowflake documentation and the account's terms before creating resources. Do not assume an offer is available.

Create only the minimum required resources: database, schema, role, warehouse, service user, and authentication configuration. Use a small auto-suspending warehouse, set conservative statement timeouts where supported, and avoid unnecessary warehouses or oversized compute. Never run destructive reset statements against an existing account.

Use a dedicated least-privilege service role/user for GitHub Actions. Grant only the required database/schema usage, table creation/migration permissions where required, warehouse usage, and DML permissions. Separate one-time migration permissions from routine ingestion permissions where practical.

## 3. Authentication

Prefer Snowflake key-pair authentication supported by the current official connector. Store the private key and passphrase only in GitHub Actions secrets. Do not commit key files or print secrets in logs. If the repository already uses another officially supported secure method, document why it is suitable and ensure no long-lived password is stored in source code.

## 4. Required GitHub Actions secrets

Create these repository or environment secrets (names may be aligned to existing repository conventions, but every required value must be mapped):

- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_USER`
- `SNOWFLAKE_ROLE`
- `SNOWFLAKE_WAREHOUSE`
- `SNOWFLAKE_DATABASE`
- `SNOWFLAKE_SCHEMA`
- `SNOWFLAKE_PRIVATE_KEY`
- `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` only if the key is encrypted

Add non-secret repository variables for non-sensitive runtime settings, source filters, and schedule configuration as needed. Do not put credentials in repository variables. Provide a `.env.example` containing placeholders only.

## 5. Runtime configuration and fail-closed behavior

- Production target is fixed to `snowflake`; remove or reject production target switches to PostgreSQL/SQLite/local files.
- Validate all required Snowflake settings before any source ingestion starts. Missing settings must produce a clear, non-secret error and a non-zero exit status.
- Run a lightweight connection/permission smoke test before ingestion.
- Do not silently downgrade to another database if connection fails.
- Separate `backfill`, `sync`, `load`, and `validate` commands. Scheduled execution must call `sync`, never a full historical backfill.
- Persist checkpoints, run manifests, and ingestion state in Snowflake. Raw payloads must be durably stored according to the approved raw-storage design; do not rely on ephemeral GitHub runner disk as the only copy.

## 6. GitHub Actions workflow requirements

Create a workflow under `.github/workflows/` with: `schedule` and `workflow_dispatch` triggers; least-privilege `permissions`; a concurrency group to prevent overlapping sync runs; a bounded job timeout; dependency installation from locked/pinned project dependencies; lint/type checks and deterministic tests before ingestion; secret validation; Snowflake connectivity test; then scheduled incremental sync and warehouse load; final validation; and a concise GitHub Actions job summary.

The schedule must respect each source's published rate limits and the configured free-access strategy. Do not assume that a daily schedule is appropriate for every source. Use retry/backoff and `Retry-After` when supplied. Ensure a failed source does not advance its checkpoint. The workflow must preserve the distinction between successful, partial, failed, and blocked runs.

Manual dispatch should expose a constrained mode choice such as `sync`, `backfill`, or `validate`, with safe defaults. Full backfills must require deliberate manual invocation, date/window bounds, and conservative page/batch limits. Never let the normal scheduled trigger start a backfill.

## 7. Operational safeguards

- Set auto-suspend to the smallest sensible interval supported by the account.
- Resume compute only for the required job and avoid idle compute.
- Add query/job timeouts and batch limits.
- Avoid repeated DDL and warehouse creation on every run.
- Log run ID, source, date window, pages, counts, durations, retry counts, and outcome; never log secrets or full connection strings.
- Do not automatically upgrade, enable paid features, or create larger resources.
- If the no-cost offer is unavailable or expires, disable scheduled production ingestion until an authorized no-cost setup is available.

## 8. Required verification

Before marking this file complete, provide evidence for all of the following:

1. Required secrets are documented and checked without revealing values.
2. Production configuration rejects non-Snowflake targets.
3. Missing credentials fail before source API calls.
4. Snowflake connectivity and required permissions are tested.
5. Migrations are repeatable and non-destructive.
6. A small end-to-end test writes a fixture or permitted sample through staging into Snowflake and validates its result.
7. Re-running the same batch does not create duplicates.
8. A forced failure leaves the relevant checkpoint unchanged.
9. GitHub Actions workflow syntax and deterministic tests pass.
10. Manual workflow execution is tested; scheduled execution is enabled only after the owner confirms the account and cost safeguards.
11. The account's no-cost status and limits were checked by the account owner; do not claim permanent free availability.

If real credentials or account access are not available to the agent, mark live Snowflake and workflow verification as **BLOCKED / NOT TESTED**. Do not claim completion and do not switch to another database.
