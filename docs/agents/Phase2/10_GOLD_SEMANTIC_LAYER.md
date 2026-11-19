# Gold / Reporting Semantic Layer — Phase 2 Only

## Scope
Create a small semantic layer in `PROJECT_REPORTING`. It makes the warehouse understandable to consumers without implementing Phase 3 analytics, dashboards, advanced aggregation queries, or business insights.

## View standards
Create one clean, business-named view per main star, flattening fact rows with relevant dimensions. Candidate names:
- `VW_RESEARCH_OUTPUT`
- `VW_CITATION_SNAPSHOT`
- `VW_SOURCE_OBSERVATION`

Expose clear column names, retain stable output grain, and avoid duplicate expansion from one-to-many bridges. Provide separate bridge views if needed. Every view must filter or join through the publication contract so unapproved batches are not exposed.

If a canonical output may be associated with several batches, do not filter it by a simplistic single batch column without verifying the data model. Prefer a published-batch registry/canonical publication watermark or another explicit design that can safely represent prior published data.

## Secure access
Grant `PAPERSONAR_REPORTER` SELECT only on approved views. Use secure views where the access-control objective warrants them and supported features are verified. Avoid exposing raw payloads, API tokens, or restricted metadata.

## Physical demonstrations
Create one materialized view and one dynamic table only as physical-design demonstrations, if the account supports them and their refresh costs are acceptable. Select a simple, justified object; do not build advanced analytical outputs. If unsupported, document the live verification evidence and keep the rest of Phase 2 functional without them.

`VERIFY:` Materialized-view definition restrictions (including single-table or other limitations), edition availability, dynamic-table availability, refresh behavior, and costs.

## Refresh/publication
Do not expose a batch before DQ passes. The task graph should perform the necessary publication-state transition only after successful DQ. Ordinary views read the currently published model; physical objects must have an equally explicit refresh and publication strategy.

## Acceptance
- Views exist and have stable grain.
- Reporter can query views but cannot modify warehouse data.
- Failed/unpublished batches are not exposed as published.
- Materialized-view and dynamic-table demonstrations are present or documented as unavailable after verification.
- No Phase 3 analytics are included.

## References
- Snowflake views: https://docs.snowflake.com/en/user-guide/views-introduction
- Secure views: https://docs.snowflake.com/en/user-guide/views-secure
- Materialized views: https://docs.snowflake.com/en/user-guide/views-materialized
- Dynamic tables: https://docs.snowflake.com/en/user-guide/dynamic-tables-intro
