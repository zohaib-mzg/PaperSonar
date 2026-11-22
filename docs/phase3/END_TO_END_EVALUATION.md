# PaperSonar — End-to-End Project Evaluation Guide

**Version:** 1.0 · **Date:** 2026-11-22 · **Repository:** `github.com/zohaib-mzg/PaperSonar` · **Branch:** `main` · **Live account:** Snowflake `NI15271` (free trial)

---

## 0. How to use this document

This is the single document that explains the whole project from end to end:
what was asked, what was built, what every layer and field means, which
decision was taken where a real choice existed, why, what was measured, what
was rejected, and what a reviewer should ask. It is written to be read by
someone who has never seen the repository.

| If you want… | Read |
|---|---|
| The 2-minute version | §1 |
| The architecture and every table | §4 |
| Every analytical question, with its numerator, denominator and threshold | §7 |
| The decision log and the reasoning | §12 |
| How to verify any claim yourself | §15 |
| What the presentation should say | §18 |

Every number in this document has a committed evidence file behind it. The
paths are given inline, and §15 lists them all.

---

## 1. Executive summary

**PaperSonar is a research-intelligence warehouse** that answers one question
honestly: which research directions are worth attention, and what evidence
supports that claim?

It ingests five scholarly metadata services (OpenAlex, Crossref, arXiv,
DataCite, Zenodo) into a Snowflake warehouse through a strict ELT pipeline,
applies a versioned 67-category taxonomy to every output, and answers 14
analytical questions with published denominators, thresholds and suppression
rules. Three OLAP cubes and five secure reporting views expose the result to a
Power BI model. The project publishes what it found, including the finding
that its own optimization experiment did not work.

**Live state (2026-11-22):**

| | |
|---|---|
| Canonical research outputs | 296,299 across 5 published batches, 0 duplicate DOIs |
| Topic coverage | 74.40% classified (was 1.92% before the taxonomy work) |
| Taxonomy | 67 categories in 10 domains, 63 populated |
| Category assignments | 894,545 rows, exactly one row per output and category |
| Relationship edges | 2,557,842 reference edges, 94,912 induced inside the corpus |
| Analytical questions | 14, every one executed live and exported as evidence |
| Reporting views | 5 `SECURE` views + 2 Phase 2 views, granted to `PAPERSONAR_REPORTER` |
| Data-quality gate | 12 rules, 9 CRITICAL / 3 WARNING, fail-closed publication |
| Tests | 270 automated tests, ruff clean, SQL parsed and contract-checked |
| Spend | one X-Small warehouse on a $400 trial; $328 remaining at Phase 3 start |

**The three sentences to say in the presentation:**

1. *The warehouse is real and live: five published batches, 296,299 outputs,
   a 12-rule quality gate that blocks publication, and 270 passing tests.*
2. *The analytics are honest: every ratio carries its denominator, every
   threshold is in SQL, and the questions that the corpus cannot yet answer are
   published as "not yet reportable" instead of being dressed up.*
3. *The project also reports its own negative results: the clustering
   experiment made the hot queries slower, so it was rolled back, and the
   before/after evidence is in the repository.*

---

## 2. The problem, the users, the objectives

### 2.1 The problem

A researcher can find any single paper. Comparing *possible* research
directions is much harder, because:

- the evidence is split across five metadata services that disagree about
  subjects, dates, identifiers and versions;
- every "trending topic" claim is really a claim about a **counting rule** —
  count a work once or split it across every field it belongs to, and the
  leaderboard changes;
- the same work appears in several sources, so raw result counts cannot be
  added up and called a corpus;
- an absent subject field is not the same as an absent topic, and treating
  the two alike is how a warehouse invents coverage.

### 2.2 The users

| User | Need | What the project gives them |
|---|---|---|
| A research strategist choosing a direction | which fields are growing, where they intersect, who works in them | Q01, Q02, Q05, Q11 + Power BI page 1 and 2 |
| A literature-review lead building a reading list | which papers and venues to read, and how much impact a cohort has | Q03, Q04, Q06 + page 2 |
| A partnership or funding team | who is active in a field, and how concentrated participation is | Q07, Q08, Q10 + page 3 |
| A data steward | can the numbers be trusted, and what is missing | Q12 + the DQ gate + the audit schemas |
| An evaluator of the project | can every claim be reproduced | this document + the evidence tree |

### 2.3 The objectives

1. One canonical output identity across five sources, with provenance kept to
   the source record.
2. A topic taxonomy that is a **versioned contract**, not a keyword search.
3. Fourteen analytical questions whose answers are reproducible from committed
   SQL and carry their own limits.
4. A BI model that cannot show an unpublished batch or an unreportable pair.
5. A measured, documented optimization decision — including a negative one.

### 2.4 Scope boundaries — what PaperSonar is not

- It is **not** a full-text system: it holds metadata, not documents.
- It is **not** a quality or impact model: citation counts do not establish
  quality or causation.
- It is **not** a claim about all of research: it measures the retained
  corpus, and the corpus is bimodal in time (§5.6).
- It is **not** a novelty detector: a sparse intersection is a signal worth
  watching, never proof of novelty.
- It is **not** free of constraints: coverage ceilings, one dominant
  institution identifier and a missing DataCite publication are all published
  rather than smoothed over.

---

## 3. Source strategy

| Priority | Source | Main value | Incremental design | Live state |
|---:|---|---|---|---|
| 1 | OpenAlex | works, authors, institutions, topics, citation metadata | one-time full backfill; incremental needs `from_updated_date` (Member+/Partner plan) | full backfill published (168,725 records); incremental **blocked by HTTP 403** |
| 2 | Crossref | DOI bibliographic metadata, reindex changes | fixed `from-index-date`/`until-index-date` windows, cursor paging, overlap | 2 batches published (18,495 + 60,000) |
| 3 | arXiv | computing preprints, categories, abstracts, versions | OAI-PMH datestamp windows, preserve versions | published (15,505) |
| 4 | DataCite | datasets, software, registered outputs | updated-date query or OAI-PMH | code fixed, **not live-proven** (§17) |
| 5 | Zenodo | datasets, software, reports, versions, related ids | OAI-PMH datestamp windows + API detail | published (33,741) |

**Decision: no sixth source until these five are individually proven.** The
rationale is cost and attention: every source needs an identity rule, an
update-window rule, a provenance mapping and a DQ expectation. Adding a
sixth before the fifth is proven multiplies the unknowns. Full detail:
`docs/sources.md` and `docs/phase2/SOURCE_CAPABILITY_MATRIX.md`.

---

## 4. Architecture end to end

### 4.1 The layers

