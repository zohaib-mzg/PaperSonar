# Phase 2 dimensional surrogate keys

Migration `005_dimensional_surrogate_keys.sql` adds numeric surrogate keys while
preserving the existing business keys and their role in lineage and idempotent
MERGE operations. It creates `PROJECT_DW.DIMENSION_KEY_MAP`, whose durable
identity is `(DIMENSION_NAME, BUSINESS_KEY)` and whose numeric
`SURROGATE_KEY` is assigned from a Snowflake sequence.

The migration adds `*_SK` columns to all eight dimensions, the source crosswalk,
the facts, and the bridges, then backfills rows by joining each retained
business key to the mapping. Publication and snapshot facts retain date/status
business keys alongside their numeric references. Missing publication dates
use the existing unknown date member (`DATE_KEY = 0`). Citation `CITED_WORK_SK`
is populated when a referenced work resolves to a canonical work; unresolved
citation edges remain unresolved and are not assigned a fabricated target.

New dimension rows are handled by `WarehouseLoader` after the ordinary
business-key upsert: it creates missing map entries and fills null `*_SK`
columns. The operation is repeatable. The workflow concurrency lock prevents
overlapping scheduled runs, but the map uniqueness checks remain necessary
because Snowflake standard-table primary keys are informational constraints.

## Apply and verify

The migration is part of the normal ordered migration runner. It has only been
reviewed and exercised through the mock migration/test path in this checkout;
it has **not** been applied to a live Snowflake account. Do not treat the
backfill or runtime SQL as live-validated until the account owner applies it
and saves the read-only results from `PHASE2_EVIDENCE_QUERIES.sql` query 02 and
`warehouse/sql/integrity_checks.sql` check 01b. All null and duplicate counts
must be zero. Live row counts and course-scale acceptance remain unmeasured.

No table is dropped and no existing natural/source key is rewritten. The
additional numeric references are additive and may be rolled forward by
reapplying the migration after an interrupted attempt.
