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

You create the account + resources; `papersonar migrate` creates all four
schemas, tables, views, and the raw-payload stage automatically.

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
-- PaperSonar one-time setup — run as ACCOUNTADMIN in one worksheet
-- =====================================================================

-- 1) Small, auto-suspending warehouse (cheapest size; suspends after 60 s idle)
CREATE WAREHOUSE IF NOT EXISTS PAPERSONAR_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  STATEMENT_TIMEOUT_IN_SECONDS = 900;

-- 2) Least-privilege role + service user (no password login; key-pair only)
CREATE ROLE IF NOT EXISTS PAPERSONAR_INGEST;

CREATE USER IF NOT EXISTS SVC_PAPERSONAR
  DEFAULT_ROLE = PAPERSONAR_INGEST
  DEFAULT_WAREHOUSE = PAPERSONAR_WH
  DISPLAY_NAME = 'PaperSonar service user'
  MUST_CHANGE_PASSWORD = FALSE;

GRANT ROLE PAPERSONAR_INGEST TO USER SVC_PAPERSONAR;

-- 3) Database + connection schema
CREATE DATABASE IF NOT EXISTS PAPERSONAR;
CREATE SCHEMA IF NOT EXISTS PAPERSONAR.INGEST;

-- 4) Grants (minimum the pipeline needs)
GRANT USAGE ON WAREHOUSE PAPERSONAR_WH TO ROLE PAPERSONAR_INGEST;
GRANT USAGE ON DATABASE PAPERSONAR TO ROLE PAPERSONAR_INGEST;
GRANT CREATE SCHEMA ON DATABASE PAPERSONAR TO ROLE PAPERSONAR_INGEST;
GRANT USAGE ON SCHEMA PAPERSONAR.INGEST TO ROLE PAPERSONAR_INGEST;

-- ✅ Expect: 9 × "Statement executed successfully"
```

**How this works:** the pipeline role owns everything it creates. When you run
`papersonar migrate` (Step 6), it creates the four schemas (`PROJECT_OPS`,
`PROJECT_STAGING`, `PROJECT_DW`, `PROJECT_REPORTING`) and all tables/views
inside them itself — you never have to create those by hand.

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
| 3 | `SNOWFLAKE_ROLE` | `PAPERSONAR_INGEST` |
| 4 | `SNOWFLAKE_WAREHOUSE` | `PAPERSONAR_WH` |
| 5 | `SNOWFLAKE_DATABASE` | `PAPERSONAR` |
| 6 | `SNOWFLAKE_SCHEMA` | `INGEST` |
| 7 | `SNOWFLAKE_PRIVATE_KEY` | open `papersonar_key.p8` in a text editor, copy **the entire file** including the `-----BEGIN PRIVATE KEY-----` and `-----END PRIVATE KEY-----` lines (multiline paste is fine) |
| 8 | `OPENALEX_API_KEY` | free OpenAlex premium key: <https://openalex.org/users/me> → "Get a key" (needed past the first page of results) |
| 9 | `CROSSREF_CONTACT_EMAIL` | your email for the Crossref polite pool (e.g. `you@example.com`) |

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
$env:SNOWFLAKE_ROLE      = "PAPERSONAR_INGEST"
$env:SNOWFLAKE_WAREHOUSE = "PAPERSONAR_WH"
$env:SNOWFLAKE_DATABASE  = "PAPERSONAR"
$env:SNOWFLAKE_SCHEMA    = "INGEST"
$env:SNOWFLAKE_PRIVATE_KEY = Get-Content -Raw "$HOME\.papersonar\papersonar_key.p8"
$env:OPENALEX_API_KEY      = "<your OpenAlex key>"
$env:CROSSREF_CONTACT_EMAIL = "<your email>"
```

Then run the pipeline in this exact order:

```powershell
# 1. Configuration check (should print: configuration OK for ingestion)
.venv\Scripts\papersonar.exe validate-config --mode ingest

# 2. Create all schemas/tables/views in Snowflake (001, 002, 003)
.venv\Scripts\papersonar.exe migrate

# 3. Live connectivity + permissions smoke test + row counts
.venv\Scripts\papersonar.exe smoke-test

# 4. See what the next sync would fetch (plans only — no fetch, no writes)
.venv\Scripts\papersonar.exe sync --dry-run

# 5. First real run (bounded incremental sync)
.venv\Scripts\papersonar.exe sync

# 6. Data-quality gate
.venv\Scripts\papersonar.exe quality
```

**What to expect:**

