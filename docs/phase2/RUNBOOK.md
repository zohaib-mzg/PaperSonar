# PaperSonar Phase 2 — Operator Runbook

This is the operator-facing guide for running the Phase 2 ingestion pipeline.
The production target is **Snowflake only** — there is no PostgreSQL, SQLite,
or local-database fallback. Deterministic tests use a mocked Snowflake adapter
(a testing technique only, never a production path).

---

## 1. Prerequisites (one-time, performed by the account owner)

### 1.1 Snowflake account (no-cost offer)

Use a currently available no-cost Snowflake trial/credits offer. Snowflake is
not guaranteed to be permanently free. Do not activate paid resources. If no
no-cost offer is available or it expires, production deployment stops and is
reported as **BLOCKED** — it is never replaced with another database.

### 1.2 Minimum resources to create

Create only what the pipeline needs (statements below use conservative,
least-privilege grants). Run these once, as `ACCOUNTADMIN` or an equivalent
administrator, in a Snowflake worksheet:

```sql
-- Warehouse: small, auto-suspending, short timeout
CREATE WAREHOUSE IF NOT EXISTS PAPERSONAR_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  STATEMENT_TIMEOUT_IN_SECONDS = 900;

-- Role and service user
CREATE ROLE IF NOT EXISTS PAPERSONAR_INGEST;
CREATE USER IF NOT EXISTS SVC_PAPERSONAR
  DEFAULT_ROLE = PAPERSONAR_INGEST
  DEFAULT_WAREHOUSE = PAPERSONAR_WH
  MUST_CHANGE_PASSWORD = FALSE;
GRANT ROLE PAPERSONAR_INGEST TO USER SVC_PAPERSONAR;

-- Database and schemas (schemas are also created by migrations, but creating
-- the database and base schemas up front keeps migration grants simple)
CREATE DATABASE IF NOT EXISTS PAPERSONAR;
GRANT USAGE ON WAREHOUSE PAPERSONAR_WH TO ROLE PAPERSONAR_INGEST;
GRANT USAGE ON DATABASE PAPERSONAR TO ROLE PAPERSONAR_INGEST;
GRANT USAGE, CREATE SCHEMA ON DATABASE PAPERSONAR TO ROLE PAPERSONAR_INGEST;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON SCHEMA PAPERSONAR.INGEST TO ROLE PAPERSONAR_INGEST;
```

> The pipeline creates four schemas itself via migrations: `INGEST` is the
> connection schema; migrations create `PROJECT_OPS` (operational state + raw
> stage), `PROJECT_STAGING`, `PROJECT_DW`, and `PROJECT_REPORTING`.

### 1.3 Key-pair authentication (preferred by the official connector)

Generate a key pair locally (never commit the private key):

```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -outform pem > papersonar_key.p8
openssl rsa -in papersonar_key.p8 -pubout -out papersonar_key.pub
```

Assign the public key to the service user. Copy the **base64 body** of
`papersonar_key.pub` — everything between `-----BEGIN PUBLIC KEY-----` and
`-----END PUBLIC KEY-----`, with the newlines removed into one long string
(this is the key body, not a fingerprint):

```sql
ALTER USER SVC_PAPERSONAR SET RSA_PUBLIC_KEY = '<public-key-body-one-long-string>';
DESC USER SVC_PAPERSONAR;  -- verify RSA_PUBLIC_KEY is set
```

If you encrypt the private key with a passphrase, keep the passphrase as a
secret too (`SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`). The detailed, Windows-friendly
walkthrough is in `docs/phase2/SNOWFLAKE_SETUP_STEP_BY_STEP.md`.

### 1.4 GitHub Actions secrets

Add these **repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
| --- | --- |
| `SNOWFLAKE_ACCOUNT` | e.g. `xy12345.eu-central-1` |
| `SNOWFLAKE_USER` | `SVC_PAPERSONAR` |
| `SNOWFLAKE_ROLE` | `PAPERSONAR_INGEST` |
| `SNOWFLAKE_WAREHOUSE` | `PAPERSONAR_WH` |
| `SNOWFLAKE_DATABASE` | `PAPERSONAR` |
| `SNOWFLAKE_SCHEMA` | `INGEST` |
| `SNOWFLAKE_PRIVATE_KEY` | full PEM text of `papersonar_key.p8` (single secret, multiline) |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | only if the key is encrypted |
| `OPENALEX_API_KEY` | OpenAlex premium key (needed past the first page) |
| `CROSSREF_CONTACT_EMAIL` | contact email for the polite Crossref pool |

