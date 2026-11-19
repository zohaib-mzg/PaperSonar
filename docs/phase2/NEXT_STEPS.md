# What to do next — PaperSonar Phase 2

## Decision: GitHub is the scheduler

- **GitHub Actions** is the only scheduler. The daily cron is `30 2 * * *` (**02:30 UTC**).
- GitHub extracts every source with `--no-task`, then runs `python -m runner.cli trigger --drain` once after all batches reach `LOADED`.
- **Snowflake does not schedule anything.** `TASK_ELT_ROOT` has no `SCHEDULE` and runs only through `EXECUTE TASK`.
- Do not add a second Snowflake cron. Do not schedule sources independently in Snowflake.

This avoids two drivers running the same global `CURRENT_BATCH` and keeps extraction + transformation in one deterministic chain.

---

## 0. Current state

- Code is committed and pushed to `origin/phase2`.
- The OpenAlex full backfill `BATCH_07D9668D4CBED88D815D30CA` reached `PUBLISHED`: 5 files, 168,725 records, 0 critical DQ failures.
- Evidence: [evidence/2026-11-19-openalex-full-load.md](evidence/2026-11-19-openalex-full-load.md).
- No tag, backup branch, force push, or merge to `main` has been performed.

---

## 1. One-time Snowflake setup — as `ACCOUNTADMIN`

1. Generate a key pair and set the public key on the service user:

   ```powershell
   openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out papersonar_key.p8 -nocrypt
   openssl rsa -in papersonar_key.p8 -pubout -out papersonar_key.pub
   ```

   ```sql
   ALTER USER <SERVICE_USER> SET RSA_PUBLIC_KEY = '<public key without BEGIN/END lines>';
   ```

2. Run these setup files manually, in this exact order:

   ```text
   sql/00_setup/00_database_schemas.sql
   sql/00_setup/02_warehouse_and_monitor.sql
   sql/00_setup/03_file_formats_and_stages.sql
   sql/00_setup/04_audit_ddl.sql
   sql/00_setup/05_reference_ddl.sql
   sql/00_setup/06_seed_reference.sql
   sql/00_setup/01_roles_and_grants.sql
   ```

3. Grant roles:

   ```sql
   GRANT ROLE PAPERSONAR_ADMIN       TO USER <DEPLOY_USER>;
   GRANT ROLE PAPERSONAR_LOADER      TO USER <LOADER_USER>;
   GRANT ROLE PAPERSONAR_TRANSFORMER TO USER <TASK_OWNER_USER>;
   GRANT ROLE PAPERSONAR_REPORTER    TO USER <REPORTER_USER>;
   GRANT EXECUTE TASK ON ACCOUNT TO ROLE PAPERSONAR_LOADER;
   ```

4. Re-run `sql/00_setup/01_roles_and_grants.sql` once **after** the first full SQL deployment so grants cover newly created objects.

Never use `ACCOUNTADMIN` in GitHub Actions or normal deployment.

---

## 2. Configure GitHub

Repository → **Settings → Secrets and variables → Actions**.

### Secrets

| Secret | Value |
|---|---|
| `SNOWFLAKE_ACCOUNT` | Account identifier |
| `SNOWFLAKE_USER` | Service user |
| `SNOWFLAKE_WAREHOUSE` | `WH_PAPERSONAR_ELT` |
| `SNOWFLAKE_DATABASE` | `PAPERSONAR` |
| `SNOWFLAKE_SCHEMA` | `PROJECT_STAGING` |
| `SNOWFLAKE_PRIVATE_KEY` | Full private key PEM |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | Only if encrypted |
| `SNOWFLAKE_ROLE` | `PAPERSONAR_LOADER` |
| `SNOWFLAKE_DEPLOY_ROLE` | `PAPERSONAR_ADMIN` |
| `OPENALEX_API_KEY` | OpenAlex key |
| `CROSSREF_CONTACT_EMAIL` | Contact email for Crossref etiquette |

### Variable

Only after OpenAlex **Member+/Partner daily sync** is active:

| Variable | Value |
|---|---|
| `OPENALEX_DAILY_SYNC` | `true` |

Until then leave it unset or `false`. Scheduled all-source runs skip OpenAlex with a warning; an explicit `source=openalex` incremental run fails closed. There is no publication-date fallback.

### Environment

Create environment **`snowflake-production`** with required reviewers. `deploy-ci.yml` uses it for approval gating.

---

## 3. Deploy SQL

`deploy-ci.yml` auto-deploys only on pushes to `main` for `sql/**`, `config/**`, `src/runner/**`, `pyproject.toml`, and the workflow itself. Our push was to `phase2`, so do one of these:

- Open a PR `phase2 → main` and merge it, **or**
- Actions → **deploy-ci** → Run workflow → branch `phase2` → input exactly `DEPLOY`.

Local equivalent:

```powershell
$env:SNOWFLAKE_ROLE = "PAPERSONAR_ADMIN"
python -m runner.cli deploy --sql-dir sql --yes
```

Deployment resumes the task graph automatically. Verify:

```sql
SHOW TASKS IN SCHEMA PAPERSONAR.PROJECT_AUDIT;
```

All 10 tasks must show `state = started`. If SQL was applied manually in Snowsight instead of the CLI/deploy workflow, resume children first, then the root.

---

## 4. First live incremental run

The daily cron runs by itself at 02:30 UTC. To test manually first:

Actions → **extract-load** → Run workflow:

- `source`: `all`
- `mode`: `incremental`
- `dry_run`: `true` for the first check, then `false`
- `openalex_daily_sync`: only `true` if the Member+/Partner plan is active

Expected: four sources load (`crossref`, `arxiv`, `datacite`, `zenodo`); OpenAlex is skipped with a warning until the variable/input confirms the plan.

---

## 5. Verify the orchestration

```sql
-- Tasks
SHOW TASKS IN SCHEMA PAPERSONAR.PROJECT_AUDIT;

-- Batches
SELECT * FROM PAPERSONAR.PROJECT_AUDIT.BATCH
ORDER BY CREATED_AT DESC LIMIT 10;

-- Stage-by-stage execution
SELECT * FROM PAPERSONAR.PROJECT_AUDIT.RUN_LOG
ORDER BY STARTED_AT DESC LIMIT 30;

-- DQ gate
SELECT * FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
ORDER BY CHECKED_AT DESC LIMIT 30;

-- Publication
SELECT * FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH
ORDER BY PUBLISHED_AT DESC LIMIT 10;

-- Snowflake task history
SELECT *
FROM TABLE(PAPERSONAR.INFORMATION_SCHEMA.TASK_HISTORY(
  SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
  RESULT_LIMIT => 100
))
ORDER BY SCHEDULED_TIME DESC;
```

Save sanitized outputs under `docs/phase2/evidence/`. Never save private keys, passphrases, or unsanitized account identifiers.

---

## 6. Force push / tag / backup — only with approval

- Tag the intended Phase 1 commit: `phase1-final`.
- Create a backup branch: `phase2-legacy`.
- Confirm target branch and inspect the diff.
- Use `--force-with-lease` only with explicit authorization. Never plain `--force`.

Nothing here has been tagged, backed up, force-pushed, or merged to `main` yet.

---

## Quick reference

| Item | Owner | Value |
|---|---|---|
| Scheduler | GitHub Actions | `30 2 * * *` (02:30 UTC) |
| Transformation | Snowflake task graph | `TASK_ELT_ROOT` + 9 children/finalizer, on demand |
| Extraction role | GitHub secret | `PAPERSONAR_LOADER` |
| Deploy role | GitHub secret | `PAPERSONAR_ADMIN` |
| Approval environment | GitHub | `snowflake-production` |
| OpenAlex incremental gate | Repo variable | `OPENALEX_DAILY_SYNC=true` after Member+ |
| Detailed setup | This repo | [YOUR_NEXT_STEPS.md](YOUR_NEXT_STEPS.md) |
