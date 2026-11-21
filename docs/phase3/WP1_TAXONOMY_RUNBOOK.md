# Phase 3 WP1 — taxonomy expansion runbook

**Branch:** `phase3` · **Status:** code complete, awaiting deployment and
re-categorization in Snowflake.

## 1. Why this work package exists

Phase 2 measured DQ-009 categorization coverage of **3.4% (OpenAlex),
5.5% (arXiv) and 4.1% (Zenodo)** against a 60% target. The cause was not a
bug: `config/taxonomy.yml` v1 contained 37 keyword rules, all of them
software-engineering or AI phrases, while the corpus is general scholarship
(OpenAlex, Crossref, arXiv, DataCite, Zenodo). A title such as "Climate
change and agricultural yield in East Africa" matched nothing and fell into
`unclassified`.

The published corpus already carries curated native taxonomies:

| Source | Native taxonomy in `SLV_SOURCE_OBSERVATION.TOPICS` |
|---|---|
| OpenAlex | topic objects (`name`) |
| Crossref | `subject` strings |
| arXiv | category codes (`cs.SE`, `q-bio.GN`, …) |
| DataCite | subject objects (`subject`) |
| Zenodo | subject strings |

Phase 2 scored those values with the same 37 software-engineering rules and
therefore discarded them.

## 2. What changed

| Change | File | Effect |
|---|---|---|
| Taxonomy contract v2 | `config/taxonomy.yml` | 62 categories in 9 top-level domains (was 22 in 2), 190 weighted rules (was 37), 140 native source mappings (was 0) |
| Generated seed | `sql/04_categorization/01_seed_taxonomy.sql` | now generated from the contract; also populates `REF_TAXONOMY_MAP` |
| Seed generator | `scripts/generate_taxonomy_seed.py` | `python scripts/generate_taxonomy_seed.py` regenerates the seed byte-for-byte |
| Categorization procedure | `sql/04_categorization/02_categorize_batch.sql` | adds the `SOURCE_TAXONOMY` method; native taxonomy matches outrank keyword matches; short keyword patterns now respect token boundaries on native values too |
| Category dimension | `sql/05_dimensions/04_load_dimensions.sql` | `DIM_CATEGORY` is now merged (label, parent and taxonomy version are refreshed), not insert-only |
| Vocabulary mining | `sql/99_tests/04_taxonomy_vocabulary.sql` | read-only queries that measure the native vocabulary and the current coverage |
| Contracts | `tests/sql/test_sql_contracts.py` | seed reproducibility, mapping parity, ranking order, domain coverage |

Ranking order after the change:

1. operator override (`CATEGORY_OVERRIDE`, score 1000);
2. native source taxonomy match (`REF_TAXONOMY_MAP`, score 2 × weight);
3. keyword/topic score (title ×3, native topic ×2, per-rule weight);
4. `unclassified` default.

## 3. Owner actions

### 3.1 Deploy

Pushes to `main` deploy automatically; this branch is `phase3`, so dispatch the
workflow manually:

> Actions → **deploy-ci** → Run workflow → branch `phase3` → input `DEPLOY`

The deploy runs the contract tests first and deploys `sql/**`. The new seed and
the categorization procedure take effect immediately; existing data is not
changed by the deployment itself.

### 3.2 Mine the native vocabulary (before re-categorizing)

Run `sql/99_tests/04_taxonomy_vocabulary.sql` as `PAPERSONAR_ADMIN` and save
the result sets under `docs/phase3/evidence/00_taxonomy/`:

| Block | Question it answers |
|---|---|
| V0 | which source supplies native topics, and how complete is that coverage |
| V1 | which native taxonomy values dominate (the `REF_TAXONOMY_MAP` candidates) |
| V2 | current DQ-009 coverage per source (the "before" number) |
| V3 | current primary-category distribution |
| V4 | most frequent title tokens of unclassified outputs |
| V5 | 200 unclassified titles for rule design |
| V6 | current `REF_TAXONOMY_MAP` coverage |

V1 and V4 decide whether the seeded mappings and rules are sufficient or
whether another iteration is needed. The rules are deliberately broad, so the
expected effect is large; the mining run is what proves it.

### 3.3 Re-categorize the published batches

No source is re-extracted: silver and bronze data are unchanged, only the
categorization, dimensions, facts, DQ and publication stages are re-run for
the batch. Run one batch at a time (the cost plan in
`docs/phase3/PHASE3_PLAN.md` assumes one batch per run):

```sql
-- Set the batch as the active batch (the stage procedures are batch-scoped)
DELETE FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH;
INSERT INTO PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH (BATCH_ID) VALUES ('<BATCH_ID>');

CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('CATEGORIZE');
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('DIMENSIONS');
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('FACTS');
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('DQ');
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('PUBLISH');

-- Release the claim
DELETE FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH;
```