Never put credentials in repository variables. `.env.example` contains
placeholders only.

---

## 2. Local operation

Python 3.12 with the pinned dependencies:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

Configuration lives in environment variables (see `.env.example`). All
warehouse commands fail closed when Snowflake settings are missing or when
`PAPERSONAR_TARGET` is not `snowflake`.

| Command | What it does |
| --- | --- |
| `papersonar validate-config` | Structural validation; no network. |
| `papersonar validate-config --mode ingest` | Additionally requires all Snowflake settings (exit 2 if missing). |
| `papersonar migrate` | Applies versioned, non-destructive migrations (001, 002, 003). |
| `papersonar sync --dry-run` | Plans this run's windows per source; fetches/writes nothing. |
| `papersonar sync` | One incremental sync run. |
| `papersonar backfill` | Bounded historical backfill (max 60 windows per source per run). |
| `papersonar quality` | Runs the SQL quality gate. |
| `papersonar smoke-test` | Connectivity + migrations + row counts (live acceptance). |

Exit codes: `0` succeeded, `1` partial (quality gate failed or some sources
failed), `2` hard error/configuration failure.

### 2.1 Window planning per source

| Source | Backfill windows | Sync windows |
| --- | --- | --- |
| openalex | one per year from `OPENALEX_BACKFILL_FROM_DATE` to current year | current-year reconciliation partition |
| crossref | daily `indexdate` partitions (max 60/run) | last 2 index dates (overlap) |
| arxiv (OAI-PMH) | single window from backfill date | from = watermark − overlap (no `until`: OAI-PMH `from`-only sync) |
| datacite | daily `updated` partitions (max 60/run) | last 2 `updated` days |
| zenodo (OAI-PMH) | single window from backfill date to yesterday | watermark − overlap → yesterday |

### 2.2 Run semantics

- A run is **succeeded** only if every enabled source succeeded *and* the
  quality gate passed.
- Any source failure ⇒ **partial** at best. All sources failed ⇒ **failed**.
- A failed source never advances its watermark. Completed watermark and
  in-progress pagination cursor are stored separately in
  `PROJECT_OPS.SOURCE_SYNC_STATE`.
- Interrupted runs resume from the saved cursor. Expired OAI-PMH resumption
  tokens restart the bounded window once (upserts make this idempotent).
- Partial runs are never reported as fully successful.

---

## 4. GitHub Actions operation

Workflow: `.github/workflows/phase2.yml`.

- `schedule` (daily 04:30 UTC): always runs **sync only**, never backfill.
- `workflow_dispatch`: choose `sync` (default), `backfill`, or `validate`.
- `push`: lint + deterministic tests only.
- Concurrency group `phase2-ingestion` prevents overlapping runs.
- Secret names are validated before any source call; missing secrets fail the
  job with the missing **names** only (never values).
- Order: lint/tests → secret check → fail-closed config validation →
  Snowflake smoke test → ingest → final quality gate → job summary.

---

## 3. SQL deployment order and warehouse engineering notes

SQL artifacts, in review/deployment order (all version-controlled):

| Artifact | Purpose |
| --- | --- |
| `warehouse/migrations/001_operational_state.sql` | Operational state: `ETL_RUN`, `SOURCE_SYNC_STATE`, `RAW_BATCH`, staging + quarantine + raw stage |
| `warehouse/migrations/002_dimensional_warehouse.sql` | `DIM_*`, `FACT_*`, `BRIDGE_*`, crosswalk, unknown-member seeds |
| `warehouse/migrations/003_reporting_views.sql` | `PROJECT_REPORTING` analytical views |
| `warehouse/sql/transforms.sql` | Warehouse-side transform layer: staging dedup view, conflict review table, canonical/crosswalk/fact/snapshot MERGEs with source precedence |
| `warehouse/sql/integrity_checks.sql` | Deep join-based integrity + quality checks (live Snowflake) |
| `warehouse/sql/analytics_queries.sql` | Demonstration analytical queries over the reporting views |

