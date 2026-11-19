# Data Quality, Reconciliation, and Publication Gate

## Purpose
Run SQL checks, log results to `PROJECT_AUDIT.DQ_RESULT`, and prevent publication when critical checks fail. Every check has an ID, description, severity, batch ID, layer, observed value, threshold, pass/fail status, query ID if available, and run timestamp.

## Required DQ families
- Completeness: required IDs, title, dates where required, source identifiers.
- Validity: DOI format, date ranges, nonnegative citation counts, controlled values.
- Uniqueness: source observation key, canonical business key, fact grain, one current SCD2 row per business key.
- Integrity: fact-to-dimension orphans = 0; bridge orphans = 0.
- Accuracy/reconciliation: source/manifest/staging/bronze/silver/rejected counts reconcile under documented definitions; DW rows reconcile to silver eligible records.
- Freshness: latest successful source window and time since watermark.
- Volume anomaly: compare counts to prior comparable windows; thresholds configurable.
- Schema drift: new/missing keys logged; critical required-key loss blocks publication.
- Category coverage: proportion categorized vs `Unclassified`.
- Citation behavior: compare source-specific citation counts; never sum across providers as a single count.

## Example integrity check
```sql
-- Purpose: Find fact rows without a matching dimension member.
-- Inputs: Current warehouse model.
-- Outputs: Orphan count for DQ_RESULT.
-- Idempotent: Yes, read-only.
-- Owner: PAPERSONAR_TRANSFORMER.
-- Parameters: BATCH_ID.
-- Cost: Scan cost; scope to affected batch where possible.
SELECT COUNT(*) AS ORPHAN_COUNT
FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT f
LEFT JOIN PAPERSONAR.PROJECT_DW.DIM_OUTPUT_TYPE d
  ON f.OUTPUT_TYPE_KEY = d.OUTPUT_TYPE_KEY
WHERE d.OUTPUT_TYPE_KEY IS NULL;
```
Repeat for every required dimension key and every bridge. Scope to the relevant published or processing batch when possible, but do not omit historical integrity checks from final acceptance.

## Reconciliation contract
Define count meanings carefully:
- `EXTRACTED`: records returned by the source.
- `STAGED`: raw records successfully copied.
- `BRONZE_INSERTED`: new unique observations inserted.
- `BRONZE_DUPLICATE`: observations already present.
- `SILVER_ACCEPTED`: records eligible for canonical processing.
- `REJECTED`: invalid or ambiguous records retained in quarantine.
- `DW_LOADED`: fact rows inserted/updated at declared grain.

Raw counts need not equal canonical output counts because sources overlap and deduplication is expected. Reconciliation must explain each difference rather than require false equality between unrelated grains.

## Critical gate
Publication is blocked if:
- Required source batch is incomplete.
- A critical schema-drift rule fails.
- Fact or bridge orphan count is nonzero.
- Fact grain uniqueness fails.
- More than one current SCD2 row exists per business key.
- Critical reconciliation has unexplained difference.
- Required acceptance checks fail.

Noncritical warnings may publish only if documented policy permits it.

## Report generation
Data Cleaning Report must include raw/staged/accepted/rejected counts, transformations, examples before/after, null handling, duplicate handling, identity-resolution outcomes, and quarantine reasons.
Data Quality Report must include rule inventory, severity, observed results, reconciliation, orphan counts, freshness, category coverage, and publication decision. Both reports must derive from actual audit queries.

## Acceptance
- DQ rules are versioned and logged.
- Orphan count is zero.
- Critical failures block publication.
- Reconciliation differences are explained.
- Reports can be generated from audit tables and actual warehouse results.

## References
- Snowflake queries and joins: https://docs.snowflake.com/en/user-guide/querying-joins
- Snowflake MERGE: https://docs.snowflake.com/en/sql-reference/sql/merge
- Snowflake query history: https://docs.snowflake.com/en/sql-reference/account-usage/query_history
