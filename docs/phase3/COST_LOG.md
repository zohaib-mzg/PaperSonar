# Phase 3 Cost Log — free-only policy

**Date:** 2026-11-22 · **Account:** NI15271 · **Policy:** free-only. Trial credits only; no paid resources, no alternative database.

## 1. Resources used

| Resource | Type | Size | Auto-suspend | Why it is on the account | Cost status |
|---|---|---|---|---|---|
| `WH_PAPERSONAR_ELT` | Standard warehouse | X-Small | 60 s | The only warehouse the project uses for ELT, analytical queries and the benchmark | Trial credit |
| `RM_PAPERSONAR_ELT` | Resource monitor | — | — | Caps the ELT warehouse so a runaway task cannot drain the trial | Free |
| `PAPERSONAR_ADMIN` / `_LOADER` / `_TRANSFORMER` / `_REPORTER` | Roles | — | — | Separation of duties for the ingestion pipeline and the reporting layer | Free |
| `COMPUTE_WH` | Account-default warehouse | X-Small | 300 s | **Not used by the project.** It is the Snowflake account default and it was left running by the provisioning. It is suspended in the housekeeping step and excluded from every job. | Trial credit, unused |
| `PAPERSONAR_WH` | Standard warehouse | X-Small | 60 s | **Not used by the project.** Created during Phase 1 and superseded by `WH_PAPERSONAR_ELT`; dropped in the housekeeping step. | Trial credit, unused |

No paid tier, no materialized-view background refresh, no dynamic table, no
external network function, no third-party service and no second database were
introduced in Phase 3.

## 2. Credit position

| Item | Value | Source |
|---|---|---|
| Trial credits at the start of Phase 3 | $400 | account statement |
| Credits remaining at the start of Phase 3 | $328 | account statement |
| Snowflake trial remaining | about 23 days at 2026-11-22 | account statement |

The trial window, not the credit balance, is the binding constraint: the
project is therefore front-loaded so that every course-visible artefact
exists in the repository before the deadline.

## 3. Cost control measures applied

1. **One X-Small warehouse with 60-second auto-suspend.** Every query in the
   analytical layer runs on it, and it suspends itself within a minute of the
   last statement.
2. **The resource monitor** limits the ELT warehouse so that a single failed
   or looping task cannot consume the remaining credits.
3. **The analytical layer is manual.** `sql/10_analytics/` is marked
   `-- Deploy: manual`, so the deployment client never runs the 14 business
   queries, the three OLAP analyses or the benchmark. They run by hand when
   the evidence is collected.
4. **Physical-design extras stay off.** `sql/07_reporting/02_physical_demos.sql`
   contains the materialized view and the dynamic table, both marked
   `-- Deploy: manual` and both left uncreated because their background
   refresh costs credits continuously for a benefit that has not been
   measured.
5. **Clustering is measured before it is kept.** The clustering keys in
   `sql/06_facts/03_phase3_clustering.sql` rewrite three tables. They are
   applied only after the baseline benchmark is saved, and the file carries
   the rollback statement for the case where the measurement does not
   justify the cost.
6. **The extraction is windowed and resumable.** A capped batch is published
   for visibility but never advances the source watermark, so a partial
   window costs one extraction pass and not a repeated full load.

## 4. Phase 3 execution cost

| Workload | Warehouse time | Notes |
|---|---|---|
| Taxonomy re-categorization of five batches (categorize, dimensions, facts, DQ, publish) | about 40 minutes of X-Small time, spread over several manual runs | The heavy part is the category bridge rebuild for 296,299 outputs |
| 14 business queries + 3 OLAP analyses | about 15 minutes | Read-only, run once each for the evidence export |
| Optimization benchmark (before/after) | about 10 minutes | Four statements, three measurement forms each |
| Clustered re-write of three tables | one-off re-clustering cost | Justified only by the measured delta in `docs/phase3/OPTIMIZATION_REPORT.md` |

## 5. What would have cost money and was avoided

* A larger warehouse (S or M) for the intersection and citation-flow queries.
  The queries complete on X-Small; the runtime is reported in
  `docs/phase3/OPTIMIZATION_REPORT.md` instead of being bought away.
* A second Snowflake account or a paid tier for the trial's last weeks.
  The project does not depend on one.
* Materialized views and dynamic tables for the BI layer. Five secure views
  and the exported CSVs are enough for the Power BI pages.
