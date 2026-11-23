# 03 — Metric Catalogue and Question Coverage

**Read after:** `02_SNOWFLAKE_PUBLIC_LAYER.md`  
**Read before:** `04_BACKEND_API_AND_LLM.md`  
**Owner:** metrics / resolver workstream

---

## 1. Purpose

Define exactly what the assistant may answer, how each answer is computed, and
what it must say when the data cannot support an answer.

The LLM does not choose SQL. It chooses one of these metric IDs and supplies
validated filters. The server compiles the metric’s SQL template.

---

## 2. Metric IDs

| ID | Metric | Primary public view | Grain |
|---|---|---|---|
| `M01` | topic growth | `VW_PUBLIC_TOPIC_YEAR` | category × year |
| `M02` | topic share | `VW_PUBLIC_TOPIC_YEAR` | category × year |
| `M03` | topic volume | `VW_PUBLIC_TOPIC_YEAR` | category × year |
| `M04` | topic citations | `VW_PUBLIC_TOPIC_CITATIONS` | category × year × snapshot |
| `M05` | citation gains | `VW_CITATION_SNAPSHOT` + `VW_RESEARCH_OUTPUT` | output × snapshot |
| `M06` | topic intersections | `VW_PUBLIC_TOPIC_INTERSECTIONS` | category pair |
| `M07` | source coverage | `VW_OUTPUT_COVERAGE` | source × year × type |
| `M08` | metadata completeness | `VW_OUTPUT_COVERAGE` + `VW_RESEARCH_OUTPUT` | source × year × type |
| `M09` | institution activity | `VW_PUBLIC_INSTITUTION_TOPIC` | institution × category × year |
| `M10` | institution concentration | `VW_PUBLIC_INSTITUTION_TOPIC` | category × year |
| `M11` | author activity | `VW_PUBLIC_AUTHOR_ACTIVITY` | category × year × author |
| `M12` | venue activity | `VW_PUBLIC_VENUE_TOPIC` | category × year × venue × type |
| `M13` | output type mix | `VW_OUTPUT_COVERAGE` | source × year × type |
| `M14` | open access | `VW_PUBLIC_ACCESS_TOPIC` | category × year × type |
| `M15` | year distribution | `VW_PUBLIC_TOPIC_YEAR` / `VW_RESEARCH_OUTPUT` | year |
| `M16` | cross-source overlap | `VW_SOURCE_OBSERVATION` + `VW_RESEARCH_OUTPUT` | output |
| `M17` | output search | `VW_PUBLIC_OUTPUT_SEARCH` | output |
| `M18` | data status | `VW_PUBLIC_DATA_STATUS` | source |
| `M19` | corpus summary | `VW_PUBLIC_CORPUS_SUMMARY` | one row |
| `M20` | topic lookup | `VW_CATEGORY_LABEL` | category |
| `M21` | comparison | composition of M01–M16 | two sides |
| `M22` | freshness | `VW_PUBLIC_CORPUS_SUMMARY` | one row |
| `M23` | output citation rank | `VW_CITATION_COHORTS` | output × snapshot |
| `M24` | source contribution | `VW_SOURCE_OBSERVATION` + `VW_RESEARCH_OUTPUT` | source |

---

## 3. Filter contract

Allowed filters:

| Filter | Type | Rule |
|---|---|---|
| `category_key` | enum | key from `config/taxonomy.yml` |
| `parent_category_key` | enum | parent key; expands to descendants |
| `year_from` / `year_to` | integer | 1900–current year |
| `source_name` | enum | `OPENALEX`, `CROSSREF`, `ARXIV`, `DATACITE`, `ZENODO` |
| `output_type` | string | exact value from the view |
| `venue_name` | string | bounded, parameterised |
| `institution_key` | string | exact key; never a fuzzy SQL string |
| `country_code` | string | ISO-like code |
| `author_key` / `orcid` | string | exact identifier |
| `access_status` | string | exact value |
| `snapshot_date` | date | only dates present in data |
| `search_term` | string | 2–100 chars; title search |
| `limit` | integer | 1–50; default 10 |
| `order` | enum | metric-specific |
| `min_works` | integer | default 30 for growth/citation cohorts |

