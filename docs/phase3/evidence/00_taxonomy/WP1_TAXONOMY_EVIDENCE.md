# WP1 Evidence — Taxonomy Expansion and Re-categorization (v2 → v3)

**Date:** 2026-11-22 · **Branch:** `phase3` · **Account:** NI15271 / `PAPERSONAR`
**Contract:** `config/taxonomy.yml` v3 (67 categories, 782 rules, 261 native mappings)
**Live evidence exports:** `res/V0.csv`–`res/V6.csv` (mining), `res/F1.csv`–`res/F4.3.csv` (post-change measurement)

---

## 1. Why the work package was needed

Phase 2 closed with a green DQ gate but a useless analytical spine: DQ-009
categorized coverage was 3.4% (OpenAlex), 0.3% (Crossref), 4.1% (Zenodo) and
5.5% (arXiv) against a 60% target. The cause was not a pipeline defect. The v1
contract held 37 keyword rules, all of them software-engineering or AI
phrases, while the corpus is general scholarship. The published corpus already
carried curated native taxonomies (OpenAlex topic objects, Crossref `subject`,
arXiv category codes, Zenodo subject strings) and v1 scored those values with
the same 37 rules, so every native value fell through to `unclassified`.

## 2. What the mining run proved

The V0–V6 vocabulary mining pack (`sql/99_tests/04_taxonomy_vocabulary.sql`,
executed 2026-11-22) produced three findings that drove the v3 contract.

| Finding | Evidence | Consequence in v3 |
|---|---|---|
| OpenAlex topics are JSON objects, so the topic token was the whole object | `V1.csv` values begin with `{"display_name":` | the procedure now reads the topic name, the OpenAlex domain, the subfield and the field as four separate candidate values |
| Substring matching mixed lookalike words | `cultural` fired inside "agricultural and biological sciences"; `art` fired inside "plant science" | every pattern is matched on word boundaries (patterns of four characters or fewer match a whole word, longer patterns match a word-initial stem) |
| Crossref carries no subject field at all | `V0.csv`: `CROSSREF,49093,0,0.0000` | Crossref classification depends on title and keyword vocabulary only, which caps its measurable coverage |

## 3. Coverage before and after

Source: `DQ009_before_after.csv` (same measure on the same published corpus,
`DQ-009` ratio = categorized outputs ÷ outputs touched by the batch).

| Source | Outputs | Before (v2) | After (v3) | Delta | Categorized | Unclassified |
|---|---:|---:|---:|---:|---:|---:|
| OpenAlex | 168,577 | 3.40% | **98.30%** | +94.90 pp | 165,714 | 2,863 |
| Crossref | 78,495 | 0.31% | **35.30%** | +34.99 pp | 27,708 | 50,787 |
| Zenodo | 33,724 | 4.08% | **34.33%** | +30.25 pp | 11,576 | 22,148 |
| arXiv | 15,503 | 5.46% | **100.00%** | +94.54 pp | 15,503 | 0 |
| **All published** | **296,299** | 1.92% | **74.40%** | +72.48 pp | 220,501 | 75,798 |

Per-batch DQ-009 gate result after the change (`res/F1.csv`):

| Batch | Source | Status | Coverage | Threshold |
|---|---|---|---:|---:|
| `BATCH_3DF8101D66B0797A217FD877` | ARXIV | PASS | 1.000000 | 0.60 |
| `BATCH_07D9668D4CBED88D815D30CA` | OPENALEX | PASS | 0.983020 | 0.60 |
| `BATCH_DAB12A7209208BE375D89C0B` | CROSSREF | FAIL (WARNING) | 0.359883 | 0.60 |
| `BATCH_A75F9C61B9BF73B40CBC8C54` | ZENODO | FAIL (WARNING) | 0.340885 | 0.60 |
| `BATCH_B51983B70B26023F22201AE2` | CROSSREF | FAIL (WARNING) | 0.329450 | 0.60 |

DQ-009 is registered as a **WARNING** rule, so a coverage below 60% is visible
but does not block publication. The two Crossref batches and Zenodo fail the
warning on purpose: the ceiling is a property of the source, not of the
contract. Crossref records in this corpus carry no subject array at all
(`V0.csv`), so classification can only use the title and the keyword
vocabulary; Zenodo subjects are free-text organism and instrument names that
mostly do not name a research field.

