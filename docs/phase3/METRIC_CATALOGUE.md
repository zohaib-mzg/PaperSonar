# PaperSonar Phase 3 metric catalogue

Every analytical question has one SQL implementation, one measure definition,
one denominator and one interpretation limit. The limits are copied verbatim
from the Phase 1 business-question definition
(`docs/submissions/phase-1/editable/03_PaperSonar_Business_questions.docx`) so
the SQL and the requirement text cannot drift; the contract test
`tests/sql/test_analytics_contracts.py` enforces the mapping.

SQL files live in `sql/10_analytics/` and are marked `-- Deploy: manual`: the
deployment client never executes them, so a deploy never burns warehouse
credits on analytical scans. Run them from a worksheet as
`PAPERSONAR_REPORTER` and save the result sets under
`docs/phase3/evidence/01_queries/`.

## 1. Question-to-implementation map

| Q | Topic | File | Result file | Primary tables | Decision |
|---|---|---|---|---|---|
| Q01 | topic growth | `01_topic_growth_share.sql` | `Q01_topic_growth.csv` | `VW_RESEARCH_OUTPUT`, `DIM_CATEGORY` | Choose a direction for a deeper review |
| Q02 | topic share | `01_topic_growth_share.sql` | `Q02_topic_share.csv` | `VW_RESEARCH_OUTPUT` | Separate corpus growth from a change in relative attention |
| Q03 | citation impact | `02_citation_impact.sql` | `Q03_citation_impact.csv` | `VW_CITATION_SNAPSHOT`, `VW_RESEARCH_OUTPUT` | Prioritize a reading shortlist without favoring older work |
| Q04 | citation gains | `02_citation_impact.sql` | `Q04_citation_gains.csv` | `VW_CITATION_SNAPSHOT` | Monitor papers that merit a fresh review |
| Q05 | topic intersections | `03_topic_intersections.sql` | `Q05_topic_intersections.csv` | `FACT_RESEARCH_OUTPUT`, `BRIDGE_OUTPUT_TOPIC_CATEGORY` | Identify candidates for manual literature review |
| Q06 | venues | `04_venues_and_institutions.sql` | `Q06_venues_by_topic.csv` | `VW_RESEARCH_OUTPUT` | Build a venue reading list |
| Q07 | institution contribution | `04_venues_and_institutions.sql` | `Q07_institution_contribution.csv` | `BRIDGE_OUTPUT_AUTHOR`, `BRIDGE_AUTHOR_INSTITUTION` | Identify potential collaborators |
| Q08 | institution concentration | `04_venues_and_institutions.sql` | `Q08_institution_concentration.csv` | same as Q07 | Find topics dominated by a small set of institutions |
| Q09 | open access | `05_access_and_authors.sql` | `Q09_open_access_by_topic.csv` | `VW_CITATION_SNAPSHOT`, `VW_RESEARCH_OUTPUT` | Estimate how accessible a reading direction will be |
| Q10 | author activity | `05_access_and_authors.sql` | `Q10_repeat_author_activity.csv` | `BRIDGE_OUTPUT_AUTHOR`, `DIM_AUTHOR` | Prepare an expert shortlist for manual review |
| Q11 | citation flow | `06_relationship_flow.sql` | `Q11_topic_citation_flow.csv` | `FACT_OUTPUT_RELATION`, topic bridge | Find intellectual links that a title search may miss |
| Q12 | metadata coverage | `07_metadata_coverage.sql` | `Q12_metadata_coverage.csv` | fact + bridges + dims | Avoid presenting unreliable rankings |
| Q13 | counting sensitivity | `08_sensitivity_and_period.sql` | `Q13_counting_sensitivity.csv` | fact + topic bridge | See whether a recommendation survives reasonable analytical choices |
| Q14 | partial year | `08_sensitivity_and_period.sql` | `Q14_partial_year_comparison.csv` | `VW_RESEARCH_OUTPUT` | Monitor recent activity without comparing a partial year to a complete one |