Forbidden filters:

- arbitrary SQL fragments
- table names
- column names
- wildcard-only search (`%`)
- unbounded date ranges without a metric default
- free-text category values that were not resolved by the resolver

---

## 4. Result envelope

Every metric returns this shape to the answer builder:

```json
{
  "metric_id": "M01",
  "metric_label": "Topic growth",
  "grain": ["category_key", "publication_year"],
  "rows": [],
  "as_of": "2026-11-22",
  "snapshot_date": null,
  "scope": {
    "filters": {},
    "source_policy": "all primary sources",
    "denominator": "distinct published outputs"
  },
  "suppressed": false,
  "suppression_reason": null,
  "caveats": [],
  "query_template": "M01_TOPIC_GROWTH_V1"
}
```

### Numeric rules

- Counts are distinct published outputs unless the metric says otherwise.
- A rate is returned only with its numerator and denominator.
- Never convert `NULL`/unknown metadata to zero.
- Never sum citation counts across sources.
- Never compare a partial year with a complete year without a label.
- Never show a ranking when the suppression rule fires.

---

## 5. Metric contracts

### M01 — Topic growth

- View: `VW_PUBLIC_TOPIC_YEAR`
- Default: latest two complete years; all sources; exclude `unclassified`
- Required: `category_key` optional; if absent, rank categories
- Measures: `works_start`, `works_end`, `absolute_growth`, `growth_ratio`,
  `cagr`
- Suppress: either endpoint `< 30` works; if suppressed, return counts and
  `suppressed=true`
- Caveat: “Growth describes the retained corpus, not all research.”
- Template ID: `M01_TOPIC_GROWTH_V1`

### M02 — Topic share

- View: `VW_PUBLIC_TOPIC_YEAR`
- Default: latest two complete years
- Measures: `works`, `corpus_works`, `share_of_corpus`,
  `share_of_classified`, `share_change_pp`
- Suppress: no ranking when corpus denominator is zero
- Caveat: “Share is relative to the selected corpus and year.”

### M03 — Topic volume

- View: `VW_PUBLIC_TOPIC_YEAR`
- Measures: `works`, `corpus_works`, `classified_works`
- Optional: year, source (source requires `VW_OUTPUT_COVERAGE` or a filtered
  metric; do not pretend source filtering is available if it is not)
- Caveat: “Counts are distinct published outputs.”

### M04 — Topic citations

- View: `VW_PUBLIC_TOPIC_CITATIONS`
- Default: latest snapshot date
- Measures: `cohort_size`, `observed_works`, `total_citations`,
  `avg_cited_by`, `median_cited_by`, `min`, `max`, `zero_citation_works`
- Suppress: if `observed_works < 30`, mark low-confidence; show counts
- Caveat: “Citations are a snapshot, not live counts and not a measure of
  quality. One source is selected per output by source priority.”

### M05 — Citation gains

- View: `VW_CITATION_SNAPSHOT` joined to `VW_RESEARCH_OUTPUT`
- Default: latest two observed snapshot dates
- Measures: `early_cited_by`, `late_cited_by`, `citation_change`, `change_kind`
- Qualify: only outputs observed at both dates and the same source
- Caveat: “Only works present in both snapshots qualify; revisions are labelled.”

### M06 — Topic intersections

- View: `VW_PUBLIC_TOPIC_INTERSECTIONS`
- Measures: `joint_works`, `parent_works_a/b`, `joint_to_smaller_parent_ratio`
- Suppress: use `IS_REPORTABLE`; threshold is 100 parent works and 5 joint works
- Caveat: “A co-occurrence is a discovery signal, not proof of novelty or
  causality.”

