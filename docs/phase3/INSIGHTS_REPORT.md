# PaperSonar Insights Report — Phase 3

**Date:** 2026-11-22 · **Corpus:** 296,299 published outputs, five sources, one Snowflake account
**Every number below is traceable to a file in `docs/phase3/evidence/` and to the SQL that produced it.**

---

## 1. Executive summary

1. **The taxonomy was the binding constraint, and it is now fixed.** Categorization
   coverage of the published corpus moved from **1.92% to 74.40%** without
   inventing a single measure. OpenAlex reached 98.30% and arXiv 100.00%;
   Crossref (35.30%) and Zenodo (34.33%) are limited by what those sources
   actually carry, not by the contract.
2. **The recent-year corpus is too small to rank growth.** 2023 holds 389
   published works and 2025 holds 1,053. Every growth row therefore trips
   the 30-work suppression threshold — the guard worked, and the honest
   answer is that this corpus cannot rank topic growth yet.
3. **Topic overlap inside the corpus is sparse but structured.** Only three
   topic pairs clear the 100-parent / 5-joint thresholds, led by
   `ai-ml × health-sciences` (10 joint works, 9.6% of the smaller parent).
4. **The counting method changes the leaderboard.** Under fractional
   allocation instead of primary-topic counting, botany falls from rank 1 to
   rank 4 and clinical medicine from 3 to 9, while physics rises to 1.
   A recommendation that does not name its counting rule is not a
   recommendation.
5. **Institutional concentration is a metadata artifact, not a finding.**
   Q08 reports 99.24% top-five concentration for physics in 2026 — and 100%
   of that credit belongs to a single OpenAlex institution identifier
   attached to 49,203 of the works. One identifier owns **56.9% of all
   institution credit in the corpus**.
6. **Open access looks high, and the unknown share is large.** 90.42% of
   works with a known access status are open access, but 39,183 works
   (17.7% of the classified cohort) have an unknown status and are excluded
   from the ratio rather than assumed to be closed.

## 2. What the corpus is, and what it is not

| Property | Value | Evidence |
|---|---|---|
| Published outputs | 296,299 (one row per canonical output, 0 duplicate DOIs) | `res/G1.csv`, `res/G3.csv` |
| Classified outputs | 220,501 (74.40%) | `DQ009_before_after.csv` |
| Unclassified outputs | 75,798 (25.60%) | `res/F3.csv` |
| Categories in use | 63 of 67 | `res/F3.csv` |
| Citation observations | 265,968 across the snapshot fact | `res/D1.csv` |
| Reference edges | 2,557,842, of which **94,912** have both endpoints inside the corpus | `res/i4.csv`, `res/i5.csv` |
| Outputs with a resolved institution | 101,257, all outside 2012–2025 | `res/i3.csv` |

**The corpus is bimodal in time.** 78,226 institution-linked outputs are
stamped 2026 (the current extraction windows), a long tail sits before 2009,
and the 2021–2025 window that most topic questions need holds only a few
thousand works. Every year-scoped result in this report must be read with
that shape in mind, and every denominator is printed next to its ratio.

## 3. Finding 1 — coverage is now a source property, not a contract property

| Source | Outputs | Before (v2) | After (v3) | Why it differs |
|---|---:|---:|---:|---|
| OpenAlex | 168,577 | 3.40% | **98.30%** | four structured native values (topic, domain, subfield, field) are read per work |
| arXiv | 15,503 | 5.46% | **100.00%** | all 154 category codes are mapped explicitly |
| Crossref | 78,495 | 0.31% | **35.30%** | Crossref records in this corpus carry **no subject field at all** (`res/V0.csv`: 49,093 records, 0 subjects) |
| Zenodo | 33,724 | 4.08% | **34.33%** | subjects are free-text organism and instrument names, not fields |

The v2 failure mode is gone: `'cultural'` no longer fires inside
"agricultural and biological sciences", and `arts-and-culture` fell from
175,415 outputs to 282. The distribution is now led by botany (56,209) and
physics (52,200) — the actual shape of the corpus rather than a substring
artifact.

## 4. Finding 2 — growth questions cannot be answered yet

| Topic | Works 2023 | Works 2025 | Share change | Status |
|---|---:|---:|---:|---|
| ai-ml | 8 | 69 | +4.50 pp | suppressed (2023 endpoint < 30) |
| clinical-medicine | 2 | 40 | +3.28 pp | suppressed |
| physics | 4 | 37 | +2.49 pp | suppressed |

The corpus itself is the limit: 389 works in 2023 and 1,053 in 2025. The
ai-ml direction is visibly rising inside that window, but the Phase 1 rule
("suppress growth rankings when either endpoint has fewer than 30 works")
exists precisely to stop a 8-to-69 ratio from being presented as a growth
rate. The rule is kept, the numbers are published, and the conclusion is
"not yet reportable".

## 5. Finding 3 — topic overlap is sparse and worth watching

| Pair | Parent A | Parent B | Joint works | Joint / smaller parent |
|---|---:|---:|---:|---:|
| ai-ml × health-sciences | 127 | 104 | 10 | 9.62% |
| health-sciences × law | 104 | 226 | 9 | 8.65% |
| ai-ml × physics | 127 | 115 | 9 | 7.83% |

