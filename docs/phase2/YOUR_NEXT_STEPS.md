# PaperSonar Phase 2 — Your Snowflake and GitHub Handoff

**Status:** implementation complete; the OpenAlex full load is live-proven through `PUBLISHED`.
See [evidence/2026-11-19-openalex-full-load.md](evidence/2026-11-19-openalex-full-load.md).
**Remaining:** OpenAlex incremental live proof (Member+/Partner plan), other sources, and force-push/tag authorization.

This file lists the actions that require **your** Snowflake account, GitHub settings, API keys, or explicit authorization. All SQL and Python changes are already in the working tree.

---

## 0. What you need before starting

- [ ] Snowflake account URL/account identifier.
- [ ] One-time `ACCOUNTADMIN` access for the initial database, role, and account-level grants.
- [ ] A deploy user that can use `PAPERSONAR_ADMIN`.
- [ ] A loader user that can use `PAPERSONAR_LOADER` (can be the same Snowflake user with a different role).
- [ ] A Snowflake key pair for the service user.
- [ ] `OPENALEX_API_KEY`.
- [ ] `CROSSREF_CONTACT_EMAIL`.
- [ ] GitHub repository admin access to add secrets and configure the `snowflake-production` environment.
- [ ] Explicit approval before any force push.

---

## 1. Create the Snowflake key pair and service user

Generate the key pair locally. Never commit the private key.

```powershell
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out papersonar_key.p8 -nocrypt
openssl rsa -in papersonar_key.p8 -pubout -out papersonar_key.pub
```

In Snowflake, set the public key on the service user:

```sql
ALTER USER <SERVICE_USER> SET RSA_PUBLIC_KEY = '<public key without BEGIN/END lines>';
```

The runner accepts either PEM content or a path to the private key in `SNOWFLAKE_PRIVATE_KEY`.

---

## 2. Run the one-time setup in the correct order

Run these files as `ACCOUNTADMIN` in Snowsight worksheets or with `snowsql -f`.

**Important:** do not run the files in numeric order. `01_roles_and_grants.sql` grants privileges on objects created by `02`–`06`, so those objects must exist first.

```text
sql/00_setup/00_database_schemas.sql
sql/00_setup/02_warehouse_and_monitor.sql
sql/00_setup/03_file_formats_and_stages.sql
sql/00_setup/04_audit_ddl.sql
sql/00_setup/05_reference_ddl.sql
sql/00_setup/06_seed_reference.sql
sql/00_setup/01_roles_and_grants.sql
```

Then grant the roles to your service users:

```sql
GRANT ROLE PAPERSONAR_ADMIN TO USER <DEPLOY_USER>;
GRANT ROLE PAPERSONAR_LOADER TO USER <LOADER_USER>;
GRANT ROLE PAPERSONAR_TRANSFORMER TO USER <TASK_OWNER_USER>;
GRANT ROLE PAPERSONAR_REPORTER TO USER <REPORTER_USER>;
```

Verify the setup:

```sql
SHOW SCHEMAS IN DATABASE PAPERSONAR;
SHOW WAREHOUSES LIKE 'WH_PAPERSONAR_ELT';
SHOW STAGES IN SCHEMA PAPERSONAR.PROJECT_STAGING;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_DW.DIM_DATE;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REF.REF_SOURCE;
SELECT COUNT(*) FROM PAPERSONAR.PROJECT_REF.REF_CATEGORY;
```

Expected seed counts are non-zero. `DIM_DATE` is seeded by the deployment, not by `00_setup`.

---

## 3. Set your local deployment environment

Use `PAPERSONAR_ADMIN` for deployment. Do not use `ACCOUNTADMIN`.

```powershell
$env:PAPERSONAR_TARGET       = "snowflake"
$env:SNOWFLAKE_ACCOUNT       = "<account-identifier>"
$env:SNOWFLAKE_USER          = "<service-user>"
$env:SNOWFLAKE_ROLE          = "PAPERSONAR_ADMIN"
$env:SNOWFLAKE_WAREHOUSE     = "WH_PAPERSONAR_ELT"
$env:SNOWFLAKE_DATABASE      = "PAPERSONAR"
$env:SNOWFLAKE_SCHEMA        = "PROJECT_STAGING"
$env:SNOWFLAKE_PRIVATE_KEY   = "C:\keys\papersonar_key.p8"
# $env:SNOWFLAKE_PRIVATE_KEY_PASSPHRASE = "<passphrase-if-any>"
```

Check the configuration:

```powershell
python -m runner.cli check
```

---

## 4. Deploy the transformation SQL

The deployment command now skips `sql/00_setup` by default. The one-time setup above must be run manually.

```powershell
python -m runner.cli deploy --sql-dir sql --yes
```

This deploys, in sorted order:

```text
01_staging
02_bronze
03_silver
04_categorization
05_dimensions
06_facts
07_reporting
08_audit_dq
09_tasks
```