### M07 — Source coverage

- View: `VW_OUTPUT_COVERAGE`
- Measures: `outputs`, `categorized_outputs`, `category_coverage_ratio`,
  missing DOI/venue/access counts, `known_access_ratio`
- Caveat: “Coverage is a property of this corpus and source, not a global
  quality judgement.”

### M08 — Metadata completeness

- View: `VW_OUTPUT_COVERAGE` + `VW_RESEARCH_OUTPUT`
- Measures: outputs missing DOI, category, venue, or access status; eligible
  population for each rate
- Caveat: “Missing metadata is reported as missing, never zero.”

### M09 — Institution activity

- View: `VW_PUBLIC_INSTITUTION_TOPIC`
- Measures: `works`, `fractional_credit`
- Default: exclude `IS_UNKNOWN_INSTITUTION` from rankings; disclose unknown
  share separately
- Caveat: “Institution credit is fractional and depends on reported
  affiliations.”

### M10 — Institution concentration

- View: `VW_PUBLIC_INSTITUTION_TOPIC`
- Measures: top-5 fractional credit, total classified credit, concentration
  ratio, unknown share
- Suppress: topic/year with fewer than 30 works
- Caveat: “Top five computed after filtering; unknown institutions excluded.”

### M11 — Author activity

- View: `VW_PUBLIC_AUTHOR_ACTIVITY`
- Measures: `works`, first/latest publication year, `author_key`, ORCID
- Default: minimum 2 works for rankings
- Caveat: “Author names are not unique identifiers; activity is not expertise.”

### M12 — Venue activity

- View: `VW_PUBLIC_VENUE_TOPIC`
- Measures: `works`, share of topic works
- Default: 2021–latest complete year if no year filter
- Caveat: “A primary venue can be a repository; this does not rank quality.”

### M13 — Output type mix

- View: `VW_OUTPUT_COVERAGE`
- Measures: `outputs` by type, source, year
- Caveat: “Output types are source-reported and not normalised across all
  providers.”

### M14 — Open access

- View: `VW_PUBLIC_ACCESS_TOPIC`
- Measures: `open_access_works`, `known_access_works`,
  `unknown_access_works`, `open_access_share_known`
- Caveat: “Unknown access status is disclosed separately and never counted as
  closed.”
- Note: this view uses the published output’s winner-source access fields; state
  that scope in the receipt.

### M15 — Year distribution

- View: `VW_PUBLIC_TOPIC_YEAR` / `VW_RESEARCH_OUTPUT`
- Measures: outputs by year, share of corpus
- Caveat: “The corpus is not a complete census; recent years may be partial.”

### M16 — Cross-source overlap

- View: `VW_SOURCE_OBSERVATION` + `VW_RESEARCH_OUTPUT`
- Measures: observations per output, source count, shared DOI/source presence
- Caveat: “One canonical output can have several source observations.”

### M17 — Output search

- View: `VW_PUBLIC_OUTPUT_SEARCH`
- Measures: matching titles, year, category, source, citations
- Default: 20 results; max 50
- Required: `search_term` 2–100 chars; no unfiltered title dump
- Caveat: “Title search is lexical, not semantic; it does not search full text.”

### M18 — Data status

- View: `VW_PUBLIC_DATA_STATUS`
- Measures: latest batch per source, published time, window, capped flag
- Caveat: “A published batch is not a promise that every source is complete.”

### M19 — Corpus summary

- View: `VW_PUBLIC_CORPUS_SUMMARY`
- Measures: total outputs, classified outputs, source count, year range, latest
  snapshot, latest published batch
- Caveat: “Summary describes the retained published corpus.”

### M20 — Topic lookup

- View: `VW_CATEGORY_LABEL` + `config/taxonomy.yml`
- Returns category key, label, parent, aliases, match type, confidence
- No counts; used to clarify an ambiguous term
- Caveat: “Mapping to a broader category is always disclosed.”

