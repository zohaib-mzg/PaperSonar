# Requirements traceability matrix v2

This matrix keeps course requirements separate from PaperSonar product scope. All Phase 2 and Phase 3 items are planned; this repository update does not implement them.

| Requirement | Phase | PaperSonar response | Evidence / acceptance proof | State |
|---|---|---|---|---|
| Business problem, users, objectives | 1 | Research-direction comparison using transparent scholarly evidence | Proposal and business requirements | Design artifact exists; review against v2 scope |
| Minimum 10 analytical questions | 1 | 14 PaperSonar questions | Business questions report and metric catalogue | Designed; queries not implemented |
| Identify business processes | 1 | Output registration, source-record observation, citation/relationship observation, periodic output snapshot | Process/grain document | Revised target design required |
| Define fact grain and fact types | 1 | Transaction/accumulating entity output, periodic snapshot, factless typed relationships as appropriate | Model and grain statements | Current publication mart designed; source-neutral model needs v2 |
| Dimensions and hierarchies | 1 | Date, output type, topic taxonomy, person, institution, venue/repository, access, funder | Logical model and data dictionary | Expand for five sources |
| Natural and surrogate keys | 1 | Source-native IDs and DOI crosswalk; warehouse surrogate keys | Key policy and dictionary | Designed at policy level; detailed model update required |
| Conceptual, logical, physical model | 1 | Source-to-canonical-output architecture and analytics mart | PNG/PDF diagram, DBML, dictionary | Existing diagrams retained; target architecture v2 added |
| Proposal, requirements, 10 questions, facts/grains, schema, dictionary | 1 | Keep editable artifacts and source register | Phase 1 deliverables folder | Existing artifacts retained; v2 master baseline added |
| 100+ dimension records | 2 | Target naturally from expanded source registry; measured after load | Count report per dimension | Not started |
| 10,000+ fact records | 2 | Corpus profiling target; no arbitrary truncation; choose feasible scope | Counts after successful load | Not started; 30k–60k is a target only |
| Staging, cleaning, transformations | 2 | `project_staging` / `project_dw` / `project_reporting` | SQL/Python scripts and run manifests | Not started |
| Surrogate-key mapping | 2 | Business/source IDs mapped to dimension keys | Load report and orphan check | Not started |
| Completeness, accuracy, integrity | 2 | Coverage, DOI conflicts, FK orphan checks, count reconciliation, bridge weight tests | Data quality PDF/CSV | Not started |
| Analytical aggregations and 14 questions | 3 | Research-output measures with denominator and coverage | SQL files and validated result extracts | Not started |
| `ROLLUP` and `CUBE` | 3 | Topic taxonomy × year, output type × source, topic × access; appropriate grouping sets | OLAP SQL and result evidence | Not started |
| Reporting views | 3 | `vw_topic_growth`, `vw_output_coverage`, `vw_citation_cohorts`, `vw_topic_intersections`, `vw_research_community` | SQL view definitions | Not started |
| Query optimization | 3 | `EXPLAIN ANALYZE` before/after indexes on representative queries | Indexing report with hardware/data caveats | Not started |
| Power BI three-page minimum example | 3 | Executive research overview, detailed direction analysis, decision/evidence page | PBIX and screenshots | Not started |
| Business insights and final presentation | 3 | Recommendations based on validated outputs, never invented outcomes | PDF report and PPT | Not started |
| Free-only | All | Local PostgreSQL core; free source access; optional Snowflake only when no-cost trial available | Cost assumptions and reproducibility test | Design constraint |

## Important course interpretation

The Phase 3 retail views and KPIs in the lab sheet are examples, not domain-fit requirements for PaperSonar. Do not create fake revenue, sales, customers or orders. Implement the required technical patterns with research-intelligence metrics and explain this mapping in the final presentation.
