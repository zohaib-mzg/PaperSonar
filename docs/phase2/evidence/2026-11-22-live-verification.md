# Live evidence — Phase 2 multi-source closeout (2026-11-22)

Captured against the live Snowflake account with `PAPERSONAR_ADMIN` for SQL and
audit queries and `PAPERSONAR_LOADER` for extraction. No credentials, private
keys or account identifiers are recorded here.

Two evidence moments are distinguished on purpose:

- **Snapshot (2026-11-21 08:41 UTC)** — the full verification pack
  `sql/99_tests/02_phase2_verification.sql` was executed and exported to
  sanitized CSV files. This snapshot is the one that exposed the two defects
  described in §5 and §6. It is the evidence of the failures.
- **Recovery (2026-11-22)** — the DQ-012 fix was deployed and the two blocked
  batches were re-run to publication by the account owner. Batch statuses were
  confirmed as `PUBLISHED`. The refreshed evidence set is reproducible with
  `sql/99_tests/03_phase2_closeout.sql` (§9) and must be exported into
  `docs/phase2/evidence/2026-11-22-live-verification/` before this document is
  treated as fully closed.

---

## 1. Environment, cost controls and object inventory

| Check | Expected | Observed | Verdict |
|---|---|---|---|
| PaperSonar schemas | 7 | `PROJECT_AUDIT`, `PROJECT_BRONZE`, `PROJECT_DW`, `PROJECT_REF`, `PROJECT_REPORTING`, `PROJECT_SILVER`, `PROJECT_STAGING` | PASS |
| PaperSonar roles | 4 | `PAPERSONAR_ADMIN`, `PAPERSONAR_LOADER`, `PAPERSONAR_TRANSFORMER`, `PAPERSONAR_REPORTER` | PASS |
| ELT warehouse | X-Small, auto-suspend 60, monitor `RM_PAPERSONAR_ELT` | `WH_PAPERSONAR_ELT` — X-Small, `AUTO_SUSPEND 60`, state `SUSPENDED`, 0 queued | PASS |
| Reporting views | 6 | `VW_RESEARCH_OUTPUT`, `VW_SOURCE_OBSERVATION`, `VW_CITATION_SNAPSHOT`, `VW_CATEGORY_COVERAGE`, `VW_PUBLISHED_BATCH`, `VW_PIPELINE_HEALTH` | PASS |
| Base tables by schema | — | audit 11, bronze 5, DW 19, reference 7, silver 3, staging 11 | PASS |
| No paid resources | none | only X-Small standard warehouses; trial account | PASS |

Role grants at snapshot time: `PAPERSONAR_ADMIN` was granted to 2 users,
the other three roles to 1 user each. See §10 for the least-privilege
housekeeping that is still open.

## 2. Task graph and scheduler contract

All 10 tasks exist in `PAPERSONAR.PROJECT_AUDIT`, owned by
`PAPERSONAR_ADMIN`, running on `WH_PAPERSONAR_ELT`:

| Task | State | Predecessor | Action |
|---|---|---|---|
| `TASK_ELT_ROOT` | `suspended` | — (root, finalizer = `TASK_ELT_FINALIZER`) | `SP_CLAIM_BATCH()` |
| `TASK_ELT_COPY` | `started` | root | `SP_RUN_STAGE('COPY')` |
| `TASK_ELT_BRONZE` | `started` | copy | `SP_RUN_STAGE('BRONZE')` |
| `TASK_ELT_SILVER` | `started` | bronze | `SP_RUN_STAGE('SILVER')` |
| `TASK_ELT_CATEGORIZE` | `started` | silver | `SP_RUN_STAGE('CATEGORIZE')` |
| `TASK_ELT_DIMENSIONS` | `started` | categorize | `SP_RUN_STAGE('DIMENSIONS')` |
| `TASK_ELT_FACTS` | `started` | dimensions | `SP_RUN_STAGE('FACTS')` |
| `TASK_ELT_DQ` | `started` | facts | `SP_RUN_STAGE('DQ')` |
| `TASK_ELT_PUBLISH` | `started` | dq | `SP_RUN_STAGE('PUBLISH')` |
| `TASK_ELT_FINALIZER` | `started` | — (finalizer of root) | `SP_FINALIZE_BATCH()` |