### M21 — Comparison

- Composition of M01–M16
- Exactly two sides; same filters except the compared dimension
- If either side is suppressed, the comparison is marked suppressed
- Caveat: “Both sides use the same snapshot/date window unless the user
  explicitly changes it.”

### M22 — Freshness

- View: `VW_PUBLIC_CORPUS_SUMMARY`
- Returns latest snapshot date, latest published batch, corpus size
- Caveat: “Citation counts and publication coverage move at different speeds.”

### M23 — Output citation rank

- View: `VW_CITATION_COHORTS` or `VW_CITATION_SNAPSHOT`
- Measures: top outputs by citations at latest snapshot
- Default: 10; max 50; one source per output
- Caveat: “Top citation counts favour older works; compare within cohorts.”

### M24 — Source contribution

- View: `VW_SOURCE_OBSERVATION` + `VW_RESEARCH_OUTPUT`
- Measures: canonical outputs per source, observations per output
- Caveat: “Source contribution is not a quality score.”

---

## 6. Question catalogue

Every row below is an acceptance question. The family heading gives the metric
IDs that may satisfy it. If a question cannot be mapped with confidence, the
resolver must clarify or refuse; it must not guess.

### 6.1 Topic growth and momentum — M01, M02

| ID | Question |
|---|---|
| Q001 | Which topics grew fastest in 2025? |
| Q002 | Which topics declined in 2025? |
| Q003 | Compare AI/ML growth in 2024 vs 2025. |
| Q004 | Which topics grew fastest among Crossref outputs? |
| Q005 | Which topics grew fastest among OpenAlex outputs? |
| Q006 | What is the year-over-year growth of health sciences? |
| Q007 | Which topics had the largest absolute increase in works? |
| Q008 | Which topics had the largest relative increase? |
| Q009 | Which topics are emerging but below the 30-work threshold? |
| Q010 | Show the growth trend for physics from 2021 to 2025. |

### 6.2 Topic volume and share — M02, M03

| ID | Question |
|---|---|
| Q011 | How many works are in AI/ML? |
| Q012 | What share of the corpus is AI/ML? |
| Q013 | Which topics have the most works? |
| Q014 | Which topics have the fewest works? |
| Q015 | How many classified vs unclassified works are there? |
| Q016 | What is the topic coverage ratio by source? |
| Q017 | Which topics appear in only one source? |
| Q018 | How many works are unclassified? |
| Q019 | What percentage of 2025 works are classified? |
| Q020 | Show the top 10 topics by work count. |

### 6.3 Citation impact — M04, M23

| ID | Question |
|---|---|
| Q021 | How many citations does AI/ML have? |
| Q022 | What is the average citation count for AI/ML? |
| Q023 | What is the median citation count for health sciences? |
| Q024 | Which topics have the highest citation impact? |
| Q025 | Which topics have the lowest citation impact? |
| Q026 | How many citations does RAG have? |
| Q027 | Compare citations for AI/ML and physics. |
| Q028 | Which AI/ML outputs have the most citations? |
| Q029 | What share of AI/ML outputs has zero citations? |
| Q030 | What is the citation distribution for 2025 outputs? |

### 6.4 Citation trends and cohorts — M05, M04

| ID | Question |
|---|---|
| Q031 | How have AI/ML citations changed across snapshots? |
| Q032 | Which topics gained the most citations between snapshots? |
| Q033 | Which topics lost citation rank? |
| Q034 | Compare citation impact for 2024 and 2025 cohorts. |
| Q035 | What is the citation trend for arXiv preprints? |
| Q036 | Which source has the highest average citations? |
| Q037 | Which output type has the highest citation impact? |
| Q038 | How many citations per output by publication year? |
| Q039 | Which topics have high citations but low volume? |
| Q040 | Show citation gains for the top 10 outputs. |

