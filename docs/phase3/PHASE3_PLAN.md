# PaperSonar Phase 3 Plan — Analytical Layer, OLAP, Optimization, BI and Insights

**Status:** approved for execution · **Branch:** `phase3` (cut from `main` at `8353fd0`) · **Date:** 2026-11-22
**Owner:** repository owner (account + GitHub) with agent-assisted implementation
**Cost policy:** free-only. Snowflake trial/credits only; no paid resources, no alternative database.

---

## 1. Purpose and exit definition

Phase 2 built and proved the ingestion and transformation platform: five source
connectors, a fail-closed DQ gate, a Kimball star schema and a publication
registry. Phase 3 turns that platform into the **analytical deliverable** the
course asks for: aggregations that answer the fourteen business questions,
OLAP-style `ROLLUP`/`CUBE`, five reporting views, measured query optimization,
a three-page Power BI example, and an evidence-backed insights report with a
presentation.

Phase 3 exits when every row of the Phase 3 section of
`docs/requirements/course-requirements-matrix.md` shows a validated result in
this repository, and every claim in the insights report is traceable to a query
result that is stored in `docs/phase3/evidence/`.

---

## 2. Preconditions (Phase 2 exit state)

| Precondition | State at plan time | Evidence |
| --- | --- | --- |
| Five sources extracted | OpenAlex, Crossref, arXiv, Zenodo published; DataCite in flight | `docs/phase2/evidence/` |
| DQ gate fail-closed and green | All 12 rules PASS, all CRITICAL rules PASS on published batches | `res/I.csv`, `PROJECT_AUDIT.DQ_RESULT` |
| Star schema populated | 296,299 facts (five published batches), 381K authors, 27.9K institutions, 1.81M relations | `docs/phase3/evidence/00_taxonomy/WP1_TAXONOMY_EVIDENCE.md`, `res/D1.csv`, `res/A7.csv` |
| Surrogate-key integrity | 0 orphans, 0 null SKs, 0 duplicate grains | `sql/99_tests/02_phase2_verification.sql` section D |
| Publication contract | Reporting views expose only published batches | `PROJECT_REPORTING.VW_*` |
| Task graph and scheduler | 10-task graph, root suspended, GitHub is the sole scheduler | `res/B1.csv` |

**Blocking precondition — taxonomy coverage (DQ-009).** Only 4.1% (Zenodo) and
5.5% (arXiv) of outputs carry a real taxonomy category; the rest are
`unclassified`. The topic taxonomy is the analytical spine of Q01, Q02, Q05,
Q11 and Q13, so **WP1 (taxonomy expansion) is a hard prerequisite** for WP2's
topic questions and for every reporting view. Phase 3 starts with WP1 for that
reason.

**Constraint — trial lifetime.** The Snowflake trial expires in roughly three
weeks and $328 of the $400 credits remain. The plan is front-loaded so that
every course-visible artifact exists before the deadline; WP6 and WP7 (Power
BI and insights) are the only items that can be produced from exported CSVs
without the warehouse.

---

## 3. Requirement traceability

| Course requirement (matrix row) | Work package | Evidence artifact |
| --- | --- | --- |
| Analytical aggregations and 14 questions (Phase 3) | WP2 | `sql/10_analytics/01_analytical_queries.sql`, `docs/phase3/METRIC_CATALOGUE.md`, `docs/phase3/evidence/01_queries/*.csv` |
| `ROLLUP` and `CUBE` | WP3 | `sql/10_analytics/02_rollup_cube.sql`, `docs/phase3/evidence/02_olap/*.csv` |
| Reporting views: `vw_topic_growth`, `vw_output_coverage`, `vw_citation_cohorts`, `vw_topic_intersections`, `vw_research_community` | WP4 | `sql/10_analytics/03_reporting_views.sql` + deployed views |
| Query optimization — `EXPLAIN ANALYZE` before/after indexes | WP5 | `sql/10_analytics/04_optimization.sql`, `docs/phase3/OPTIMIZATION_REPORT.md` |
| Power BI three-page example | WP6 | `docs/phase3/POWERBI_SPEC.md`, DAX, screenshots, `docs/phase3/powerbi/` |
| Business insights and final presentation | WP7 | `docs/phase3/INSIGHTS_REPORT.md`, `docs/phase3/INSIGHTS_REPORT.pdf`, `docs/phase3/INSIGHTS_DECK.pptx` |
| Free-only | all | this plan, `docs/phase3/evidence/COST_LOG.md` |