Deployment order: `papersonar migrate` (applies 001 → 002 → 003 exactly once,
checksummed, transactional) → optionally execute `transforms.sql` for
warehouse-side reprocessing → run `integrity_checks.sql` → query via
`analytics_queries.sql`. Transform/integrity/analytics files are reviewed SQL,
not migrations: they are idempotent and safe to re-run, but are not
auto-applied by the migration runner.

Operational SQL notes:

- **Snowflake does not enforce PK/unique constraints.** Uniqueness is enforced
  by the loading logic: MERGE upserts keyed on natural keys, staging keyed by
  `(SOURCE_NAME, SOURCE_RECORD_ID, PAYLOAD_SHA256)`, and validation queries
  (`integrity_checks.sql` checks 03–06, 10) that detect duplicates.
- **Transaction boundaries:** migrations run in one transaction per version
  (checksum recorded on commit). Each pipeline window completes its loads
  before the checkpoint write; the completed watermark and in-progress cursor
  are separate rows in `SOURCE_SYNC_STATE`, so a crash mid-window leaves the
  watermark untouched and the cursor resumable. Recovery: re-run `sync`/
  `backfill` — upserts make replay idempotent; expired OAI tokens restart the
  bounded window once.
- **Measured counts per run** (`ETL_RUN` / `SOURCE_SYNC_STATE`): records seen,
  accepted (staged), quarantined, warehouse rows written, retries, per-source
  statuses. Not yet measured separately: inserted vs updated vs unchanged
  (MERGE doesn't return per-action counts in the current adapter); planned as
  a follow-up using Snowflake MERGE result metadata.

---

## 5. Data-quality and quarantine review

The quality gate (SQL `COUNT`-based, runs on Snowflake and in mocked tests)
checks: staging row counts, quarantine ratio (default limit 20%, configurable
via code), row counts per fact/dimension table, and crosswalk-orphan ratio
(0 allowed). A failing gate downgrades the run to `partial` — never `succeeded`.

Quarantined records live in `PROJECT_STAGING.STG_QUARANTINE` with reason codes
(`missing_source_id`, `malformed_identifier`, `invalid_date`,
`impossible_negative_count`, `conflicting_doi_identity`,
`doi_change_review`, `missing_title`). They are never silently discarded;
review and resolve them by updating `RESOLUTION_STATUS` in that table after
investigation. Review query:

```sql
SELECT REASON_CODE, COUNT(*) FROM PROJECT_STAGING.STG_QUARANTINE
WHERE RESOLUTION_STATUS = 'open' GROUP BY REASON_CODE ORDER BY 2 DESC;
```

---

## 6. Troubleshooting

| Symptom | Cause / remedy |
| --- | --- |
| `Missing mandatory Snowflake configuration: ...` | Set the listed env vars/secrets; re-run. Fail-closed by design. |
| `PAPERSONAR_TARGET must be 'snowflake'` | A non-Snowflake target was configured. Fix it; there is no fallback. |
| `Could not load SNOWFLAKE_PRIVATE_KEY ...` | Key malformed or passphrase wrong; regenerate or correct `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`. |
| OAI `badResumptionToken` retries then restart | Expected: the window restarts from its beginning once; upserts keep it idempotent. |
| `max_pages=N reached without completing window` | Source throttling or too-large window. The run is marked partial for that source; re-run to resume from the saved cursor. |
| Repeated 429/5xx | The HTTP client honors `Retry-After` with capped exponential backoff + jitter; if attempts are exhausted the run is partial/failed and nothing durable is lost. |
| Warehouse idle costs | The warehouse auto-suspends after 60 s; jobs keep it suspended otherwise. |

---

## 7. Cost and operational safeguards

- Smallest warehouse size (`XSMALL`), auto-suspend 60 s, statement timeout.
- Bounded windows and page limits per run (backfill ≤ 60 windows/source).
- No automatic resource upgrades, no paid-feature activation, no destructive
  statements against existing data.
- Raw payloads are stored durably in the Snowflake internal stage
  `PROJECT_OPS.RAW_STAGE` with a registry row in `PROJECT_OPS.RAW_BATCH`;
  the runner disk is never the only copy.
- If the no-cost offer expires, disable the scheduled workflow until an
  authorized no-cost setup exists (do not switch databases).