### 6.5 Topic intersections — M06

| ID | Question |
|---|---|
| Q041 | Which topic pairs co-occur most? |
| Q042 | Do AI/ML and health sciences intersect? |
| Q043 | How many works combine AI/ML and physics? |
| Q044 | Which topic pairs are reportable? |
| Q045 | Which topic pairs are suppressed? |
| Q046 | Compare intersections for 2024 and 2025. |
| Q047 | Which topics bridge the most domains? |
| Q048 | Which topic pairs grew fastest? |
| Q049 | What share of AI/ML works also has health sciences? |
| Q050 | Show top topic pairs by joint works. |

### 6.6 Source coverage and metadata — M07, M08, M13

| ID | Question |
|---|---|
| Q051 | Which source has the highest topic coverage? |
| Q052 | Which source has the most works without a DOI? |
| Q053 | Which source has the most works without a venue? |
| Q054 | Compare coverage for OpenAlex and Crossref. |
| Q055 | How many works have a missing publication year? |
| Q056 | How many works have a missing author? |
| Q057 | How many works have a language value? |
| Q058 | Which topics are underrepresented in Crossref? |
| Q059 | Which source contributes the most 2025 outputs? |
| Q060 | Show metadata completeness by source and year. |

### 6.7 Institutions — M09, M10

| ID | Question |
|---|---|
| Q061 | Which institutions have the most works? |
| Q062 | Which institutions lead AI/ML? |
| Q063 | Which institutions lead physics in 2025? |
| Q064 | How concentrated is institutional credit? |
| Q065 | Which countries have the most works? |
| Q066 | Which institutions collaborate most? |
| Q067 | Which institutions have the highest citation impact? |
| Q068 | Which institutions are active in health sciences? |
| Q069 | How many works have a resolved institution? |
| Q070 | Show top institutions by topic. |

### 6.8 Authors and communities — M11

| ID | Question |
|---|---|
| Q071 | Who are the most prolific authors? |
| Q072 | Which authors have the most citations? |
| Q073 | Which authors work across multiple topics? |
| Q074 | How many repeat authors are there? |
| Q075 | Which authors are active in AI/ML? |
| Q076 | Which authors publish across the most sources? |
| Q077 | How many authors have an ORCID? |
| Q078 | Which authors published in both 2024 and 2025? |
| Q079 | What is the author-count-per-output distribution? |
| Q080 | Show top authors for a topic. |

### 6.9 Venues and output types — M12, M13

| ID | Question |
|---|---|
| Q081 | Which venues have the most works? |
| Q082 | Which venues have the highest citation impact? |
| Q083 | Which output types are most common? |
| Q084 | How many datasets are in the corpus? |
| Q085 | How many preprints are in the corpus? |
| Q086 | Compare citation impact of articles vs preprints. |
| Q087 | Which venues publish the most AI/ML work? |
| Q088 | Which output types grew in 2025? |
| Q089 | Which venues are associated with high-impact topics? |
| Q090 | Show top venues by year. |

### 6.10 Open access and access status — M14

| ID | Question |
|---|---|
| Q091 | What share of outputs is open access? |
| Q092 | How many outputs have unknown access status? |
| Q093 | Which topics have the highest open-access share? |
| Q094 | Compare open access by source. |
| Q095 | Which institutions have the highest open-access share? |
| Q096 | How has open access changed by year? |
| Q097 | Which venues are most open access? |
| Q098 | Do open-access works have more citations? |
| Q099 | How many outputs are closed access? |
| Q100 | Show open-access coverage by topic and year. |

### 6.11 Time and period comparisons — M15, M21

