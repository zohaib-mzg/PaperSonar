# What to do next — PaperSonar Phase 2

## Decision: GitHub is the scheduler

- **GitHub Actions** is the only scheduler. The daily cron is `0 1 * * *` (**01:00 UTC**).
- GitHub extracts every source with `--no-task`, then runs `python -m runner.cli trigger --drain` once after all batches reach `LOADED`.
- **Snowflake does not schedule anything.** `TASK_ELT_ROOT` has no `SCHEDULE` and runs only through `EXECUTE TASK`.
- Do not add a second Snowflake cron. Do not schedule sources independently in Snowflake.

This avoids two drivers running the same global `CURRENT_BATCH` and keeps extraction + transformation in one deterministic chain.

---

## 0. Current state

Phase 2 is **closed with known limits** as of 2026-11-22. Everything below is
kept as the reference procedure for a fresh account or a repeat deployment.

- Code is committed and pushed to `origin/main`; Phase 3 work continues on the
  `phase3` branch.
- Published batches (live): OpenAlex `BATCH_07D9668D4CBED88D815D30CA`,
  Crossref `BATCH_B51983B70B26023F22201AE2` and
  `BATCH_DAB12A7209208BE375D89C0B`, arXiv `BATCH_3DF8101D66B0797A217FD877`,
  Zenodo `BATCH_A75F9C61B9BF73B40CBC8C54` — all with `critical_failures=0`.
- Evidence:
  [evidence/2026-11-19-openalex-full-load.md](evidence/2026-11-19-openalex-full-load.md)
  and
  [evidence/2026-11-22-live-verification.md](evidence/2026-11-22-live-verification.md).
- Two defects were found by live verification and fixed: the DQ-012
  crosswalk fan-out (false CRITICAL failure) and the DataCite oversize-text
  truncation. Both are covered by regression tests.
- No tag, backup branch, force push, or merge to `main` has been performed
  beyond the normal fast-forward merges.

### 0.1 Remaining Phase 2 housekeeping (account owner)

Run these once as `ACCOUNTADMIN`; they are audit-truth fixes, not new
features.

```sql
-- 1. Close the batch that is stuck in EXTRACTING (DQ-001 failed: 4 file count mismatches)
UPDATE PAPERSONAR.PROJECT_AUDIT.BATCH
SET STATUS = 'FAILED',
    ERROR_SUMMARY = 'Closed manually: DQ-001 file count mismatch; staged files will not be replayed',
    FINISHED_AT = CURRENT_TIMESTAMP()
WHERE BATCH_ID = 'BATCH_70CEE97747ED6A70D3E40411'
  AND STATUS NOT IN ('PUBLISHED', 'FAILED', 'SKIPPED');

-- 2. Point the service user at the roles and warehouse that actually exist
ALTER USER SVC_PAPERSONAR SET DEFAULT_ROLE = 'PAPERSONAR_LOADER';
ALTER USER SVC_PAPERSONAR SET DEFAULT_WAREHOUSE = 'WH_PAPERSONAR_ELT';

-- 3. Drop the unused warehouse
DROP WAREHOUSE IF EXISTS PAPERSONAR_WH;
```

Optional: revoke `PAPERSONAR_ADMIN` from the service user (keep the owner
grant) and suspend the account-default `COMPUTE_WH` if it is not used
elsewhere.

### 0.2 Known limits carried into Phase 3

| Limit | Handling |
|---|---|
| Incremental OpenAlex needs a Member+/Partner plan (HTTP 403) | keep OpenAlex on explicit full windows; no publication-date fallback |
| DataCite backlog (windows 2026-11-18, 2026-11-19) | replay one window per run after the width fix; not required for acceptance |
| Categorization coverage 4–6% vs the 60% DQ-009 target | Phase 3 WP1: expand `config/taxonomy.yml`, seed `REF_TAXONOMY_MAP`, re-categorize published batches |
| `DIM_TOPIC` has no fact bridge | Phase 3 WP2 adds it only if the business questions require it |

---

## 1. One-time Snowflake setup — as `ACCOUNTADMIN` (completed 2026-11-18)

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

## 2. Configure GitHub (completed 2026-11-19)

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

## 3. Deploy SQL (completed; now automatic on push to `main`)

`deploy-ci.yml` auto-deploys only on pushes to `main` for `sql/**`, `config/**`, `src/runner/**`, `pyproject.toml`, and the workflow itself. Our push was to `phase2`, so do one of these:

- Open a PR `phase2 → main` and merge it, **or**
- Actions → **deploy-ci** → Run workflow → branch `phase2` → input exactly `DEPLOY`.

Local equivalent:

```powershell
$env:SNOWFLAKE_ROLE = "PAPERSONAR_ADMIN"
python -m runner.cli deploy --sql-dir sql --yes
```

Deployment prepares the task graph automatically. Verify:

```sql
SHOW TASKS IN SCHEMA PAPERSONAR.PROJECT_AUDIT;
```

The 9 child/finalizer tasks must show `state = started`. The root must show
`state = suspended` — that is correct. Snowflake rejects `ALTER TASK ... RESUME`
on a root with no `SCHEDULE`, `AFTER`, `FINALIZE` or `WHEN`; GitHub runs the
suspended root with `EXECUTE TASK`. Do not resume the root manually.

---

## 4. First live incremental run (completed 2026-11-19..21)

The daily cron runs by itself at 01:00 UTC. To test manually first:

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

The maintained read-only query packs are:

| File | Purpose |
|---|---|
| `sql/99_tests/01_acceptance.sql` | acceptance queries from the specification pack |
| `sql/99_tests/02_phase2_verification.sql` | full verification pack: environment, tasks, pipeline state, model, publication, cost, failure drill-down (sections A–H) |
| `sql/99_tests/03_phase2_closeout.sql` | closeout pack: batch ledger, publication contract, latest DQ verdict, watermarks, housekeeping (sections J) |

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
| Scheduler | GitHub Actions | `0 1 * * *` (01:00 UTC) |
| Transformation | Snowflake task graph | `TASK_ELT_ROOT` + 9 children/finalizer, on demand |
| Extraction role | GitHub secret | `PAPERSONAR_LOADER` |
| Deploy role | GitHub secret | `PAPERSONAR_ADMIN` |
| Approval environment | GitHub | `snowflake-production` |
| OpenAlex incremental gate | Repo variable | `OPENALEX_DAILY_SYNC=true` after Member+ |
| Detailed setup | This repo | [YOUR_NEXT_STEPS.md](YOUR_NEXT_STEPS.md) |
| Phase 2 closeout evidence | This repo | [evidence/2026-11-22-live-verification.md](evidence/2026-11-22-live-verification.md) |
| Phase 3 plan | This repo | [../phase3/PHASE3_PLAN.md](../phase3/PHASE3_PLAN.md) |
