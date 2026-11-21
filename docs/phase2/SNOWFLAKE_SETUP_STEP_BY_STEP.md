# PaperSonar — Snowflake Setup, Step by Step (do this → run this)

**Who this is for:** you, the account owner. Everything here is run by you once;
after that the pipeline (`papersonar` CLI + GitHub Actions) does the rest.

**Golden rules:** Snowflake is the only production warehouse (no PostgreSQL/
SQLite/local fallback). Use a **no-cost** trial/credits offer only — never
activate paid features or upgrades. Nothing in this guide deletes existing data.

**Time needed:** ~20–30 minutes.

---

## Overview — what runs where

```
[Five scholarly APIs]                [Snowflake]                       [GitHub Actions]
 OpenAlex / Crossref / arXiv /   →   PROJECT_OPS   (runs, checkpoints,   scheduled sync +
 DataCite / Zenodo                   raw payload stage)                manual dispatch
        │                        →   PROJECT_STAGING (validated rows,     │
        │                            quarantine)                       │ runs on schedule only
        └── papersonar CLI /        →   PROJECT_DW     (canonical dims,    ▼
            GitHub Actions runner       facts, bridges)                 job summary + quality
                                    →   PROJECT_REPORTING (views)       gate
```

You create the account + resources; `python -m runner.cli deploy --sql-dir sql
--yes` creates the seven schemas, tables, views, stages and the task graph
from the versioned scripts in `sql/`.

---

## STEP 1 — Create the no-cost account

1. Go to **<https://signup.snowflake.com/>** and choose the **free 30-day trial**
   (or an educational/no-cost offer you have access to). No credit card is
   charged; the trial includes free credits.
2. Choose:
   - Cloud provider: **AWS** (any region is fine; pick one near you, e.g. `eu-central-1`).
   - Edition: **Standard** (sufficient — never pick editions just for features).
3. After signup you land in **Snowsight** (the web UI). Look at the bottom-left
   of Snowsight: your **account identifier** looks like
   `XY12345.EU-CENTRAL-1` (or `ORGNAME-ACCOUNTNAME` on newer accounts).
   **Write it down — this is `SNOWFLAKE_ACCOUNT`.**

> ⚠️ Trial accounts expire (~30 days). When it expires, report it as **BLOCKED**
> and stop — do not upgrade to paid, do not switch databases.

---

## STEP 2 — Create the resources (one worksheet, copy-paste)

**Where:** Snowsight → left sidebar **Worksheets** → **+** → **SQL Worksheet**.

**Important:** make sure the worksheet context (top bar) shows the role
`ACCOUNTADMIN` (or `SYSADMIN`) — the default after signup.

Paste **all** of the following and click **Run All** (or press
`Ctrl+Shift+Enter`):

```sql
-- =====================================================================
-- PaperSonar Phase 2 one-time setup — run as ACCOUNTADMIN in one worksheet
-- =====================================================================

-- 1) Database + the seven approved schemas
CREATE DATABASE IF NOT EXISTS PAPERSONAR;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_STAGING;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_BRONZE;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_SILVER;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_DW;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_REPORTING;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_AUDIT;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.PROJECT_REF;
```

The warehouse, the four roles, the resource monitor, the raw stage and every
table, view and task are created by the versioned setup scripts in
`sql/00_setup/` through `sql/09_tasks/`. Deploy them in file order with:

```powershell
python -m runner.cli deploy --sql-dir sql --yes
```

The deployment needs an administrative role (`PAPERSONAR_ADMIN`), not
`ACCOUNTADMIN`, and it leaves the Snowflake root task suspended on purpose:
GitHub Actions is the only scheduler.

| Phase 2 object | Name |
|---|---|
| Warehouse | `WH_PAPERSONAR_ELT` (XSMALL, auto-suspend 60 s) |
| Resource monitor | `RM_PAPERSONAR_ELT` |
| Roles | `PAPERSONAR_ADMIN`, `PAPERSONAR_LOADER`, `PAPERSONAR_TRANSFORMER`, `PAPERSONAR_REPORTER` |
| Service user | `SVC_PAPERSONAR` (key-pair only, no password) |
| Schemas | `PROJECT_STAGING`, `PROJECT_BRONZE`, `PROJECT_SILVER`, `PROJECT_DW`, `PROJECT_REPORTING`, `PROJECT_AUDIT`, `PROJECT_REF` |

