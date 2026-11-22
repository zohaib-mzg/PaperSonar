# Phase 3 Power BI Specification — build sheet for the three-page research-intelligence model

**Date:** 2026-11-22 · **Branch:** `main` · **Data source:** Snowflake `PAPERSONAR.PROJECT_REPORTING` (five Phase 3 views + two Phase 2 views + one label lookup)

> **How to use this document.** Sections 1–3 are the contract: what exists, what
> every field means and how the tables relate. Section 4 is the build order —
> follow it in order. Sections 5–7 are the page build sheets: every visual, the
> exact fields it uses, what it demonstrates and how to read it. Section 8 is
> the complete DAX catalogue. Section 9 is the delivery checklist.
> **Every field name in this document was verified against the live view
> definitions** in `sql/07_reporting/`. Where an earlier draft named a field
> that does not exist, the correction is listed in section 11.

---

## 1. Why the views are the model

The reporting views are the BI contract. They already carry the grain, the
labels, the publication filter and the denominators, so a Power BI measure
never has to re-derive a metric and can never accidentally read an unpublished
batch. The reporting role holds `SELECT` on the views and nothing else.

Two rules make the pages trustworthy:

1. **Every ratio has its denominator on the page.** A share without a
   denominator is not published.
2. **The thresholds live in SQL, not in the visual.** The reportability
   thresholds (100 parent works, 5 joint works) and the coverage rules are
   applied inside the views, so a page cannot show a pair that the evidence
   CSV excludes, or a topic the suppression rule removed.

---

## 2. The data contract — every view and every field

Import these seven tables. All are granted to `PAPERSONAR_REPORTER`.

### 2.1 `VW_TOPIC_GROWTH` — category × publication year (Page 1)

Grain: one row per category per publication year. The `unclassified` category
is kept in the table and flagged, so corpus coverage sits next to the growth
ranking.

| Field | Type | Meaning |
|---|---|---|
| `CATEGORY_KEY` | text | Stable topic key, e.g. `ai-ml`. `unclassified` is a coverage pseudo-topic |
| `CATEGORY_LABEL` | text | Human label, e.g. "AI and machine learning" |
| `PUBLICATION_YEAR` | whole number | Year of publication; null-dated outputs are excluded by the view |
| `WORKS` | whole number | Distinct published outputs assigned to the category in that year (a work in two categories counts in both) |
| `CORPUS_WORKS` | whole number | Every published output of that year — the denominator of `SHARE_OF_CORPUS`. **Repeated on every category row of the year: do not sum it** |
| `CLASSIFIED_WORKS` | whole number | Published outputs of that year with a real category — the denominator of `SHARE_OF_CLASSIFIED_CORPUS`. **Repeated on every row: do not sum it** |
| `SHARE_OF_CORPUS` | decimal (6) | `WORKS / CORPUS_WORKS` for that category-year. The authoritative topic share |
| `SHARE_OF_CLASSIFIED_CORPUS` | decimal (6) | `WORKS / CLASSIFIED_WORKS` for that category-year. The authoritative share inside the classified corpus |
| `IS_COVERAGE_CATEGORY` | boolean | `TRUE` only for `unclassified`. Use it to hide the pseudo-topic from rankings and keep it on the coverage card |
| `RETRIEVED_ON` | date | Extraction date of the snapshot the row was read from |

### 2.2 `VW_OUTPUT_COVERAGE` — source × year × output type (Page 1)

Grain: one row per primary source per publication year per output type.

| Field | Type | Meaning |
|---|---|---|
| `PRIMARY_SOURCE_NAME` | text | The source that owns the canonical output (`OPENALEX`, `CROSSREF`, `ARXIV`, `ZENODO`, `DATACITE`) |
| `PUBLICATION_YEAR` | whole number | Publication year |
| `OUTPUT_TYPE_NAME` | text | "journal-article", "preprint", "dataset", "software", … |
| `OUTPUTS` | whole number | Distinct published outputs in the cell — the denominator of every ratio on this row |
| `CATEGORIZED_OUTPUTS` | whole number | Outputs with a real category |
| `CATEGORY_COVERAGE_RATIO` | decimal (6) | `CATEGORIZED_OUTPUTS / OUTPUTS` |
| `OUTPUTS_WITHOUT_DOI` | whole number | Outputs with no DOI — identifier completeness |
| `OUTPUTS_WITHOUT_VENUE` | whole number | Outputs with no venue or repository name |
| `OUTPUTS_WITHOUT_ACCESS_STATUS` | whole number | Outputs whose access status is unknown — reported separately, never folded into open access |
| `KNOWN_ACCESS_RATIO` | decimal (6) | Outputs with a known access status divided by `OUTPUTS` |
| `RETRIEVED_ON` | date | Extraction date |