| ID | Question |
|---|---|
| Q101 | How many works were published in 2024? |
| Q102 | How many works were published in 2025? |
| Q103 | Which year has the most works? |
| Q104 | What is the publication-year distribution? |
| Q105 | Compare 2020–2022 with 2023–2025. |
| Q106 | Which topics grew most over the last five years? |
| Q107 | Which topics declined over the last five years? |
| Q108 | What is the partial-year effect for 2026? |
| Q109 | Which years are under-represented in the corpus? |
| Q110 | Show works by year and source. |

### 6.12 Cross-source and identity — M16, M24

| ID | Question |
|---|---|
| Q111 | How many duplicate DOIs were removed? |
| Q112 | How many outputs are observed by multiple sources? |
| Q113 | Which outputs appear in both OpenAlex and Crossref? |
| Q114 | Which source contributes the most canonical outputs? |
| Q115 | How many source observations map to one output? |
| Q116 | Which topics have the most cross-source agreement? |
| Q117 | How many outputs have more than one source observation? |
| Q118 | What share of outputs have a DOI? |
| Q119 | How many outputs are source-only identities? |
| Q120 | Show cross-source overlap by year. |

### 6.13 Search and discovery — M17, M03

| ID | Question |
|---|---|
| Q121 | Find papers about retrieval-augmented generation. |
| Q122 | Show recent papers on graph neural networks. |
| Q123 | Find works by a specific author. |
| Q124 | Find works from a specific institution. |
| Q125 | Find papers in a specific venue. |
| Q126 | Search titles containing “transformer”. |
| Q127 | Find highly cited papers about climate. |
| Q128 | Show papers with both AI/ML and health sciences categories. |
| Q129 | Find datasets about genomics. |
| Q130 | Search for a topic that is not in the taxonomy. |

### 6.14 Comparisons and rankings — M21, M01–M16

| ID | Question |
|---|---|
| Q131 | Compare AI/ML and physics. |
| Q132 | Compare OpenAlex and Crossref coverage. |
| Q133 | Compare 2024 and 2025 topic rankings. |
| Q134 | Compare institutions in AI/ML. |
| Q135 | Compare venues by citation impact. |
| Q136 | Compare open access across sources. |
| Q137 | Compare preprints and articles. |
| Q138 | Compare topic growth across sources. |
| Q139 | Rank topics by citations per work. |
| Q140 | Rank institutions by output count. |

### 6.15 Data trust and freshness — M18, M19, M22

| ID | Question |
|---|---|
| Q141 | When was the data last updated? |
| Q142 | Which batches are published? |
| Q143 | How many DQ rules passed? |
| Q144 | Which batch failed? |
| Q145 | What is the current corpus size? |
| Q146 | What is the topic coverage today? |
| Q147 | Which sources are currently included? |
| Q148 | How fresh are citation snapshots? |
| Q149 | What data is not reportable? |
| Q150 | Why is a topic missing from an answer? |

> Q143 and Q144 are public-safe only at the aggregate level. Do not expose raw
> DQ rule text, internal payloads or unpublished batch details. If exact internal
> detail is requested, refuse and link to the published data-status summary.

---

## 7. Resolver rules

### 7.1 Pipeline

```text
normalise -> classify -> extract entities -> resolve aliases ->
confidence check -> choose metric(s) -> validate filters -> execute
```

### 7.2 Taxonomy resolution

Source of truth: `config/taxonomy.yml` (v3).

- Exact category key: confidence 1.0.
- Exact category label: confidence 0.98.
- Pattern/alias in the taxonomy `rules`: confidence 0.90.
- Parent/child expansion: confidence 0.80; disclose the expansion.
- Fuzzy/title match: confidence 0.55; use only with disclosure.
- Below 0.55: ask a clarification question.

Important taxonomy facts:

- `rag` is a real category under `llm` / `ai-ml`. Do **not** map RAG to AI/ML
  unless the user asks for the broader category.
- `llm` and `ai-ml` are distinct categories.
- `unclassified` is a coverage category, never a topic ranking entry.
- Category labels can change; always return the key plus the current label.

### 7.3 Time resolution

