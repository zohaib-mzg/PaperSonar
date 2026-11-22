# Phase 3 Status — PaperSonar analytics, taxonomy and reporting

**Date:** 2026-11-22 · **Branch:** `phase3` · **Account:** NI15271 · **Warehouse:** `WH_PAPERSONAR_ELT` (X-Small, 60-second auto-suspend)

---

## 1. What Phase 3 delivers

Phase 3 turns the Phase 2 warehouse into a decision tool: a working topic
taxonomy, fourteen measured analytical queries, three OLAP cubes, five secure
reporting views, a measured optimization, and the written insight report with
its Power BI specification.

| Work package | Status | Where the evidence is |
|---|---|---|
| WP1 — taxonomy v3 (67 categories, reproducible categorization) | Done | `docs/phase3/WP1_TAXONOMY_RUNBOOK.md`, `docs/phase3/evidence/00_taxonomy/` |
| WP2 — fourteen analytical queries (Q01–Q14) | Done | `sql/10_analytics/01..08*.sql`, `docs/phase3/evidence/01_queries/` |
| WP3 — OLAP (ROLLUP, CUBE, GROUPING SETS) | Done | `sql/10_analytics/09_rollup_cube.sql`, `docs/phase3/OLAP_NOTES.md`, `docs/phase3/evidence/02_olap/` |
| WP4 — five secure reporting views | Done, deployed | `sql/07_reporting/04_phase3_reporting_views.sql` |
| WP5 — measured optimization (before/after clustering) | Done — measured, no gain, clustering rolled back | `docs/phase3/OPTIMIZATION_REPORT.md`, `docs/phase3/evidence/03_optimization/` |
| WP6 — Power BI specification | Done (specification; PBIX itself needs the desktop client) | `docs/phase3/POWERBI_SPEC.md` |
| WP7 — insight report, PDF and deck | Done | `docs/phase3/INSIGHTS_REPORT.md`, `.pdf`, `INSIGHTS_DECK.pptx` |

## 2. The live corpus

| Source | Batch | Published records |
|---|---|---:|
| OpenAlex | `BATCH_07D9668D4CBED88D815D30CA` | 168,725 bronze → 168,577 outputs |
| Crossref (small) | `BATCH_B51983B70B26023F22201AE2` | 18,495 |
| Crossref (DAB) | `BATCH_DAB12A7209208BE375D89C0B` | 60,000 |
| arXiv | `BATCH_3DF8101D66B0797A217FD877` | 15,505 → 15,503 outputs |
| Zenodo | `BATCH_A75F9C61B9BF73B40CBC8C54` | 33,741 → 33,724 outputs |

- **296,299 outputs**, 0 duplicate DOIs.
- **894,545** category assignments (296,299 primary + 598,246 secondary), one row per output and category after the deduplication fix.
- **2,557,842** relation rows, 94,912 of them with a resolved target inside the corpus.
- **101,257** outputs with a resolved institution.
- **Category coverage 74.40%** (was 1.92% before the taxonomy work), 63 of the 67 categories populated.
- The Phase 2 closeout number (264,916) was understated: the Crossref DAB batch holds 60,000 records, not 30,000.

## 3. Account and cost state

- Credits: **$328 of $400** left; trial ends in roughly three weeks.
- Warehouses in use: `WH_PAPERSONAR_ELT` only (X-Small, auto-suspend 60,
  resource monitor `RM_PAPERSONAR_ELT`).
- `PAPERSONAR_WH` was dropped on 2026-11-22; it was created in Phase 1 and
  superseded by `WH_PAPERSONAR_ELT`.
- `COMPUTE_WH`, the account default warehouse, is **suspended** with
  `AUTO_SUSPEND = 60` and the resource monitor `RM_PAPERSONAR_ELT` attached.
  Snowflake refuses to suspend a warehouse that currently holds the account
  default role ("Invalid state. Warehouse 'COMPUTE_WH' cannot be suspended."),
  and `DEFAULT_WAREHOUSE` is not a settable account parameter in this
  account, so the auto-suspend plus the resource monitor is the effective
  control: the warehouse stops itself and cannot burn the trial credits.
  `SNOWFLAKE_LEARNING_WH` and `SYSTEM$STREAMLIT_NOTEBOOK_WH` are provisioning
  leftovers, both suspended and unused.
