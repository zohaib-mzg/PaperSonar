# Source documentation verification log

Checked for the Phase 1 design update on 10 November 2026. This confirms the cited documentation pages were available; it does not constitute an API integration test. Recheck before implementation.

- OpenAlex authentication: https://help.openalex.org/api/authentication/ — free key increases budget and is required for cursor paging beyond first page at scale.
- OpenAlex pricing: https://help.openalex.org/access/pricing/ — free daily allowance exists, but usage is budgeted.
- Crossref API pagination/update windows: https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/ — cursor paging, fixed date windows, and caching recommended for large harvests.
- Crossref filter semantics: https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/ — `from-index-date` and `until-index-date` available.
- DataCite public API: https://support.datacite.org/docs/rest-api — public unauthenticated API and OAI-PMH harvesting documented.
- DataCite query filters/pagination: https://support.datacite.org/docs/api-queries — updated query and cursor/page parameters documented; validate exact query semantics in connector tests.
- Zenodo developer docs: https://developers.zenodo.org/ — OAI-PMH, datestamps, resumption tokens and rate limits documented.
- arXiv API/OAI-PMH: https://info.arxiv.org/help/api/index.html and https://oaipmh.arxiv.org/oai — planned harvesting path; confirm current limits and datestamp behavior before use.
- Snowflake trial: https://www.snowflake.com/en/data-cloud/platform/try-snowflake/ — treat as trial/credit-based, not a guaranteed permanent free tier.

Source-specific incremental designs remain proposed until pagination, watermark, overlap, replay and idempotency tests pass against each service.