- The `schedule` column is empty for **every** task, including the root.
  Snowflake owns no cron; GitHub Actions (`0 1 * * *`, 01:00 UTC) is the only
  scheduler and runs the suspended root through `EXECUTE TASK`.
- The root stays suspended by design: Snowflake refuses `ALTER TASK ... RESUME`
  on a root without `SCHEDULE`, `AFTER`, `FINALIZE` or `WHEN`.

## 3. Batch ledger at snapshot time

| Batch | Source | Mode | Window | Files | Records | Capped | Status |
|---|---|---|---|---|---|---|---|
| `BATCH_07D9668D4CBED88D815D30CA` | OPENALEX | full | 11-17 → 11-18 | 5 | 168,725 | no | PUBLISHED |
| `BATCH_B51983B70B26023F22201AE2` | CROSSREF | incremental | 11-20 | 2 | 20,000 | yes | PUBLISHED |
| `BATCH_DAB12A7209208BE375D89C0B` | CROSSREF | incremental | 11-21 | 2 | 30,000 | yes | PUBLISHED |
| `BATCH_70CEE97747ED6A70D3E40411` | CROSSREF | incremental | 11-17 | 7 | 118,400 | no | EXTRACTING (stuck — §10) |
| `BATCH_2F4B3168EE13A751ECFE8AE4` | ARXIV | incremental | 11-13 → 11-20 | 1 | 19,824 | no | FAILED (regex, since fixed) |
| `BATCH_3DF8101D66B0797A217FD877` | ARXIV | incremental | 11-14 → 11-21 | 1 | 15,505 | no | FAILED (DQ-012 — §5) |
| `BATCH_0D23C6C167941A817239C45B` | ZENODO | incremental | 11-13 → 11-20 | 5 | 109,499 | no | FAILED (regex, since fixed) |
| `BATCH_A75F9C61B9BF73B40CBC8C54` | ZENODO | incremental | 11-14 → 11-21 | 3 | 54,750 | yes | FAILED (DQ-012 — §5) |
| `BATCH_E0303CAD6AAC633E2C60BC2A` | DATACITE | incremental | 11-18 | 26 | 582,512 | no | FAILED (oversize text — §6) |
| `BATCH_FA946DC9EA79F54798BBFE82` | DATACITE | incremental | 11-19 | 15 | 327,419 | no | FAILED (oversize text — §6) |
| `BATCH_EB4210A9204AF7243A942647` | DATACITE | incremental | 11-20 | 1 | 15,075 | no | FAILED (oversize text — §6) |
| `BATCH_8773F6D3E97673137420667B` | OPENALEX | incremental | 11-18 | 0 | 0 | no | FAILED (staged file size mismatch) |

Publication ledger at snapshot time (the publication contract — only these
batches are visible through the reporting views):

| Batch | Published at | DQ summary | Capped |
|---|---|---|---|
| `BATCH_DAB12A7209208BE375D89C0B` | 2026-11-21 08:38:42 | `critical_failures=0;total_failures=2` | yes |
| `BATCH_B51983B70B26023F22201AE2` | 2026-11-19 22:49:43 | `critical_failures=0;total_failures=2` | yes |
| `BATCH_07D9668D4CBED88D815D30CA` | 2026-11-19 09:58:29 | `critical_failures=0;total_failures=2` | no |

## 4. Data quality gate

12 rules are evaluated per batch (`config/quality_rules.yml`, mirrored in
`PROJECT_REF.REF_DQ_RULE`). Every **CRITICAL** rule passed on every published
batch. The only failures were warnings:

| Rule | Severity | Layer | Meaning | Snapshot status |
|---|---|---|---|---|
| DQ-001 | CRITICAL | STAGING | manifest file count = staged row count | PASS |
| DQ-002 | CRITICAL | BRONZE | bronze = distinct staged keys | PASS |
| DQ-003 | CRITICAL | SILVER | crosswalk + quarantine = bronze | PASS |
| DQ-004 | CRITICAL | DW | one fact row per `OUTPUT_SK` | PASS |
| DQ-005 | CRITICAL | DW | no orphan/null dimension references | PASS |
| DQ-006 | CRITICAL | DW | no orphan bridge dimension references | PASS |
| DQ-007 | CRITICAL | DW | one current SCD2 row per author key | PASS |
| DQ-008 | WARNING | SILVER | invalid DOIs visible in quarantine | PASS (FAIL on arXiv, 5 records) |
| DQ-009 | WARNING | CATEGORIZATION | categorization coverage ≥ 0.60 | FAIL (0.0408 Zenodo / 0.0546 arXiv) |
| DQ-010 | WARNING | AUDIT | watermark freshness ≤ 72 h | FAIL on first backfill (no prior watermark) |
| DQ-011 | CRITICAL | BRONZE | required top-level payload keys present | PASS |
| DQ-012 | CRITICAL | CATEGORIZATION | exactly one primary category per output | PASS on published batches (FAIL on the two batches of §5) |

DQ-010 fails by design on a first backfill: the gate runs before `PUBLISH`, so
no watermark exists yet. DQ-009 is the known taxonomy-coverage gap that Phase 3
WP1 must close.

## 5. Incident 1 — DQ-012 fan-out (false CRITICAL failure)

**Symptom.** arXiv `BATCH_3DF8101D66B0797A217FD877` and Zenodo
`BATCH_A75F9C61B9BF73B40CBC8C54` were blocked at the publication gate with
`DQ-012` FAIL — observed 1 and 12 outputs respectively — even though every
other critical rule passed and the data was demonstrably loaded
(`arXiv: staging 15,505 = bronze 15,505 = crosswalk 15,505 = silver 15,505`;
`Zenodo: staging 54,750, bronze/silver/crosswalk 31,751, quarantine 835`).

**Root cause.** DQ-012 counted *join rows* between
`SLV_OUTPUT_CROSSWALK` and the primary-category assignment. The crosswalk is
unique **per source observation**, not per canonical output, so one canonical
output observed by several sources produced several joined rows and was
counted as several primary-category assignments. The fan-out was a defect in
the check, not in the data.

**Fix.** `sql/08_audit_dq/02_run_dq.sql` now de-duplicates to one row per
canonical output (`SELECT DISTINCT OUTPUT_BK`) and compares the number of
primary-category assignments (`PRIMARY_COUNT`) with exactly one. Regression
coverage: `tests/sql/test_sql_contracts.py::test_dq012_counts_primary_categories_without_crosswalk_fanout`.

**Verification.** After the fix was deployed, both batches were re-run to
publication; the account owner confirmed both as `PUBLISHED` with
`critical_failures=0`. The refreshed DQ verdict set is captured by
`sql/99_tests/03_phase2_closeout.sql` J3/J4 (§9).

**Related runner defect.** A green GitHub Actions run had previously hidden a
failed Snowflake batch: `trigger --drain` returned success even when the batch
ended `FAILED`. `src/runner/cli.py` now exits `1` when a batch that was pending
at drain start ends `FAILED`, and `src/runner/snowflake.py::batch_statuses`
reports `ERROR_SUMMARY`. Covered by `tests/unit/test_runner_cli.py`.

## 6. Incident 2 — DataCite oversize text truncation

**Symptom.** Three DataCite batches failed in the warehouse, never in the
extractor:

- `PUBLICATION_DATE_RAW` — `String '2022-05-23/2022-06-05/2024-09-30/...' is
  too long and would be truncated` (SILVER stage).
- `TOPIC_NAME` — `String 'Topología relacional humano-IA, ...' is too long and
  would be truncated` (DIMENSIONS stage, `STG_DIM_TOPIC`).

**Root cause.** DataCite records can carry multi-valued dates and very long
subject/topic strings. The silver and staging columns were sized for the
common case (`VARCHAR(200)` / `VARCHAR(500)`), so Snowflake refused the write
instead of silently truncating it.