```
 five public APIs
      │  Python extractors (src/extract): HTTP/OAI only, no transformation
      ▼
 raw gzip NDJSON shards + deterministic manifest
      │  Snowflake internal stage → COPY
      ▼
 PROJECT_STAGING ──► PROJECT_BRONZE ──► PROJECT_SILVER ──► PROJECT_DW ──► PROJECT_REPORTING
 (typed, per batch)  (current state,   (typed, quarantined, (conformed dims, (SECURE views,
                      one row per        identity crosswalk)  facts, bridges)  published only)
                      source record id)
      ▲                  ▲                 ▲                   ▲
      └──────────────────┴─────────────────┴───────────────────┘
                     PROJECT_AUDIT  (batch, manifest, DQ, lineage, quarantine, watermarks)
                     PROJECT_REF    (versioned taxonomy, rules, expected keys, overrides)
```

### 4.2 The seven schemas and every object

| Schema | Objects | Purpose |
|---|---:|---|
| `PROJECT_STAGING` | 7 tables | per-batch typed landing: raw observation, output crosswalk, category assignment, dimension staging tables |
| `PROJECT_BRONZE` | 5 tables | one current-state table per source: `BRZ_OPENALEX_WORK`, `BRZ_CROSSREF_WORK`, `BRZ_ARXIV_RECORD`, `BRZ_DATACITE_DOI`, `BRZ_ZENODO_RECORD` |
| `PROJECT_SILVER` | 3 tables + UDFs | `SLV_SOURCE_OBSERVATION` (typed observations), `SLV_OUTPUT_CROSSWALK` (identity), `SLV_RESEARCH_OUTPUT` (canonical output), plus normalization and priority functions |
| `PROJECT_DW` | 19 tables | 10 dimensions, 4 facts, 3 bridges, `DIMENSION_KEY_MAP` |
| `PROJECT_REPORTING` | 7 views | the BI contract; every view exposes published data only |
| `PROJECT_AUDIT` | 11 tables | batch, manifest, DQ result, quarantine, lineage, watermarks, run log, schema drift, file load log, published batch, current batch |
| `PROJECT_REF` | 7 tables | versioned contracts: `REF_CATEGORY`, `REF_CATEGORY_KEYWORD`, `REF_TAXONOMY_MAP`, `CATEGORY_OVERRIDE`, `REF_EXPECTED_KEY`, `REF_DQ_RULE`, `REF_SOURCE` |

### 4.3 The dimensional model

| Table | Grain | Type | Key fields |
|---|---|---|---|
| `FACT_RESEARCH_OUTPUT` | one canonical research output | accumulating entity | `OUTPUT_SK`, `OUTPUT_BK`, `DOI_NORMALIZED`, `PUBLICATION_YEAR`, `PUBLICATION_DATE_SK`, `SOURCE_SK`, `CITED_BY_COUNT`, `OA_IS_OA`, `FIRST_SEEN_AT`, `LAST_SEEN_AT`, `LAST_BATCH_ID` |
| `FACT_CITATION_SNAPSHOT` | output × source × snapshot date | periodic snapshot | `SNAPSHOT_DATE_SK`, `CITED_BY_COUNT`, `OA_STATUS`, `BATCH_ID` |
| `FACT_OUTPUT_RELATION` | output → relation type → target output | factless typed relationship | `RELATION_TYPE`, `TARGET_OUTPUT_SK`, unresolved targets keep their identifier |
| `FACT_OUTPUT_SOURCE_OBSERVATION` | output × source observation | lineage fact | connects an output to the source record that produced it |
| `BRIDGE_OUTPUT_TOPIC_CATEGORY` | output × category | bridge (many-to-many) | `SCORE`, `CATEGORY_RANK`, `IS_PRIMARY`, `METHOD`, `TAXONOMY_VERSION` |
| `BRIDGE_OUTPUT_AUTHOR` | output × author | bridge | author contribution to an output |
| `BRIDGE_AUTHOR_INSTITUTION` | author × institution | bridge | affiliation, with validity dates |
| `DIM_AUTHOR` | one author business key | **SCD2** | `AUTHOR_KEY`, `AUTHOR_NAME`, `ORCID`, `HASH_DIFF`, valid-from/valid-to |
| `DIM_INSTITUTION` | one institution business key | Type 1 | `INSTITUTION_KEY`, `INSTITUTION_NAME`, `COUNTRY_CODE`, `IS_UNKNOWN` |
| `DIM_CATEGORY` | one internal taxonomy category | Type 1 | `CATEGORY_KEY`, `LABEL`, `PARENT_KEY`, `TAXONOMY_VERSION`, `IS_UNKNOWN` |
| `DIM_TOPIC` | one source topic/keyword | Type 1 | source-native topics, normalized to stable keys |
| `DIM_DATE`, `DIM_VENUE`, `DIM_SOURCE`, `DIM_OUTPUT_TYPE`, `DIM_ACCESS_STATUS`, `DIM_LANGUAGE`, `DIM_COUNTRY` | one member each | Type 1 | conformed dimension members |
| `DIMENSION_KEY_MAP` | one business key per dimension | key map | `BUSINESS_KEY` → `*_SK` for every dimension; 942,762 rows live |

**Why the author dimension is SCD2 and the rest are Type 1.** Affiliation
changes over time, and the community page credits works to institutions
through authors. Keeping the author history means a work published in 2022
keeps the affiliation the source reported then. Every other dimension member
is a stable descriptive attribute, so a Type 1 overwrite is sufficient and
cheaper.

**Why `DIMENSION_KEY_MAP` exists.** Every dimension key is derived from a
source business key through one map table, so a key can be recomputed, audited
and re-pointed without touching the facts. It also makes the surrogate-key
policy explicit: business key → surrogate key, always through one place.

### 4.4 The batch lifecycle

```
EXTRACTING ──► LOADED ──► PROCESSING ──► PUBLISHED
                   │            │
                   └────────────┴──────► FAILED
```

1. **EXTRACTING** — the extractor computes a deterministic batch id from the
   source and the window, writes gzip NDJSON shards, uploads them, verifies
   the staged size against the manifest, and registers the manifest.
2. **LOADED** — the manifest is registered and verified.
3. **PROCESSING** — the Snowflake task graph runs, in order: staging → bronze
   → silver → categorization → dimensions → facts → DQ.
4. **PUBLISHED** — only if the DQ gate passes. Publication is fail-closed:
   `SP_PUBLISH_BATCH` refuses to publish a batch with a CRITICAL failure.
   **FAILED** — the batch stays visible with its error summary; it is never
   silently dropped.

**Decision: a deterministic batch id from source + window.** The same window
always produces the same id, so a re-run is idempotent and two operators
cannot create two batches for the same data. The alternative (a UUID) makes
re-runs unsafe.

**Decision: the watermark advances only after publication.** If a batch
fails, the next run re-reads the same window. Advancing the watermark earlier
would silently skip records — the one failure mode a warehouse must never
have.

### 4.5 Where each transformation runs