## 4. The false positive is gone

The v2 run assigned 175,415 outputs to `arts-and-culture` because the pattern
`cultural` matched inside "agricultural and biological sciences". After the
boundary-matching change the primary-category distribution (`res/F3.csv`) is:

| Category | Method | Outputs |
|---|---|---:|
| unclassified | DEFAULT | 75,798 |
| botany | SOURCE_TAXONOMY | 56,209 |
| physics | SOURCE_TAXONOMY | 52,200 |
| ai-ml | SOURCE_TAXONOMY | 11,196 |
| clinical-medicine | SOURCE_TAXONOMY | 11,116 |
| ecology | SOURCE_TAXONOMY | 4,204 |
| computer-science | SOURCE_TAXONOMY | 3,136 |
| genetics | SOURCE_TAXONOMY | 2,867 |

63 categories are populated across 105 category/method combinations; the
method mix is 181,242 `SOURCE_TAXONOMY`, 39,259 `KEYWORD` and 75,798
`DEFAULT` assignments over 296,299 outputs.

## 5. Grain defects found by the re-run and fixed

The first re-categorization run exposed two defects that the Phase 2
acceptance pack did not cover. Both are fixed in the branch and both are now
guarded by automated checks.

| Defect | Symptom | Fix | Guard |
|---|---|---|---|
| The same category reached by two methods was written twice, so the category bridge held 412,145 rows on a (output, category) grain that the bridge declares as unique | `F4.2.csv` = 412,145 duplicate bridge rows | `sql/04_categorization/02_categorize_batch.sql` keeps one row per output and category, choosing the strongest method (override → native taxonomy → keyword) before the category rank is assigned | `DQ-004` now also checks the category bridge grain, and `tests/sql/test_sql_contracts.py::test_categorization_writes_one_row_per_output_and_category` asserts the semantics |
| The DQ-004 bridge duplicate check was global, so each batch was judged on duplicates still sitting in other batches' rows | four batches ended `FAILED` with `BLOCKED_DQ` although their own rows were clean | the bridge check is scoped to the rows the batch wrote (`bridge.BATCH_ID = :batch_id`) | the same rule, re-run per batch |

## 6. Post-change DQ state

| Check | Result | Evidence |
|---|---|---|
| Outputs without exactly one primary category | **0** | `res/F4.1.csv` |
| Duplicate rows in `BRIDGE_OUTPUT_TOPIC_CATEGORY` | **0** | `res/F4.2.csv` |
| Critical DQ failures on the published batches | **0** | `res/F4.3.csv` |
| Unclassified share of the published corpus | 25.60% (75,798 of 296,299) | `res/F3.csv` |

## 7. Corpus reconciliation

The Phase 2 closeout snapshot (`docs/phase2/evidence/2026-11-22-live-verification.md`,
2026-11-21 08:41 UTC) recorded 264,916 rows in `FACT_RESEARCH_OUTPUT` with
three batches published. The current corpus holds **296,299** rows
(296,299 distinct output keys, no duplicate grain) with five batches
published: arXiv and Zenodo were published after the closeout snapshot, and
the fact loader attributes each row to the batch that last wrote it, so a
batch-level attribution shifts when a later batch re-writes a shared output.
The live per-batch composition is the authoritative figure for every Phase 3
query and is re-measured before each evidence export.

## 8. Residual gaps (declared, not hidden)

1. **Crossref and Zenodo stay below the 60% warning threshold.** The cause is
   measured, not inferred: no subject field in Crossref, free-text organism
   subjects in Zenodo. Raising the contract further would map those outputs to
   categories the source does not support.
2. **25.60% of the published corpus is unclassified.** For OpenAlex the
   residual is 1.7%; for Crossref 64.7%; for Zenodo 65.7%. Those outputs are
   reported in the coverage views instead of being forced into a category.
3. **The orphan batch `BATCH_70CEE97747ED6A70D3E40411`** (Crossref, four file
   mismatches) is still open in `EXTRACTING` and is excluded from every
   published figure.
4. **DataCite** (`BATCH_EB4210A9204AF7243A942647`) is still unpublished, so no
   DataCite output contributes to the coverage numbers above.