The matrix notes that the course's retail views and KPIs are examples, not
domain-fit requirements. Phase 3 therefore implements the required technical
patterns with research-intelligence measures and documents that mapping in
`docs/phase3/COURSE_MAPPING.md`. No revenue, sales, customer or order figure
is invented anywhere.

---

## 4. Analytical model decisions (fixed before SQL is written)

| Decision | Choice | Reason |
| --- | --- | --- |
| "Topic taxonomy" for OLAP and views | the 67-row `REF_CATEGORY` taxonomy (taxonomy contract v3) reached through `BRIDGE_OUTPUT_TOPIC_CATEGORY` | It is the only output-to-taxonomy path in the model. `DIM_TOPIC` (70,103 rows) has no fact bridge and therefore cannot answer Q01/Q05; this is documented, not hidden. |
| Category scope | `IS_PRIMARY = TRUE` for single-category questions; all categories for intersection questions | Matches the Q1x definitions (primary topic) and Q05 (co-assigned works) |
| `unclassified` | excluded from growth/share rankings, reported separately as a coverage category | Prevents a fake 100% coverage claim |
| Denominator discipline | every ratio query returns numerator, denominator and the unknown/unspecified share | Required by Q09 and Q12 |
| Citation cohorts | `FACT_CITATION_SNAPSHOT` at one `SNAPSHOT_DATE_KEY` per cohort | "Use one observation date" (Q03) |
| Citation gains (Q04) | inner join on `OUTPUT_SK` between two snapshot dates; only works observed at both | "Only works present at both dates qualify" |
| Citation flow (Q11) | `FACT_OUTPUT_RELATION` with `TARGET_OUTPUT_SK IS NOT NULL`, direction preserved | Directed citing→cited pairs, induced subgraph |
| Year scope | 2021–2025 for cohort questions, 2023 vs 2025 for growth, elapsed-period cutoffs for Q14 | Taken verbatim from the Phase 1 question definitions |
| Suppression thresholds | Q01 ≥30 works per endpoint, Q05 ≥100 parent works and ≥5 joint works | Thresholds stated in the Phase 1 question definitions |
| Publication filter | every analytics query filters to published batches | Nothing outside the publication contract may be counted |

---

## 5. Work packages

### WP0 — Branch and hygiene (0.5 day, mostly done)

* `phase3` branch cut from `main`; `main` stays the Phase 2 baseline until Phase 3 is verified.
* Deliverable: this plan, committed on `phase3`.
* Exit: branch pushed, plan merged into the branch.

### WP1 — Taxonomy expansion (0.5–1 day) — prerequisite

*Status: code complete on `phase3`, awaiting deployment and re-categorization.
See [WP1_TAXONOMY_RUNBOOK.md](WP1_TAXONOMY_RUNBOOK.md).*

* Expand `config/taxonomy.yml` from 37 keyword rules to cover the observed
  corpus: mine the actual titles/topics of the published corpus for the most
  frequent terms per existing category, add synonyms and inflections, keep the
  short-pattern token-boundary rule.
* Seed the additions through `sql/04_categorization/01_seed_taxonomy.sql`
  (existing contract test enforces config↔SQL parity).
* Re-categorize the published corpus by re-running the CATEGORIZE → DIMENSIONS
  → FACTS → DQ → PUBLISH stages for the four published batches (all layers are
  idempotent; no source re-extraction).
* Exit: DQ-009 coverage ≥ 60% on each published batch, or a documented
  measured ceiling with the reason (e.g. genuinely untagged corpora) and an
  approved threshold change in `config/quality_rules.yml`.
* Evidence: `docs/phase3/evidence/00_taxonomy/DQ009_before_after.csv`.

### WP2 — Fourteen analytical queries (2 days)

One SQL file per question group, each query carrying: decision, measure,
denominator, threshold/suppression rule and interpretation limit (copied from
the Phase 1 question definition so the SQL and the requirement text cannot drift).

