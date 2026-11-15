# Phase 2 warehouse key addendum

This addendum documents the additive columns introduced by migration
`005_dimensional_surrogate_keys.sql`. The Phase 1 workbook remains a logical
design artifact; this page records the physical Phase 2 key implementation.

| Object | New column | Meaning |
| --- | --- | --- |
| `DIM_WORK` | `WORK_SK` | Numeric warehouse surrogate for retained `WORK_KEY`. |
| `DIM_DATE` | `DATE_SK` | Numeric warehouse surrogate for retained `DATE_KEY`; date key `0` is unknown. |
| `DIM_TOPIC` | `TOPIC_SK` | Numeric warehouse surrogate for retained `TOPIC_KEY`. |
| `DIM_VENUE` | `VENUE_SK` | Numeric warehouse surrogate for retained `VENUE_KEY`. |
| `DIM_WORK_TYPE` | `WORK_TYPE_SK` | Numeric warehouse surrogate for retained `WORK_TYPE_KEY`. |
| `DIM_ACCESS_STATUS` | `ACCESS_STATUS_SK` | Numeric warehouse surrogate for retained `ACCESS_STATUS_KEY`. |
| `DIM_AUTHOR` | `AUTHOR_SK` | Numeric warehouse surrogate for retained `AUTHOR_KEY`. |
| `DIM_INSTITUTION` | `INSTITUTION_SK` | Numeric warehouse surrogate for retained `INSTITUTION_KEY`. |
| `DIMENSION_KEY_MAP` | `DIMENSION_NAME`, `BUSINESS_KEY`, `SURROGATE_KEY`, `CREATED_AT` | Durable business-key mapping and sequence-generated numeric identifier. |
| `WORK_SOURCE_XW` | `WORK_SK` | Canonical work surrogate alongside source/canonical business keys. |
| `FACT_PUBLICATION` | `WORK_SK`, `PUBLICATION_DATE_KEY`, `PUBLICATION_DATE_SK`, `WORK_TYPE_SK`, `VENUE_SK`, `ACCESS_STATUS_SK` | Numeric dimension references; existing business references remain for lineage. |
| `FACT_WORK_SNAPSHOT` | `WORK_SK`, `SNAPSHOT_DATE_SK`, `ACCESS_STATUS_KEY`, `ACCESS_STATUS_SK` | Numeric work/date/access references; existing snapshot date and status remain available. |
| `FACT_CITATION` | `WORK_SK`, `CITED_WORK_SK` | Numeric citing and resolved cited-work references. Unresolved citations have no cited surrogate. |
| `BRIDGE_WORK_TOPIC` | `WORK_SK`, `TOPIC_SK` | Numeric work/topic references. |
| `BRIDGE_WORK_AUTHOR` | `WORK_SK`, `AUTHOR_SK` | Numeric work/author references. |
| `BRIDGE_WORK_INSTITUTION` | `WORK_SK`, `INSTITUTION_SK`, `AUTHOR_SK` | Numeric work/institution/author references. |

Dimension surrogate IDs are not source identifiers and should not be
interpreted as ordered, stable across environments, or portable between
separately initialized warehouses. The durable lookup is the dimension name
plus business key. See [migration notes](SURROGATE_KEY_MIGRATION.md) for
backfill and verification details. The live values and null/orphan checks are
still unverified until Snowflake runs the migration and evidence queries.
