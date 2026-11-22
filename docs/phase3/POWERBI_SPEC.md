# Phase 3 Power BI Specification — three-page research-intelligence model

**Date:** 2026-11-22 · **Branch:** `phase3` · **Data source:** Snowflake `PAPERSONAR.PROJECT_REPORTING` (five Phase 3 views + two Phase 2 views)

---

## 1. Why the views are the model

The five Phase 3 reporting views are the BI contract. They already carry the
grain, the labels, the publication filter and the denominators, so a Power BI
measure never has to re-derive a metric and can never accidentally read an
unpublished batch.

| View | Grain | Feeds |
|---|---|---|
| `VW_TOPIC_GROWTH` | category × publication year | Page 1 |
| `VW_OUTPUT_COVERAGE` | source × year × output type | Page 1 |
| `VW_CITATION_COHORTS` | output × snapshot date | Page 2 |
| `VW_TOPIC_INTERSECTIONS` | category pair | Page 2 |
| `VW_RESEARCH_COMMUNITY` | institution × category × year | Page 3 |

Relationship model (import mode, one-to-many from the dimension views to the
fact views):

```
VW_TOPIC_GROWTH        ─┐
VW_OUTPUT_COVERAGE     ─┤
                        ├─► VW_CITATION_COHORTS (OUTPUT_SK, SNAPSHOT_DATE)
                        │
VW_RESEARCH_COMMUNITY  ─┘
VW_TOPIC_INTERSECTIONS (standalone pair table, used on its own page)
```

Cross-filtering direction is single, from the category/year slicers down to
the facts. No bidirectional relationship is used: the fact views are
aggregated and the dimension views are the smaller side, so bidirectional
filtering would only create ambiguity.

## 2. Page 1 — Topic landscape and coverage

**Question answered:** which research directions are growing, and how much of
the corpus is actually classified well enough to make a claim?

Visuals:

1. **Clustered column chart** — `VW_TOPIC_GROWTH`: axis `CATEGORY_LABEL`,
   values `WORKS`, legend `PUBLICATION_YEAR`, filtered to
   `IS_COVERAGE_CATEGORY = FALSE`.
2. **Line chart** — `VW_TOPIC_GROWTH`: axis `PUBLICATION_YEAR`, values
   `SHARE_OF_CLASSIFIED_CORPUS`, detail `CATEGORY_LABEL`, for the three
   selected topics.
3. **Stacked bar** — `VW_OUTPUT_COVERAGE`: axis `PRIMARY_SOURCE_NAME`, values
   `OUTPUTS`, legend `OUTPUT_TYPE_NAME`.
4. **Matrix / heat table** — `VW_OUTPUT_COVERAGE`: rows `PRIMARY_SOURCE_NAME`,
   columns `PUBLICATION_YEAR`, values `CATEGORY_COVERAGE_RATIO`, with
   `OUTPUTS` as the count on the cell.
5. **Card** — `VW_OUTPUT_COVERAGE`: `SUM(OUTPUTS)`, `SUM(CATEGORIZED_OUTPUTS)`
   and the ratio between them.

DAX measures:

```DAX
Outputs := SUM('VW_OUTPUT_COVERAGE'[OUTPUTS])
Categorized Outputs := SUM('VW_OUTPUT_COVERAGE'[CATEGORIZED_OUTPUTS])
Coverage Ratio := DIVIDE([Categorized Outputs], [Outputs])
Classified Share := DIVIDE('VW_TOPIC_GROWTH'[WORKS], CALCULATE(SUM('VW_TOPIC_GROWTH'[WORKS]), 'VW_TOPIC_GROWTH'[IS_COVERAGE_CATEGORY] = FALSE))
Unknown Access Share := DIVIDE(SUM('VW_OUTPUT_COVERAGE'[OUTPUTS_WITHOUT_ACCESS_STATUS]), [Outputs])
```

The `IS_COVERAGE_CATEGORY` flag keeps `unclassified` visible on the card and
hidden from the growth ranking. It is the same rule the SQL uses, so the page
and the evidence CSV cannot disagree.

## 3. Page 2 — Citation impact and topic overlap

**Question answered:** which topic cohorts carry citation impact, and which
topic pairs are actually connected inside the corpus?

Visuals:

1. **Scatter chart** — `VW_CITATION_COHORTS`: x `CATEGORY_KEY`,
   y `CITED_BY_COUNT`, size `COHORT_SIZE`, play axis `SNAPSHOT_DATE`.
2. **Slicer** — `SNAPSHOT_DATE` (single select). One observation date at a
   time, as the Phase 1 limit requires.
3. **Table** — `VW_CITATION_COHORTS`: rows `CATEGORY_KEY`,
   `PUBLICATION_YEAR`, values `MEDIAN_CITED_BY`, `COHORT_SIZE`,
   `COHORT_MISSING_SNAPSHOT`.