Do **not** use `--include-setup` in CI or normal deployment. That flag is only for a controlled account-administrator run.

Verify for compile errors:

```sql
SHOW PROCEDURES IN SCHEMA PAPERSONAR.PROJECT_STAGING;
SHOW PROCEDURES IN SCHEMA PAPERSONAR.PROJECT_BRONZE;
SHOW PROCEDURES IN SCHEMA PAPERSONAR.PROJECT_SILVER;
SHOW PROCEDURES IN SCHEMA PAPERSONAR.PROJECT_DW;
SHOW PROCEDURES IN SCHEMA PAPERSONAR.PROJECT_AUDIT;
SHOW PROCEDURES IN SCHEMA PAPERSONAR.PROJECT_REPORTING;
SHOW TASKS IN SCHEMA PAPERSONAR.PROJECT_AUDIT;
```

Because `01_roles_and_grants.sql` was run before the transformation tables existed, re-run it once after the deployment so all current objects are covered:

```sql
-- Run as ACCOUNTADMIN
-- sql/00_setup/01_roles_and_grants.sql
```

Future-table grants are already included, but re-running is a safe verification step.

---

## 5. Start the task graph

`CREATE OR REPLACE TASK` recreates the graph suspended. `python -m runner.cli deploy --sql-dir sql --yes`
(and `deploy-ci.yml`) now prepares it automatically after applying
`sql/09_tasks/02_task_graph.sql`: keep the root suspended and resume every child.
Confirm with:

```sql
SHOW TASKS IN SCHEMA PAPERSONAR.PROJECT_AUDIT;
```

The 9 child/finalizer tasks should show `state = started`. The root should show
`state = suspended` — this is correct. Snowflake refuses to RESUME a task that
has no `SCHEDULE`, `AFTER`, `FINALIZE` or `WHEN`, and this root intentionally has
none. `EXECUTE TASK` can run a suspended root, so GitHub does not need it started.
If you must repair manually, resume children only; leave the root suspended.

**GitHub Actions is the only scheduler.** The Snowflake root has no cron schedule
and runs on demand through `EXECUTE TASK`. GitHub extracts at `02:30 UTC` and calls
`python -m runner.cli trigger --drain` once after every source reaches `LOADED`.
Do not add a second Snowflake schedule and do not RESUME the root.

---

## 6. Smoke-test the procedures

Before loading data, these should safely return `NO_BATCH`:

```sql
CALL PAPERSONAR.PROJECT_AUDIT.SP_CLAIM_BATCH();
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('COPY');
```

Also verify the loader can execute the root task:

```sql
-- Run as ACCOUNTADMIN if needed
GRANT EXECUTE TASK ON ACCOUNT TO ROLE PAPERSONAR_LOADER;
```

---

## 7. Configure GitHub secrets and the production environment

Go to **Repository Settings → Secrets and variables → Actions**.

Add these repository secrets:

| Secret | Value |
|---|---|
| `SNOWFLAKE_ACCOUNT` | Account identifier |
| `SNOWFLAKE_USER` | Service user |
| `SNOWFLAKE_WAREHOUSE` | `WH_PAPERSONAR_ELT` |
| `SNOWFLAKE_DATABASE` | `PAPERSONAR` |
| `SNOWFLAKE_SCHEMA` | `PROJECT_STAGING` |
| `SNOWFLAKE_PRIVATE_KEY` | Full private key PEM or path in the runner environment |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | Only if the key is encrypted |
| `SNOWFLAKE_ROLE` | `PAPERSONAR_LOADER` for the extraction workflow |
| `SNOWFLAKE_DEPLOY_ROLE` | `PAPERSONAR_ADMIN` for the deployment workflow |
| `OPENALEX_API_KEY` | OpenAlex key |
| `CROSSREF_CONTACT_EMAIL` | Contact email for Crossref etiquette |

Add this repository **variable** only after OpenAlex Member+/Partner daily sync is active:

| Variable | Value |
|---|---|
| `OPENALEX_DAILY_SYNC` | `true` |

Until then leave it unset or `false`: scheduled all-source runs skip OpenAlex with a warning, and an explicit `source=openalex` incremental run fails closed. No publication-date fallback is used.

Create the environment **`snowflake-production`** and add required reviewers. The deploy workflow uses this environment for approval gating.

**Do not set `SNOWFLAKE_ROLE=ACCOUNTADMIN`.** Both workflows refuse it.

The deploy workflow uses `SNOWFLAKE_DEPLOY_ROLE`; the extraction workflow uses `SNOWFLAKE_ROLE` (loader). Keep them separate.

---

## 8. Run the first live extraction

Use the loader role for extraction:

```powershell
$env:SNOWFLAKE_ROLE = "PAPERSONAR_LOADER"
```

Start with a local dry run:

```powershell
python -m runner.cli extract --source crossref --mode incremental --dry-run
```

Then load one window without triggering the graph:

```powershell
python -m runner.cli extract --source crossref --mode incremental --no-task
```

Inspect the batch before transformation:

```sql
SELECT * FROM PAPERSONAR.PROJECT_AUDIT.BATCH
ORDER BY CREATED_AT DESC
LIMIT 5;

SELECT * FROM PAPERSONAR.PROJECT_AUDIT.BATCH_MANIFEST
WHERE BATCH_ID = '<batch_id>';

LIST @PAPERSONAR.PROJECT_STAGING.RAW_STAGE;
```

If the batch and files look correct, drain all loaded batches:

```powershell
python -m runner.cli trigger --drain
```

`--drain` keeps triggering the root task until no batch remains `LOADED` or `PROCESSING`.

For a full first load, run each source with `--mode full` and `--no-task`, then `trigger --drain`. Keep the first run small until the live `VERIFY:` items pass.

---

## 9. Capture acceptance evidence

Run these after a batch publishes:

```sql
SELECT * FROM PAPERSONAR.PROJECT_AUDIT.BATCH
WHERE BATCH_ID = '<batch_id>';

SELECT * FROM PAPERSONAR.PROJECT_AUDIT.RUN_LOG
WHERE BATCH_ID = '<batch_id>'
ORDER BY STARTED_AT;

SELECT * FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
WHERE BATCH_ID = '<batch_id>'
ORDER BY RULE_ID;

SELECT * FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH
WHERE BATCH_ID = '<batch_id>';

SELECT * FROM PAPERSONAR.PROJECT_AUDIT.SOURCE_WATERMARK;
```

Task history:

```sql
SELECT *
FROM TABLE(PAPERSONAR.INFORMATION_SCHEMA.TASK_HISTORY(
  SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
  RESULT_LIMIT => 100
))
ORDER BY SCHEDULED_TIME DESC;
```

Then execute the acceptance file:

```text
sql/99_tests/01_acceptance.sql
```

Save sanitized outputs under:

```text
docs/phase2/evidence/
```

Do not save private keys, passphrases, or unsanitized account identifiers.

Acceptance targets:

- [ ] At least 100 dimension rows.
- [ ] At least 10,000 fact rows.
- [ ] Zero orphan facts/bridges.
- [ ] 10,000 facts loaded within 60 minutes of staging.
- [ ] At least one batch reaches `PUBLISHED`.
- [ ] All 12 DQ rules have rows for the batch.
- [ ] A controlled CRITICAL DQ failure leaves the batch unpublished and does not advance the watermark.

For the DQ blocking test, use a scratch batch only. For example, after loading but before triggering, change one manifest `RECORD_COUNT` so `DQ-001` fails. Confirm no `PUBLISHED_BATCH` row and no watermark movement, then repair the test batch.

---

## 10. Live `VERIFY:` checks

These cannot be proven by local tests. Confirm them in Snowflake and record the result:

- [ ] `COPY INTO` with `METADATA$FILENAME` / `METADATA$FILE_ROW_NUMBER` and `SQLROWCOUNT`.
- [ ] arXiv/Zenodo XML extraction with `REGEXP_SUBSTR_ALL(..., 'e', 1)`.
- [ ] DataCite live date-query syntax.
- [ ] `SHA2(TO_JSON(payload))` replay stability.
- [ ] Task finalizer runs after a failed child and marks the batch `FAILED`.
- [ ] Task graph redeployment preserves or safely rebuilds dependencies.
- [ ] `EXECUTE TASK` works for `PAPERSONAR_LOADER`.
- [ ] Materialized view / dynamic table edition support. Those files are manual-only.
- [ ] Trial credits, resource monitor actions, and actual account features.

If any check fails, stop and fix it before loading the remaining sources.

---

## 11. Git and force-push actions

Only do this after the Snowflake work is accepted, or if you are explicitly preparing the branch for review.

- [ ] Create a tag for the intended Phase 1 commit: `phase1-final`.
- [ ] Create a backup branch for the old Phase 2 branch: `phase2-legacy`.
- [ ] Confirm the target branch.
- [ ] Inspect the full diff and untracked files.
- [ ] Get explicit authorization for `--force-with-lease`.
- [ ] Never use plain `--force`.

The implementation is committed and pushed to `origin/phase2`; see `git log` for
the current commit. No tag, backup branch, force push, or merge to `main` has been performed.

---

## 12. What to send back

If you want me to continue, send:

1. The role used for setup and deployment.
2. The first `SHOW TASKS` output (state column).
3. The first failed SQL statement and full error text, if any.
4. The `BATCH`, `RUN_LOG`, and `DQ_RESULT` rows for the first batch.
5. The acceptance query output.
6. Whether you want me to prepare the tag/backup/force-push sequence.

Do not send private keys or passphrases.