### 2.3 `VW_CITATION_COHORTS` — output × citation snapshot date (Page 2)

Grain: **one row per published output per citation snapshot date.** This view
is deliberately row-level: the cohort aggregates are computed in DAX so the
page can slice by year, topic and source without a second join.

| Field | Type | Meaning |
|---|---|---|
| `OUTPUT_SK` | whole number | Surrogate key of the canonical output |
| `OUTPUT_BK` | text | Business key of the output |
| `SNAPSHOT_DATE` | date | The observation date of the citation count |
| `SNAPSHOT_DATE_KEY` | whole number | Date dimension key |
| `CITED_BY_COUNT` | whole number | Citation count at that observation date |
| `OA_STATUS` | text | Source-reported OA status at that date |
| `ACCESS_STATUS_NAME` | text | Normalized access status at that date |
| `PUBLICATION_YEAR` | whole number | Publication year of the output |
| `CATEGORY_KEY` | text | **Primary** topic of the output |
| `CATEGORY_LABEL` | text | Human label of the primary topic |
| `PRIMARY_SOURCE_NAME` | text | Owning source |
| `OUTPUT_TYPE_NAME` | text | Output type |
| `RETRIEVED_ON` | date | Extraction date |

### 2.4 `VW_TOPIC_INTERSECTIONS` — category pair (Page 2)

Grain: one row per unordered category pair. A pair means "these two topics are
assigned to the same work"; every category of a work is admitted, primary and
secondary alike.

| Field | Type | Meaning |
|---|---|---|
| `CATEGORY_KEY_A` | text | First category of the pair (alphabetically first) |
| `CATEGORY_KEY_B` | text | Second category of the pair |
| `JOINT_WORKS` | whole number | Works carrying both categories — the numerator of the ratio |
| `PARENT_WORKS_A` | whole number | Works carrying category A |
| `PARENT_WORKS_B` | whole number | Works carrying category B |
| `JOINT_TO_SMALLER_PARENT_RATIO` | decimal (6) | `JOINT_WORKS / LEAST(PARENT_WORKS_A, PARENT_WORKS_B)` — already computed, use it |
| `IS_REPORTABLE` | boolean | `TRUE` when both parents have ≥ 100 works and the pair has ≥ 5 joint works |
| `MIN_PARENT_WORKS` | whole number | The threshold used (100) — put it in the tooltip |
| `MIN_JOINT_WORKS` | whole number | The threshold used (5) — put it in the tooltip |
| `RETRIEVED_ON` | date | Extraction date |

**There are no label columns in this view.** Use `VW_CATEGORY_LABEL` to label
both sides (section 4, step 6).

### 2.5 `VW_RESEARCH_COMMUNITY` — institution × category × year (Page 3)

Grain: one row per institution per category per publication year. A work is
credited to an institution through its authors; when a work has several
institutions the credit is fractional, so the credit column sums to the number
of works in the cell rather than the number of affiliations.

| Field | Type | Meaning |
|---|---|---|
| `INSTITUTION_SK` | whole number | Surrogate key |
| `INSTITUTION_KEY` | text | Business key (e.g. `openalex:I4210108322`) |
| `INSTITUTION_NAME` | text | Institution name |
| `COUNTRY_CODE` | text | Country code, nullable |
| `CATEGORY_KEY` | text | Topic of the cell |
| `CATEGORY_LABEL` | text | Human label of the topic |
| `PUBLICATION_YEAR` | whole number | Publication year |
| `WORKS` | whole number | Distinct works credited to the institution in the cell |
| `FRACTIONAL_CREDIT` | decimal (4) | Fractional credit summed in the cell |
| `IS_UNKNOWN_INSTITUTION` | boolean | `TRUE` for the "unknown affiliation" row. Filter it out of rankings, keep it on the card |
| `RETRIEVED_ON` | date | Extraction date |