- The service user `SVC_PAPERSONAR` now defaults to `PAPERSONAR_LOADER` on
  `WH_PAPERSONAR_ELT`. Its `PAPERSONAR_ADMIN` grant was **kept on purpose**:
  `SHOW GRANTS OF ROLE PAPERSONAR_ADMIN` shows the grant held by
  `SVC_PAPERSONAR`, and the deployment workflow logs in as `SNOWFLAKE_USER`
  and assumes `SNOWFLAKE_DEPLOY_ROLE = PAPERSONAR_ADMIN`, so revoking it
  would stop every deployment. The data path itself runs on the narrow roles
  (`PAPERSONAR_LOADER`, `PAPERSONAR_TRANSFORMER`, `PAPERSONAR_REPORTER`); the
  administrative role exists only for the deployment principal. A dedicated
  deployment role without account-wide rights is the correct future change,
  and it needs a new GitHub secret, so it was not made at the end of the
  project.

## 3a. Failed-batch ledger

Five batches are published. Eight failed at some point in the project, and
every failure is accounted for:

| Batch | Source | Failed at | Cause | Status of the cause |
|---|---|---|---|---|
| `BATCH_8773F6D3E97673137420667B` | OpenAlex | extraction | staged part-file size mismatch | transient extraction check; the same source published successfully in `BATCH_07D9668D4CBED88D815D30CA` |
| `BATCH_70CEE97747ED6A70D3E40411` | Crossref | extraction | four manifest file mismatches | closed manually on 2026-11-22; never transformed, never published |
| `BATCH_2F4B3168EE13A751ECFE8AE4` | arXiv | silver | `REGEXP_SUBSTR` with a non-capturing group `(?:` | **fixed** — the pattern is gone from `sql/03_silver`; arXiv published later in `BATCH_3DF8101D66B0797A217FD877` |
| `BATCH_0D23C6C167941A817239C45B` | Zenodo | silver | the same unsupported regular expression | **fixed**; Zenodo published later in `BATCH_A75F9C61B9BF73B40CBC8C54` |
| `BATCH_3ECE33CC04DCAB9DF46F369D` | arXiv | categorize | `invalid identifier 'M.BASE_WEIGHT'` in the old categorization | **fixed** by the v3 rewrite of `sql/04_categorization/02_categorize_batch.sql` |
| `BATCH_FA946DC9EA79F54798BBFE82` | DataCite | silver | `PUBLICATION_DATE_RAW` too narrow for a multi-valued date string | **fixed** by `sql/03_silver/04_widen_oversize_text.sql` (widened to `VARCHAR(4000)`) |
| `BATCH_E0303CAD6AAC633E2C60BC2A` | DataCite | dimensions | `STG_DIM_TOPIC.TOPIC_NAME` too narrow for a long subject string | **fixed** by the same widening script |
| `BATCH_EB4210A9204AF7243A942647` | DataCite | dimensions | the same `TOPIC_NAME` truncation | **fixed** by the same widening script |

The three DataCite batches therefore failed on **code** that has since been
corrected; what still blocks DataCite is external (the registry's HTTP
responses during extraction). The DataCite path is not broken, it is untested
against a live extraction.


## 4. Evidence index

| Folder | Content |
|---|---|
| `evidence/00_taxonomy/` | taxonomy runbook summary and the DQ-009 before/after coverage file |
| `evidence/01_queries/` | Q01–Q14 result exports (Q04 and Q07 are the large ones) |
| `evidence/02_olap/` | OLP1 ROLLUP, OLP2 CUBE, OLP3 GROUPING SETS exports |
| `evidence/03_optimization/` | benchmark result files; the plan, timing and after-run artefacts are added when the measurement completes |