- “last year” = latest **complete** publication year in the corpus.
- “this year” is unsupported when the latest year is partial; explain why.
- “last five years” = the five latest complete publication years.
- “since 2021” = 2021 through the latest complete year.
- Citation “latest” = latest `SNAPSHOT_DATE` in the public citation view.
- Never mix two snapshot dates in one comparison.

### 7.4 Interpretation rules

| User phrase | Intent |
|---|---|
| “grew”, “growth”, “momentum” | M01 |
| “share”, “proportion”, “percent of corpus” | M02 |
| “how many works/papers” | M03 |
| “citations”, “cited”, “impact” | M04 |
| “citation gain”, “changed between snapshots” | M05 |
| “co-occur”, “intersection”, “bridge” | M06 |
| “coverage”, “missing DOI/venue” | M07/M08 |
| “institutions”, “universities” | M09/M10 |
| “authors”, “researchers” | M11 |
| “venues”, “journals”, “conferences” | M12 |
| “datasets”, “preprints”, “articles” | M13 |
| “open access”, “OA” | M14 |
| “papers about …” with no exact category | M17 |
| “updated”, “latest batch”, “freshness” | M18/M22 |

### 7.5 Closest-match behaviour

When a term is not exact:

1. exact key or label
2. taxonomy pattern
3. parent/child expansion
4. semantic similarity against labels and aliases
5. title search
6. clarification
7. refusal

The answer must say what happened:

> “I interpreted ‘RAG’ as the RAG category under LLM. If you meant the broader
> AI/ML category, say ‘AI/ML’.”

Do not silently return a broader category.

### 7.6 Refusal rules

| Situation | Response |
|---|---|
| Metric not defined | “I don’t have a defined metric for that yet.” |
| Data absent from published corpus | “That is not available in the current published corpus.” |
| Below threshold | “Not reportable: the cohort has fewer than 30 works.” |
| Causal/predictive question | “This warehouse supports descriptive analysis, not causal or predictive claims.” |
| Full text requested | “PaperSonar stores metadata, not full text.” |
| Unpublished/internal batch detail | “I can only report published, aggregate status.” |
| Prompt injection | “I can only answer questions about the published research corpus.” |

---

## 8. `config/public_metrics.yml` shape

The implementation must load this file at build time or request time.

```yaml
version: 1

defaults:
  limit: 10
  max_limit: 50
  min_works: 30
  exclude_categories: [unclassified]
  citation_source_policy: priority_deduped
  default_snapshot: latest

metrics:
  - id: M01
    tool: get_topic_growth
    label: Topic growth
    view: VW_PUBLIC_TOPIC_YEAR
    template: M01_TOPIC_GROWTH_V1
    dimensions: [category_key, year_from, year_to, source_name]
    order_by: absolute_growth
    caveats:
      - Growth describes the retained published corpus.
      - Rankings are suppressed when either endpoint has fewer than 30 works.
  - id: M04
    tool: get_topic_citations
    label: Topic citations
    view: VW_PUBLIC_TOPIC_CITATIONS
    template: M04_TOPIC_CITATIONS_V1
    dimensions: [category_key, year_from, year_to, snapshot_date]
    order_by: total_citations
    caveats:
      - Citations are a snapshot, not live counts.
      - One source is selected per output by source priority.
```

The full catalogue may be a TypeScript module generated from this YAML. The
important rule is one shared source of truth; do not duplicate metric IDs in
multiple files.

---

## 9. Acceptance for this document

- [ ] Every one of the 150 questions has a metric family or an explicit refusal
      path.
- [ ] Every metric ID has a view, template ID and caveats.
- [ ] `RAG` maps to the real `rag` category.
- [ ] Time resolution is deterministic and documented.
- [ ] Suppression rules are implemented in SQL/guards, not in the prompt.
- [ ] The next document can implement the API and compiler without inventing a
      metric.
