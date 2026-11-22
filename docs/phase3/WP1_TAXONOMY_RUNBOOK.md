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
| Taxonomy contract v3 | `config/taxonomy.yml` | 67 categories in 10 top-level domains (was 22 in 2), 782 weighted rules (was 37), 261 native source mappings (was 0) |
| Generated seed | `sql/04_categorization/01_seed_taxonomy.sql` | now generated from the contract; also populates `REF_TAXONOMY_MAP`; deactivates every row whose version is not the current one |
| Seed generator | `scripts/generate_taxonomy_seed.py` | `python scripts/generate_taxonomy_seed.py` regenerates the seed byte-for-byte |
| Categorization procedure | `sql/04_categorization/02_categorize_batch.sql` | reads native taxonomy values as structured parts (topic name, OpenAlex domain/subfield/field), matches on word boundaries, and ranks the most specific native value first |
| Category dimension | `sql/05_dimensions/04_load_dimensions.sql` | `DIM_CATEGORY` is now merged (label, parent and taxonomy version are refreshed), not insert-only |
| Vocabulary mining | `sql/99_tests/04_taxonomy_vocabulary.sql` | read-only queries that measure the native vocabulary and the current coverage |
| Contracts | `tests/sql/test_sql_contracts.py` | seed reproducibility, mapping parity, ranking order, domain coverage, version deactivation, boundary semantics |

Ranking order after the change:

1. operator override (`CATEGORY_OVERRIDE`, score 1000);
2. native source taxonomy match (`REF_TAXONOMY_MAP`, score 2 × weight + specificity);
3. keyword/topic score (title ×3, native topic ×2, per-rule weight);
4. `unclassified` default.

### 2.1 What the v2 mining run proved

The V0–V6 run on 2026-11-22 (saved under `res/`) produced three findings that
drove the v3 contract:

| Finding | Evidence | Consequence in v3 |
|---|---|---|
| OpenAlex topics are JSON objects, so the topic token was the whole object | V1 values start with `{"display_name":` | the procedure now reads the topic name, the OpenAlex domain, the subfield and the field as four separate candidate values |
| Substring matching mixed lookalike words | `cultural` fired on `agricultural and biological sciences`, `art` fired on `plant science` | every pattern is now a whole word or phrase and matches on a word boundary; the v2 stems (`ecolog`, `astron`, `pharmac`) were expanded into their word forms |
| Crossref carries no subject field at all | V0: `CROSSREF, 49093, 0, 0.0000` | Crossref can only be classified from its title, so the v3 title rules were extended with the chemistry, materials and medicine vocabulary found in the sampled Crossref titles (V5) |

Measured against the mined corpus, v3 raises the expected coverage of the
topic-based sources from 12% (Zenodo), 78% (arXiv) and 98% (OpenAlex, with
the misclassifications) to **100% (OpenAlex), 100% (arXiv) and 23.5% (Zenodo)**;
the title rules reach a further ~18% of the currently unclassified outputs.
Crossref has no native taxonomy, so its ceiling is set by title coverage.

## 3. Owner actions

### 3.1 Deploy

Pushes to `main` deploy automatically; this branch is `phase3`, so dispatch the
workflow manually:

> Actions → **deploy-ci** → Run workflow → branch `phase3` → input `DEPLOY`

The deploy runs the contract tests first and deploys `sql/**`. The new seed and
the categorization procedure take effect immediately; existing data is not
changed by the deployment itself.

After the deployment, verify the seed landed:

```sql
SELECT 'categories' AS OBJECT, COUNT(*) AS ROWS FROM PAPERSONAR.PROJECT_REF.REF_CATEGORY WHERE IS_ACTIVE
UNION ALL SELECT 'rules', COUNT(*) FROM PAPERSONAR.PROJECT_REF.REF_CATEGORY_KEYWORD WHERE IS_ACTIVE
UNION ALL SELECT 'mappings', COUNT(*) FROM PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP WHERE IS_ACTIVE
UNION ALL SELECT 'stale_rules', COUNT(*) FROM PAPERSONAR.PROJECT_REF.REF_CATEGORY_KEYWORD WHERE NOT IS_ACTIVE
UNION ALL SELECT 'stale_mappings', COUNT(*) FROM PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP WHERE NOT IS_ACTIVE;
```

Expected: 67 categories, 782 active rules, 261 active mappings, and the stale
v2 rows inactive (their count is however many v2 rows the new version did not
rewrite, normally 0 because the rule identifiers are reused).

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
`docs/phase3/PHASE3_PLAN.md` assumes one batch per run), starting with the
smallest batch so that a broken stage is found on 15,505 rows instead of
168,725.

Order to use: **arXiv → Crossref (20 k) → Crossref (30 k) → Zenodo →
OpenAlex**.