### 2.6 `VW_CATEGORY_LABEL` — category lookup (labels for the pair view)

| Field | Type | Meaning |
|---|---|---|
| `CATEGORY_SK` | whole number | Surrogate key |
| `CATEGORY_KEY` | text | Join key to every category field in the model |
| `CATEGORY_LABEL` | text | Human label |
| `PARENT_KEY` | text | Parent category key, nullable |
| `TAXONOMY_VERSION` | text | Taxonomy version that seeded the row (v3) |
| `IS_UNKNOWN` | boolean | `TRUE` for the `unclassified` pseudo-category |
| `RETRIEVED_ON` | date | Extraction date |

### 2.7 `VW_RESEARCH_OUTPUT` — one row per published output (Pages 1–3, measures only)

Used only for measures and filters that need the output level: the output
count, the classified-output count, and the gap between "outputs in scope" and
"outputs with a citation snapshot".

| Field | Type | Meaning |
|---|---|---|
| `OUTPUT_SK`, `OUTPUT_BK` | number / text | Surrogate and business key |
| `DOI_NORMALIZED` | text | Normalized DOI, nullable |
| `PUBLICATION_YEAR` | whole number | Publication year |
| `PUBLICATION_DATE` | date | Publication date |
| `OUTPUT_TYPE_NAME` | text | Output type |
| `VENUE_NAME` | text | Venue or repository, nullable |
| `ACCESS_STATUS_NAME` | text | Normalized access status, nullable |
| `PRIMARY_SOURCE_NAME` | text | Owning source |
| `CITED_BY_COUNT` | whole number | Current citation count |
| `OA_IS_OA` | boolean | Open-access flag from the source |
| `CATEGORY_KEY`, `CATEGORY_LABEL` | text | **Primary** topic of the output |
| `CATEGORY_SCORE` | decimal | Score of the primary assignment |
| `FIRST_SEEN_AT`, `LAST_SEEN_AT` | timestamp | First and last observation in the warehouse |
| `LAST_BATCH_ID` | text | Batch that last touched the output |

---

## 3. The model — relationships and why they are one-directional

Import mode, one-to-many, single direction, **no bidirectional relationships**.
The fact-side views are aggregated and the lookup is the smaller side, so
bidirectional filtering would only create ambiguity.

```
VW_CATEGORY_LABEL ──(CATEGORY_KEY)──► VW_TOPIC_GROWTH          1 : *
VW_CATEGORY_LABEL ──(CATEGORY_KEY)──► VW_CITATION_COHORTS      1 : *
VW_CATEGORY_LABEL ──(CATEGORY_KEY)──► VW_RESEARCH_COMMUNITY    1 : *
VW_CATEGORY_LABEL ──(CATEGORY_KEY_A)─► VW_TOPIC_INTERSECTIONS  1 : *
VW_CATEGORY_LABEL ──(CATEGORY_KEY_B)─► VW_TOPIC_INTERSECTIONS  1 : *
```

Two relationships from the lookup to the pair view are intentional: one for
each side of the pair. Both are single-direction, so each slicer filters only
its own side of the matrix. If Power BI objects to using the same lookup
table twice, duplicate it (right-click → Copy) and name the copies
`Categories (A)` and `Categories (B)`.

`VW_OUTPUT_COVERAGE` and `VW_RESEARCH_OUTPUT` are not related to the others:
they are self-contained aggregates used by their own page visuals and by the
card measures. `VW_RESEARCH_OUTPUT` is imported only for the two
output-level measures on page 2.

---

## 4. Build order — follow it in this sequence

1. **Install the connector.** Power BI Desktop → *Get Data* → search
   *Snowflake* → install *Power BI Snowflake connector by Microsoft*. Sign in
   with the dedicated reporting user (role `PAPERSONAR_REPORTER`, no
   administrative rights).
2. **Connect.** Account `NI15271`, role `PAPERSONAR_REPORTER`, warehouse
   `WH_PAPERSONAR_ELT` (X-Small, 60-second auto-suspend), database
   `PAPERSONAR`, schema `PROJECT_REPORTING`. Use *Import* mode, not DirectQuery:
   the pages aggregate millions of bridge rows and the trial credits are
   limited.
3. **Import the seven tables** of section 2, using the advanced navigator to
   pick the views by name.