| Step | Where | Why |
|---|---|---|
| Fetching, pagination, gzip packing | Python | Network concerns belong in the client; the warehouse never calls an API |
| Type parsing, identity resolution, quarantine | Snowflake SQL | Must be versioned, reviewable and re-runnable against stored raw data |
| Categorization | Snowflake SQL (`SP_CATEGORIZE_BATCH`) | A rule change must be re-runnable on the stored corpus, not require a re-download |
| Dimensional loads, surrogate keys | Snowflake SQL | Keeps key derivation in one auditable place |
| DQ gate, publication | Snowflake SQL | The gate must be impossible to bypass |
| Analytic queries, OLAP, views | Snowflake SQL, manual | They are the product; they run on demand, not on every deploy |

**Decision: Python extracts only raw NDJSON.** Every transformation is SQL, so
the raw data in the stage is enough to rebuild every downstream table. This is
what made the taxonomy v3 rewrite possible without re-downloading 296,299
outputs, and it is what makes the project reproducible.

### 4.6 The shape of the corpus (a fact that constrains every answer)

| Property | Value |
|---|---|
| Published outputs | 296,299 (0 duplicate DOIs) |
| Classified / unclassified | 220,501 (74.40%) / 75,798 (25.60%) |
| Citation observations | 265,968 |
| Reference edges | 2,557,842, of which **94,912** have both endpoints inside the corpus |
| Outputs with a resolved institution | 101,257, all outside 2012–2025 |
| Years 2023 / 2025 | 389 / 1,053 works |
| Institution-linked outputs stamped 2026 | 78,226 |

The corpus is **bimodal in time**: a 2026 block from the current extraction
windows, a long tail before 2009, and a thin 2021–2025 band in the middle.
Every year-scoped result therefore prints its denominator, and the Phase 1
suppression rule (fewer than 30 works at either endpoint ⇒ no growth rank)
is kept and published.

---

## 5. The reporting layer (the BI contract)

Seven views, all granted to `PAPERSONAR_REPORTER`, all exposing published data
only.

| View | Grain | Feeds |
|---|---|---|
| `VW_RESEARCH_OUTPUT` | one published output | measures, filters, pages 1–3 |
| `VW_CITATION_SNAPSHOT` | output × snapshot date | citation measures |
| `VW_OUTPUT_COVERAGE` | source × year × output type | page 1 |
| `VW_CITATION_COHORTS` | output × snapshot date | page 2 |
| `VW_TOPIC_GROWTH` | category × publication year | page 1 |
| `VW_TOPIC_INTERSECTIONS` | category pair | page 2 |
| `VW_RESEARCH_COMMUNITY` | institution × category × year | page 3 |
| `VW_CATEGORY_LABEL` | category key → label | labels for the pair view |

**Decision: the publication filter lives inside the view.** A bridge row is
visible only when its `BATCH_ID` is in `PROJECT_AUDIT.PUBLISHED_BATCH`; an
output only when its `LAST_BATCH_ID` is published. The BI layer therefore
*cannot* show an unpublished batch, whatever the user does in the tool. The
alternative — filtering in the visual — is one click away from being wrong.

**Decision: thresholds live in SQL, not in the visual.** The reportability
thresholds (≥ 100 parent works, ≥ 5 joint works) are applied in
`VW_TOPIC_INTERSECTIONS`, so the page cannot show a pair the evidence CSV
excludes.

Full field-by-field documentation for the BI build is in
`docs/phase3/POWERBI_SPEC.md` (sections 2 and 8 are the field catalogue and
the DAX).

---

## 6. Data quality — the 12-rule gate

`PROJECT_AUDIT.DQ_RESULT` holds one row per rule per batch per run.

| Rule | Severity | Threshold | What it proves |
|---|---|---|---|
| DQ-001 | CRITICAL | 0 | every manifest file's staged row count equals its manifest record count |
| DQ-002 | CRITICAL | 0 | bronze observations equal the distinct staged (source, record id) keys |
| DQ-003 | CRITICAL | 0 | silver crosswalk rows + quarantined rows reconcile to the bronze observations |
| DQ-004 | CRITICAL | 0 | every fact grain (`OUTPUT_SK`) is unique in `FACT_RESEARCH_OUTPUT`; also checks the category bridge is one row per output and category |
| DQ-005 | CRITICAL | 0 | no orphan or null dimension references (date, type, venue, access) |
| DQ-006 | CRITICAL | 0 | no orphan author/topic/category references on the bridges |
| DQ-007 | CRITICAL | 0 | exactly one current SCD2 row per `DIM_AUTHOR` business key |
| DQ-008 | WARNING | 0 | invalid DOIs are visible in quarantine, never silently replaced |
| DQ-009 | WARNING | 0.60 | categorized outputs meet the minimum coverage ratio |
| DQ-010 | WARNING | 72 h | source watermark freshness |
| DQ-011 | CRITICAL | 0 | required top-level payload keys present; missing required keys block publication |
| DQ-012 | CRITICAL | 0 | every output touched by the batch has exactly one primary category assignment |

**Decision: fail-closed publication.** A CRITICAL failure blocks
`SP_PUBLISH_BATCH`; the batch stays `FAILED` with its error summary. A
half-published corpus is far worse than a delayed one, because a reader
cannot tell which half is missing.

**Decision: DQ-009 is a WARNING, not a CRITICAL.** The 0.60 coverage target
was set before the sources were profiled. Once the sources were measured,
Crossref turned out to carry **no subject field at all** (49,093 records, 0
subjects) and Zenodo carries free-text organism/instrument subjects. A rule
that can never be satisfied by the data would either block every legitimate
Crossref batch or be quietly weakened. Making it a WARNING keeps it visible
while letting the pipeline proceed — and the ceiling is published instead.