> The older Phase 1 objects `PAPERSONAR_WH`, `PAPERSONAR_INGEST` and the
> `INGEST` schema are **not** part of Phase 2. If they exist in the account,
> they are leftovers and can be dropped after Phase 2 is verified.

---

## STEP 3 — Generate the key pair (on your Windows machine)

The service user authenticates with a **key pair**, not a password. You need
`openssl` — easiest source on Windows is **Git Bash** (you have Git installed).

**Open Git Bash** (Start → "Git Bash") and run, line by line:

```bash
mkdir -p ~/.papersonar && cd ~/.papersonar

# Private key (unencrypted PKCS8 PEM — this is SNOWFLAKE_PRIVATE_KEY later)
openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -outform pem > papersonar_key.p8

# Public key (used in the next step)
openssl rsa -in papersonar_key.p8 -pubout -out papersonar_key.pub

# Print the public key body (the long base64 line):
grep -v 'PUBLIC KEY' papersonar_key.pub | tr -d '\n' && echo
```

The last command prints one very long string like
`MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...` — **copy it fully** (this is the
*public key body*, not a fingerprint).

**Windows alternative (PowerShell, if you prefer ssh-keygen):**

```powershell
mkdir $HOME\.papersonar -Force; cd $HOME\.papersonar
ssh-keygen -t rsa -b 2048 -m PKCS8 -f .\papersonar_key -N '""'
# papersonar_key      = private key (PKCS8 PEM — use this as the secret)
# papersonar_key.pub  = public key; the body is the 2nd token on its single line:
$parts = (Get-Content .\papersonar_key.pub).Split(' '); $parts[1] | Set-Clipboard
```

> 🔐 **Security:** keep `papersonar_key.p8` private — never commit it, never
> paste it anywhere except the GitHub secret (Step 5) / your local env (Step 6).

---

## STEP 4 — Assign the public key to the service user

Back in the Snowsight worksheet (still as ACCOUNTADMIN), run — paste your
copied body inside the quotes:

```sql
ALTER USER SVC_PAPERSONAR
  SET RSA_PUBLIC_KEY = 'MIIBIjANBgkqh...paste-the-full-key-body-here...';

-- Verify it was set (you should see RSA_PUBLIC_KEY in the output):
DESC USER SVC_PAPERSONAR;
```

> ❌ **Do NOT paste the key fingerprint here.** Snowflake wants the public key
> *body* (the `MIIB...` string). A fingerprint will cause auth failures.

---

## STEP 5 — Add the GitHub secrets

**Where:** your repo on GitHub → **Settings** → **Secrets and variables** →
**Actions** → **New repository secret**.

Add each secret with **exactly** these names:

| # | Secret name | Value — where it comes from |
|---:|---|---|
| 1 | `SNOWFLAKE_ACCOUNT` | account identifier from Step 1, e.g. `XY12345.EU-CENTRAL-1` |
| 2 | `SNOWFLAKE_USER` | `SVC_PAPERSONAR` |
| 3 | `SNOWFLAKE_ROLE` | `PAPERSONAR_LOADER` (extraction workflow) |
| 4 | `SNOWFLAKE_WAREHOUSE` | `WH_PAPERSONAR_ELT` |
| 5 | `SNOWFLAKE_DATABASE` | `PAPERSONAR` |
| 6 | `SNOWFLAKE_SCHEMA` | `PROJECT_STAGING` |
| 7 | `SNOWFLAKE_PRIVATE_KEY` | open `papersonar_key.p8` in a text editor, copy **the entire file** including the `-----BEGIN PRIVATE KEY-----` and `-----END PRIVATE KEY-----` lines (multiline paste is fine) |
| 8 | `OPENALEX_API_KEY` | free OpenAlex premium key: <https://openalex.org/users/me> → "Get a key" (needed past the first page of results) |
| 9 | `CROSSREF_CONTACT_EMAIL` | your email for the Crossref polite pool (e.g. `you@example.com`) |
| 10 | `SNOWFLAKE_DEPLOY_ROLE` | `PAPERSONAR_ADMIN` — used only by the deployment workflow |

