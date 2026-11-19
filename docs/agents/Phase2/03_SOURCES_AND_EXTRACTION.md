# Sources and Extraction Contract

## Goal
Implement one adapter per source. Python only fetches, paginates, retries, writes raw one-object-per-line NDJSON, gzip-compresses, uploads, and registers files. It must not clean fields or assign warehouse keys.

## Shared adapter contract
Inputs: source, entity, mode (`full`/`incremental`), date window, prior cursor, batch ID.
Outputs: deterministic `.ndjson.gz` files, manifest rows, checkpoint candidate, metrics.
For every request record request type, status, latency, retry count, page/cursor, and returned count without logging secrets or excessive payload.
Use bounded exponential backoff with jitter for transient network errors, HTTP 429, and eligible 5xx. Honor `Retry-After` where supplied. Do not retry permanent 4xx indefinitely. Keep per-source concurrency and polite request pacing.

File naming: `<source>/<entity>/<window_start>_<window_end>/part-000001-<stable-window-id>.ndjson.gz`. A retry for the same logical window must not silently create a second logical batch. Include a batch ID in manifest metadata; filenames must remain deterministic for the same extraction unit. Target 100–250 MB compressed files as an initial operational goal, not a hard rule. Small tails are acceptable. `VERIFY:` confirm Snowflake load guidance for file-size recommendations.

Each line is one complete JSON object. Detect records exceeding the VARIANT/object size limit before upload where practical; route them to a separate audit/error artifact and never silently drop them. `VERIFY:` confirm the current maximum supported VARIANT size and COPY behavior in Snowflake docs.

## Source adapters
### OpenAlex
Use the official API and cursor pagination where available. Entity: works, plus authors/sources/institutions only where required by the Phase 1 dictionary. Incremental extraction should use a date filter supported by the endpoint and overlap window. Preserve OpenAlex IDs and raw payload.
`VERIFY:` current endpoint, filter syntax, cursor behavior, polite-pool requirements, and API limits: https://docs.openalex.org/

### Crossref
Use the REST API for works and required related entities. Use date/update filters and cursor pagination where supported. Send an informative User-Agent with project contact information when configured. Preserve DOI and Crossref record ID.
`VERIFY:` endpoint filters, cursor behavior, rate limits, and bulk/public data availability: https://api.crossref.org/swagger-ui/index.html and https://www.crossref.org/documentation/retrieve-metadata/rest-api/

### arXiv
Use the official export API for metadata search and pagination; preserve arXiv identifiers and version metadata. Do not assume the API supports arbitrary date windows without checking its query syntax.
`VERIFY:` API query syntax, paging limits, and rate etiquette: https://info.arxiv.org/help/api/user-manual.html

### DataCite
Use the DataCite REST API for DOI metadata, date filters, pagination, and relevant dataset/software records. Preserve DOI and DataCite identifier.
`VERIFY:` exact endpoint, pagination model, filter syntax, limits, and public bulk options: https://support.datacite.org/docs/api

### Zenodo
Use the Zenodo API for records and metadata, with date filtering and pagination as supported. Preserve record ID, DOI, concept DOI, and version relationships where present.
`VERIFY:` rate limits, pagination, date filters, token requirements, and public export options: https://developers.zenodo.org/

## Full backfill strategy
Evaluate source APIs first, then bulk alternatives before spending trial credits:
- OpenAlex snapshot/bulk data.
- Crossref public data files and REST API.
- DataCite public data/bulk options.
- OAI-PMH or other documented bulk endpoints for sources where available.
- arXiv bulk metadata or export options.

For each option record: coverage, freshness, format, download size, licensing, resumability, hosting requirements, processing cost, and whether it is practical within the project time. Do not claim a bulk option exists or is suitable until verified from official source documentation. The default remains API extraction unless a verified bulk route is clearly better.

## Watermarks and overlap
Maintain one watermark per source/entity: committed value, window start/end, overlap duration, cursor/resumption token, status, last good checkpoint, and update timestamp. Incremental windows intentionally overlap to tolerate late updates. Tune overlap per source based on observed update behavior. A missing record in a response does not mean deletion.

Full and incremental loads share the same code path with different windows. Full load never truncates bronze. Advance watermark only after bronze commit and safe checkpoint update. If a checkpoint update fails after commit, replay is safe.

### OpenAlex window semantics

- Full mode keeps `has_doi:true`, the checked-in `select`, no topic narrowing and no `max_pages`; it uses publication-date filters and honours explicit `--from`/`--until` exactly. This is the one-time 100,000+ backfill.
- Incremental mode uses `from_updated_date`/`to_updated_date` with `overlap_days: 1`. There is no fallback to publication-date filters.
- Shards are resumable deterministic gzip files; one batch per window; re-runs neither lose nor duplicate records. A window with zero new records is designed to load zero rows and exit cleanly (unit-tested; live proof blocked by the plan below).
- `VERIFY:` `from_updated_date` is part of OpenAlex daily sync and requires a Member+/Partner plan; the current plan returns HTTP 403 `Plan upgrade required`. Official docs: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/filter-entity-lists

## Manifest
One manifest insert per file, including `BATCH_ID`, `SOURCE_NAME`, `ENTITY_NAME`, `FILE_NAME`, `FILE_SIZE_BYTES`, `RECORD_COUNT`, `WINDOW_START`, `WINDOW_END`, `CURSOR_START`, `CURSOR_END`, checksum, extraction timestamps, and status. Reconcile manifest counts with staging counts where the source output permits it.

## Acceptance
- Each source has documented pagination, filters, retries, and resumption.
- A forced retry produces no duplicate logical bronze observations.
- An incomplete extraction cannot become LOADED.
- Watermark advances only after bronze is durable.
- Oversize or malformed records are visible in audit.
- Full load does not truncate historical bronze.

## References
- OpenAlex: https://docs.openalex.org/
- Crossref REST API: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- arXiv API: https://info.arxiv.org/help/api/user-manual.html
- DataCite API: https://support.datacite.org/docs/api
- Zenodo API: https://developers.zenodo.org/
- Snowflake load considerations: https://docs.snowflake.com/en/user-guide/data-load-considerations-load