**Decision: DQ-004 was scoped to the batch.** The duplicate check originally
compared the whole bridge, which made four batches fail because *other*
batches' rows were duplicated. The check now compares `bridge.BATCH_ID =
:batch_id`. A rule that measures the whole table cannot attribute a failure
to a batch, and an unattributable failure is not actionable.

### 6.1 The failed-batch ledger

Five batches are published. Eight failed at some point, and every failure is
accounted for:

| Batch | Source | Failed at | Cause | Status |
|---|---|---|---|---|
| `BATCH_8773F6D3E97673137420667B` | OpenAlex | extraction | staged part-file size mismatch | transient; the same source published successfully in another batch |
| `BATCH_70CEE97747ED6A70D3E40411` | Crossref | extraction | four manifest file mismatches | closed manually on 2026-11-22; never transformed, never published |
| `BATCH_2F4B3168EE13A751ECFE8AE4` | arXiv | silver | `REGEXP_SUBSTR` with a non-capturing group `(?:` | **fixed**; arXiv published later |
| `BATCH_0D23C6C167941A817239C45B` | Zenodo | silver | the same unsupported regular expression | **fixed**; Zenodo published later |
| `BATCH_3ECE33CC04DCAB9DF46F369D` | arXiv | categorize | `invalid identifier 'M.BASE_WEIGHT'` in the old categorization | **fixed** by the v3 rewrite |
| `BATCH_FA946DC9EA79F54798BBFE82` | DataCite | silver | `PUBLICATION_DATE_RAW` too narrow for a multi-valued date string | **fixed** by `sql/03_silver/04_widen_oversize_text.sql` |
| `BATCH_E0303CAD6AAC633E2C60BC2A` | DataCite | dimensions | `STG_DIM_TOPIC.TOPIC_NAME` too narrow | **fixed** by the same script |
| `BATCH_EB4210A9204AF7243A942647` | DataCite | dimensions | the same `TOPIC_NAME` truncation | **fixed** by the same script |

The lesson recorded from the DataCite failures: a `VARCHAR` width is a data
contract, and the source must be profiled before the width is chosen.

---

## 7. The taxonomy — the central design decision

The taxonomy is a **versioned contract** (`PROJECT_REF.REF_CATEGORY`,
`REF_CATEGORY_KEYWORD`, `REF_TAXONOMY_MAP`, `CATEGORY_OVERRIDE`), not a
runtime search. 67 categories in 10 domains, seeded by
`scripts/generate_taxonomy_seed.py` and `config/taxonomy.yml`.

### 7.1 How an output is categorized

Three candidate sources, ranked, with the winner and the losers all stored:

1. **Operator override** (score 1000) — `CATEGORY_OVERRIDE`, for a known
   misclassification.
2. **Native source taxonomy** — the source's own structured value (OpenAlex
   topic/domain/subfield/field, arXiv category codes, Zenodo subjects). A
   curated label supplied by the source outranks a keyword hit. Within this
   method the most specific part wins: topic display name > subfield > field
   > domain.
3. **Keyword score** — `REF_CATEGORY_KEYWORD` matched against the normalized
   title (weight × 3) and topics, with base weights.
4. **Fallback** — `unclassified`.

Matching is **boundary aware**: a pattern must start on a word boundary, so
`cultural` cannot match `agricultural` and `art` cannot match `plant`.
Patterns of four characters or fewer must match a whole word; longer ones
match a word-initial stem.

**Decision: store every candidate, not just the winner.** `BRIDGE_OUTPUT_TOPIC_CATEGORY`
keeps the score, rank, primary flag, method and taxonomy version of every
assignment. That is what makes Q13 (counting sensitivity) and Q05
(intersections) possible, and what let the coverage defect below be found.

### 7.2 The defect that was found and fixed

The first live run produced **more than one row per (output, category)** in
the bridge: 894,545 rows for 296,299 outputs and 67 categories, with
598,246 "secondary" rows that were partly duplicates of the same assignment.
That inflated topic counts and made intersections meaningless.

The fix (`sql/04_categorization/02_categorize_batch.sql`) ranks the candidates
with

```sql
ROW_NUMBER() OVER (
  PARTITION BY OUTPUT_BK, CATEGORY_KEY
  ORDER BY PRIORITY, SCORE DESC, METHOD
)
```

and keeps `CATEGORY_PICK = 1`, so the bridge holds exactly one row per output
and category. A contract test was added
(`tests/sql/test_sql_contracts.py::test_categorization_writes_one_row_per_output_and_category`)
so the same defect cannot come back silently. All five batches were re-run
after the fix: F4.2 = 0 duplicates, coverage unchanged.

**The lesson:** the "primary vs secondary" distinction is a *ranking* inside
one output-category pair, not a second copy of the pair. Both concepts existed
in the model and had to be separated.

### 7.3 The coverage result

| Source | Outputs | Before (v2) | After (v3) | Why |
|---|---:|---:|---:|---|
| OpenAlex | 168,577 | 3.40% | **98.30%** | four structured native values per work are read |
| arXiv | 15,503 | 5.46% | **100.00%** | all 154 category codes mapped explicitly |
| Crossref | 78,495 | 0.31% | **35.30%** | the records carry **no subject field** |
| Zenodo | 33,724 | 4.08% | **34.33%** | subjects are free-text organism/instrument names |
| **All** | **296,299** | **1.92%** | **74.40%** | |

The v2 failure mode is gone: `'cultural'` no longer fires inside
"agricultural and biological sciences", and `arts-and-culture` fell from
175,415 outputs to 282. The distribution is now led by botany (56,209) and
physics (52,200) — the actual shape of the corpus rather than a substring
artefact.

---

## 8. The fourteen analytical questions

Every question has one SQL implementation, one numerator, one denominator, one
threshold and one evidence file. The measure definitions are copied verbatim
from the Phase 1 business-question document
(`docs/submissions/phase-1/editable/03_PaperSonar_Business_questions.docx`)
and a contract test (`tests/sql/test_analytics_contracts.py`) enforces the
mapping, so the SQL and the requirement text cannot drift.

| Q | Question | File | Numerator | Denominator | Threshold / suppression |
|---|---|---|---|---|---|
| **Q01** | Which research topics are growing? | `01_topic_growth_share.sql` | distinct published outputs with the primary topic, per year | absolute counts (CAGR on counts) | suppress the growth ranking when either 2023 or 2025 has < **30** works; CAGR only when both endpoints are positive |
| **Q02** | How much of the corpus does each topic represent? | `01_topic_growth_share.sql` | topic primary-publication count | all admitted publications in the same year, and also the categorized corpus | percentage-point change, not a rank cut |
| **Q03** | Which topic cohorts have the highest citation impact? | `02_citation_impact.sql` | median `CITED_BY_COUNT` at **one** snapshot date | cohort size | one observation date only; cohort size and missing-snapshot count printed next to the median |
| **Q04** | Which papers gained citations between two observations? | `02_citation_impact.sql` | late `CITED_BY_COUNT` − early `CITED_BY_COUNT` | — | only outputs observed at both dates qualify; gains and revisions labelled separately |
| **Q05** | Which topic pairs genuinely intersect? | `03_topic_intersections.sql` | distinct works co-assigned to an unordered pair | the smaller parent topic count | each parent ≥ **100** works and the pair ≥ **5** works, else suppressed |
| **Q06** | Which venues publish in each topic? | `04_venues_and_institutions.sql` | distinct published outputs per venue and topic | topic outputs 2021–2025 | missing-venue share reported separately |
| **Q07** | Which institutions contribute to each topic? | `04_venues_and_institutions.sql` | fractional institution credit per topic and year | one output contributes 1.0, split evenly over its distinct institutions | unknown institutions are shown as their own category, not dropped |
| **Q08** | Is a topic dominated by a few institutions? | `04_venues_and_institutions.sql` | fractional credit of the top five institutions | all fractional credit of classified institutions in the same topic and year | top five computed **after** filtering; unknown institutions excluded from the ranking and their share disclosed |
| **Q09** | How accessible is each topic's literature? | `05_access_and_authors.sql` | open-access outputs at the snapshot date | outputs with a **known** access status | unknown-status share reported separately, never folded into the numerator |
| **Q10** | Which authors are repeatedly active in a topic? | `05_access_and_authors.sql` | distinct published outputs per author key, 2021–2025 | — | activity only, not expertise; the topic filter is a parameter |
| **Q11** | Which topics cite which other topics? | `06_relationship_flow.sql` | citation edges with both endpoints admitted | — | directed; induced subgraph, so global citation totals are not reproduced |
| **Q12** | How complete is the metadata? | `07_metadata_coverage.sql` | outputs missing DOI / primary topic / venue / institution / access status | the eligible population per topic and year | every rate is returned with its eligible population |
| **Q13** | Does the conclusion survive a different counting rule? | `08_sensitivity_and_period.sql` | primary-topic count versus equal fractional allocation | — | low-volume groups (< **30** works) are flagged and their rank shift suppressed |
| **Q14** | How does the current period compare with the same period last year? | `08_sensitivity_and_period.sql` | outputs published through a common month/day cutoff | the same cutoff in the previous year | unknown and year-only dates excluded; cutoff and retrieval date returned |

### 8.1 The cross-cutting rules

1. **Publication contract** — queries on the reporting views inherit it;
   queries that touch the bridge tables repeat the `PUBLISHED_BATCH` filter
   explicitly.
2. **No invented measures** — a rate is only produced when both its numerator
   and its denominator are in the result set.
3. **No null-to-zero conversion** — missing metadata is counted as missing
   (Q12) or reported as an unknown share (Q06, Q09), never as zero.
4. **One source scope per output per snapshot** — Q03 and Q09 fix a single
   source per output by source priority and return that scope as
   `SCOPE_SOURCE`.
5. **Retrieval date** — every result carries `RETRIEVED_ON`.
6. **Cost** — the queries scan between 265k and 1.8m rows; Q05, Q11 and Q13
   are the expensive ones and run on the X-Small warehouse.

### 8.2 The findings the questions produced

**Q01/Q02 — growth cannot be answered yet.**

| Topic | Works 2023 | Works 2025 | Share change | Status |
|---|---:|---:|---:|---|
| ai-ml | 8 | 69 | +4.50 pp | suppressed (2023 endpoint < 30) |
| clinical-medicine | 2 | 40 | +3.28 pp | suppressed |
| physics | 4 | 37 | +2.49 pp | suppressed |

389 works in 2023 and 1,053 in 2025. The rule exists precisely to stop an
8-to-69 ratio from being presented as a growth rate. The numbers are
published; the conclusion is "not yet reportable".

**Q05 — only three topic pairs are reportable.**

| Pair | Parent A | Parent B | Joint works | Joint / smaller parent |
|---|---:|---:|---:|---:|
| ai-ml × health-sciences | 127 | 104 | 10 | 9.62% |
| health-sciences × law | 104 | 226 | 9 | 8.65% |
| ai-ml × physics | 127 | 115 | 9 | 7.83% |

These describe works the taxonomy genuinely places in two fields: applied
machine learning with clinical work, health law, and AI with physics. On a
corpus this young in its taxonomy coverage, a short list is the correct
answer.

**Q07/Q08 — the concentration metric is dominated by one identifier.**

| Topic | Year | Works | Top-5 share | Largest single institution |
|---|---|---:|---:|---|
| physics | 2026 | 49,203 | **99.24%** | National Institute for Fusion Science (`openalex:I4210108322`) |
| ecology | 2026 | 1,056 | 58.07% | University of Piura (1,056 works) |

Across the corpus that one OpenAlex identifier holds **56.9% of all
institutional credit** (49,378.5 of 86,767.9) and the next holds 1.2%. This
is an affiliation artefact in the source metadata — a bulk institution field
attached to a large series of works — not a statement about physics. The
practical consequence is a rule for the BI layer: the community page shows an
institution's work count next to its credit.

**Q09 — open access.** 163,951 of 181,318 outputs with a known access status
are open (90.42%); 39,183 outputs have an unknown status and are reported
separately.

**Q11 — citation flow.** 2,557,842 relation rows, 94,912 of them induced
inside the corpus; the flow table produces 3,254 topic-pair rows.

**Q13 — the counting rule decides the leaderboard.**

| Topic | Primary count (rank) | Fractional count (rank) | Shift |
|---|---|---|---|
| botany | 57,419 (1) | 15,501.9 (4) | −3 |
| physics | 56,353 (2) | 25,854.3 (1) | +1 |
| clinical-medicine | 17,190 (3) | 10,538.3 (9) | −6 |
| ai-ml | 12,025 (4) | 6,424.8 (11) | −7 |
| ecology | 5,625 (6) | 16,016.5 (3) | +3 |

Botany leads the corpus by primary topic because botanical works carry botany
as their strongest label, but they distribute across several categories more
often than physics does. A reader told only "botany is the largest topic"
would reach a different conclusion from one told "botany is the largest topic
when each work is counted once". The Q13 evidence makes the difference visible
instead of hiding it.

**Q12 — metadata coverage.** For the 220,501 classified works there are **0
missing citation snapshots**; the coverage table per topic and year is the
evidence for the claims on page 1.

---

## 9. OLAP

`sql/10_analytics/09_rollup_cube.sql` (manual, three statements):

| Cube | Statement | Grain of the output | Subtotal handling |
|---|---|---|---|
| OLP1 | `ROLLUP(category, year)` | category × year with year and category subtotals | `GROUPING_ID` plus `IS_MEMBER` / `IS_SUBTOTAL` / `IS_GRAND_TOTAL` flags |
| OLP2 | `CUBE(output type, source)` | output type × source with both single-dimension subtotals | same flags |
| OLP3 | `GROUPING SETS(topic, access, year)` | the three marginal totals side by side | same flags |

**Decision: every row carries `GROUPING_ID` and explicit flags.** A reader
cannot mistake a subtotal for a member row, and a BI tool can filter on
`IS_SUBTOTAL` instead of guessing from a null key. The evidence exports are
`docs/phase3/evidence/02_olap/OLP1…OLP3*.csv`; the reasoning is in
`docs/phase3/OLAP_NOTES.md`.

---

## 10. The Power BI model

The three-page model, the field catalogue for every view, the DAX catalogue,
the build order and the delivery checklist are in
**`docs/phase3/POWERBI_SPEC.md`**. The short version:

| Page | Question | Visuals | Views |
|---|---|---|---|
| 1 — Topic landscape and coverage | Which directions are growing, and how much of the corpus is classified? | clustered column, line of classified share, source × year coverage matrix, stacked bar by output type, 4 cards | `VW_TOPIC_GROWTH`, `VW_OUTPUT_COVERAGE` |
| 2 — Citation impact and topic overlap | Which cohorts carry impact, and which topic pairs are really connected? | cohort scatter, cohort table with the missing-snapshot gap, reportable-pair matrix, 2 cards | `VW_CITATION_COHORTS`, `VW_TOPIC_INTERSECTIONS` |
| 3 — Research community | Which institutions carry which topics, and how concentrated is that? | treemap, top-20 bar, institution table, works-vs-credit scatter, 4 cards | `VW_RESEARCH_COMMUNITY` |

**The three rules the model enforces:** the publication filter is in the
views; the thresholds are in the views; every ratio shows its denominator.

**Known limitation:** the PBIX itself is not in the repository because the
Power BI desktop client is outside the warehouse. The deliverable is the
specification plus the exported evidence CSVs that every visual is built
from — the numbers can be reproduced without the client.

---

## 11. The optimization experiment (a published negative result)

**What was measured:** four representative statements — the topic growth scan,
the intersection self-join, the citation flow join, and the heaviest
reporting view — before and after applying clustering keys to three tables.

**The change under test**

```sql
ALTER TABLE PROJECT_DW.FACT_RESEARCH_OUTPUT  CLUSTER BY (PUBLICATION_YEAR, SOURCE_NAME);
ALTER TABLE PROJECT_DW.FACT_OUTPUT_RELATION  CLUSTER BY (RELATION_TYPE, OUTPUT_SK);
ALTER TABLE PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY CLUSTER BY (OUTPUT_SK, CATEGORY_KEY);
```

**The result**

| Benchmark | Execution before | after | like-for-like? |
|---|---:|---:|---|
| BENCH1 topic growth | 2 ms | 1,000 ms | no — before was a result-cache hit |
| BENCH2 intersections | 531 ms | 570 ms | **yes, 7% slower** |
| BENCH3 citation flow | 789 ms | 890 ms | **yes, 13% slower** |
| BENCH4 community view | 2 ms | 1,600 ms | no — before was a result-cache hit |

**Decision: rolled back.** The rule was fixed before the measurement — keep
the keys only if the measured execution time or bytes scanned improved — and
they did not, so the project keeps the simpler cluster-free layout and
publishes the negative result.

**Why it could not pay off at this scale:** the tables are 296k, 894k and
2.5m rows, which an X-Small scans in hundreds of milliseconds; two of the four
statements read through secure views with no predicate push-down into the
clustered tables; and clustering is a standing cost, because later writes that
do not match the key order trigger background re-clustering.

**Two measurement lessons recorded in the report:**

1. *The before-run was partly a result-cache hit.* `ALTER TABLE … CLUSTER BY`
   invalidates cached results, so the before/after comparison was not
   like-for-like. The honest numbers are the two statements that executed in
   both runs.
2. *The `ALTER TABLE` is asynchronous.* The after-run may have overlapped
   background re-clustering, which can only make the after-run look worse.

**When to revisit:** when `FACT_OUTPUT_RELATION` passes ~25 million rows or
the analytical tables pass five million, re-run the same measurement with
three repetitions per statement and a cold warehouse.

Artefacts: `docs/phase3/evidence/03_optimization/` (16 files plus
`BENCH_TIMINGS.csv`); reasoning: `docs/phase3/OPTIMIZATION_REPORT.md` §5.

---

## 12. The decision log

Each decision lists the alternatives that were rejected and why.

| # | Decision | Alternatives rejected | Why |
|---:|---|---|---|
| 1 | Snowflake only, free-only policy, no database fallback | PostgreSQL / SQLite fallback | The course allowed a free local database; the project chose the target that the deployment story needs. If the trial had expired, the work would have been reported **BLOCKED**, not silently moved |
| 2 | Python extracts raw NDJSON only; all transformation in SQL | Transforming in Python | A rule change must be re-runnable on stored raw data. This is what made the taxonomy rewrite possible without re-downloading 296,299 outputs |
| 3 | Current-state bronze (one row per source record id) | Append-only bronze | Bronze is the re-runnable base for the silver layer. Version history is kept where it matters — the citation snapshot fact |
| 4 | Deterministic batch id from source + window | UUID batch ids | Re-runs must be idempotent, and two operators must not create two batches for the same data |
| 5 | Watermark advances only after publication | Advance after load | Otherwise a failed batch silently skips records |
| 6 | Fail-closed publication on CRITICAL DQ failures | Publish with warnings | A half-published corpus is worse than a delayed one, because a reader cannot tell which half is missing |
| 7 | DQ-009 coverage is a WARNING, not a CRITICAL | Keep it CRITICAL | The 0.60 target is unreachable for Crossref and Zenodo by source design. A rule that can never pass would either block every legitimate batch or be quietly weakened |
| 8 | Taxonomy as a versioned contract with three candidate sources and stored runners-up | Pure keyword search; pure source taxonomy | Keyword matching alone produced the `'cultural'` failure; source taxonomy alone leaves Crossref and Zenodo unclassified. Storing every candidate enables Q05 and Q13 |
| 9 | Boundary-aware matching (word boundary; ≤ 4 chars = whole word) | Substring matching | `cultural` inside `agricultural` was the single largest false positive (175,415 outputs) |
| 10 | One row per (output, category) in the bridge, ranked in SQL | Keeping every candidate row | The duplicate defect inflated topic counts and made intersections meaningless. The ranking rule is now enforced by a contract test |
| 11 | Primary topic = highest-ranked category; secondary categories kept but flagged | One category per output only | Intersections and the fractional counting rule need the second category; the primary flag still gives a clean leaderboard |
| 12 | Fractional institutional credit (1.0 split over institutions) | Counting one affiliation per work | A work with three institutions would otherwise give one institution all the credit. The fractional rule is published next to the raw work count |
| 13 | Reportability thresholds in SQL (100 parent / 5 joint) | Thresholds typed into the BI visual | The page and the evidence CSV cannot disagree |
| 14 | The publication filter inside every view | Filtering in the tool | The BI layer cannot show an unpublished batch, whatever the user does |
| 15 | Keep the 30-work suppression rule even though it hides the growth ranking | Publish the ranking | An 8-to-69 ratio presented as growth is the failure mode the rule exists to prevent. The numbers are published; the ranking is suppressed |
| 16 | The analytical layer is `-- Deploy: manual` | Deploying the queries with the schema | A deploy must never burn warehouse credits on analytical scans |
| 17 | Materialized view and dynamic table left uncreated | Creating them as "extras" | Both refresh continuously and cost credits for a benefit that has not been measured. They stay as a manual demonstration file |
| 18 | Clustering applied, measured, then rolled back | Keeping it because it is "best practice" | The pre-registered rule said keep only if it improved. It did not, so it was rolled back and the negative result published |
| 19 | The service user's `PAPERSONAR_ADMIN` grant kept | Revoking it as "least privilege" | The deployment logs in as that user assuming `PAPERSONAR_ADMIN`; revoking it would break every deployment. The data path itself runs on the narrow roles. The future fix (a dedicated deploy role) is recorded |
| 20 | `COMPUTE_WH` left suspended with a resource monitor rather than deleted | Deleting the account default | Snowflake refuses to suspend the account's default warehouse; `AUTO_SUSPEND = 60` plus the resource monitor stops the credit burn without breaking the account |
| 21 | Phase 3 delivered as SQL + evidence + specification, not as a PBIX | Building the PBIX in the warehouse | The desktop client is outside the warehouse; the specification plus the exported evidence is the honest deliverable, and every number on a page can be traced to a CSV |
| 22 | Both `main` and `phase3` kept at the same commit | Deleting the branch | The delivered branch is the deployed branch; the history stays readable |

---

## 13. Cost and resource control

| Resource | Purpose | Setting |
|---|---|---|
| `WH_PAPERSONAR_ELT` | the only warehouse used for ELT, analytics and the benchmark | X-Small, auto-suspend 60 s, resource monitor `RM_PAPERSONAR_ELT` |
| `RM_PAPERSONAR_ELT` | caps the ELT warehouse so a looping task cannot drain the trial | monthly credit cap |
| `PAPERSONAR_ADMIN` / `_LOADER` / `_TRANSFORMER` / `_REPORTER` | separation of duties for deployment, ingestion, transformation and reporting | custom roles |
| `COMPUTE_WH` | account default, **unused by the project** | suspended, auto-suspend 60 s, monitor attached |
| `PAPERSONAR_WH` | Phase 1 leftover | dropped 2026-11-22 |

Trial position: **$400 credit, $328 remaining at the start of Phase 3**, and
about 23 days left. The binding constraint is the trial window, not the credit
balance, so the project was front-loaded: every course-visible artefact
exists in the repository before the deadline.

Five cost measures are applied (full list: `docs/phase3/COST_LOG.md`): one
X-Small warehouse with a 60-second auto-suspend; a resource monitor; a manual
analytical layer; no background-refreshing physical objects; and clustering
applied only after a baseline measurement.

---

## 14. Security and access

| Role | Holds | Used for |
|---|---|---|
| `ACCOUNTADMIN` | everything | the human owner only; never used by CI (the deployment refuses to run with it) |
| `PAPERSONAR_ADMIN` | project schemas | the deployment principal (SVC_PAPERSONAR) |
| `PAPERSONAR_LOADER` | stage and bronze | the ingestion path |
| `PAPERSONAR_TRANSFORMER` | silver, dimensions, facts | the transformation path |
| `PAPERSONAR_REPORTER` | `SELECT` on the reporting views | the BI path, and read-only by construction |

Other controls: key-pair authentication (no password in the repository), all
secrets in GitHub environment secrets, no raw records, logs, credentials or
dumps in Git, and the data path itself is not administrative even though the
deployment principal is.

---

## 15. Evidence and reproducibility

### 15.1 The evidence tree

```
docs/phase3/evidence/
  00_taxonomy/   WP1_TAXONOMY_EVIDENCE.md, DQ009_before_after.csv
  01_queries/    Q01..Q14 exports (Q04 and Q07 are the large ones)
  02_olap/       OLP1_rollup_category_year.csv, OLP2_cube_output_type_source.csv,
                 OLP3_grouping_sets_topic_access.csv
  03_optimization/ BENCH1..BENCH4 before/after results and plans, BENCH_TIMINGS.csv
docs/phase3/     PLAN, STATUS, METRIC_CATALOGUE, WP1_TAXONOMY_RUNBOOK, OLAP_NOTES,
                 POWERBI_SPEC, INSIGHTS_REPORT (+PDF), INSIGHTS_DECK.pptx,
                 COURSE_MAPPING, COST_LOG, OPTIMIZATION_REPORT
docs/phase2/evidence/  the Phase 2 live verification and the OpenAlex backfill evidence
docs/requirements/     the requirement-by-requirement traceability matrix
```

### 15.2 How to verify any claim in five minutes

```sql
USE ROLE PAPERSONAR_ADMIN;
USE WAREHOUSE WH_PAPERSONAR_ELT;

-- corpus size
SELECT COUNT(*) AS OUTPUTS FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT;

-- one row per output and category
SELECT COUNT(*) AS ROWS_, COUNT(DISTINCT OUTPUT_SK || '|' || CATEGORY_KEY) AS PAIRS
FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY;

-- classification coverage
SELECT COUNT(DISTINCT IFF(CATEGORY_KEY <> 'unclassified', OUTPUT_SK, NULL)) AS CLASSIFIED,
       COUNT(DISTINCT OUTPUT_SK) AS TOTAL
FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY;

-- published batches and their status
SELECT BATCH_ID, SOURCE_NAME, STATUS, ERROR_SUMMARY
FROM PAPERSONAR.PROJECT_AUDIT.BATCH ORDER BY CREATED_AT;

-- the DQ results of every batch
SELECT BATCH_ID, RULE_ID, SEVERITY, STATUS FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT
ORDER BY BATCH_ID, RULE_ID;

-- the reporting layer
SHOW VIEWS IN SCHEMA PAPERSONAR.PROJECT_REPORTING;
```

```bash
python -m pytest tests -q      # 270 tests
python -m ruff check src tests
```

---

## 16. Course requirement traceability

| Requirement | Phase | State | Proof |
|---|---|---|---|
| Business problem, users, objectives | 1 | delivered | proposal + business requirements |
| 10+ analytical questions | 1–3 | delivered | 14 questions, each with SQL, thresholds and evidence |
| Business processes | 1 | delivered | output registration, source observation, citation/relationship observation, periodic snapshot |
| Fact grain and fact types | 1–2 | delivered | accumulating entity, periodic snapshot, factless typed relationships |
| Dimensions and hierarchies | 1–3 | delivered | 10 conformed dimensions + the category bridge |
| Natural and surrogate keys | 1–2 | delivered | `DIMENSION_KEY_MAP` (942,762 rows) |
| Conceptual, logical, physical model | 1 | delivered | diagram set + data dictionary + addendum |
| 100+ dimension records | 2 | validated | `DIM_AUTHOR` 381,172 · `DIM_TOPIC` 70,103 · `DIM_INSTITUTION` 27,858 · `DIM_VENUE` 15,172 · `DIM_DATE` 14,611 |
| 10,000+ fact records | 2 | validated | `FACT_RESEARCH_OUTPUT` 296,299 · `FACT_OUTPUT_RELATION` 2,557,842 |
| Staging, cleaning, transformation | 2 | validated | `sql/01_staging` … `sql/07_reporting`, live on 5 batches |
| Surrogate-key mapping | 2 | validated | key map + DQ-004…DQ-007 orphan checks |
| Completeness, accuracy, integrity | 2–3 | validated | 12-rule DQ gate; DQ-009 measured at 74.40% |
| Analytical aggregations, 14 questions | 3 | validated | `sql/10_analytics/01..08*.sql` + 14 evidence exports |
| `ROLLUP` and `CUBE` | 3 | validated | `09_rollup_cube.sql` + 3 evidence exports |
| Reporting views | 3 | validated | 5 SECURE views, granted to `PAPERSONAR_REPORTER` |
| Query optimization | 3 | validated | before/after measurement; negative result; rollback |
| Power BI three-page example | 3 | specification delivered | `POWERBI_SPEC.md`; the PBIX needs the desktop client |
| Business insights and presentation | 3 | validated | insights report + PDF + deck, 7 traceable findings |
| Free-only | all | honoured | X-Small standard warehouses on the free trial, no paid resource |

The element-by-element mapping from the course's retail example onto the
research domain is in `docs/phase3/COURSE_MAPPING.md`.

---

## 17. Risks, limits, and what comes next

| Limit | Impact | What is done about it | Next step |
|---|---|---|---|
| OpenAlex incremental blocked (HTTP 403, plan required) | no daily refresh for the largest source | the full backfill is live and published; no fallback was invented | re-test when a plan is available; the window logic is already implemented |
| DataCite not live-proven | one of five sources has no published batch | the two code defects (truncating columns) are fixed and verified live at `VARCHAR(4000)` | run one DataCite window when the registry serves a stable extraction |
| Coverage ceiling ≈ 35% for Crossref and Zenodo | two sources cannot support a full topic analysis | published as a source property, not hidden; DQ-009 is a WARNING | enrich from the source's own subject vocabulary if a future version exposes one |
| 101,257 institution-linked outputs, all outside 2012–2025 | the community page cannot answer "who is active now" | published; the BI rule shows work count next to credit | re-extract affiliations with the next OpenAlex window |
| One identifier holds 56.9% of institutional credit | the concentration metric is an artefact | published as an artefact; the rule "show works next to credit" is on the page | exclude bulk identifiers in a future metric definition, with the exclusion published |
| The corpus is bimodal in time | year-on-year questions are unstable | the 30-work suppression rule; every denominator printed | a second full backfill of a different period would balance the corpus |
| The PBIX is not built | the course asks for a dashboard | the full specification plus the exported evidence behind every visual | build it on a desktop client from `POWERBI_SPEC.md` |
| The trial expires around 2026-12-15 | the live account ends | everything course-visible is committed to the repository; the evidence CSVs reproduce every number | keep the repository as the deliverable; the account is the demo |

---

## 18. Presenting the project

### 18.1 A 10-minute run of show

| Minute | Slide / action | The point being made |
|---:|---|---|
| 0–1 | the problem | comparing research directions is hard because the evidence is split and the counting rule decides the answer |
| 1–2 | the architecture (one diagram) | strict ELT: Python extracts raw, SQL transforms, the gate publishes |
| 2–3 | the live state | 5 batches, 296,299 outputs, 12 DQ rules, 270 tests, one X-Small warehouse |
| 3–5 | the taxonomy before/after | 1.92% → 74.40%, and the reason it stops at 35% for two sources |
| 5–7 | three findings | growth not yet reportable · three reportable topic pairs · one identifier holding 56.9% of the credit |
| 7–8 | the BI model | three pages, thresholds in SQL, every ratio with its denominator |
| 8–9 | the negative result | clustering measured, slower, rolled back — with the evidence |
| 9–10 | what is next and what is blocked | the honest list, and the fact that every number is in the repository |

### 18.2 Questions an evaluator will ask, with the answers

**"How do you know the data is correct?"**
Twelve DQ rules run on every batch; nine are CRITICAL and block publication;
the fail-closed publish procedure refuses a batch with a CRITICAL failure;
the results are per rule, per batch, in `PROJECT_AUDIT.DQ_RESULT`. The
independence checks are DQ-004 (fact grain), DQ-005/DQ-006 (orphans) and
DQ-007 (one current author row). All five published batches have
`critical_failures = 0`.

**"What if the same record appears twice?"**
It cannot: DQ-004 fails the batch if the fact grain is not unique, and the
category bridge is checked the same way. The 296,299-output corpus has 0
duplicate DOIs, measured live.

**"Why did you roll back the clustering?"**
Because it was measured, not assumed. On the two like-for-like measurements it
was 7% and 13% slower, and at 296k–2.5m rows on an X-Small the pruning
cannot repay the re-clustering cost. The rule was fixed before the
measurement, the evidence is committed, and the decision to revisit at ~25m
rows is recorded.

**"Your growth numbers are small — are they reliable?"**
No, and that is why they are suppressed. 389 works in 2023 and 1,053 in 2025
means any ratio is unstable. The Phase 1 rule (suppress below 30 works at
either endpoint) is kept, the numbers are published, and the conclusion is
"not yet reportable".

**"What is the biggest weakness of the project?"**
The DataCite source has never published a batch. The two code defects behind
its failures are fixed and verified live, but the registry's extraction
behaviour is outside the project, so the path is untested against live data.

**"Why only 35% coverage for Crossref?"**
Because those records carry no subject field at all — 49,093 records, zero
subjects. A warehouse that claimed 60% coverage there would be inventing
coverage. The ceiling is published as a source property.

**"How would you scale this?"**
Re-test clustering when the relation fact passes ~25m rows; add an incremental
OpenAlex path when a plan allows it; balance the corpus with a second period
backfill so the year-on-year questions become answerable; and replace the
deployment role with a dedicated least-privilege principal.

---

## 19. Appendix — where everything lives

| Area | Path |
|---|---|
| Phase 3 delivery documents | `docs/phase3/` |
| Phase 3 evidence | `docs/phase3/evidence/{00_taxonomy,01_queries,02_olap,03_optimization}/` |
| The BI build sheet | `docs/phase3/POWERBI_SPEC.md` |
| The metric catalogue (Q01–Q14) | `docs/phase3/METRIC_CATALOGUE.md` |
| The taxonomy contract and runbook | `config/taxonomy.yml`, `docs/phase3/WP1_TAXONOMY_RUNBOOK.md` |
| The seed generator | `scripts/generate_taxonomy_seed.py` |
| The deployable SQL, in layer order | `sql/00_setup/` … `sql/10_analytics/` |
| The manual analytical layer | `sql/10_analytics/01..10*.sql` |
| The reporting views | `sql/07_reporting/04_phase3_reporting_views.sql` |
| The category label lookup | `sql/07_reporting/05_phase3_view_labels.sql` |
| The clustering experiment and its rollback | `sql/06_facts/03_phase3_clustering.sql` |
| The DQ rules and the gate | `sql/08_audit_dq/01_dq_rules.sql`, `02_run_dq.sql` |
| The batch control procedures | `sql/09_tasks/01_batch_control.sql` |
| The acceptance queries | `sql/99_tests/01_acceptance.sql` |
| The extractors | `src/extract/` |
| The runner, CLI and deployer | `src/runner/` |
| The tests | `tests/` (unit, contract, SQL guards) |
| The workflows | `.github/workflows/extract-load.yml`, `deploy-ci.yml` |
| The course traceability | `docs/requirements/course-requirements-matrix.md` |
| The Phase 2 operator runbook | `docs/phase2/RUNBOOK.md` |
| The cost log | `docs/phase3/COST_LOG.md` |
| The housekeeping script | `sql/00_setup/07_housekeeping.sql` |
| The insight report and deck | `docs/phase3/INSIGHTS_REPORT.md`, `.pdf`, `INSIGHTS_DECK.pptx` |