4. **Set the data types.** `PUBLICATION_YEAR`, `SNAPSHOT_DATE_KEY`,
   `CATEGORY_SK`, `INSTITUTION_SK`, `OUTPUT_SK` → whole number.
   `SNAPSHOT_DATE`, `PUBLICATION_DATE`, `RETRIEVED_ON` → date.
   `IS_COVERAGE_CATEGORY`, `IS_REPORTABLE`, `IS_UNKNOWN_INSTITUTION`,
   `IS_UNKNOWN` → true/false. Everything else stays text or decimal.
5. **Create the relationships** of section 3. Set the cardinality to *many to
   one* from the fact view to `VW_CATEGORY_LABEL`, cross-filter direction
   *single*, and enable the relationship. Do not add any relationship that is
   not listed.
6. **Create the label lookup if the view is not deployed.** If
   `VW_CATEGORY_LABEL` is not in the account yet, run
   `sql/07_reporting/05_phase3_view_labels.sql` as `PAPERSONAR_ADMIN`
   (it is a `CREATE OR REPLACE SECURE VIEW` plus a `GRANT`, idempotent), or
   build the lookup inside Power BI with a calculated table:

   ```DAX
   Categories = DISTINCT(
       SELECTCOLUMNS(
           'VW_TOPIC_GROWTH',
           "CATEGORY_KEY", 'VW_TOPIC_GROWTH'[CATEGORY_KEY],
           "CATEGORY_LABEL", 'VW_TOPIC_GROWTH'[CATEGORY_LABEL]
       )
   )
   ```

   Then relate it to `VW_TOPIC_INTERSECTIONS` on `CATEGORY_KEY_A` and
   `CATEGORY_KEY_B`.
7. **Create a dedicated measure table** (*Home → Enter data*, name it
   `Measures`) and paste every measure from section 8 into it. Keeping the
   measures in one table makes the model readable and the screenshots cleaner.
8. **Build the pages** in the order of sections 5, 6 and 7. Each page ends
   with a title, a one-line question and a footnote that names the view and
   the evidence file behind it.
9. **Format** using section 8.5: one accent colour per topic family is not
   required — what is required is that every visual shows its number, its
   denominator and its filter context.
10. **Refresh and capture.** *Refresh* once, then take the page screenshots of
    section 9 and export the report as a PDF from Power BI Desktop
    (*File → Export → Export to PDF*).

---

## 5. Page 1 — Topic landscape and coverage

**Question answered:** which research directions are growing, and how much of
the corpus is classified well enough to make a claim?

**What the page demonstrates (for the evaluator):** that the dashboard is
built on a taxonomy contract rather than on a keyword search, that every
growth statement is printed with its denominator, and that the project's own
coverage weakness is visible on the page instead of hidden in a footnote.

