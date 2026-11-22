# Phase 3 Course Mapping — PaperSonar questions vs the course's example domain

**Date:** 2026-11-22 · **Branch:** `phase3` · **Status:** final for the Phase 3 submission

The course requirements describe a **retail analytics** example (products,
stores, revenue, customers). PaperSonar is a **research-intelligence** platform
built on five scholarly metadata sources. The course explicitly states that
the retail domain is an example and not a domain-fit requirement, so this
document maps every required technical element onto the PaperSonar model
instead of copying retail names into the SQL.

## 1. Element-by-element mapping

| Course requirement (example domain) | PaperSonar implementation | Evidence |
|---|---|---|
| Product dimension | `DIM_CATEGORY` (taxonomy contract v3: 67 categories in 10 domains) reached through `BRIDGE_OUTPUT_TOPIC_CATEGORY` | `docs/phase3/evidence/00_taxonomy/WP1_TAXONOMY_EVIDENCE.md` |
| Store dimension | `DIM_VENUE` (15,172 venues) and `DIM_INSTITUTION` (38,363 institutions) | `docs/phase3/evidence/01_queries/Q06_venues_by_topic.csv`, `Q07_institution_contribution.csv` |
| Customer dimension | `DIM_AUTHOR` (381,172 authors) reached through `BRIDGE_OUTPUT_AUTHOR` | `docs/phase3/evidence/01_queries/Q10_repeat_author_activity.csv` |
| Time dimension | `DIM_DATE` (14,611 days) and `PUBLICATION_YEAR` on the fact | `docs/phase3/evidence/01_queries/Q14_partial_year_comparison.csv` |
| Sales fact | `FACT_RESEARCH_OUTPUT` (296,299 outputs) | `docs/phase3/evidence/00_taxonomy/WP1_TAXONOMY_EVIDENCE.md` §7 |
| Transaction fact | `FACT_OUTPUT_RELATION` (2,557,842 citation/reference edges, 94,912 induced inside the corpus) | `docs/phase3/evidence/01_queries/Q11_companion_citation_edges.csv` |
| Snapshot fact | `FACT_CITATION_SNAPSHOT` (265,968 observations) | `docs/phase3/evidence/01_queries/Q03_citation_impact.csv` |
| Revenue measure | `CITED_BY_COUNT` (citation impact) and `WORKS` counts | `Q03_citation_impact.csv`, `Q04_citation_gains.csv` |
| Margin / basket measure | fractional institution credit per work, and topic-pair joint-work counts | `Q07_institution_contribution.csv`, `Q05_topic_intersections.csv` |
| Customer segment | author key / ORCID, and category co-assignment | `Q10_repeat_author_activity.csv`, `Q05_topic_intersections.csv` |
| Sales growth by product | topic growth and topic share, 2023 vs 2025 | `Q01_topic_growth.csv`, `Q02_topic_share.csv` |
| Store-level performance | venues and institutions that publish or contribute to a topic | `Q06_venues_by_topic.csv`, `Q08_institution_concentration.csv` |
| ROLLUP / CUBE / GROUPING SETS | `sql/10_analytics/09_rollup_cube.sql` | `docs/phase3/evidence/02_olap/OLP1…OLP3` |
| Five reporting views | `sql/07_reporting/04_phase3_reporting_views.sql` | `SHOW VIEWS` in `PROJECT_REPORTING` |
| Data-quality gate | 12 DQ rules, fail-closed publication, per-batch results | `PROJECT_AUDIT.DQ_RESULT`, `res/I.csv` |
| Optimization proof | `EXPLAIN ANALYZE` / `EXPLAIN USING JSON` before and after clustering | `docs/phase3/evidence/03_optimization/` |
| BI deliverable | three Power BI pages over the five views | `docs/phase3/POWERBI_SPEC.md` |
| Insight deliverable | evidence-backed insights report and deck | `docs/phase3/INSIGHTS_REPORT.md` |

## 2. Measures that were deliberately **not** invented

* No revenue, sales, price, margin, customer-spend or conversion figure
  exists anywhere in the project. The model has no such attributes, and a
  made-up number would break the traceability rule.
* The only measures are counts, ratios with an explicit denominator,
  citation counts, fractional credit and dates.
* Every ratio in the evidence states its denominator and its unknown share
  (`Q12_metadata_coverage.csv` is the worked example).

## 3. Named-question correspondence

The fourteen Phase 1 questions are business questions about research
literature. Each one keeps its decision, measure, analysis and limit in the
SQL comment block that implements it, so the requirement text and the
implementation cannot drift apart:

| Phase 1 question (PaperSonar wording) | SQL | Evidence CSV |
|---|---|---|
| Q01 topic growth | `01_topic_growth_share.sql` | `Q01_topic_growth.csv` |
| Q02 topic share | `01_topic_growth_share.sql` | `Q02_topic_share.csv` |
| Q03 citation impact by cohort | `02_citation_impact.sql` | `Q03_citation_impact.csv` |
| Q04 citation gains | `02_citation_impact.sql` | `Q04_citation_gains.csv` |
| Q05 topic intersections | `03_topic_intersections.sql` | `Q05_topic_intersections.csv` |
| Q06 venues by topic | `04_venues_and_institutions.sql` | `Q06_venues_by_topic.csv` |
| Q07 institution contribution | `04_venues_and_institutions.sql` | `Q07_institution_contribution.csv` |
| Q08 institution concentration | `04_venues_and_institutions.sql` | `Q08_institution_concentration.csv` |
| Q09 open access by topic | `05_access_and_authors.sql` | `Q09_open_access_by_topic.csv` |
| Q10 repeat author activity | `05_access_and_authors.sql` | `Q10_repeat_author_activity.csv` |
| Q11 topic citation flow | `06_relationship_flow.sql` | `Q11_topic_citation_flow.csv` |
| Q12 metadata coverage weakness | `07_metadata_coverage.sql` | `Q12_metadata_coverage.csv` |
| Q13 counting-method sensitivity | `08_sensitivity_and_period.sql` | `Q13_counting_sensitivity.csv` |
| Q14 partial-year comparison | `08_sensitivity_and_period.sql` | `Q14_partial_year_comparison.csv` |

## 4. Interpretation limits that travel with the numbers

1. **The corpus is the retained corpus.** Every count describes the 296,299
   published outputs of this account, not all research worldwide.
2. **The recent-year corpus is small.** 2023 holds 389 published works and
   2025 holds 1,053 (Q01/Q02 evidence). Growth rankings between those years
   are therefore suppressed by the 30-work threshold, exactly as the Phase 1
   limit requires. The corpus is bimodal in time: a large block of 2026
   records from the current extraction windows and a long pre-2009 tail.
3. **Affiliation metadata is historical.** No output with a resolved
   institution is dated between 2009 and 2025, so the institution questions
   run over the whole corpus and report the year as a dimension.
4. **Citation edges inside the corpus are rare.** 94,912 of 2,557,842
   relation rows have both endpoints inside the published corpus; Q11 reports
   that induced subgraph and nothing else.
5. **Categorization coverage is uneven by source.** OpenAlex 98.30%,
   arXiv 100.00%, Crossref 35.30%, Zenodo 34.33%. Crossref carries no
   subject field at all, so its ceiling is measured, not assumed.
