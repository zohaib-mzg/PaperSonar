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
| WP5 — measured optimization (before/after clustering) | **In progress** — measurement runs outstanding | `docs/phase3/OPTIMIZATION_REPORT.md`, `docs/phase3/evidence/03_optimization/` |
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
- Warehouses in use: `WH_PAPERSONAR_ELT` only. `PAPERSONAR_WH` is unused and scheduled for deletion; `COMPUTE_WH` is the account default warehouse and is scheduled to be suspended.
- The service user `SVC_PAPERSONAR` now defaults to `PAPERSONAR_LOADER` on `WH_PAPERSONAR_ELT`; whether the administrative grant can be revoked depends on whether that user is the deployment login, which is checked in `sql/00_setup/07_housekeeping.sql` step 3.

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

1. **WP5 measurement.** Run the twelve before-runs and the twelve after-runs
   described in `docs/phase3/OPTIMIZATION_REPORT.md` §2, save the artefacts in
   `res/`, and fill in §5 of the report with the measured table and the
   keep-or-roll-back decision.
2. **Housekeeping.** Run `sql/00_setup/07_housekeeping.sql` statement by
   statement: close the abandoned Crossref batch
   `BATCH_70CEE97747ED6A70D3E40411` as `FAILED`, set the service-user
   defaults, decide the administrative revoke, drop `PAPERSONAR_WH` and
   suspend `COMPUTE_WH`.
3. **Merge.** Merge `phase3` into `main` once 1 and 2 are closed; the
   deployment workflow then runs against `main`.

## 6. How to verify the current state

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
```