These three pairs are the only ones that clear the Phase 1 thresholds. They
describe works that the taxonomy genuinely places in two fields: applied
machine learning with clinical work, health law, and AI with physics. On a
corpus this young in its taxonomy coverage, a pair list this short is the
correct answer, and the suppression rule is what makes it trustworthy.

## 6. Finding 4 — the counting rule decides the leaderboard

| Topic | Primary count (rank) | Fractional count (rank) | Shift |
|---|---:|---:|---:|
| botany | 57,419 (1) | 15,501.9 (4) | −3 |
| physics | 56,353 (2) | 25,854.3 (1) | +1 |
| clinical-medicine | 17,190 (3) | 10,538.3 (9) | −6 |
| ai-ml | 12,025 (4) | 6,424.8 (11) | −7 |
| ecology | 5,625 (6) | 16,016.5 (3) | +3 |

Botany leads the corpus by primary topic because botanical works carry
botany as their strongest label, but it distributes its works across several
categories more often than physics does: under fractional allocation
ecology (16,016.5) overtakes both botany and clinical medicine, and ai-ml
falls from 4th to 11th. A reader told only "botany is the largest topic"
would reach a different conclusion from one told "botany is the largest
topic when each work is counted once". The Q13 evidence makes the difference
visible instead of hiding it.

## 7. Finding 5 — the concentration metric is dominated by one identifier

Q08 reports the five largest institutions' share of institutional credit
inside a topic and year:

| Topic | Year | Works | Top-5 share | Largest single institution |
|---|---|---:|---:|---|
| physics | 2026 | 49,203 | **99.24%** | National Institute for Fusion Science (49,203 works, `openalex:I4210108322`) |
| ecology | 2026 | 1,056 | 58.07% | University of Piura (1,056 works) |

Across the whole corpus that one OpenAlex institution identifier holds
**56.9% of all institutional credit** (49,378.5 of 86,767.9), and the next
institution holds 1.2%. This is an affiliation artifact in the source
metadata — a bulk institution field attached to a large series of works — and
not a statement about physics. The practical consequence is a rule for the
BI layer: the community page must show an institution's work count next to
its credit, and the concentration card must not be read without it.

## 8. Finding 6 — access status is high where it is known, and often unknown

| Measure | Value |
|---|---:|
| Classified cohort with a citation snapshot | 220,501 (100.00%, 0 missing) |
| Works with a known access status | 181,318 |
| Open access among known-status works | 163,951 (**90.42%**) |
| Works with an unknown access status | 39,183 (17.7% of the cohort, excluded from the ratio) |

Citation observation is complete for the classified cohort, so the citation
questions are limited by cohort size rather than by missing data. Access
status is the opposite: the 17.7% unknown share is reported next to the
ratio rather than folded into it.

## 9. Finding 7 — the citation-bearing cohorts are historical

Among cohorts with at least 30 works, the highest median citation impact
sits in older, small cohorts:

| Topic | Year | Type | Cohort | Median citations | Max |
|---|---|---|---:|---:|---:|
| neuroscience | 2002 | journal-article | 35 | 676 | 15,665 |
| neuroscience | 2004 | journal-article | 48 | 419 | 6,562 |
| management | 2002 | journal-article | 38 | 400 | 2,970 |
| climate-science | 2007 | journal-article | 30 | 375 | 4,893 |
| statistics | 2008 | journal-article | 45 | 366 | 2,971 |

These are small cohorts of older work, which is what the corpus contains.
They are reported with their cohort size, never as a ranking of research
quality.

## 10. What this project cannot claim

1. **No growth ranking.** The recent-year corpus is too small, and the
   suppression rule blocks the ranking that the raw ratios would suggest.
2. **No crossref or Zenodo coverage claim above ~35%.** The sources do not
   carry the metadata; the contract cannot invent it.
3. **No institution-based conclusion from the concentration metric.** One
   source identifier dominates it.
4. **No global research claim.** Every number describes the retained corpus
   of this account, at the observation dates printed in the evidence files.
5. **No citation flow between topics outside the 94,912 induced edges.** The
   2.46 million other reference rows point outside the corpus and are not
   counted as flow.

## 11. Evidence index

| Claim | File |
|---|---|
| Coverage before and after | `docs/phase3/evidence/00_taxonomy/DQ009_before_after.csv` |
| Taxonomy evidence and defects fixed | `docs/phase3/evidence/00_taxonomy/WP1_TAXONOMY_EVIDENCE.md` |
| Q01–Q14 results | `docs/phase3/evidence/01_queries/Q01…Q14*.csv` |
| ROLLUP / CUBE / GROUPING SETS | `docs/phase3/evidence/02_olap/OLP1…OLP3*.csv` |
| Optimization before/after | `docs/phase3/evidence/03_optimization/` |
| OLAP method | `docs/phase3/OLAP_NOTES.md` |
| Question-to-code mapping | `docs/phase3/METRIC_CATALOGUE.md`, `docs/phase3/COURSE_MAPPING.md` |
| Cost and free-only policy | `docs/phase3/COST_LOG.md` |