| Command | Success looks like |
|---|---|
| `validate-config --mode ingest` | `configuration OK for ingestion (Snowflake settings present)` |
| `migrate` | `migrations applied: 001, 002, 003` |
| `smoke-test` | `connected to database=PAPERSONAR ...` + row counts (all `0` on a fresh account) |
| `sync --dry-run` | one line per source window, e.g. `source crossref: sync window indexdate:...` |
| `sync` | `status=succeeded` (or `partial` if a source is throttled — safe to re-run) + counters + `quality_gate=PASS` |

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

New worksheet (**use role PAPERSONAR_INGEST**):

```sql
USE ROLE PAPERSONAR_INGEST;
USE DATABASE PAPERSONAR;

-- Recent runs: status + counters (partial/failed also recorded, never hidden)
SELECT RUN_ID, MODE, STATUS, SOURCE_STATUSES, RAW_ROWS, STAGING_ROWS,
       QUARANTINED_ROWS, WAREHOUSE_ROWS, QUALITY_GATE_RESULT, STARTED_AT
FROM PROJECT_OPS.ETL_RUN ORDER BY STARTED_AT DESC LIMIT 5;

-- Canonical works loaded
SELECT COUNT(*) AS WORKS FROM PROJECT_DW.DIM_WORK;

-- Per-source checkpoints (watermarks)
SELECT SOURCE_NAME, STREAM_NAME, STATUS, LAST_SUCCESSFUL_WATERMARK, LAST_SUCCESS_AT
FROM PROJECT_OPS.SOURCE_SYNC_STATE ORDER BY SOURCE_NAME;

-- Quarantine review queue (should typically be small / zero)
SELECT REASON_CODE, COUNT(*) FROM PROJECT_STAGING.STG_QUARANTINE
WHERE RESOLUTION_STATUS = 'open' GROUP BY REASON_CODE;

-- Try a reporting view (empty until sync lands data, then populated)
SELECT * FROM PROJECT_REPORTING.VW_PUBLICATION_BY_YEAR ORDER BY PUB_YEAR;
```

---

## STEP 8 — Run it via GitHub Actions

1. Repo → **Actions** → **phase2-pipeline**.
2. First run **validate** (no ingestion): click **Run workflow** → mode
   `validate` → **Run**. Expect green: tests → secret check → smoke test →
   quality gate.
3. Then **sync**: Run workflow → mode `sync`. Expect a job summary with
   `outcome=succeeded` (or `partial` — check per-source statuses in the log).
4. Scheduled incremental sync runs **daily at 04:30 UTC** automatically
   (`schedule` trigger). Backfill is **dispatch-only** and never runs on the
   schedule.

---

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `Could not load SNOWFLAKE_PRIVATE_KEY (wrong passphrase or malformed key)` | The `.p8` content got truncated or you used the wrong key. Re-copy the whole file into the env var / secret; if encrypted, set `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`. |
| `Failed to connect ... 250001` / auth error | `RSA_PUBLIC_KEY` mismatch. You probably pasted the fingerprint or missed characters. Redo Step 3–4 (key body = one unbroken base64 string). |
| `... does not exist or not authorized` on tables | Role/grant missing → re-run the Step 2 grant block, confirm role `PAPERSONAR_INGEST` and warehouse grants. |
| Account identifier rejected | Some accounts need the `ORGNAME-ACCOUNTNAME` form — copy the identifier exactly as shown bottom-left in Snowsight. |
| `sync` returns `partial` | One source hit rate limits or an incomplete window. Nothing is lost — re-run `sync`; it resumes from the saved cursor. Check per-source statuses printed after `status=`. |
| `HTTP 429` in logs | Source throttling; the client honors `Retry-After` with capped backoff. If attempts exhaust, the source is marked failed for that run. |
| Everything `0 rows` after sync | Check `ETL_RUN.STATUS` and `SOURCE_STATUSES` (Step 7 query); a failed source leaves its watermark untouched — fix and re-run. |
| Trial expired | Stop and report **BLOCKED**; do not upgrade; do not switch databases. |

---

## Cost-safety checklist (confirm once)

- [ ] Warehouse `PAPERSONAR_WH` is `XSMALL`, `AUTO_SUSPEND = 60`, `INITIALLY_SUSPENDED = TRUE`
- [ ] `STATEMENT_TIMEOUT_IN_SECONDS = 900` set (Step 2 SQL includes it)
- [ ] Only one warehouse created; no new warehouses/roles/DBs beyond the guide
- [ ] Service user has key-pair auth only (no password)
- [ ] Scheduled workflow = `sync` only; backfill only via manual dispatch
- [ ] You know where to check credit usage: Snowsight → Admin → **Cost Management → Consumption**

---

*After completing Steps 1–5, tell the agent — it will run Steps 6–7 with you,
fill the acceptance report's BLOCKED items with real evidence, and only then
enable scheduled ingestion.*