### 5.1 Layout (16:9, 1280 × 720)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Topic landscape and coverage      [Category] [Year] [Source] [Output type]│
│ Which directions are growing, and how much of the corpus is classified?   │
├───────────────────────────────┬──────────────────────────────────────────┤
│ 1 Clustered column            │ 2 Line chart                             │
│   topic works by year         │   classified share over time             │
│                               │                                          │
├───────────────────────────────┼──────────────────────────────────────────┤
│ 3 Coverage matrix             │ 4 Stacked bar                             │
│   source × year, coverage %   │   outputs by source and output type      │
├───────────────────────────────┴──────────────────────────────────────────┤
│ 5 Cards: outputs | classified | coverage % | unknown-access share         │
└──────────────────────────────────────────────────────────────────────────┘
```

### 5.2 The visuals

| # | Visual type | Table | Fields used | Filter | What it demonstrates | How to read it |
|---|---|---|---|---|---|---|
| 1 | Clustered column chart | `VW_TOPIC_GROWTH` | Axis `CATEGORY_LABEL`, values `WORKS`, legend `PUBLICATION_YEAR` | `IS_COVERAGE_CATEGORY = FALSE`; year slicer | The size of each direction in the corpus, and how it splits across years | A tall bar with a thin neighbour means the direction is concentrated in one year. Because `WORKS` counts category assignments, a work in two topics appears in two bars |
| 2 | Line chart | `VW_TOPIC_GROWTH` | Axis `PUBLICATION_YEAR`, values `SHARE_OF_CLASSIFIED_CORPUS`, detail `CATEGORY_LABEL` | `IS_COVERAGE_CATEGORY = FALSE`; pick 3 topics | Growth of a direction **inside the classified corpus**, with the denominator applied by SQL | This is the only growth figure on the page. Use the years where the corpus has enough works; elsewhere the line is noise. Add the cohort size in the tooltip |
| 3 | Matrix / heat table | `VW_OUTPUT_COVERAGE` | Rows `PRIMARY_SOURCE_NAME`, columns `PUBLICATION_YEAR`, values `CATEGORY_COVERAGE_RATIO` | none | Where the classification coverage comes from and where it cannot | Dark cells are well-classified sources; Crossref and Zenodo stay pale because those records carry no structured subject, not because the taxonomy is weak |
| 4 | Stacked bar | `VW_OUTPUT_COVERAGE` | Axis `PRIMARY_SOURCE_NAME`, values `OUTPUTS`, legend `OUTPUT_TYPE_NAME` | year slicer | The composition of the corpus by source and output type | A source dominated by one type (OpenAlex: journal articles; Zenodo: datasets and software) is a selection effect of the extraction windows |
| 5 | Cards (4) | `VW_OUTPUT_COVERAGE` | `OUTPUTS`, `CATEGORIZED_OUTPUTS`, ratio, unknown-access share | none | The headline denominator for the whole page | Every card shows the numerator and the denominator. The unknown-access card is separate on purpose: an unknown access status is never counted as closed access |

### 5.3 Slicers on page 1

`CATEGORY_LABEL` (from `VW_CATEGORY_LABEL`), `PUBLICATION_YEAR`, and
`PRIMARY_SOURCE_NAME`. Default selection: all categories, all years, all
sources. Keep the category slicer on `CATEGORY_LABEL` so the reader sees a
label, not a key.

---

## 6. Page 2 — Citation impact and topic overlap

**Question answered:** which topic cohorts carry citation impact, and which
topic pairs are actually connected inside the corpus?

**What the page demonstrates (for the evaluator):** that a citation metric is
read at one observation date at a time, that cohort medians are computed
against the cohort size, and that the reportability thresholds are part of the
data contract rather than a filter typed into a visual.

### 6.1 Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Citation impact and topic overlap      [Snapshot date] [Category] [Year]  │
│ Which cohorts carry impact, and which topic pairs are really connected?   │
├───────────────────────────────┬──────────────────────────────────────────┤
│ 1 Scatter: cohort size vs     │ 2 Table: cohort statistics               │
│   median citations            │   category × year                        │
├───────────────────────────────┼──────────────────────────────────────────┤
│ 3 Matrix: reportable pairs    │ 4 Cards: reportable pairs | joint works   │
└───────────────────────────────┴──────────────────────────────────────────┘
```

### 6.2 The visuals

| # | Visual type | Table | Fields / measures | Filter | What it demonstrates | How to read it |
|---|---|---|---|---|---|---|
| 1 | Scatter chart | `VW_CITATION_COHORTS` | X `COHORT_SIZE`, Y `Median Cited By`, details `CATEGORY_LABEL`, `PUBLICATION_YEAR` | `SNAPSHOT_DATE` (single select) | Cohort impact against cohort size — the only honest way to compare citation medians | A point high and far left is a small cohort with high impact and must be read with its size, not as a leader |
| 2 | Table | `VW_CITATION_COHORTS` | Rows `CATEGORY_LABEL`, `PUBLICATION_YEAR`; values `Cohort Size`, `Median Cited By`, `Missing Snapshot Outputs` | `SNAPSHOT_DATE` | The cohort behind every median, with the missing-snapshot gap shown | The gap column is the honesty check: a median computed over 40 of 400 outputs is not a median of the cohort |
| 3 | Matrix | `VW_TOPIC_INTERSECTIONS` | Rows `CATEGORY_KEY_A` (labelled via the lookup), columns `CATEGORY_KEY_B` (labelled via the lookup), values `JOINT_WORKS` | `IS_REPORTABLE = TRUE` | Which topics genuinely co-occur | Only reportable pairs are shown. The tooltip names both thresholds (100 parent works, 5 joint works) so the reader knows what was filtered |
| 4 | Cards (2) | `VW_TOPIC_INTERSECTIONS` | `Reportable Pairs`, `Joint Works` | — | The size of the connected space | Three reportable pairs is the honest answer for this corpus; a longer list would be a filter artefact |