4. **Matrix** — `VW_TOPIC_INTERSECTIONS`: rows `CATEGORY_A_LABEL`, columns
   `CATEGORY_B_LABEL`, values `JOINT_WORKS`, filtered to
   `IS_REPORTABLE = TRUE`.
5. **Card** — `VW_TOPIC_INTERSECTIONS`: number of reportable pairs.

DAX measures:

```DAX
Cohort Size := SUM('VW_CITATION_COHORTS'[COHORT_SIZE])
Missing Snapshot Share := DIVIDE(SUM('VW_CITATION_COHORTS'[COHORT_MISSING_SNAPSHOT]), [Cohort Size])
Joint Works := SUM('VW_TOPIC_INTERSECTIONS'[JOINT_WORKS])
Joint To Smaller Parent := DIVIDE([Joint Works], MIN('VW_TOPIC_INTERSECTIONS'[PARENT_WORKS_A], 'VW_TOPIC_INTERSECTIONS'[PARENT_WORKS_B]))
Reportable Pairs := CALCULATE(COUNTROWS('VW_TOPIC_INTERSECTIONS'), 'VW_TOPIC_INTERSECTIONS'[IS_REPORTABLE] = TRUE)
```

The 100-parent / 5-joint thresholds are applied inside the view, so the page
cannot show a pair that the evidence CSV excludes.

## 4. Page 3 — Research community

**Question answered:** which institutions carry which topics, and how
concentrated is that participation?

Visuals:

1. **Treemap** — `VW_RESEARCH_COMMUNITY`: size `FRACTIONAL_CREDIT`, detail
   `CATEGORY_LABEL`, grouping `INSTITUTION_NAME`.
2. **Bar chart** — top 20 institutions by `FRACTIONAL_CREDIT` for the
   selected category and year.
3. **Table** — `VW_RESEARCH_COMMUNITY`: rows `INSTITUTION_NAME`,
   `COUNTRY_CODE`, values `WORKS`, `FRACTIONAL_CREDIT`.
4. **Scatter chart** — x `WORKS`, y `FRACTIONAL_CREDIT`, detail
   `CATEGORY_LABEL`, to show the institutions whose credit is fractional
   because their works carry several institutions.
5. **Card** — unknown-institution share, taken from the Q08 evidence
   (`UNKNOWN_INSTITUTION_CREDIT_SHARE`).

DAX measures:

```DAX
Works := SUM('VW_RESEARCH_COMMUNITY'[WORKS])
Fractional Credit := SUM('VW_RESEARCH_COMMUNITY'[FRACTIONAL_CREDIT])
Unknown Institution Share := DIVIDE(SUMX(FILTER('VW_RESEARCH_COMMUNITY', 'VW_RESEARCH_COMMUNITY'[IS_UNKNOWN_INSTITUTION] = TRUE), 'VW_RESEARCH_COMMUNITY'[FRACTIONAL_CREDIT]), [Fractional Credit])
Credit Per Work := DIVIDE([Fractional Credit], [Works])
```

`IS_UNKNOWN_INSTITUTION` rows are filtered out of the treemap and the bar
chart but stay visible in the card. An unknown affiliation is never counted
as a collaborator.

## 5. Connection, refresh and security

* **Connection:** Snowflake connector, `PAPERSONAR` database, warehouse
  `WH_PAPERSONAR_ELT` (X-Small, 60-second auto-suspend), role
  `PAPERSONAR_REPORTER`. The role is read-only: `GRANT SELECT` on the views,
  no write privilege and no ownership.
* **Refresh:** import mode with a scheduled refresh once per week, or manual
  refresh after a publication. The views enforce the publication contract, so
  a refresh after a new batch picks up exactly the published state.
* **Security:** the service user for Power BI is a dedicated user with
  `PAPERSONAR_REPORTER` only. It holds no `PAPERSONAR_ADMIN` right and cannot
  publish a batch.
* **RLS:** none. The reporting role cannot see unpublished batches by
  construction, which is the access model the course asks for.
* **Fallback:** every page can be reproduced from the exported CSVs in
  `docs/phase3/evidence/01_queries/` if the trial expires before the
  connector is set up. The measures above are the same in both cases.

## 6. Screenshots and delivery

The three page definitions above are the specification. The delivered
artefacts are:

* `docs/phase3/POWERBI_SPEC.md` — this document.
* `docs/phase3/powerbi/` — the page images and the DAX measure file when the
  desktop client is run against the account.
* `docs/phase3/evidence/01_queries/*.csv` — the exported result sets behind
  every visual, so each number on a page can be traced to a file in the
  repository.

## 7. Known caveats carried onto the pages

1. The recent-year corpus is small (389 works in 2023, 1,053 in 2025), so
   growth visuals on those years are mostly suppressed by the 30-work rule.
2. Affiliation data only exists for the historical part of the corpus; the
   community page is therefore dominated by older years and by the 2026
   block.
3. `unclassified` is a coverage category, not a topic: it never appears on
   the growth axis, and the coverage card always shows it.
4. Every ratio on every page has its denominator on the page. A share with no
   denominator is not published.