```sql
-- 0. Session setup
USE ROLE PAPERSONAR_ADMIN;
USE WAREHOUSE WH_PAPERSONAR_ELT;
```

The claim is released at the end of every batch, so step 1 has to be repeated
for each batch. A stage that returns `NO_BATCH` means the control table was
empty, not that the stage failed.

```sql
-- 1. Claim the batch by hand. SP_CLAIM_BATCH only picks STATUS = 'LOADED'
--    batches, and these five are already PUBLISHED, so the control table is
--    set directly. The BATCH row is moved to PROCESSING for the audit trail.
DELETE FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH;
INSERT INTO PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH (BATCH_ID, CLAIMED_AT)
VALUES ('BATCH_3DF8101D66B0797A217FD877', CURRENT_TIMESTAMP());
UPDATE PAPERSONAR.PROJECT_AUDIT.BATCH
   SET STATUS = 'PROCESSING', UPDATED_AT = CURRENT_TIMESTAMP()
 WHERE BATCH_ID = 'BATCH_3DF8101D66B0797A217FD877';
```

```sql
-- 2. Run the five stages in order. Each CALL returns its status and writes a
--    RUN_LOG row; a stage that raises leaves the failure in RUN_LOG and in
--    BATCH.ERROR_SUMMARY.
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('CATEGORIZE');   -- returns CATEGORIZED:<n>
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('DIMENSIONS');   -- returns SUCCEEDED
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('FACTS');        -- returns SUCCEEDED
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('DQ');           -- returns SUCCEEDED
CALL PAPERSONAR.PROJECT_AUDIT.SP_RUN_STAGE('PUBLISH');      -- returns SUCCEEDED
```

`DIMENSIONS` must run before `FACTS`: the category bridge is written by the
facts stage and joins `DIM_CATEGORY`, which is where the four new v3
categories (`botany`, `entomology`, `formal-methods`, `research-methods`) are
created. `PUBLISH` returns `BLOCKED_DQ` and sets the batch to `FAILED` if any
CRITICAL DQ rule failed, and `BLOCKED_INCOMPLETE_DQ` if the DQ stage did not
produce one result per active rule.

```sql
-- 3. Check the categorization before publishing it (optional but cheap:
--    read-only on the staging table)
SELECT COUNT(*) AS OUTPUTS,
       COUNT_IF(c.CATEGORY_KEY <> 'unclassified') AS CATEGORIZED,
       ROUND(COUNT_IF(c.CATEGORY_KEY <> 'unclassified') / NULLIF(COUNT(*), 0), 4) AS COVERAGE
FROM PAPERSONAR.PROJECT_STAGING.STG_OUTPUT_CATEGORY c
WHERE c.BATCH_ID = 'BATCH_3DF8101D66B0797A217FD877' AND c.IS_PRIMARY;

SELECT c.CATEGORY_KEY, c.METHOD, COUNT(*) AS OUTPUTS
FROM PAPERSONAR.PROJECT_STAGING.STG_OUTPUT_CATEGORY c
WHERE c.BATCH_ID = 'BATCH_3DF8101D66B0797A217FD877' AND c.IS_PRIMARY
GROUP BY c.CATEGORY_KEY, c.METHOD
ORDER BY OUTPUTS DESC;
```

```sql
-- 4. Release the claim (mandatory: the next batch needs to claim again)
DELETE FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH;
```

**If a stage fails:** `SP_RUN_STAGE` re-raises the error, writes the failure to
`RUN_LOG` and to `BATCH.ERROR_SUMMARY`, and the batch stays unpublished until
the stage succeeds. A failed `CATEGORIZE` leaves `STG_OUTPUT_CATEGORY` empty
for that batch, which makes DQ-012 fail as CRITICAL and blocks the
publication; re-running the five stages repairs it, because the stages rebuild
the staging rows, the bridge rows, the DQ results and the publication row in
that order.

Batches to re-run (from the Phase 2 closeout evidence):

| Order | Batch | Source | Records |
|---|---|---|---|
| 1 | `BATCH_3DF8101D66B0797A217FD877` | ARXIV | 15,505 |
| 2 | `BATCH_B51983B70B26023F22201AE2` | CROSSREF | 20,000 |
| 3 | `BATCH_DAB12A7209208BE375D89C0B` | CROSSREF | 30,000 |
| 4 | `BATCH_A75F9C61B9BF73B40CBC8C54` | ZENODO | 54,750 |
| 5 | `BATCH_07D9668D4CBED88D815D30CA` | OPENALEX | 168,725 |

The stages are idempotent: the category bridge rows of the touched outputs are
deleted and rebuilt, `DQ_RESULT` rows for the batch are replaced, and
`PUBLISHED_BATCH` is merged, so the batch stays published. `FACT_RESEARCH_OUTPUT`
is merged on the output surrogate key and keeps `LAST_BATCH_ID` equal to the
same batch, so the reporting views stay complete.