## 2. Measures, denominators and thresholds

| Q | Numerator | Denominator | Threshold / suppression |
|---|---|---|---|
| Q01 | distinct published outputs with the primary topic, per year | — (absolute counts; CAGR on counts) | suppress the growth ranking when either 2023 or 2025 has fewer than **30** works; CAGR only when both endpoints are positive |
| Q02 | topic primary-publication count | all admitted publications in the same year (also reported against the categorized corpus) | none; percentage-point change is shown, not a rank cut |
| Q03 | median `CITED_BY_COUNT` at one snapshot date | cohort size (publications in that topic/year/type) | one observation date only; cohort size and missing-snapshot count are reported next to the median |
| Q04 | late `CITED_BY_COUNT` − early `CITED_BY_COUNT` | — | only outputs observed at both dates qualify; gains and revisions are labelled separately |
| Q05 | distinct works co-assigned to an unordered topic pair | smaller parent topic count | each parent ≥ **100** works and the pair ≥ **5** works, otherwise the pair is suppressed |
| Q06 | distinct published outputs per venue and topic | topic outputs 2021–2025 | missing-venue share reported separately |
| Q07 | fractional institution credit per topic and year | one output contributes 1.0 split evenly over its distinct institutions | unknown institutions are shown as their own category, not dropped |
| Q08 | fractional credit of the top five institutions | all fractional credit of classified institutions in the same topic and year | top five computed **after** filtering; unknown institutions excluded from the ranking and their credit share disclosed |
| Q09 | open-access outputs at the snapshot date | outputs with a **known** access status | unknown-status share reported separately; never folded into the numerator |
| Q10 | distinct published outputs per author key, 2021–2025 | — | activity only, not expertise; the topic filter is a parameter |
| Q11 | citation edges with both endpoints admitted | — | directed; induced subgraph, so global citation totals are not reproduced |
| Q12 | outputs missing DOI / primary topic / venue / institution / access status | eligible population per topic and year | every rate is returned with its eligible population |
| Q13 | primary-topic count versus equal fractional allocation | — | low-volume groups (< **30** works) are flagged and their rank shift suppressed |
| Q14 | outputs published through a common month/day cutoff | the same cutoff in the previous year | unknown and year-only dates are excluded; cutoff and retrieval date are returned |

## 3. Cross-cutting rules

1. **Publication contract.** Queries that use the reporting views inherit it
   automatically; queries that touch the bridge tables repeat the same
   `PUBLISHED_BATCH` filter explicitly. Staged, quarantined and failed-batch
   rows never reach a result.
2. **No invented measures.** A rate is only produced when both its numerator
   and its denominator are present in the result set.
3. **No null-to-zero conversion.** Missing metadata is counted as missing
   (Q12) or reported as an unknown share (Q06, Q09), never as zero.
4. **One source scope per output per snapshot.** The snapshot fact has one row
   per output/source/date; Q03 and Q09 therefore fix a single source per
   output by source priority and return that scope in `SCOPE_SOURCE`.
5. **Retrieval date.** Every result carries `RETRIEVED_ON`, so an archived
   result can be told apart from a later refresh.
6. **Cost.** The queries scan between 265k (outputs) and 1.8m (relations) rows.
   Run them on `WH_PAPERSONAR_ELT` outside peak time; Q05, Q11 and Q13 are the
   expensive ones.

## 4. Known limits carried from Phase 1

- Topic growth is measured on the retained corpus, not on all research.
- Citation counts do not establish quality or causation.
- The topic taxonomy is the internal v2 taxonomy (`REF_CATEGORY`), and
  `unclassified` outputs are excluded from every topic result; their share is
  itself reported by Q12.
- `DIM_TOPIC` (source topics) has no fact bridge and therefore cannot answer
  Q01 or Q05; the internal category bridge is the only output-to-taxonomy path.
- Institutional credit depends on the affiliations the sources report; unknown
  affiliations are visible rather than silently dropped.
