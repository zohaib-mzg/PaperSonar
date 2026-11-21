# Requirements traceability matrix v2

This matrix keeps course requirements separate from PaperSonar product scope. Phase 2 items were implemented and live-verified on 2026-11-22; Phase 3 items are planned in `docs/phase3/PHASE3_PLAN.md` and not yet implemented.

| Requirement | Phase | PaperSonar response | Evidence / acceptance proof | State |
|---|---|---|---|---|
| Business problem, users, objectives | 1 | Research-direction comparison using transparent scholarly evidence | Proposal and business requirements | Design artifact exists; review against v2 scope |
| Minimum 10 analytical questions | 1 | 14 PaperSonar questions | Business questions report and metric catalogue | Designed; queries not implemented |
| Identify business processes | 1 | Output registration, source-record observation, citation/relationship observation, periodic output snapshot | Process/grain document | Revised target design required |
| Define fact grain and fact types | 1 | Transaction/accumulating entity output, periodic snapshot, factless typed relationships as appropriate | Model and grain statements | Current publication mart designed; source-neutral model needs v2 |
| Dimensions and hierarchies | 1 | Date, output type, topic taxonomy, person, institution, venue/repository, access, funder | Logical model and data dictionary | Expanded for five sources; `DIM_TOPIC` bridge is Phase 3 scope |
| Natural and surrogate keys | 1 | Source-native IDs and DOI crosswalk; warehouse surrogate keys | Key policy and dictionary | Implemented as `DIMENSION_KEY_MAP` + `SLV_OUTPUT_CROSSWALK` |
| Conceptual, logical, physical model | 1 | Source-to-canonical-output architecture and analytics mart | PNG/PDF diagram, DBML, dictionary | Existing diagrams retained; target architecture v2 added |
| Proposal, requirements, 10 questions, facts/grains, schema, dictionary | 1 | Keep editable artifacts and source register | Phase 1 deliverables folder | Existing artifacts retained; v2 master baseline added |
| 100+ dimension records | 2 | Target naturally from expanded source registry; measured after load | Count report per dimension | **Validated** — `DIM_AUTHOR` 381,172; `DIM_TOPIC` 70,103; `DIM_INSTITUTION` 27,858; `DIM_VENUE` 15,172; `DIM_DATE` 14,611 |
| 10,000+ fact records | 2 | Corpus profiling target; no arbitrary truncation; choose feasible scope | Counts after successful load | **Validated** — `FACT_RESEARCH_OUTPUT` 264,916; `FACT_OUTPUT_RELATION` 1,811,026; `FACT_CITATION_SNAPSHOT` 265,968 |
| Staging, cleaning, transformations | 2 | `PROJECT_STAGING` / `PROJECT_DW` / `PROJECT_REPORTING` | SQL/Python scripts and run manifests | **Validated** — `sql/01_staging`..`sql/07_reporting`; live batches published for 4 sources |
| Surrogate-key mapping | 2 | Business/source IDs mapped to dimension keys | Load report and orphan check | **Validated** — `DIMENSION_KEY_MAP` 942,762 rows; DQ-004..DQ-007 orphan checks pass live |
| Completeness, accuracy, integrity | 2 | Coverage, DOI conflicts, FK orphan checks, count reconciliation, bridge weight tests | Data quality PDF/CSV | **Validated** — 12-rule DQ gate live on every batch, `critical_failures=0` on published batches; DQ-009 coverage remains a Phase 3 gap (4–6% vs 60% target) |
| Analytical aggregations and 14 questions | 3 | Research-output measures with denominator and coverage | SQL files and validated result extracts | Planned — Phase 3 WP2 |
| `ROLLUP` and `CUBE` | 3 | Topic taxonomy × year, output type × source, topic × access; appropriate grouping sets | OLAP SQL and result evidence | Planned — Phase 3 WP2 |
| Reporting views | 3 | `vw_topic_growth`, `vw_output_coverage`, `vw_citation_cohorts`, `vw_topic_intersections`, `vw_research_community` | SQL view definitions | Planned — Phase 3 WP3 |
| Query optimization | 3 | `EXPLAIN ANALYZE` before/after indexes on representative queries | Indexing report with hardware/data caveats | Planned — Phase 3 WP4 |
| Power BI three-page minimum example | 3 | Executive research overview, detailed direction analysis, decision/evidence page | PBIX and screenshots | Planned — Phase 3 WP6 |
| Business insights and final presentation | 3 | Recommendations based on validated outputs, never invented outcomes | PDF report and PPT | Planned — Phase 3 WP7 |
| Free-only | All | Local PostgreSQL core; free source access; optional Snowflake only when no-cost trial available | Cost assumptions and reproducibility test | Design constraint — live account uses only X-Small standard warehouses on the free trial |

## Important course interpretation

The Phase 3 retail views and KPIs in the lab sheet are examples, not domain-fit requirements for PaperSonar. Do not create fake revenue, sales, customers or orders. Implement the required technical patterns with research-intelligence metrics and explain this mapping in the final presentation.