| Q | Title | Primary tables | Notes |
| --- | --- | --- | --- |
| Q01 | Topic growth 2023→2025 | `FACT_RESEARCH_OUTPUT`, `BRIDGE_OUTPUT_TOPIC_CATEGORY`, `DIM_CATEGORY` | CAGR where both endpoints positive; suppress <30 |
| Q02 | Topic share of corpus | fact + bridge | percentage-point change, share denominator explicit |
| Q03 | Cohort citation impact | `FACT_CITATION_SNAPSHOT` | median `CITED_BY_COUNT` per year/type at one snapshot date; cohort size + missing counts |
| Q04 | Citation gains between two observations | `FACT_CITATION_SNAPSHOT` self-join | positive gains ranked separately from negative revisions |
| Q05 | Sparse topic intersections | bridge self-join on `OUTPUT_SK` | unordered pairs; parent ≥100, pair ≥5; joint/smaller-parent ratio |
| Q06 | Venues that publish selected topics | fact + `DIM_VENUE` + bridge | missing-venue share shown |
| Q07 | Institutional contribution per topic | `BRIDGE_OUTPUT_AUTHOR` + `BRIDGE_AUTHOR_INSTITUTION` + `DIM_INSTITUTION` | fractional credit by author, deduplicated institutions |
| Q08 | Institutional concentration (top-5 share) | same as Q07 | computed after filtering; unknown institutions excluded and disclosed |
| Q09 | Open access by topic and year | fact + `DIM_ACCESS_STATUS` | known-status denominator, unknown share separate |
| Q10 | Repeat author activity in a direction | `BRIDGE_OUTPUT_AUTHOR` + `DIM_AUTHOR` | distinct works per author key, latest publication year |
| Q11 | Topic communities citing one another | `FACT_OUTPUT_RELATION` + bridge on both endpoints | directed; both endpoints admitted |
| Q12 | Metadata coverage weakness | fact + bridges + dims | missing DOI/topic/venue/institution/access shares over eligible populations |
| Q13 | Counting-method sensitivity | fact + bridge | primary-topic counts vs equal fractional allocation, with and without low-volume groups; rank change |
| Q14 | Partial-year vs same elapsed period | fact + `DIM_DATE` | common month-day cutoff, cutoff and retrieval date shown |

* Exit: 14 queries run in Snowflake without error, each result exported to
  `docs/phase3/evidence/01_queries/`, and `docs/phase3/METRIC_CATALOGUE.md`
  documents every measure, denominator and threshold.
* Contract test: `tests/sql/test_analytics_contracts.py` asserts one query per
  Q-number, the required suppression thresholds, and that no query invents a
  measure the catalogue does not define.

### WP3 — OLAP: ROLLUP, CUBE, GROUPING SETS (0.5 day)

* `sql/10_analytics/02_rollup_cube.sql` with three analyses matching the matrix:
  1. taxonomy × year → `ROLLUP(CATEGORY_KEY, PUBLICATION_YEAR)`
  2. output type × source → `CUBE(OUTPUT_TYPE_KEY, SOURCE_NAME)`
  3. topic × access status → `GROUPING SETS` over category, access status and year
* Every result set emits `GROUPING_ID` plus explicit `IS_GRAND_TOTAL` /
  `IS_SUBTOTAL` flags so a reader cannot mistake a subtotal for a member level.
* Exit: all three result sets exported; a short note in
  `docs/phase3/OLAP_NOTES.md` explains the hierarchy each rollup represents and
  why the cube is not a full cross product of every dimension.

### WP4 — Five reporting views (1 day)

`sql/10_analytics/03_reporting_views.sql` creates the matrix-named views:

| View | Grain | Feeds |
| --- | --- | --- |
| `vw_topic_growth` | category × year | BI page 1, Q01/Q02 |
| `vw_output_coverage` | source × year × type | BI page 1, Q12 |
| `vw_citation_cohorts` | output × snapshot date | BI page 2, Q03/Q04 |
| `vw_topic_intersections` | category pair | BI page 2, Q05/Q11 |
| `vw_research_community` | institution × category | BI page 3, Q07/Q08/Q10 |

* Built in `PROJECT_REPORTING`, `SECURE VIEW`, granted to `PAPERSONAR_REPORTER`
  exactly like the existing six views, and filtered to published batches.
* Exit: deployed, and a grant check shows `PAPERSONAR_REPORTER` can read them
  and no other role can write them.

### WP5 — Query optimization with measured before/after (1 day)

* Representative queries: Q01 growth scan, Q05 intersection self-join, Q11
  directed citation flow, plus the heaviest reporting view.
