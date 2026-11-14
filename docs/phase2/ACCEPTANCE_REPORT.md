# PaperSonar Phase 2 — Acceptance Report

Date: 2026-11-14
Branch: `phase2` (HEAD at time of writing: step 6 commit)

Status legend: **PASS** (verified in this environment) · **PASS-MOCK** (verified
against the deterministic mocked Snowflake adapter; live verification pending)
· **BLOCKED** (cannot be verified without live Snowflake credentials/GitHub
secrets — requires the account owner's no-cost setup) · **NOT TESTED**.

Nothing in this report is fabricated. Mock-warehouse counts are labeled as such
and come from the checked-in integration tests.

---

## 1. Executive status

| Area | Status | Evidence |
| --- | --- | --- |
| Repository audit, fail-closed config, logging, CLI | PASS | 51 tests at step 0–1; `papersonar validate-config` verified locally |
| Snowflake adapter, migrations, transactional state store | PASS-MOCK | 63 tests at step 2; key-pair auth code path per official connector API |
| Raw payload + manifest durability (internal stage + registry) | PASS-MOCK | 73 tests at step 3 |
| Five source adapters with verified API parameters | PASS-MOCK | 97 tests at step 4; capability matrix |
| Staging validation, quarantine, canonical resolution, DW loads, quality gate | PASS-MOCK | 122 tests at step 5 |
| Orchestration, checkpoints, recovery, partial/failed policy | PASS-MOCK | 129 tests at step 6 |
| **Live Snowflake: account access confirmed by owner; `migrate` executed** | **FAIL → FIXED** | First live run exposed a real defect: naive statement split sent comment-only statements to Snowflake (`000900 (42601): Empty SQL statement`). Root cause fixed with a Snowflake-aware statement splitter (`warehouse/sqlsplit.py`); 147 tests incl. regression on the real migration files. Pending: re-run `migrate` + `smoke-test` on the live account. |
| **Live Snowflake smoke test + migrations + sample E2E on real warehouse** | **BLOCKED** | Needs no-cost Snowflake account + secrets (account owner action) |
| **GitHub Actions live run (dispatch + schedule)** | **BLOCKED** | Needs the secrets above; workflow syntax validated locally |
| **Course-scale corpus targets (30k–60k works; ≥100 dims; ≥10k facts)** | **BLOCKED** | Requires live multi-day sync/backfill against real sources + warehouse |

Test totals (latest run): **129 passed, 0 failed, 0 skipped** in 2.67 s
(`python -m pytest tests -q`, mocked warehouse, no network).
Lint: `ruff check src tests` → all checks passed.

---

## 2. Machine-readable summary

```json
{
  "commands_executed": [
    {"command": "python -m pytest tests -q", "pass": true, "tests": 129, "skipped": 0},
    {"command": "python -m ruff check src tests", "pass": true},
    {"command": "papersonar validate-config --mode ingest (without secrets)", "pass": true,
     "note": "exit 2 with non-secret missing-settings error, before any source call"},
    {"command": "papersonar sync --dry-run (fake Snowflake env values)", "pass": true,
     "note": "window plans for all five sources; no fetch, no writes"},
    {"command": "papersonar migrate / smoke-test / quality / sync (live Snowflake)",
     "pass": null, "blocked": true,
     "reason": "no live Snowflake account credentials available to the agent"}
  ],
  "environment_limitations": [
    "No live Snowflake account (no-cost offer pending account owner).",
    "GitHub secrets not configured yet, so live workflow runs are blocked.",
    "Network-dependent tests are deterministic and fixture-based by design."
  ],
  "sample_run_id": "dynamic uuid recorded in PROJECT_OPS.ETL_RUN by mocked orchestrator tests",
  "mocked_source_level_result": {
    "openalex": {"records_seen": 2, "accepted": 2, "quarantined": 0},
    "crossref": {"records_seen": 2, "accepted": 2, "quarantined": 0}
  },
  "mocked_warehouse_row_counts": {
    "PROJECT_STAGING.STG_WORK_RECORD": 4,
    "PROJECT_DW.DIM_WORK": 4,
    "PROJECT_DW.WORK_SOURCE_XW": 4,
    "PROJECT_DW.FACT_PUBLICATION": 4,
    "PROJECT_DW.FACT_WORK_SNAPSHOT": 4,
    "PROJECT_DW.FACT_CITATION": 4,
    "PROJECT_OPS.SCHEMA_MIGRATION": 2
  },
  "quality_gate_result": "PASS (mocked environment)",
  "idempotency_proof": "tests/integration/test_pipeline_mock.py::test_replay_is_idempotent — replaying the same fetches leaves every table count unchanged",
  "checkpoint_non_advance_proof": "tests/unit/test_orchestrator.py::test_source_failure_marks_run_partial_and_keeps_watermark — after a forced HTTP 429 failure the source status is 'failed', ERROR_CODE is recorded, and LAST_SUCCESSFUL_WATERMARK stays NULL"
}
```

---

## 3. Requirement-to-evidence matrix

### 3.1 Playbook 01 — Target architecture and requirements

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Snowflake is the only production target; no fallback database | PASS-MOCK | `config.py` rejects non-`snowflake` `PAPERSONAR_TARGET` (`test_config.py`); no other adapter exists |
| 2 | Fail-closed validation before ingestion | PASS | `require_snowflake()` called first in `Orchestrator.run` (`test_requires_snowflake_before_any_source_call`) and in every CLI warehouse command |
| 3 | Raw payloads durable before checkpoint advance | PASS-MOCK | Pages written + manifest before staging/checkpoint (`test_raw_store.py`); watermark advances only after full window (`test_successful_sync_run`) |
| 4 | Quarantined records never silently discarded | PASS-MOCK | `STG_QUARANTINE` rows with reason codes (`test_staging.py`, `test_quarantined_records_do_not_pollute_warehouse`) |
| 5 | Partial runs never labeled fully successful | PASS-MOCK | `_final_status` matrix + ETL_RUN status assertions (`test_orchestrator.py`) |

### 3.2 Playbook 02 — Source connectors and incremental loading

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | API parameters verified from official docs; no invented URLs | PASS | `docs/phase2/SOURCE_CAPABILITY_MATRIX.md` (fetched 2026-11-14); adapter contract tests |
| 2 | Cursor/token pagination per source (OpenAlex cursor, Crossref cursor+index-date, OAI-PMH tokens, DataCite cursor, Zenodo) | PASS-MOCK | `test_source_adapters.py` for all five sources |
| 3 | Retry/backoff, Retry-After, jitter, idempotent upserts | PASS-MOCK | `test_http_client.py`; loader MERGE semantics |
| 4 | Watermark per stream persisted in Snowflake | PASS-MOCK | `SOURCE_SYNC_STATE` (`test_state_store.py`) |
| 5 | Live API behavior (rate limits in practice, DataCite updated-range syntax) | NOT TESTED / flagged | Capability matrix flags DataCite range syntax for live validation |

### 3.3 Playbook 03 — Raw, staging, canonical model

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Raw stage + manifest with redaction of secrets | PASS-MOCK | `test_raw_store.py` (`scrub_request_descriptor`) |
| 2 | Staging table keyed (source, record id, payload hash) — content-versioned history | PASS-MOCK | `test_changed_content_creates_new_staging_version` |
| 3 | Canonical identity: DOI crosswalk, conflict quarantine, field precedence | PASS-MOCK | `test_canonical.py` (6 resolution tests) |
| 4 | Replay from raw payload without network | PASS-MOCK | Raw store replay API + idempotent integration replay |

### 3.4 Playbook 04 — Dimensional warehouse and SQL

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | DDL/loading/transforms via Snowflake SQL, not Python-only persistence | PASS-MOCK | Migrations 001/002 are versioned SQL files applied via `execute_script`; loads are MERGE-based via the adapter; deep checks are versioned SQL (`warehouse/sql/integrity_checks.sql`) |
| 2 | dim/fact/bridge objects per approved dictionary | PASS-MOCK | `002_dimensional_warehouse.sql`; mock materialization test |
| 3 | Unknown member seeds | BLOCKED (live) | Seeds are `INSERT ... SELECT` statements — only materializable on real Snowflake; mock has no INSERT-script parser. On Snowflake: check 01 of `integrity_checks.sql` |
| 4 | MERGE-based idempotent loads | PASS-MOCK | `test_replay_is_idempotent` |

### 3.5 Playbook 05 — Orchestration, retries and recovery

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Separate sync / backfill / validate / migrate commands | PASS | CLI (`test_cli.py` + local dry-run) |
| 2 | Scheduled runs never start backfill | PASS | Workflow: scheduled job pins `MODE=sync` in code (not input-dependent) |
| 3 | Checkpoint transactionality; watermark untouched on failure | PASS-MOCK | `test_state_store.py`; `test_source_failure_marks_run_partial_and_keeps_watermark` |
| 4 | Expired OAI token restart semantics | PASS-MOCK | Adapter-level restart + orchestrator one-restart handling (`_run_window`) |
| 5 | Source failure isolation (A ok, B failed ⇒ partial) | PASS-MOCK | `test_source_failure_marks_run_partial_and_keeps_watermark` |

### 3.6 Playbook 06 — Snowflake setup and GitHub Actions

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Workflow with schedule + dispatch, least-privilege permissions, concurrency group, bounded timeouts | PASS | `.github/workflows/phase2.yml` (YAML validated locally) |
| 2 | Lint + deterministic tests before ingestion | PASS | `tests` job gates `ingest` via `needs:` |
| 3 | Secret validation without revealing values | PASS | Secret-check steps print missing **names** only |
| 4 | Fail-closed config + smoke test before ingestion | PASS | `validate-config --mode ingest` step + `smoke-test` step precede the run step |
| 5 | Key-pair auth via official connector | PASS-MOCK | `SnowflakeAdapter` (key-pair, role/db/schema/warehouse) |
| 6 | Required secrets documented | PASS | `docs/phase2/RUNBOOK.md` §1.4 |
| 7 | **Live workflow execution tested (manual dispatch + schedule)** | **BLOCKED** | Requires the account owner's no-cost Snowflake account and configured secrets |
| 8 | Owner confirms no-cost offer status | BLOCKED | Owner action |

### 3.7 Playbook 07 — Testing, data quality, acceptance

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Unit layer (DOI/ID normalization, dates, cursors, hashes, conflicts, retries, redaction) | PASS-MOCK | `test_identifiers.py`, `test_timeutil.py`, `test_source_adapters.py`, `test_http_client.py`, `test_logging_setup.py` |
| 2 | Contract tests with sanitized fixtures | PASS-MOCK | `tests/fixtures/<source>/`; `test_source_adapters.py` |
| 3 | Integration layer (raw+manifest, staging upsert, quarantine, crosswalk, dims/facts, duplicates, checkpoint tx, run status) | PASS-MOCK | `test_pipeline_mock.py`, `test_state_store.py`, `test_orchestrator.py` |
| 4 | Same batch twice → no duplicates | PASS-MOCK | `test_replay_is_idempotent` |
| 5 | Same DOI from two sources → one canonical work | PASS-MOCK | `test_same_doi_two_sources_merge` |
| 6 | Conflicting titles for one DOI → quarantine | PASS-MOCK | `test_conflicting_title_quarantined` |
| 7 | Record with no DOI → src-keyed identity | PASS-MOCK | `test_source_fallback_key` |
| 8 | Missing optional author/venue tolerated | PASS-MOCK | `test_missing_title_is_not_fatal` + adapter tests |
| 9 | Cursor page fails / rate limit / transient / permanent errors | PASS-MOCK | `test_http_client.py`, `test_orchestrator.py` failure paths |
| 10 | OAI-PMH token expiry | PASS-MOCK | `test_source_adapters.py` (arxiv/zenodo token tests) |
| 11 | Database failure before commit | PASS-MOCK | State store transaction tests (`test_state_store.py`) |
| 12 | Workflow missing secrets → clear failure | PASS | Secret-check step + `validate-config --mode ingest` exit 2 (verified locally without secrets) |
| 13 | **Live Snowflake connectivity + warehouse smoke test before acceptance** | **BLOCKED** | `papersonar smoke-test` implemented; needs live account |
| 14 | Scheduled run with no new records stays succeeded | BLOCKED (live) | Designed for (empty pages ⇒ complete window, watermark advance); live run required to demonstrate |
| 15 | Quality metrics recorded (missingness %, per-source counters) | PASS-MOCK | ETL_RUN counters + sync state; missingness % as SQL (check 12 of `integrity_checks.sql`, live) |
| 16 | Mandatory warehouse checks 1–12 | PASS-MOCK (subset) | COUNT-based gate + orchestrator/state assertions; join-based checks (unknown seeds, FK resolution, self-citations, negative counts) are versioned SQL for live Snowflake (BLOCKED live) |
| 17 | Fatal vs warning thresholds documented | PASS | Staging policy: fatal = contradictory/impossible values (quarantined); warnings = missingness (accepted, nulls preserved); documented in `staging.py` module docstring and RUNBOOK |
| 18 | Course-scale targets (30k–60k works, ≥100 dims, ≥10k facts) | BLOCKED | Requires live multi-day backfill; report actual counts when available; never force data |

### 3.8 Playbook 08 — Security, costs, operations

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Secrets never logged or committed | PASS-MOCK | `test_logging_setup.py` redaction; `.env.example` placeholders only |
| 2 | Cost safeguards (bounded windows, small warehouse, timeouts) | PASS | RUNBOOK §6 + workflow timeouts + `BACKFILL_MAX_WINDOWS` |
| 3 | No destructive statements; migrations non-destructive | PASS-MOCK | All DDL `IF NOT EXISTS`; MERGE upserts only |
| 4 | Audit trail (run id, source, window, pages, counts, retries, outcome) | PASS-MOCK | `ETL_RUN` + `SOURCE_SYNC_STATE` + `RAW_BATCH` |

### 3.9 Playbook 10 — Source and runtime configuration reference

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | `.env.example` contains placeholders only, Snowflake-first | PASS | Rewritten at step 0–1 |
| 2 | Per-source config (enabled, page size, max pages, backfill date, overlap) | PASS | `config.py` + `--dry-run` window plans |

---

## 4. What is needed to unblock the remaining items

The account owner must:

1. Provide a **no-cost Snowflake account** (trial/credits) and confirm its
   no-cost status and limits.
2. Run the one-time resource setup in `docs/phase2/RUNBOOK.md` §1.2–1.3
   (warehouse, role, service user, key-pair).
3. Add the GitHub Actions secrets listed in RUNBOOK §1.4.

Once available, the agent will (in order): run `papersonar migrate`, the live
`smoke-test`, a bounded first `sync`, the `validate` workflow dispatch, verify
unknown-member seeds and join-based integrity checks on real Snowflake, and
then enable the scheduled sync. Until then, live verification stays
**BLOCKED** and scheduled production ingestion must not be enabled.

---

## 5. Post-Phase-2 hardening audit

Source: `docs/agents/Phase2/PaperSonar_Post_Phase2_Integration_and_Hardening_UPDATED.md`.
Matrix columns per §3 of that document: requirement → implementation location →
evidence → status → remaining work. **Phase 3 has not been started** (§10.10
confirmation; no analytics/BI/Phase 3 code was written).

| # | Requirement (hardening doc) | Implementation location | Evidence | Status | Remaining work |
| --- | --- | --- | --- | --- | --- |
| H1 | Snowflake SQL for DDL, loading, transformations, quality (not Python-only) | `warehouse/migrations/*.sql`, `warehouse/sql/transforms.sql`, loaders use MERGE via adapter | migration tests; `transforms.sql` reviewed | PASS-MOCK | Execute `transforms.sql` on live Snowflake (BLOCKED) |
| H2 | Deduplicate staged input before MERGE | `transforms.sql` T1 (`V_STG_WORK_RECORD_LATEST` QUALIFY dedup); Python path: deterministic 3-pass precedence sort with payload-hash tiebreak | `test_same_record_two_versions_one_batch_is_deterministic` | PASS-MOCK | Live verification (BLOCKED) |
| H3 | Deterministic match keys + conflict rules; DOI as signal not assumption | `canonical.py` (`work_key_for` DOI-or-src), `transforms.sql` T2–T4 | `test_canonical.py` (DOI + src-fallback + conflict tests) | PASS-MOCK | Live verification (BLOCKED) |
| H4 | Provenance preserved, never overwritten by normalized record | `RAW_BATCH` + internal stage; staging keeps `DOI_RAW`, full arrays, `SOURCE_UPDATED_AT` vs `INGESTED_AT` | `test_raw_store.py`, migration 001 DDL | PASS-MOCK | — |
| H5 | Idempotent re-run of same input | loaders MERGE upserts; crosswalk/dim/fact natural keys | `test_replay_is_idempotent` | PASS-MOCK | Live verification (BLOCKED) |
| H6 | SQL quality checks executable + documented | `quality.py` (COUNT-based, runs everywhere) + `integrity_checks.sql` (join-based, live) | mocked gate PASS/FAIL tests; SQL reviewed | PASS-MOCK | Live execution of join checks (BLOCKED) |
| H7 | Analytical SQL queries/views demonstrating queryability | `migrations/003_reporting_views.sql` (8 views), `warehouse/sql/analytics_queries.sql` (Q1–Q11) | YAML/SQL review; migration applies in mock (schema recorded) | PASS-MOCK | Live view validation (BLOCKED) |
| H8 | Checkpoint values never advance past durable validated writes | `orchestrator._process_window` (loads complete → transactional checkpoint) | `test_successful_sync_run`, `test_source_failure_marks_run_partial_and_keeps_watermark` | PASS-MOCK | Live verification (BLOCKED) |
| H9 | Source-specific watermarks (no global watermark) | per (source, stream) rows in `SOURCE_SYNC_STATE` | `test_source_watermarks_remain_independent` | PASS-MOCK | Live verification (BLOCKED) |
| H10 | Dry-run explicit; cannot advance production checkpoints | CLI `--dry-run` plans windows only; no warehouse session, no HTTP | `test_dry_run_never_connects_to_warehouse` (connection monkeypatched to raise) | PASS | — |
| H11 | Source-by-source incremental behavior documented | `SOURCE_CAPABILITY_MATRIX.md` + RUNBOOK §2.1 | reviewed | PASS | DataCite range syntax live validation (BLOCKED) |
| H12 | Deleted/withdrawn records handled per documented capability | adapters count tombstones, do not stage; policy in capability matrix | `test_source_adapters.py` | PASS-MOCK | Live tombstone observation (BLOCKED) |
| H13 | Attempted/fetched/accepted/rejected/failed counts recorded | `ETL_RUN` counters, `SOURCE_SYNC_STATE`, `RAW_BATCH.RECORDS_SEEN`, `STG_QUARANTINE` | state-store + orchestrator tests | PASS-MOCK | inserted/updated/unchanged split not yet measured (follow-up) |
| H14 | Transaction boundaries + recovery documented | RUNBOOK §3 (migration tx, window checkpoint semantics, restart behavior) | documentation review | PASS | — |
| H15 | PK/unique constraints not relied on for uniqueness | RUNBOOK §3 note; uniqueness enforced by MERGE keys + integrity checks 03–06, 10 | documentation + `test_replay_is_idempotent` | PASS | — |
| H16 | Secrets/costs safeguards; no paid resources | config fail-closed, redaction logging, workflow secret checks, XSMALL auto-suspend guidance | `test_logging_setup.py`, workflow steps, RUNBOOK §7 | PASS-MOCK | Live account cost confirmation by owner (BLOCKED) |
| H17 | Documentation matches implementation; NOT IMPLEMENTED/BLOCKED labeled | RUNBOOK, capability matrix, this report | cross-checked | PASS | — |
| H18 | Phase 1 behavior and tests remain intact | Phase 1 docs untouched; no Phase 1 code changed | `git status`/diff scope | PASS | — |

### Hardening additions (files)

Added in the hardening step (uncommitted; awaiting approval):

- `src/papersonar/warehouse/sqlsplit.py` + `tests/unit/test_sql_split.py` — **live-Snowflake defect fix**: the previous naive `split(";")` sent comment-only statements to Snowflake (`000900 (42601) Empty SQL statement`) and split statements inside string literals containing `;` (several migration `COMMENT` strings contain semicolons). The new state-machine splitter is used by both the real adapter and the mock, with regressions against the real migration files. Live evidence: owner ran `papersonar migrate` on a real no-cost account and hit exactly this error; re-run pending.
- `src/papersonar/warehouse/migrations/003_reporting_views.sql` — `PROJECT_REPORTING` schema + 8 analytical views (non-destructive, `IF NOT EXISTS`).
- `src/papersonar/warehouse/sql/transforms.sql` — warehouse-side SQL transform layer: staging dedup view, `CANONICAL_CONFLICT_REVIEW` table, conflict-detection insert, crosswalk/canonical/fact/snapshot MERGEs with cross-run source precedence.
- `src/papersonar/warehouse/sql/analytics_queries.sql` — Q1–Q11 demonstration queries with dependency labels.
- `docs/phase2/RUNBOOK.md` §3 — SQL deployment order, transaction boundaries, PK non-enforcement, measured-counts vocabulary.
- Tests: dry-run warehouse-connection safety, watermark independence, multi-version batch determinism (132 tests total, up from 129).
- `canonical.py` — documented deterministic tiebreak (payload hash) for same-timestamp content versions.

### Known defects / limitations (§10.9)

1. `transforms.sql` T5 leaves `VENUE_KEY` as the unknown member for
   warehouse-side reprocessing (venue keys are derived in the orchestrated
   loader path); documented in the file. Never references a missing venue.
2. MERGE inserted/updated/unchanged split is not yet captured per run.
3. OAI-PMH `from`-only sync (arXiv) means deleted records are not detected by
   re-checking the window; bounded reconciliation is the documented fallback.
4. Live-only behaviors (unknown-member seeds, reporting views, join-based
   integrity checks, DataCite range syntax) are BLOCKED until a no-cost
   Snowflake account exists.