### 6.3 Slicers on page 2

`SNAPSHOT_DATE` (**single-select**, one observation date at a time — this is
the Phase 1 limit), `CATEGORY_LABEL`, `PUBLICATION_YEAR`.

---

## 7. Page 3 — Research community

**Question answered:** which institutions carry which topics, and how
concentrated is that participation?

**What the page demonstrates (for the evaluator):** that institutional credit
is fractional, that an unknown affiliation is never counted as a partner, and
that a concentration metric dominated by one identifier is labelled as such
instead of being presented as a fact about physics.

### 7.1 Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Research community                 [Category] [Year] [Country]           │
│ Which institutions carry which topics, and how concentrated is that?      │
├───────────────────────────────┬──────────────────────────────────────────┤
│ 1 Treemap: institutions by     │ 2 Bar: top 20 by fractional credit       │
│   fractional credit           │                                          │
├───────────────────────────────┼──────────────────────────────────────────┤
│ 3 Table: institution details  │ 4 Scatter: works vs fractional credit    │
├───────────────────────────────┴──────────────────────────────────────────┤
│ 5 Cards: works | credit | unknown-institution share | credit per work   │
└──────────────────────────────────────────────────────────────────────────┘
```

### 7.2 The visuals

| # | Visual type | Table | Fields / measures | Filter | What it demonstrates | How to read it |
|---|---|---|---|---|---|---|
| 1 | Treemap | `VW_RESEARCH_COMMUNITY` | Size `FRACTIONAL_CREDIT`, detail `CATEGORY_LABEL`, group `INSTITUTION_NAME` | `IS_UNKNOWN_INSTITUTION = FALSE` | The shape of participation | One tile can dominate the map. In this corpus the National Institute for Fusion Science holds 56.9% of all institutional credit — a source artefact, and the page shows it rather than hiding it |
| 2 | Bar chart (top 20) | `VW_RESEARCH_COMMUNITY` | Y `INSTITUTION_NAME`, X `FRACTIONAL_CREDIT` | `IS_UNKNOWN_INSTITUTION = FALSE`; Top N = 20 | Who carries the credit, by topic and year | The tooltip must show `WORKS` next to the credit: credit per work below 1 means the works are shared with other institutions |
| 3 | Table | `VW_RESEARCH_COMMUNITY` | Rows `INSTITUTION_NAME`, `COUNTRY_CODE`; values `WORKS`, `FRACTIONAL_CREDIT` | `IS_UNKNOWN_INSTITUTION = FALSE` | The identity behind the ranking | `INSTITUTION_KEY` is the identifier behind the name; add it to the table so the artefact can be verified against the source |
| 4 | Scatter chart | `VW_RESEARCH_COMMUNITY` | X `WORKS`, Y `FRACTIONAL_CREDIT`, detail `CATEGORY_LABEL` | `IS_UNKNOWN_INSTITUTION = FALSE` | Which institutions share their works | Points below the 1:1 line are institutions whose works are co-credited; points on it are single-institution works |
| 5 | Cards (4) | `VW_RESEARCH_COMMUNITY` | `Works`, `Fractional Credit`, `Unknown Institution Share`, `Credit Per Work` | — | The denominators behind the page | `Credit Per Work` below 1 means the corpus's institutional credit is shared; the unknown share is shown next to it, never inside it |

### 7.3 Slicers on page 3

`CATEGORY_LABEL`, `PUBLICATION_YEAR`, `COUNTRY_CODE`. Do not filter out
`IS_UNKNOWN_INSTITUTION` with a slicer — the treemap and the bar chart filter
it out, the card keeps it visible.

---

## 8. The measure catalogue (DAX)

### 8.1 Coverage and volume (page 1)

```DAX
Outputs := SUM('VW_OUTPUT_COVERAGE'[OUTPUTS])
Categorized Outputs := SUM('VW_OUTPUT_COVERAGE'[CATEGORIZED_OUTPUTS])
Coverage Ratio := DIVIDE([Categorized Outputs], [Outputs])
Outputs Missing Access := SUM('VW_OUTPUT_COVERAGE'[OUTPUTS_WITHOUT_ACCESS_STATUS])
Unknown Access Share := DIVIDE([Outputs Missing Access], [Outputs])
Known Access Ratio := DIVIDE([Outputs] - [Outputs Missing Access], [Outputs])
Outputs Missing DOI := SUM('VW_OUTPUT_COVERAGE'[OUTPUTS_WITHOUT_DOI])
Outputs Missing Venue := SUM('VW_OUTPUT_COVERAGE'[OUTPUTS_WITHOUT_VENUE])
```

### 8.2 Topic growth (page 1)

Use the **pre-computed share columns** of `VW_TOPIC_GROWTH`. Do not divide
`SUM(WORKS)` by `SUM(CORPUS_WORKS)`: `CORPUS_WORKS` repeats on every category
row of a year, so summing it multiplies the denominator by the number of
categories on screen.

```DAX
Topic Works := SUM('VW_TOPIC_GROWTH'[WORKS])
Corpus Works (selected years) :=
SUMX(
    VALUES('VW_TOPIC_GROWTH'[PUBLICATION_YEAR]),
    CALCULATE(MAX('VW_TOPIC_GROWTH'[CORPUS_WORKS]))
)
Classified Works (selected years) :=
SUMX(
    VALUES('VW_TOPIC_GROWTH'[PUBLICATION_YEAR]),
    CALCULATE(MAX('VW_TOPIC_GROWTH'[CLASSIFIED_WORKS]))
)
Topic Share of Corpus (selected years) :=
DIVIDE([Topic Works], [Corpus Works (selected years)])
Classified Share (selected topic, year) :=
DIVIDE(
    'VW_TOPIC_GROWTH'[WORKS],
    CALCULATE(MAX('VW_TOPIC_GROWTH'[CLASSIFIED_WORKS]), ALLEXCEPT('VW_TOPIC_GROWTH', 'VW_TOPIC_GROWTH'[CATEGORY_KEY], 'VW_TOPIC_GROWTH'[PUBLICATION_YEAR]))
)
```

> `Topic Share of Corpus` can exceed 100% when several categories are
> selected, because a work in two categories is counted in both. That is a
> property of the assignment count, not an error. For the per-topic share use
> the view's own `SHARE_OF_CORPUS` column.

### 8.3 Citation cohorts (page 2)

`VW_CITATION_COHORTS` is row-level (one row per output per snapshot date), so
the cohort statistics are measures.

```DAX
Cohort Size := DISTINCTCOUNT('VW_CITATION_COHORTS'[OUTPUT_SK])
Median Cited By :=
MEDIANX(
    FILTER('VW_CITATION_COHORTS', NOT ISBLANK('VW_CITATION_COHORTS'[CITED_BY_COUNT])),
    'VW_CITATION_COHORTS'[CITED_BY_COUNT]
)
Mean Cited By := AVERAGE('VW_CITATION_COHORTS'[CITED_BY_COUNT])
Outputs In Scope := DISTINCTCOUNT('VW_RESEARCH_OUTPUT'[OUTPUT_SK])
Outputs With Snapshot := DISTINCTCOUNT('VW_CITATION_COHORTS'[OUTPUT_SK])
Missing Snapshot Outputs := [Outputs In Scope] - [Outputs With Snapshot]
Missing Snapshot Share := DIVIDE([Missing Snapshot Outputs], [Outputs In Scope])
```

### 8.4 Topic overlap (page 2)

```DAX
Joint Works := SUM('VW_TOPIC_INTERSECTIONS'[JOINT_WORKS])
Joint To Smaller Parent :=
DIVIDE(
    [Joint Works],
    MIN(
        SUM('VW_TOPIC_INTERSECTIONS'[PARENT_WORKS_A]),
        SUM('VW_TOPIC_INTERSECTIONS'[PARENT_WORKS_B])
    )
)
Reportable Pairs :=
CALCULATE(
    COUNTROWS('VW_TOPIC_INTERSECTIONS'),
    'VW_TOPIC_INTERSECTIONS'[IS_REPORTABLE] = TRUE
)
```

### 8.5 Community (page 3)

```DAX
Works := SUM('VW_RESEARCH_COMMUNITY'[WORKS])
Fractional Credit := SUM('VW_RESEARCH_COMMUNITY'[FRACTIONAL_CREDIT])
Unknown Institution Share :=
DIVIDE(
    CALCULATE(
        SUM('VW_RESEARCH_COMMUNITY'[FRACTIONAL_CREDIT]),
        'VW_RESEARCH_COMMUNITY'[IS_UNKNOWN_INSTITUTION] = TRUE
    ),
    [Fractional Credit]
)
Credit Per Work := DIVIDE([Fractional Credit], [Works])
Top Institution Share :=
DIVIDE(
    CALCULATE(MAX('VW_RESEARCH_COMMUNITY'[FRACTIONAL_CREDIT])),
    [Fractional Credit]
)
```

### 8.6 Formatting standards

- Number format: counts `#,##0`; ratios `0.0%`; the join ratio `0.00%`.
- Every card: value, then the label, then the denominator in the subtitle.
- Every table and matrix: a tooltip with the numerator, the denominator and
  the rule that produced it.
