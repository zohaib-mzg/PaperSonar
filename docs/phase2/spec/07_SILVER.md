# Silver Layer: Cleaning, Canonicalization, and Quarantine

## Goal
Create typed, standardized, deduplicated, canonical records using set-based SQL. Python must not perform these transformations.

## Processing contract
Input is a committed bronze batch. Output is accepted silver records, source-to-canonical crosswalk rows, rejected/quarantined rows, and audit metrics. Every output row retains source provenance, batch ID, and transformation version.

Use `LATERAL FLATTEN` for nested arrays/objects. Use `TRY_TO_DATE`, `TRY_TO_TIMESTAMP_*`, and numeric conversion functions to avoid aborting a whole batch for one bad value. Invalid values must be classified, not silently replaced.

## Standardization
- Trim whitespace and normalize Unicode consistently.
- Standardize casing only for fields where casing is not semantically meaningful.
- Normalize DOI prefixes, URL wrappers, whitespace, and case using a documented DOI rule.
- Normalize titles for matching separately from display titles; preserve the preferred display title.
- Standardize publication dates and UTC timestamp handling.
- Normalize language/country values using controlled reference tables.
- Reconstruct OpenAlex inverted-index abstracts in set-based SQL only if the Phase 1 dictionary requires abstracts.
- Use explicit per-column null rules: required, optional, defaulted, or reject.
- Keep raw source values available in bronze for traceability.

Examples:
| Input | Cleaned result | Rule |
|---|---|---|
| `" lahore "` | `"Lahore"` | Trim and controlled proper-case rule for a known place field |
| `"LAHORE"` | `"Lahore"` | Same canonical mapping |
| `"https://doi.org/10.x/ABC"` | `"10.x/abc"` | DOI normalization; validate format separately |
| Empty publication date | NULL plus reason/status | Do not invent a date |
| Invalid numeric citation count | NULL/reject with reason | Do not silently coerce to zero |

The city example is illustrative only; do not apply proper-case indiscriminately to names, acronyms, or titles.

## Deduplication and identity resolution
Use this precedence:
1. Exact normalized DOI when valid.
2. arXiv identifier where appropriate.
3. Normalized title + publication year + first-author identity hash.
4. Optional fuzzy matching only for residual candidates and only with an evaluation and manual-review path.

Create a crosswalk table mapping `(SOURCE_NAME, SOURCE_RECORD_ID)` to `CANONICAL_OUTPUT_BK`, match method, confidence, rule version, and review status. Never merge solely on title without recording uncertainty.

## Attribute survivorship
Use a documented per-attribute source preference and quality rule. A possible starting policy:
- DOI: valid, normalized DOI from a source with a populated value.
- Title: non-empty, least-corrupted title; retain provenance.
- Abstract: source with available complete abstract, respecting license and terms.
- Publication date: prefer explicit publication date over ingestion/update timestamp.
- Citation count: retain source-specific observations; do not add counts across sources.
- Authors/affiliations: preserve source mappings and avoid assuming identical names are identical people.

Treat this as a proposed policy; reconcile with the Phase 1 data dictionary before implementation.

## Quarantine
Store rejected records with source/entity, source record ID, batch ID, payload reference, reason code, column, raw value where safe, and rejection timestamp. Reason codes include `MISSING_REQUIRED_ID`, `INVALID_DOI`, `INVALID_DATE`, `INVALID_NUMERIC`, `OVERSIZE_RECORD`, `SCHEMA_DRIFT_REQUIRED`, `IDENTITY_AMBIGUOUS`, and `UNSUPPORTED_SHAPE`.

Do not drop invalid records silently. Distinguish row-level rejects from batch-level critical failures.

## Incremental SQL pattern
Process only the current batch or rows identified by streams/change markers. A full rebuild of silver may be used only for controlled recovery and must preserve crosswalk consistency. Use `QUALIFY ROW_NUMBER()` with stable ordering to deduplicate source rows before MERGE. A MERGE source must be unique per target key.

## Acceptance
- Typed columns use explicit DDL.
- Null rules exist per important column.
- DOI/title/date normalization has tests.
- Invalid casts are visible and reason-coded.
- Crosswalk identity is reproducible.
- Re-running a batch produces no duplicates.
- Rejected rows reconcile to source/staging totals.
- OpenAlex abstract reconstruction is tested if enabled.

## References
- Snowflake FLATTEN: https://docs.snowflake.com/en/sql-reference/functions/flatten
- TRY_TO_DATE: https://docs.snowflake.com/en/sql-reference/functions/try_to_date
- TRY_TO_TIMESTAMP: https://docs.snowflake.com/en/sql-reference/functions/try_to_timestamp
- MERGE: https://docs.snowflake.com/en/sql-reference/sql/merge
- OpenAlex API: https://docs.openalex.org/