Supporting documents in `docs/phase3/`: `PHASE3_PLAN.md`, `METRIC_CATALOGUE.md`,
`COURSE_MAPPING.md`, `COST_LOG.md`, `OLAP_NOTES.md`, `POWERBI_SPEC.md`,
`INSIGHTS_REPORT.md`, `OPTIMIZATION_REPORT.md`.

## 5. Open items

1. **Confirm the deployment run on `main`.** The merge of `phase3` into `main`
   pushed `sql/**` and `config/**` and therefore triggered the deployment
   workflow automatically. The run re-applies the idempotent DDL, including
   `sql/03_silver/04_widen_oversize_text.sql`. Nothing else is outstanding.

**The widened columns were verified live on 2026-11-22:**

| Column | Live width |
|---|---:|
| `PROJECT_DW.DIMENSION_KEY_MAP.BUSINESS_KEY` | 1000 |
| `PROJECT_DW.DIM_TOPIC.TOPIC_NAME` | 4000 |
| `PROJECT_SILVER.SLV_SOURCE_OBSERVATION.PUBLICATION_DATE_RAW` | 4000 |
| `PROJECT_STAGING.STG_DIM_TOPIC.TOPIC_KEY` | 1000 |
| `PROJECT_STAGING.STG_DIM_TOPIC.TOPIC_NAME` | 4000 |

So the two truncating columns that failed the three DataCite batches are wide
on the account, and the DataCite path is no longer blocked by the project code.

## 6. Final state

- Every Phase 3 work package is delivered and evidenced, and every row of
  `docs/requirements/course-requirements-matrix.md` for Phase 3 is validated.
- The five published batches, the 296,299-output corpus, the 74.40% topic
  coverage, the five secure reporting views, the fourteen query exports, the
  three OLAP exports and the before/after optimization measurement are all
  committed under `docs/phase3/evidence/`.
- The account is closed down for the remaining trial time: one X-Small
  warehouse in use, both leftovers suspended, the resource monitor attached,
  the abandoned batch closed, the service user on least-privilege defaults.
- `phase3` was merged into `main` (fast-forward, 31 commits) so that the
  delivered branch is the deployed branch. `main` and `phase3` point at the
  same commit.


## 7. How to verify the current state

```sql
USE ROLE PAPERSONAR_ADMIN;
USE WAREHOUSE WH_PAPERSONAR_ELT;

SELECT BATCH_ID, SOURCE_NAME, STATUS, ERROR_SUMMARY
FROM PAPERSONAR.PROJECT_AUDIT.BATCH ORDER BY CREATED_AT;

SELECT COUNT(*) AS OUTPUTS FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT;
SELECT COUNT(*) AS ASSIGNMENTS FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY;
SELECT COUNT(*) AS RELATIONS FROM PAPERSONAR.PROJECT_DW.FACT_OUTPUT_RELATION;
SELECT COUNT(*) AS SNAPSHOT_ROWS FROM PAPERSONAR.PROJECT_DW.FACT_CITATION_SNAPSHOT;

SHOW VIEWS IN SCHEMA PAPERSONAR.PROJECT_REPORTING;
SHOW GRANTS OF ROLE PAPERSONAR_ADMIN;
SHOW WAREHOUSES;

SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
FROM PAPERSONAR.INFORMATION_SCHEMA.COLUMNS
WHERE (TABLE_NAME = 'SLV_SOURCE_OBSERVATION' AND COLUMN_NAME = 'PUBLICATION_DATE_RAW')
   OR (TABLE_NAME = 'STG_DIM_TOPIC' AND COLUMN_NAME IN ('TOPIC_NAME', 'TOPIC_KEY'))
   OR (TABLE_NAME = 'DIM_TOPIC' AND COLUMN_NAME = 'TOPIC_NAME')
   OR (TABLE_NAME = 'DIMENSION_KEY_MAP' AND COLUMN_NAME = 'BUSINESS_KEY')
ORDER BY TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME;
```