**Fix.** `sql/03_silver/04_widen_oversize_text.sql` widens the affected
columns (`PUBLICATION_DATE_RAW` → 4000, `TOPIC_NAME` → 4000, `TOPIC_KEY` and
`BUSINESS_KEY` → 1000) and the loaders guard with `LEFT(..., n)`. Coverage:
`tests/sql/test_sql_contracts.py::test_oversize_source_text_columns_are_wide_enough`.

**Verification.** The migration was deployed by `deploy-ci` on push to `main`.
The refreshed DataCite batch status is captured by §9 (J1). Historical
DataCite windows remain failed and are retained as audit history — they are
not re-run automatically.

## 7. Model population at snapshot time

| Dimension | Rows | | Fact / bridge | Rows |
|---|---|---|---|---|
| `DIM_AUTHOR` | 381,172 | | `FACT_RESEARCH_OUTPUT` | 264,916 |
| `DIM_INSTITUTION` | 27,858 | | `FACT_OUTPUT_RELATION` | 1,811,026 |
| `DIM_TOPIC` | 70,103 | | `FACT_CITATION_SNAPSHOT` | 265,968 |
| `DIM_VENUE` | 15,172 | | `FACT_OUTPUT_SOURCE_OBSERVATION` | 265,981 |
| `DIM_DATE` | 14,611 | | `BRIDGE_OUTPUT_AUTHOR` | 599,309 |
| `DIM_CATEGORY` | 22 | | `BRIDGE_OUTPUT_TOPIC_CATEGORY` | 265,037 |
| `DIM_COUNTRY` | 1 | | `BRIDGE_AUTHOR_INSTITUTION` | 164,829 |
| `DIM_LANGUAGE` | 103 | | `DIMENSION_KEY_MAP` | 942,762 |
| `DIM_ACCESS_STATUS` | 7 | | `SLV_RESEARCH_OUTPUT` | 829,436 |
| `DIM_OUTPUT_TYPE` | 59 | | `SLV_OUTPUT_CROSSWALK` | 863,568 |
| `DIM_SOURCE` | 6 | | `SLV_SOURCE_OBSERVATION` | 863,568 |

Course-scale targets (≥100 dimension rows, ≥10,000 fact rows) are exceeded by
roughly three orders of magnitude. `DIM_COUNTRY` with a single row reflects
that the current sources carry almost no country data; it is a data-coverage
limit, not a load failure.

## 8. Quarantine, watermarks and rejected data

Rejected records are visible, never dropped:

| Batch | Source | Reason | Records |
|---|---|---|---|
| `BATCH_EB4210A9204AF7243A942647` | DATACITE | `INVALID_DATE` | 1,229 |
| `BATCH_A75F9C61B9BF73B40CBC8C54` | ZENODO | `INVALID_DATE` | 835 |
| `BATCH_DAB12A7209208BE375D89C0B` | CROSSREF | `INVALID_DATE` | 507 |
| `BATCH_E0303CAD6AAC633E2C60BC2A` | DATACITE | `INVALID_DATE` | 410 |
| `BATCH_B51983B70B26023F22201AE2` | CROSSREF | `INVALID_DATE` | 194 |
| `BATCH_3DF8101D66B0797A217FD877` | ARXIV | `INVALID_DOI` | 5 |

Watermarks advance **only** after a complete window is published. At snapshot
time exactly two rows existed — one per published source window:

| Source | Entity | Watermark | Last batch |
|---|---|---|---|
| CROSSREF | WORK | 2026-11-21 | `BATCH_DAB12A7209208BE375D89C0B` |
| OPENALEX | WORK | 2026-11-19 | `BATCH_07D9668D4CBED88D815D30CA` |

No watermark row exists for the sources that had not yet published — the
fail-closed behaviour is working as designed. The refreshed watermark state
after the recovery is captured by §9 (J5).

## 9. How to refresh this evidence