Optional: `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` — only if you generated an
**encrypted** key (we used `-nocrypt`, so normally not needed).

> Names must match exactly — the pipeline fails closed with a clear message
> listing any missing secret names (values are never printed).

---

## STEP 6 — Run it locally (PowerShell, right now)

Open **PowerShell** in the repo folder (`D:\PaperSonar`) and set the
environment variables (same values as the secrets):

```powershell
cd D:\PaperSonar

$env:PAPERSONAR_TARGET = "snowflake"
$env:SNOWFLAKE_ACCOUNT   = "XY12345.EU-CENTRAL-1"     # your account identifier
$env:SNOWFLAKE_USER      = "SVC_PAPERSONAR"
$env:SNOWFLAKE_ROLE      = "PAPERSONAR_LOADER"
$env:SNOWFLAKE_WAREHOUSE = "WH_PAPERSONAR_ELT"
$env:SNOWFLAKE_DATABASE  = "PAPERSONAR"
$env:SNOWFLAKE_SCHEMA    = "PROJECT_STAGING"
$env:SNOWFLAKE_PRIVATE_KEY = Get-Content -Raw "$HOME\.papersonar\papersonar_key.p8"
$env:OPENALEX_API_KEY      = "<your OpenAlex key>"
$env:CROSSREF_CONTACT_EMAIL = "<your email>"
```

Then run the pipeline in this exact order:

```powershell
# 1. Configuration check (validates sources, taxonomy and DQ configuration)
python -m runner.cli check

# 2. Deploy the SQL layers and the task graph (needs PAPERSONAR_ADMIN)
python -m runner.cli deploy --sql-dir sql --yes

# 3. Extract one source window and load it into Snowflake
python -m runner.cli extract --source crossref --mode incremental --no-task

# 4. Drain the Snowflake task graph (one root per LOADED batch)
python -m runner.cli trigger --drain

# 5. Show batch status and per-source totals
python -m runner.cli report
```

**What to expect:**

| Command | Success looks like |
|---|---|
| `check` | `configuration OK` with no missing key reported |
| `deploy` | one line per SQL file, ending with the task graph prepared |
| `extract` | a new `BATCH_*` id in `LOADED` state with its manifest registered |
| `trigger --drain` | batches end in `PUBLISHED` (or `FAILED` with a recorded DQ reason) |
| `report` | one row per source with batch counts and record totals |

Exit codes: `0` succeeded · `1` partial · `2` error. Re-running `sync` is
always safe (idempotent upserts).

**Optional — historical backfill (deliberate, bounded):**

```powershell
.venv\Scripts\papersonar.exe backfill
```

Bounded to 60 windows per source per run; re-run until historical coverage is
complete. Never runs on a schedule by accident.

---

## STEP 7 — Verify in Snowsight that data actually landed

New worksheet (**use role PAPERSONAR_ADMIN**):

```sql
USE ROLE PAPERSONAR_ADMIN;
USE DATABASE PAPERSONAR;

-- Batch lifecycle: the published batches are the visible contract
SELECT BATCH_ID, SOURCE_NAME, EXTRACTION_MODE, STATUS, FILE_COUNT, RECORD_COUNT,
       CREATED_AT, FINISHED_AT
FROM PROJECT_AUDIT.BATCH ORDER BY CREATED_AT DESC LIMIT 10;

-- Publication registry (one row per published batch, zero critical DQ failures)
SELECT BATCH_ID, PUBLISHED_AT, PUBLISHED_BY, DQ_SUMMARY, IS_CAPPED
FROM PROJECT_AUDIT.PUBLISHED_BATCH ORDER BY PUBLISHED_AT DESC;

-- Canonical outputs in the star schema
SELECT COUNT(*) AS RESEARCH_OUTPUTS FROM PROJECT_DW.FACT_RESEARCH_OUTPUT;

-- DQ gate evidence: critical failures must be zero for every published batch
SELECT BATCH_ID,
       COUNT_IF(SEVERITY = 'CRITICAL' AND STATUS = 'FAIL') AS CRITICAL_FAILURES,
       COUNT_IF(SEVERITY = 'WARNING' AND STATUS = 'FAIL') AS WARNING_FAILURES
FROM PROJECT_AUDIT.DQ_RESULT GROUP BY BATCH_ID ORDER BY BATCH_ID;

-- Quarantine review queue (malformed records stay visible, never dropped)
SELECT SOURCE_NAME, REASON_CODE, COUNT(*) AS RECORDS
FROM PROJECT_AUDIT.QUARANTINE_RECORD GROUP BY 1, 2 ORDER BY RECORDS DESC;

-- Try a reporting view (populated only for published batches)
SELECT * FROM PROJECT_REPORTING.VW_RESEARCH_OUTPUT LIMIT 10;
```