- Category labels come from the lookup; never display a raw `CATEGORY_KEY`
  without its label.
- One accent colour per page, greys for everything else; no 3-D, no shadows,
  no pie charts.
- Every page footnote: `Source: <view name> · Evidence:
  docs/phase3/evidence/...`.

---

## 9. Delivery checklist

- [ ] Three pages built, titled, with the question printed under the title.
- [ ] Every visual uses a field that exists (section 2 is the contract).
- [ ] Every card and ratio shows its denominator.
- [ ] The snapshot-date slicer on page 2 is single-select.
- [ ] The reportability thresholds appear in the page-2 tooltip.
- [ ] Unknown institutions are excluded from rankings and visible on the card.
- [ ] Page screenshots captured at full size (PNG, one per page) and saved in
      `docs/phase3/powerbi/`.
- [ ] The PBIX exported and saved as `docs/phase3/powerbi/PaperSonar_Phase3.pbx`.
- [ ] The PDF export of the three pages saved as
      `docs/phase3/powerbi/PaperSonar_Phase3_pages.pdf`.
- [ ] A screenshot of the model view (tables and relationships) captured — it
      is the evidence for the "one-to-many, single direction" decision.
- [ ] Each page cross-checked against its evidence CSV: the headline numbers
      must match.

## 10. Caveats carried onto the pages