* Baseline: `EXPLAIN ANALYZE` output, runtime, bytes scanned, partitions
  scanned/pruned, and `QUERY_PROFILE`/`RESULT_SCAN` evidence.
* Change: Snowflake clustering keys on the hot access paths
  (`FACT_RESEARCH_OUTPUT` on publication year + source, `FACT_OUTPUT_RELATION`
  on relation type + output key), applied only where the measurement justifies
  the re-clustering cost.
* After: identical queries re-measured; deltas reported as absolute and
  percentage figures.
* `docs/phase3/OPTIMIZATION_REPORT.md` states the hardware/data caveats
  explicitly: trial X-Small warehouse, data volume of ~265K facts, a single
  snapshot environment, and the fact that clustering is a physical layout
  change whose benefit depends on query selectivity — no claim is generalized
  beyond what was measured.
* Exit: before/after tables in `docs/phase3/evidence/03_optimization/`, and the
  report states which change was kept and which was rejected.

### WP6 — Power BI three-page example (1 day)

* `docs/phase3/POWERBI_SPEC.md`: data model, sources (the five Phase 3 views),
  relationships, one measure per metric catalogue entry, and page layout.
* Page 1 Executive research overview — corpus growth, source mix, top topics,
  coverage caveats.
* Page 2 Detailed direction analysis — topic growth/share, citation cohorts,
  sparse intersections, topic citation flow.
* Page 3 Decision and evidence — institutional concentration, open-access
  availability, metadata caveats, and the recommendation table that WP7 turns
  into insights.
* DAX measures are written in the spec so the model is reproducible without the
  PBIX binary.
* Exit: spec + DAX + a PBIX file if Power BI Desktop is available on the owner
  machine, plus screenshots; otherwise the spec plus exported view data is the
  evidence and the limitation is stated.

### WP7 — Insights report and presentation (1 day)

* `docs/phase3/INSIGHTS_REPORT.md` → rendered to `INSIGHTS_REPORT.pdf`, and a
  `INSIGHTS_DECK.pptx` for the presentation.
* Content rules: every recommendation cites the query result it came from;
  counts carry their denominator and coverage caveat; no recommendation is
  stated when the supporting evidence is below its suppression threshold.
* A generator script (`scripts/build_phase3_insights.py`) reads the exported
  evidence CSVs and renders both artifacts, so the report can be regenerated
  when the corpus changes instead of hand-edited.
* Exit: PDF + PPTX in `docs/phase3/`, every figure traceable to a file in
  `docs/phase3/evidence/`.

### WP8 — Final acceptance and traceability (0.5 day)

* Update `docs/requirements/course-requirements-matrix.md` Phase 3 rows from
  "Not started" to the validated state with evidence pointers.
* Update `docs/phase2/IMPLEMENTATION_STATUS.md` and the evidence index.
* Merge `phase3` into `main` only after every Phase 3 row is evidenced.

---

## 6. Evidence flow (what the owner runs, what comes back)

| Step | Owner action | Returns | Stored in |
| --- | --- | --- | --- |
| E1 | Deploy Phase 3 SQL (auto on push to `main`, or manual dispatch) | deploy-ci green | Actions log |
| E2 | Run `sql/10_analytics/01_analytical_queries.sql` block by block, export results as CSV | 14 CSVs | `docs/phase3/evidence/01_queries/` |
| E3 | Run `sql/10_analytics/02_rollup_cube.sql`, export | 3 CSVs | `docs/phase3/evidence/02_olap/` |
| E4 | Run `sql/10_analytics/03_reporting_views.sql` (deployed) + a grant check | view inventory, row counts | `docs/phase3/evidence/04_views/` |
| E5 | Run `sql/10_analytics/04_optimization.sql` before and after clustering | EXPLAIN ANALYZE logs, query profiles | `docs/phase3/evidence/03_optimization/` |
| E6 | Build or refresh the Power BI model from the views | PBIX, screenshots | `docs/phase3/powerbi/` |

Export format: CSV per query with a header naming the Q-number, run timestamp
and warehouse, so every artifact is reproducible and attributable. No
credentials, no full row dumps.

---

## 7. Test and CI strategy