Batches to re-run (from the Phase 2 closeout evidence):

| Batch | Source | Records |
|---|---|---|
| `BATCH_07D9668D4CBED88D815D30CA` | OPENALEX | 168,725 |
| `BATCH_B51983B70B26023F22201AE2` | CROSSREF | 20,000 |
| `BATCH_DAB12A7209208BE375D89C0B` | CROSSREF | 30,000 |
| `BATCH_3DF8101D66B0797A217FD877` | ARXIV | 15,505 |
| `BATCH_A75F9C61B9BF73B40CBC8C54` | ZENODO | 54,750 |

The stages are idempotent: the category bridge rows of the touched outputs are
deleted and rebuilt, `DQ_RESULT` rows for the batch are replaced, and
`PUBLISHED_BATCH` is merged, so the batch stays published.

### 3.4 Measure the result

```sql
SELECT batch.BATCH_ID,
       batch.SOURCE_NAME,
       COUNT(DISTINCT fact.OUTPUT_SK) AS OUTPUTS,
       COUNT(DISTINCT IFF(bridge.CATEGORY_KEY <> 'unclassified', fact.OUTPUT_SK, NULL)) AS CATEGORIZED,
       ROUND(
         COUNT(DISTINCT IFF(bridge.CATEGORY_KEY <> 'unclassified', fact.OUTPUT_SK, NULL))
         / NULLIF(COUNT(DISTINCT fact.OUTPUT_SK), 0), 4) AS COVERAGE_RATIO
FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
JOIN PAPERSONAR.PROJECT_AUDIT.BATCH batch
  ON batch.BATCH_ID = fact.LAST_BATCH_ID
LEFT JOIN PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
  ON bridge.OUTPUT_SK = fact.OUTPUT_SK AND bridge.IS_PRIMARY
GROUP BY batch.BATCH_ID, batch.SOURCE_NAME
ORDER BY OUTPUTS DESC;
```

Save the result to `docs/phase3/evidence/00_taxonomy/DQ009_before_after.csv`
together with the V2 "before" export.

### 3.5 Verify the gate

```sql
SELECT batch.BATCH_ID, batch.SOURCE_NAME, rule.RULE_ID, rule.SEVERITY, rule.STATUS,
       rule.OBSERVED_VALUE, rule.THRESHOLD_VALUE
FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT rule
JOIN PAPERSONAR.PROJECT_AUDIT.BATCH batch ON batch.BATCH_ID = rule.BATCH_ID
WHERE rule.RULE_ID = 'DQ-009'
ORDER BY batch.BATCH_ID;
```

DQ-009 must remain a WARNING: a coverage below 60% is visible, but it must
never block publication.

## 4. Exit criteria

| Criterion | Target |
|---|---|
| DQ-009 coverage per published batch | ≥ 0.60, or a measured ceiling that is documented with its reason |
| No CRITICAL DQ failure after re-categorization | 0 (DQ-012 especially: exactly one primary category per output) |
| `DIM_CATEGORY` rows | 62 categories + the unknown member, with `PARENT_KEY` populated from the v2 tree |
| Every published batch still `PUBLISHED` | yes, with an updated `PUBLISHED_AT` |
| Reproducibility | `python scripts/generate_taxonomy_seed.py` produces no diff |

If the measured ceiling stays below 60%, the fallback recorded in the Phase 3
plan applies: document the ceiling with the evidence and change the threshold
in `config/quality_rules.yml` **with an explicit owner decision**, never
silently.

## 5. Rollback

The taxonomy version lives in the reference tables, so a rollback is a data
change, not a code change:

```sql
-- Disable the v2 taxonomy rules and mappings (keeps the audit trail)
UPDATE PAPERSONAR.PROJECT_REF.REF_CATEGORY_KEYWORD SET IS_ACTIVE = FALSE WHERE RULE_VERSION = 'v2';
UPDATE PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP SET IS_ACTIVE = FALSE WHERE MAPPING_VERSION = 'v2';
```

Then re-run §3.3 for the affected batches. The code change itself is reverted
with `git revert` on the `phase3` branch.

## 6. Cost

The re-categorization runs the CATEGORIZE stage over the outputs of each batch
(about 280,000 outputs in total) plus dimension and fact upserts on
`WH_PAPERSONAR_ELT` (X-Small, auto-suspend 60 s). One batch per run keeps the
peak inside the plan's cost envelope; the mining queries V4 and V5 are the only
full-corpus scans and are also run once, outside peak time.