1. The recent-year corpus is small (389 works in 2023, 1,053 in 2025), so
   growth visuals on those years are mostly suppressed by the 30-work rule.
2. Affiliation data exists only for the historical part of the corpus; the
   community page is dominated by older years and by the 2026 block.
3. `unclassified` is a coverage category, not a topic: it never appears on the
   growth axis, and the coverage card always shows it.
4. Every ratio on every page has its denominator on the page. A share with no
   denominator is not published.
5. One institution identifier holds 56.9% of all institutional credit, so the
   concentration visuals must be read as source artefacts, not as statements
   about a field.

## 11. Corrections applied to the earlier draft of this specification

Found while checking the specification against the live view definitions:

| Earlier draft | Problem | Correction |
|---|---|---|
| `MEDIAN_CITED_BY`, `COHORT_SIZE`, `COHORT_MISSING_SNAPSHOT` on page 2 | These fields **do not exist** in `VW_CITATION_COHORTS`, which is row-level by design | Section 8.3 defines `Cohort Size`, `Median Cited By` and the missing-snapshot measures in DAX over the row-level view |
| `CATEGORY_A_LABEL`, `CATEGORY_B_LABEL` on page 2 | The pair view carries keys, not labels | `VW_CATEGORY_LABEL` (new, `sql/07_reporting/05_phase3_view_labels.sql`) or the Power BI calculated table in section 4, step 6 |
| `Classified Share` computed as `WORKS / SUM(CLASSIFIED_WORKS)` | `CLASSIFIED_WORKS` repeats on every category row, so the denominator would be multiplied | Section 8.2 uses `MAX` inside `SUMX` over the selected years, and the per-topic share column for the chart |
| `Joint To Smaller Parent` using `MIN` of two columns in one measure | `MIN` over two columns is not a valid DAX aggregation shape | Section 8.4 aggregates each parent column with `SUM` first, then takes the smaller one |

The views themselves were not changed; the specification was corrected to match
the data contract, and the one new artefact (`VW_CATEGORY_LABEL`) is an
additive lookup view.
