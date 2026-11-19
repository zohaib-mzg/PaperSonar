# GitHub Actions Workflows

## Workflow A: `extract-load`
Location: `.github/workflows/extract-load.yml`.

Triggers: GitHub cron at `02:30 UTC` (the only scheduler) and `workflow_dispatch` with inputs:
- `mode`: `full` or `incremental`
- `source`: one source or `all`
- `from_date`
- `until_date`
- `dry_run`
- `force`
- `openalex_daily_sync`: confirms the OpenAlex Member+/Partner daily-sync entitlement; scheduled runs read the `OPENALEX_DAILY_SYNC` repository variable

The job extracts selected sources sequentially with `--no-task`, then drains the Snowflake task graph once with `python -m runner.cli trigger --drain`. Full mode is the one-time 100,000+ initial backfill and uses publication-date filters; incremental mode uses `from_updated_date`/`to_updated_date` only. OpenAlex incremental fails closed for an explicit `source=openalex` request and is skipped in `source=all` runs unless confirmation comes from the input or the repository variable; no publication-date fallback is used. `VERIFY:` OpenAlex daily-sync entitlement and current GitHub-hosted runner limits; official docs: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/filter-entity-lists and https://docs.github.com/en/actions/reference/runners/github-hosted-runners.

Steps:
1. Validate input and window.
2. Load only required secrets.
3. Create/claim batch manifest state.
4. Run source adapter.
5. Write deterministic NDJSON and gzip.
6. Calculate file checksum and counts.
7. Upload using Snowflake PUT to the internal stage.
8. Insert one manifest row per file.
9. Verify all expected files and mark source batch `LOADED`.
10. After every selected source is `LOADED`, run `python -m runner.cli trigger --drain`; this repeatedly executes the root task until no batch is `LOADED` or `PROCESSING`.
11. Upload sanitized logs/evidence as workflow artifacts.

Retries must be bounded and use backoff. A partial failure leaves the batch failed/incomplete and eligible for safe resume. Do not mark `LOADED` until every required file is registered and verified. Avoid logging API responses containing unnecessary personal data.

## Workflow B: `deploy-ci`
Location: `.github/workflows/deploy-ci.yml`.

Triggers: `workflow_dispatch` with `confirm=DEPLOY` and push to `main` on SQL/config/runner paths. This workflow never moves research data and never starts extraction.

Steps:
1. Checkout repository and install pinned Python dependencies.
2. Run `ruff` and `pytest` (including SQL static contracts).
3. Authenticate with `SNOWFLAKE_DEPLOY_ROLE` (`PAPERSONAR_ADMIN`, never `ACCOUNTADMIN`).
4. Upload SQL files to the internal `SQL_STAGE` with `PUT` and apply them with `EXECUTE IMMEDIATE FROM`.
5. When `09_tasks/02_task_graph.sql` is deployed, resume the task graph automatically: suspend the root, resume all children, then resume the root. Children must be resumed before the root.
6. Save test results and sanitized logs.
7. Fail the check if any mandatory test fails.

`VERIFY:` the exact syntax and privilege model for `PUT` to the internal stage and `EXECUTE IMMEDIATE FROM`; official docs: https://docs.snowflake.com/en/sql-reference/sql/execute-immediate-from and https://docs.snowflake.com/en/user-guide/tasks-graphs.

## Secrets and permissions
Store private key, passphrase if any, account, username, role, and required connection configuration in GitHub Secrets or appropriately scoped variables. Never print environment variables wholesale. Give workflows the minimum GitHub permissions required. Pin third-party actions to reviewed versions or commit SHAs according to repository policy.

## Resumability and concurrency
- One active extraction job per source/logical window.
- Distinct sources may run concurrently if API etiquette and credit/storage constraints allow.
- Use a durable cursor/checkpoint in the manifest/watermark model.
- On timeout, record failed state and resume from the last confirmed cursor.
- Use stable filenames and checksums.
- Upload is not proof of load; staging COPY and bronze MERGE are separate audited stages.

## Acceptance
- Manual full/incremental dispatch works.
- Scheduled extraction can be disabled without affecting CI.
- CI never moves data.
- Failed extraction cannot mark batch LOADED.
- Retries and concurrency do not duplicate data.
- Secrets are absent from logs.
- CI proves SQL lint, Python tests, DDL deployment, and SQL checks.
- A recreated task graph is resumed before the root can be triggered.
- GitHub Actions is the only scheduler; the Snowflake root has no cron schedule.
- OpenAlex incremental fails closed for an explicit run and is skipped in all-source runs without Member+/Partner daily sync.

## References
- GitHub Actions workflow syntax: https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- GitHub concurrency: https://docs.github.com/en/actions/using-jobs/using-concurrency
- GitHub encrypted secrets: https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
- Snowflake Git repository setup: https://docs.snowflake.com/en/developer-guide/git/git-setting-up
- Snowflake EXECUTE IMMEDIATE FROM: https://docs.snowflake.com/en/sql-reference/sql/execute-immediate-from
