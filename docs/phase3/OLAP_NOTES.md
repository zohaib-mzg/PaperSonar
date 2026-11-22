# Phase 3 OLAP Notes — ROLLUP, CUBE and GROUPING SETS

**Date:** 2026-11-22 · **Branch:** `phase3` · **Implementation:** `sql/10_analytics/09_rollup_cube.sql`
**Evidence:** `docs/phase3/evidence/02_olap/OLP1_rollup_category_year.csv`,
`OLP2_cube_output_type_source.csv`, `OLP3_grouping_sets_topic_access.csv`

---

## 1. Why three techniques and not one

The published corpus is one taxonomy, one output-type vocabulary and one
source list. A single `ROLLUP` would show a hierarchy that the model does not
have; a single `CUBE` over every dimension would multiply rows into a matrix
nobody reads. The three analyses therefore each use the technique that matches
the question being asked.

| Analysis | Technique | Dimensions | Rows produced |
|---|---|---|---|
| OLP1 | `ROLLUP` | category → publication year | member rows, one subtotal per category, one grand total |
| OLP2 | `CUBE` | output type × primary source | member rows, one subtotal per type, one per source, one grand total |
| OLP3 | `GROUPING SETS` | topic × access status × publication year | seven explicitly chosen aggregation levels |

## 2. How to read the output

Every result set emits `GROUPING_ID` plus four or five explicit flags:

| Flag | Meaning |
|---|---|
| `IS_MEMBER` | both (or all) dimensions are present: a real data point |
| `IS_SUBTOTAL` | one dimension grouped out: a partial aggregate |
| `IS_TYPE_SUBTOTAL` / `IS_SOURCE_SUBTOTAL` | the cube's two partial aggregates |
| `IS_TOPIC_ACCESS_SUBTOTAL` / `IS_ACCESS_YEAR_SUBTOTAL` / `IS_TOPIC_YEAR_SUBTOTAL` | the grouping sets' partial aggregates |
| `IS_GRAND_TOTAL` | every dimension grouped out: the total |

`GROUPING_ID` is the raw bitmask and is kept because the matrix asks for it;
`GROUPING()` is used next to it because it states each grouped-out column
explicitly and does not depend on the bit order of `GROUPING_ID`. A reader who
filters on `IS_MEMBER = TRUE` can never mistake an aggregate for a data point.

## 3. What each hierarchy means

**OLP1 — category → year.** The category is the analytical spine of the
project (`REF_CATEGORY` v3, 67 categories, reached through
`BRIDGE_OUTPUT_TOPIC_CATEGORY`), and the publication year is the only time
dimension the Phase 1 questions use. The rollup answers "how many works does
this topic have in total, and how is that split by year". `unclassified` is
excluded from this analysis: it is a coverage category, not a topic, and
including it would turn the rollup into a coverage report.

**OLP2 — output type × primary source.** A cube is used because neither
dimension is a parent of the other: an output type and a source are two
independent classifications of the same work. The cube therefore answers
"which types does this source publish, and which sources publish this type"
in one result set, with the marginal totals already computed. The cube is
deliberately two-dimensional: adding the year, the access status or the
category to the cube would produce a matrix whose cells are too small to read
and whose marginal totals would be misleading.

**OLP3 — topic × access status × year.** `GROUPING SETS` is used instead of a
cube because the analysis levels are a decision, not a hierarchy: full detail,
topic × access, topic × year, access × year and the three single-dimension
totals. Every one of those seven levels is a question the course asks, so each
is written out. A `CUBE` over the same three dimensions would add four
combinations that are not asked for.

## 4. Scope and honesty rules

1. **Publication contract.** All three analyses read
   `PROJECT_REPORTING.VW_RESEARCH_OUTPUT`, which exposes an output only when
   its batch is in `PROJECT_AUDIT.PUBLISHED_BATCH`.
2. **No invented hierarchy.** The category → year rollup is a hierarchy because
   the taxonomy defines the categories; the type × source cube is not, and is
   labelled as a cube of two independent dimensions.
3. **The counts are the corpus.** Every count is a distinct published work in
   the retained corpus, not a share of all research worldwide.
4. **Unclassified stays visible.** OLP1 and OLP3 exclude it from the
   hierarchy, and `docs/phase3/evidence/00_taxonomy/WP1_TAXONOMY_EVIDENCE.md`
   reports its share (25.60% of the published corpus) so the exclusion is
   never a hidden one.

## 5. Reproducing the evidence

Run the three result sets in `sql/10_analytics/09_rollup_cube.sql` as
`PAPERSONAR_REPORTER` and export each result set to the CSV path named in the
file header. The file is marked `-- Deploy: manual`: the analytical layer is
run by a person, never by the deployment client.
