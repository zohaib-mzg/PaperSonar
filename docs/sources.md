# PaperSonar source strategy v2

**Status:** Phase 1 design only. No Phase 2 ingestion code has been started.  
**Rule:** Keep the source set to these five until each connector has a proven extraction, reconciliation, and refresh design. All services must be usable without a paid plan. Free usage is subject to provider limits and can change.

## Why five sources, and what each contributes

| Priority | Source | Primary role | Core identifier | Historical approach | Incremental approach | Main caveat |
|---|---|---|---|---|---|---|
| 1 | [OpenAlex](https://api.openalex.org/) | Scholarly works, authors, institutions, topics, sources, references/citation counts, OA metadata | OpenAlex entity ID; DOI as secondary identifier | Topic/year partitioning with cursor pagination; evaluate free public snapshot releases if storage and licence review allow | Free API does not provide the paid created/updated sync filters described in current docs. Use a bounded re-fetch and recent overlap, plus periodic full reconciliation. Save observation snapshots. | It is a large graph but not a complete record of all research; taxonomy and coverage change. Free API key required for cursor traversal beyond the first page at scale. |
| 2 | [Crossref](https://api.crossref.org/) | DOI metadata, publication/issued dates, publisher, authors, funding, references when deposited | Normalized DOI / Crossref DOI | Partition full history by index date or other declared filters; cursor paging | `from-index-date` **and** `until-index-date` windows, with overlap and saved watermark; cursor pagination | Broad and noisy metadata; missing references are not evidence that no references exist. Crossref overlaps with OpenAlex and is not independent citation ground truth. |
| 3 | [arXiv](https://export.arxiv.org/api/query) | Preprints, revisions, abstracts, categories, authors, submission/update dates | arXiv ID plus version | OAI-PMH/ListRecords or bounded query with durable resumption | OAI-PMH datestamp windows using `from`/`until`, with overlap; retain each observed version separately and map versions to a logical record | Primarily preprints; categories and submission dates are not equivalent to peer-reviewed publication metadata. Respect rate limits and version history. |
| 4 | [DataCite](https://api.datacite.org/) | Research datasets, software, reports, other registered research outputs and relationships | DataCite DOI | Public API/OAI-PMH harvesting in bounded windows; filter by resource type and client/provider where appropriate | Query `updated` date ranges or sort by `-updated` with overlap; API cursor/page pagination or OAI-PMH resumption tokens | Public API returns Findable records; not all drafts/registered states are visible. `updated` filtering needs validation against API pagination and date semantics. |
| 5 | [Zenodo](https://zenodo.org/api/) | Datasets, research software, reports, papers, conference outputs, versions and related identifiers | Zenodo record ID; DOI when assigned | API pagination or OAI-PMH ListRecords, by resource type and date | Prefer OAI-PMH datestamp harvesting with `from`/`until`; API can support record detail and backfill. OAI resumption tokens are short-lived, so persist pages promptly. | Zenodo records overlap with DataCite and other registries. Deduplicate through source identity and DOI crosswalk, not title alone. |

## Cross-source identity policy

1. Preserve each source-native identifier and the raw source record.
2. Create a canonical `research_output` entity only after identity rules have been applied. Maintain a `source_record` crosswalk with source, source ID, canonical output key, first seen, last seen, and match method.
3. Normalize DOI by trimming, lowercasing, removing `https://doi.org/`, `http://dx.doi.org/`, `doi:` and trailing punctuation. Keep the original value too.
4. A matching DOI is a strong candidate, not permission to merge silently: compare title, resource type, creator/date metadata, and record versions. Quarantine conflicting DOI matches.
5. Never auto-merge on title similarity alone. arXiv versions belong to one logical preprint with version observations, but should not be collapsed into a journal article unless explicit relation evidence supports it.
6. Model relationships explicitly: `is-version-of`, `is-preprint-of`, `is-supplement-to`, `is-dataset-for`, `is-software-for`, `cites`, `is-cited-by`, and other source-provided relation types. Keep the source relationship label and normalized relationship type.
7. Store provenance for every field or at least every source record, including source, source ID, extraction run, observed timestamp, raw object path, and checksum.

## Incremental synchronization contract

Each source has an independent state row. Never share one global watermark across sources.

- `last_successful_watermark`: last fully processed source watermark.
- `window_start`: prior watermark minus configured overlap.
- `window_end`: fixed at the start of the run; do not let a moving endpoint change the result set while paging.
- `next_cursor_or_resumption_token`: checkpoint only after raw page and manifest are durable.
- `run_status`: started, partial, failed, validated, published.
- `source_record_hash`: hash of normalized source payload for change detection.
- `first_seen_at`, `last_seen_at`, `source_updated_at`, `last_changed_at`: separate observation and provider timestamps.

### Commit rules

1. Use UTC and fixed, inclusive source windows with a documented overlap. De-duplicate overlapping windows by source-native ID.
2. Save raw page bytes, response metadata, extraction time, request parameters (secrets redacted), page sequence, and SHA-256 before advancing the checkpoint.
3. Retry 429/5xx and transient network errors with exponential backoff and provider `Retry-After` when present. Do not retry permanent 4xx indefinitely.
4. A run may advance its watermark only when every partition/page in the fixed window has completed and validation passes.
5. Upsert changed source records by `(source_name, source_native_id)`. Preserve prior raw versions and append a change observation rather than overwriting evidence.
6. Re-fetch a small overlap every incremental run. Periodically perform a full reconciliation because source feeds can be delayed, records can be reindexed, and API semantics can change.
7. Absence from one response is not a deletion. Mark records as possibly missing only after a complete reconciliation and explicit policy check.
8. Only a complete, validated observation run can publish warehouse snapshots. Failed/partial runs must never appear as a successful business observation date.

## Initial cadence (proposal, not measured)

| Source | Proposed initial cadence | Recovery/reconciliation |
|---|---|---|
| OpenAlex | Monthly bounded refresh, with a small recent-year overlap only if free budget allows | Full bounded reconciliation quarterly; evaluate public snapshot download only after storage and format profiling |
| Crossref | Daily or weekly index-date window, based on free rate limits and laptop resources | Weekly overlap; monthly re-scan of recent months; periodic historical reconciliation |
| arXiv | Daily OAI-PMH datestamp window | Weekly overlap; retain version-level history; periodic category/date backfill |
| DataCite | Daily or weekly `updated` window / OAI-PMH | Weekly overlap and periodic full metadata reconciliation |
| Zenodo | Daily or weekly OAI-PMH datestamp window | Re-fetch recent records and periodically reconcile API/OAI metadata |

These are starting proposals. Use the slowest cadence that meets project requirements and fits documented free limits. No scheduled jobs or connectors are implemented in Phase 1.

## Free-only policy

- No paid API, subscription, paid connector, or required payment method.
- OpenAlex's free API key is optional in general but required for cursor paging at scale under current documentation; never place it in source control.
- Do not depend on Snowflake as the only warehouse: its free trial is time/credit-limited and is not a permanent free tier. The architecture must run locally on PostgreSQL with open tools. Snowflake is a compatible optional deployment target only while an available no-cost trial/educational allowance is active, with a written stop-before-charge rule.
- Power BI Desktop can be used locally; do not assume paid Power BI sharing/service features are free.
- Source data licences apply independently of the repository's MIT code licence. Keep source-level licence and attribution fields in provenance.

## Official documentation checked for this design

- OpenAlex authentication and cursor access: https://help.openalex.org/api/authentication/
- OpenAlex pricing: https://help.openalex.org/access/pricing/
- OpenAlex API: https://help.openalex.org/api/
- Crossref cursor and indexing-window guidance: https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/
- Crossref filters: https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/
- arXiv API: https://info.arxiv.org/help/api/index.html
- arXiv OAI-PMH: https://oaipmh.arxiv.org/oai
- DataCite REST API: https://support.datacite.org/docs/rest-api
- DataCite query and update filtering: https://support.datacite.org/docs/api-queries
- DataCite OAI-PMH: https://support.datacite.org/docs/oai-pmh
- Zenodo developer documentation and OAI-PMH: https://developers.zenodo.org/
- Snowflake trial information: https://www.snowflake.com/en/data-cloud/platform/try-snowflake/

Provider behaviour, limits, terms, and free allowances must be rechecked immediately before implementation. This source plan is a design, not proof that a connector has been tested.