Run the following read-only file as `PAPERSONAR_ADMIN` and save each result
set as a sanitized CSV under
`docs/phase2/evidence/2026-11-22-live-verification/`:

```text
sql/99_tests/03_phase2_closeout.sql
```

| Block | Purpose | Expected result |
|---|---|---|
| J1 | batch ledger | arXiv and Zenodo batches from §5 are `PUBLISHED` |
| J2 | publication contract | one row per published batch, nothing else |
| J3 / J4 | latest DQ verdict and rollup | `CRITICAL_FAILURES = 0` for every published batch |
| J5 | watermarks | a row per published source window |
| J6 / J7 | task graph and schedule contract | 9 children `started`, root `suspended`, zero scheduled tasks |
| J8 | model population | counts ≥ the §7 snapshot |
| J9 | quarantine composition | matches §8 plus any new rejections |
| J10 | non-terminal batches | empty, after the §10 cleanup |
| J11 | taxonomy reference state | `REF_TAXONOMY_MAP` / `CATEGORY_OVERRIDE` still empty — Phase 3 WP1 |
| J12 | user defaults and grants | service-user defaults fixed |
| J13 | reporting view counts | views expose only published batches |

## 10. Open items at closeout

| # | Item | Severity | Action | Owner |
|---|---|---|---|---|
| 1 | `BATCH_70CEE97747ED6A70D3E40411` (CROSSREF) stuck in `EXTRACTING` with DQ-001 FAIL (4 file count mismatches) | medium | close the batch as `FAILED` so no batch is left in a non-terminal state | account owner |
| 2 | `SVC_PAPERSONAR` default role points at the non-existent `PAPERSONAR_INGEST`; default warehouse points at `PAPERSONAR_WH` | medium | `ALTER USER SVC_PAPERSONAR SET DEFAULT_ROLE='PAPERSONAR_LOADER', DEFAULT_WAREHOUSE='WH_PAPERSONAR_ELT'` | account owner |
| 3 | `PAPERSONAR_ADMIN` granted to 2 users | low | keep the owner grant, revoke the service-user grant | account owner |
| 4 | `PAPERSONAR_WH` (unused) and account-default `COMPUTE_WH` left running | low | drop `PAPERSONAR_WH`; suspend `COMPUTE_WH` or leave it as the account default deliberately | account owner |
| 5 | Categorization coverage 4.1% / 5.5% against a 60% target (DQ-009) | high for Phase 3 | Phase 3 WP1: expand `config/taxonomy.yml`, seed `REF_TAXONOMY_MAP`, re-categorize published batches | Phase 3 |
| 6 | `DIM_TOPIC` has no fact bridge | low | Phase 3 WP2 adds the output-to-topic bridge if the business questions require it | Phase 3 |
| 7 | OpenAlex incremental (`from_updated_date`) returns HTTP 403 `Plan upgrade required` | medium | needs a Member+/Partner plan; no publication-date fallback is allowed | account owner |
| 8 | DataCite historical windows (11-18, 11-19) still failed | low | optional replay after the width fix; one window per run | account owner |
| 9 | `DIM_COUNTRY` has 1 row | low | accept for Phase 2; revisit if the business questions require geography | Phase 3 |

## 11. Known limits of this evidence

- The evidence is a snapshot of one account at one point in time; no
  credential, key or account identifier is included.
- The arXiv and Zenodo publication statuses in §5 were confirmed by the
  account owner's own query output after the DQ-012 fix was deployed. The
  machine-readable export of that confirmation is the §9 refresh.
- OpenAlex incremental mode is **not** proven live: `from_updated_date`
  requires a Member+/Partner daily-sync plan and currently returns HTTP 403.
  The zero-record/nothing-new path is covered by unit tests only.
- `ACCOUNTADMIN` setup grants in `sql/00_setup/` were not applied to the
  account by these runs; the inline JSON file format in `SP_COPY_BATCH` avoids
  requiring `USAGE` on `FF_NDJSON_GZ` for the service roles.
- Local verification for the code changes quoted here:
  `python -m pytest tests -q` (242 passed) and `ruff check src tests` (clean).