The full read-only audit pack is `sql/99_tests/02_phase2_verification.sql`
(sections A–H).

---

## STEP 8 — Run it via GitHub Actions

1. Repo → **Actions** → **deploy-ci**: runs lint, tests and deploys the SQL
   layers and task graph. Run it once after any change under `sql/`.
2. Repo → **Actions** → **extract-load**: extracts the source windows, uploads
   the raw shards and drains the Snowflake task graph. Use **Run workflow** →
   source `all` (or one source) → mode `incremental`.
3. The scheduled run fires **daily at 01:00 UTC**. The Snowflake root task has
   no cron of its own and is only ever started with `EXECUTE TASK` by the
   workflow. Backfill (`mode = full`) is **dispatch-only** and never runs on
   the schedule.

---

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `Could not load SNOWFLAKE_PRIVATE_KEY (wrong passphrase or malformed key)` | The `.p8` content got truncated or you used the wrong key. Re-copy the whole file into the env var / secret; if encrypted, set `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`. |
| `Failed to connect ... 250001` / auth error | `RSA_PUBLIC_KEY` mismatch. You probably pasted the fingerprint or missed characters. Redo Step 3–4 (key body = one unbroken base64 string). |
| `... does not exist or not authorized` on tables | Role/grant missing → redeploy `sql/00_setup/01_roles_and_grants.sql` with an administrative role and confirm role `PAPERSONAR_LOADER` (extraction) or `PAPERSONAR_ADMIN` (deployment) plus the `WH_PAPERSONAR_ELT` warehouse grant. |
| Account identifier rejected | Some accounts need the `ORGNAME-ACCOUNTNAME` form — copy the identifier exactly as shown bottom-left in Snowsight. |
| Workflow fails with `Refusing to run extraction with ACCOUNTADMIN` | `SNOWFLAKE_ROLE` is set to `ACCOUNTADMIN`. Use `PAPERSONAR_LOADER` for `extract-load` and `PAPERSONAR_ADMIN` for `deploy-ci`. |
| Batch stays `FAILED` with `Publication blocked by N critical DQ failure(s)` | The gate is working as designed. Read the failing rule in `PROJECT_AUDIT.DQ_RESULT` for that batch id, fix the cause, then requeue: `python -m runner.cli trigger --retry-batch-id <BATCH_ID> --drain`. |
| `HTTP 429` in logs | Source throttling; the client honors `Retry-After` with capped backoff. If attempts exhaust, the source is marked failed for that run. |
| Everything `0 rows` after extract | Check `PROJECT_AUDIT.BATCH.STATUS` (Step 7 query); a failed source leaves its watermark untouched — fix and re-run. |
| Trial expired | Stop and report **BLOCKED**; do not upgrade; do not switch databases. |

---

## Cost-safety checklist (confirm once)

- [ ] Warehouse `WH_PAPERSONAR_ELT` is `XSMALL`, `AUTO_SUSPEND = 60`, `INITIALLY_SUSPENDED = TRUE`
- [ ] `STATEMENT_TIMEOUT_IN_SECONDS = 900` set (Step 2 SQL includes it)
- [ ] Resource monitor `RM_PAPERSONAR_ELT` exists
- [ ] Only the four `PAPERSONAR_*` roles exist; no extra warehouses/roles/DBs
- [ ] Service user has key-pair auth only (no password)
- [ ] Scheduled workflow = `sync` only; backfill only via manual dispatch
- [ ] You know where to check credit usage: Snowsight → Admin → **Cost Management → Consumption**

---

*After completing Steps 1–5, tell the agent — it will run Steps 6–7 with you,
fill the acceptance report's BLOCKED items with real evidence, and only then
enable scheduled ingestion.*
