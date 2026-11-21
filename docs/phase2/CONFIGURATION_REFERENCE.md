# PaperSonar Phase 2 configuration reference

Runtime configuration is environment-based. `.env.example` contains
placeholders only; never put real credentials in Git. All warehouse commands
fail closed when mandatory Snowflake settings are missing or when
`PAPERSONAR_TARGET` is not `snowflake`. There is no fallback database.

---

## 1. Global settings

| Variable | Default | Rules |
| --- | --- | --- |
| `PAPERSONAR_TARGET` | *(none — mandatory)* | Must be exactly `snowflake`. `postgres`, `sqlite`, `local`, blank or unknown values are rejected at startup. No production database switch exists. |
| `PAPERSONAR_ALLOW_FULL` | `false` (fail-closed) | Set to `1`/`true`/`yes`/`on` only to allow `papersonar full` (ordered backfill + sync). Any other/empty value keeps `full` disabled. Scheduled runs never use it. |
| `PAPERSONAR_LOG_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `PAPERSONAR_CORPUS_CONFIG` | *(unset)* | Optional path to a corpus JSON contract (e.g. `config/corpus.example.json`). The file must exist or startup fails. |
| `PAPERSONAR_SCHEMA_VERSION` | `1` | Short version token (`A-Za-z0-9._-`); stamped into raw batches/manifests and staging rows for parser/schema lineage. |
| `PAPERSONAR_RAW_DIR` | `data/raw` | Local raw mirror for development/testing. Production durability comes from the Snowflake internal stage `PROJECT_OPS.RAW_STAGE` + `RAW_BATCH` registry; the runner disk is never the only copy. |
| `OPENALEX_API_KEY` | *(unset)* | OpenAlex key (free tier requires it for cursor paging past the first page). Treated as a secret: redacted from logs. |
| `CROSSREF_CONTACT_EMAIL` | *(unset)* | Contact email for the Crossref polite pool. Treated as confidential: redacted from logs. |

## 2. Snowflake settings (mandatory for ingestion)

| Variable | Notes |
| --- | --- |
| `SNOWFLAKE_ACCOUNT` | e.g. `xy12345.eu-central-1` |
| `SNOWFLAKE_USER` | Service user, e.g. `SVC_PAPERSONAR` |
| `SNOWFLAKE_ROLE` | Least-privilege role: `PAPERSONAR_LOADER` for extraction, `PAPERSONAR_ADMIN` for deployment |
| `SNOWFLAKE_WAREHOUSE` | `WH_PAPERSONAR_ELT` |
| `SNOWFLAKE_DATABASE` | e.g. `PAPERSONAR` |
| `SNOWFLAKE_SCHEMA` | Connection schema, e.g. `PROJECT_STAGING` |
| `SNOWFLAKE_PRIVATE_KEY` | Either inline PEM content (`-----BEGIN PRIVATE KEY-----...`) or a path to the `.p8` key file. Both forms are accepted; the value is never logged. |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | Only when the private key is encrypted. Treated as a secret. |
| `SNOWFLAKE_DEPLOY_ROLE` | Deployment workflow only: `PAPERSONAR_ADMIN`. Never `ACCOUNTADMIN`. |

`python -m runner.cli check` verifies all of the above (and that the key
material is resolvable) before any source call, exiting `2` with the missing
setting **names** only.

## 3. Per-source settings

Prefix each variable with the source name: `OPENALEX_`, `CROSSREF_`,
`ARXIV_`, `DATACITE_`, `ZENODO_` (for example `CROSSREF_MAX_PAGES`).

| Suffix | Default | Allowed range | Meaning |
| --- | --- | --- | --- |
| `_ENABLED` | `true` | bool | Enable the source for this run. Values `0/false/no/off` disable it; anything else enables it. |
| `_PAGE_SIZE` | `100` | 1–2000 | Requested page size (adapter may clamp to the provider maximum). |
| `_MAX_PAGES` | `50` | 1–200000 | Hard page cap per window; hitting it marks the window partial and preserves the cursor. |
| `_TIMEOUT_SECONDS` | `30` | 1.0–600.0 | HTTP connect/read timeout. |
| `_RATE_DELAY_SECONDS` | `1` | 0.0–3600.0 | Politeness delay between requests. |
| `_SYNC_OVERLAP_DAYS` | `1` | 0–90 | Overlap subtracted from the last watermark on sync windows. |
| `_BACKFILL_FROM_DATE` | source-specific | `YYYY-MM-DD` | Start of historical backfill. |
| `_MAX_ATTEMPTS` | `4` | 0–10 | Bounded retry attempts for transient failures (429/5xx/timeouts). |
| `_BACKOFF_BASE_SECONDS` | `2` | 0.1–600.0 | Exponential backoff base. |
| `_BACKOFF_MAX_SECONDS` | `60` | 1.0–3600.0 | Backoff cap; `Retry-After` is honored up to this ceiling. |

Any other `<PREFIX>_<UPPERCASE>` variable is passed through to the adapter as
an `extras` entry (e.g. `DATACITE_QUERY=...`). Reserved suffixes listed above
are never forwarded as extras.

## 4. Commands and exit codes

| Command | Purpose |
| --- | --- |
| `papersonar validate-config` | Structural validation; no network, no secrets check. |
| `papersonar validate-config --mode ingest` | Additionally requires all mandatory Snowflake settings. |
| `papersonar migrate` | Applies versioned, non-destructive migrations (001–005) once each. |
| `papersonar sync --dry-run` | Plans this run's windows per enabled source; fetches/writes nothing. |
| `papersonar sync` | One incremental sync run. |
| `papersonar backfill --dry-run` / `backfill` | Plans/runs bounded historical backfill windows (≤ 60 per source per run). |
| `papersonar full --dry-run` / `full` | Ordered backfill then sync in one run; **requires `PAPERSONAR_ALLOW_FULL=true`** or it fails closed. |
| `papersonar replay --source NAME --batch-id ID` | Reprocesses one persisted raw batch from the durable stage: no source API calls, watermarks and cursors untouched, `replay` lineage recorded in `PROJECT_OPS.ETL_RUN`. |
| `papersonar quality` | Runs the SQL data-quality gate against the warehouse. |
| `papersonar smoke-test` | Live acceptance: connect, apply migrations, report row counts. |

Exit codes: `0` succeeded · `1` partial (quality gate failed or some sources
failed) · `2` hard error / configuration failure.

## 5. Secret handling

`Settings.secret_values` redacts the private key, its passphrase and the
OpenAlex API key from all log records. `.env` files are Git-ignored; in GitHub
Actions the same names come from repository secrets (see
`docs/phase2/RUNBOOK.md` §1.4). Raw request descriptors are scrubbed of
secret-looking keys before storage (`raw_store.scrub_request_descriptor`).