### 3.4 Measure the result

Run this after every batch, and once more after the last one:

```sql
-- a) The DQ-009 gate result per batch (the "after" number)
SELECT batch.BATCH_ID,
       batch.SOURCE_NAME,
       result.STATUS,
       result.OBSERVED_VALUE AS COVERAGE_RATIO,
       result.THRESHOLD_VALUE AS THRESHOLD,
       result.CHECKED_AT
FROM PAPERSONAR.PROJECT_AUDIT.DQ_RESULT result
JOIN PAPERSONAR.PROJECT_AUDIT.BATCH batch
  ON batch.BATCH_ID = result.BATCH_ID
WHERE result.RULE_ID = 'DQ-009'
ORDER BY batch.SOURCE_NAME, batch.BATCH_ID;
```

```sql
-- b) Coverage per source over the published corpus (same shape as the V2
--    "before" export, so the two can be put in one CSV)
SELECT batch.SOURCE_NAME,
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
GROUP BY batch.SOURCE_NAME
ORDER BY OUTPUTS DESC;
```

```sql
-- c) The new primary-category distribution. The v2 run put 175,415 topic
--    occurrences into arts-and-culture because "cultural" matched inside
--    "agricultural and biological sciences"; that false positive must be gone.
SELECT bridge.CATEGORY_KEY,
       category.LABEL,
       bridge.METHOD,
       COUNT(*) AS OUTPUTS
FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
JOIN PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  ON fact.OUTPUT_SK = bridge.OUTPUT_SK
JOIN PAPERSONAR.PROJECT_DW.DIM_CATEGORY category
  ON category.CATEGORY_SK = bridge.CATEGORY_SK
WHERE bridge.IS_PRIMARY
  AND EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    WHERE published.BATCH_ID = fact.LAST_BATCH_ID
  )
GROUP BY bridge.CATEGORY_KEY, category.LABEL, bridge.METHOD
ORDER BY OUTPUTS DESC;
```

```sql
-- d) Integrity: exactly one primary category per output, no duplicate bridge
--    rows, every batch still published
SELECT COUNT(*) AS OUTPUTS_WITHOUT_EXACTLY_ONE_PRIMARY
FROM (
  SELECT fact.OUTPUT_SK,
         COUNT(IFF(bridge.IS_PRIMARY, 1, NULL)) AS PRIMARY_COUNT
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  LEFT JOIN PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
    ON bridge.OUTPUT_SK = fact.OUTPUT_SK
  GROUP BY fact.OUTPUT_SK
) counts
WHERE counts.PRIMARY_COUNT <> 1;

SELECT COUNT(*) AS DUPLICATE_BRIDGE_ROWS
FROM (
  SELECT OUTPUT_SK, CATEGORY_KEY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY
  GROUP BY OUTPUT_SK, CATEGORY_KEY
  HAVING COUNT(*) > 1
) duplicates;

SELECT b.BATCH_ID, b.SOURCE_NAME, b.STATUS, p.PUBLISHED_AT
FROM PAPERSONAR.PROJECT_AUDIT.BATCH b
LEFT JOIN PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH p ON p.BATCH_ID = b.BATCH_ID
WHERE b.BATCH_ID IN (
  'BATCH_07D9668D4CBED88D815D30CA', 'BATCH_B51983B70B26023F22201AE2',
  'BATCH_DAB12A7209208BE375D89C0B', 'BATCH_3DF8101D66B0797A217FD877',
  'BATCH_A75F9C61B9BF73B40CBC8C54'
)
ORDER BY b.SOURCE_NAME;
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
| `DIM_CATEGORY` rows | 67 categories + the unknown member, with `PARENT_KEY` populated from the v3 tree |
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
-- Disable the v3 taxonomy rules and mappings (keeps the audit trail)
UPDATE PAPERSONAR.PROJECT_REF.REF_CATEGORY_KEYWORD SET IS_ACTIVE = FALSE WHERE RULE_VERSION = 'v3';
UPDATE PAPERSONAR.PROJECT_REF.REF_TAXONOMY_MAP SET IS_ACTIVE = FALSE WHERE MAPPING_VERSION = 'v3';
```

Then re-run §3.3 for the affected batches. The code change itself is reverted
with `git revert` on the `phase3` branch.

## 6. Cost

The re-categorization runs the CATEGORIZE stage over the outputs of each batch
(about 280,000 outputs in total) plus dimension and fact upserts on
`WH_PAPERSONAR_ELT` (X-Small, auto-suspend 60 s). One batch per run keeps the
peak inside the plan's cost envelope; the mining queries V4 and V5 are the only
full-corpus scans and are also run once, outside peak time.