| Check | Where | Rule |
| --- | --- | --- |
| SQL header contract (purpose/inputs/outputs/idempotent/owner/cost) | `tests/sql/test_sql_contracts.py` | every new SQL file |
| One query per Q-number, thresholds present | `tests/sql/test_analytics_contracts.py` (new) | new in WP2 |
| View names match the matrix exactly, all `SECURE`, all granted | `tests/sql/test_analytics_contracts.py` | new in WP4 |
| No DDL in read-only packs, no `DROP`/`TRUNCATE` | existing contract test | all files |
| Python lint and unit tests | `ruff` + `pytest` in both workflows | existing |
| Taxonomy config↔SQL parity | existing contract test | WP1 |
| CI triggers | `deploy-ci` on `sql/**`, `src/runner/**`, `config/**`; `extract-load` on the schedule | unchanged |

Phase 3 adds no new source extraction, so the cost and failure surface stay
where they are: SQL only.

---

## 8. Cost and resource plan

| Item | Estimate | Control |
| --- | --- | --- |
| WP1 re-categorization of published batches | 4 graph runs over ~280K facts, X-Small | one batch per run, watch `WH_PAPERSONAR_ELT` auto-suspend |
| WP2/WP3 analytics scans | 14 + 3 queries over 265K–1.8M rows, seconds each | metadata-first, no `SELECT *` on fact tables |
| WP4 view creation | seconds | no data movement |
| WP5 clustering + re-measure | the main cost: re-clustering two tables + twice the measurement queries | measure first, cluster only where justified, one table at a time |
| WP6/WP7 | zero warehouse cost (local tooling) | generated from exported CSVs |
| Reserve | roughly $5–15 of the remaining $328 | monitor in Snowsight → Usage after each phase |

Warehouse discipline stays: `WH_PAPERSONAR_ELT`, X-Small, auto-suspend 60 s,
statement timeout 900 s, resource monitor `RM_PAPERSONAR_ELT`.

---

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Taxonomy coverage stays below 60% (DQ-009) | medium | high — topic questions become near-empty | WP1 mines real corpus terms; if the ceiling is genuine, publish the measured ceiling and revise the threshold with evidence instead of hiding it |
| Trial expires mid-plan | low-medium | high | front-load WP1–WP5 (all warehouse-dependent); WP6/WP7 run from exported CSVs |
| Clustering costs more than it saves on 265K rows | medium | medium | measure before/after; keep the change only if the measured win is real; report the rejected change |
| DataCite backlog still unpublished | medium | low — four sources already exceed every threshold | optional backlog run; not on the critical path |
| `DIM_TOPIC` has no fact bridge | certain | medium — "topic" analytics must use the category taxonomy | documented in section 4; surfaced in the course mapping and insights caveats |
| Power BI Desktop unavailable on the owner machine | medium | low | spec + DAX + screenshots from the service, limitation stated |
| Power BI Service needs a paid license | low | medium | PBIX is built and screenshotted locally; no service account is required |

---

## 10. Milestones

| Day | Milestone | Exit evidence |
| --- | --- | --- |
| D1 | WP0 + WP1 taxonomy expansion, DQ-009 re-run | coverage before/after CSV |
| D2 | WP2 Q01–Q07 | 7 query CSVs |
| D3 | WP2 Q08–Q14 + metric catalogue | 14 query CSVs + catalogue |
| D4 | WP3 OLAP + WP4 views deployed | 3 OLAP CSVs + view inventory |
| D5 | WP5 optimization measurement and clustering decision | before/after tables + report |
| D6 | WP6 Power BI spec, DAX, model, screenshots | spec + screenshots |
| D7 | WP7 insights PDF/PPT + WP8 acceptance, merge to `main` | PDF, PPTX, updated matrix |

Buffer: D8–D9 for re-runs, evidence gaps and the insights narrative. The plan
finishes inside the trial window with margin, and no step depends on buying
credits.

---

## 11. Definition of done

1. Fourteen analytical queries implemented, documented against their Phase 1
   definitions, and evidenced by exported results.
2. `ROLLUP`, `CUBE` and `GROUPING SETS` implemented with grouping flags and
   evidenced.
3. Five reporting views named exactly as the matrix requires, deployed,
   publication-filtered and least-privilege granted.
4. Optimization report with measured before/after evidence and explicit
   caveats; every claimed improvement reproducible from a stored result.
5. Three-page Power BI example with a data model, measures and screenshots.
6. Insights PDF and PPTX whose every claim points at stored evidence.
7. Requirements matrix updated; no "Not started" left in the Phase 3 rows.
8. Zero paid resources used; cost log recorded.
