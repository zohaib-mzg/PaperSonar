# 02. Source Connectors and Incremental Loading

## General contract

Implement only these five approved sources: OpenAlex, Crossref, arXiv, DataCite, Zenodo. Do not add more providers in Phase 2.

Every adapter must support:
- bounded historical backfill;
- incremental or reconciliation mode;
- pagination;
- rate-limit-aware requests;
- connection/read timeout;
- bounded retries with exponential backoff and jitter;
- response validation;
- raw response persistence;
- run/source-level metrics;
- deterministic replay;
- checkpoint persistence;
- safe resume after interruption.

Do not claim a source is incremental merely because the job runs daily. The adapter must have a documented change-detection strategy.

## 1. OpenAlex

### Data
Works, authorships, institutions, topics, source/venue, work type, open-access metadata, citation counts and referenced works.

### Historical strategy
Use the configured corpus filters and cursor pagination. Freeze and checksum the configuration (dates, topics/fields, work types, language, and exclusions). Preserve the exact filter description in each run manifest.

### Free refresh limitation
The free approach must not rely on paid `from_updated_date` or `from_created_date` change feeds. Use bounded corpus reconciliation:
- partition the configured corpus into manageable deterministic slices, such as publication-year ranges and/or configured topic partitions;
- periodically re-fetch selected slices;
- upsert by stable OpenAlex work ID;
- compare normalized content hashes to detect changed records;
- record last successful reconciliation time per partition;
- do not call this a complete change feed;
- expose reconciliation coverage and stale-partition age.

The agent must confirm current OpenAlex API terms and parameters from official documentation during implementation. If a filter is unavailable in the free access tier, do not silently use it.

### Checkpoint
Store partition ID, query/config checksum, cursor progress for an in-progress run, completed-through timestamp, record count, and last successful reconciliation. A cursor token is run-scoped; do not treat it as a permanent watermark.

### Required checks
- cursor pagination completes or the run remains incomplete;
- repeated records are upserted;
- IDs are stable;
- record hashes change only when normalized content changes;
- a failed partition is retried without marking the full reconciliation complete.

## 2. Crossref

### Historical strategy
Use cursor pagination for bounded historical ranges. Use `from-index-date` and `until-index-date` to define incremental index-date windows where supported by the API.

### Incremental strategy
- Keep a per-source successful high-water mark based on the provider's index-date semantics.
- Use a small overlap window on the next run to tolerate boundary and indexing delays.
- Deduplicate/upsert by Crossref DOI/record identity.
- Record the actual query window and cursor completion.
- Do not advance the high-water mark until every page in the window has been stored and accepted.
- Re-running the same window must not create duplicates.

### Reconciliation
Periodically revisit a bounded recent period and selected records, because providers can correct metadata after first indexing. Record this as reconciliation, separate from the main watermark.

### Required checks
- cursor pagination terminates correctly;
- missing DOI records still retain a stable Crossref identifier where available;
- date-window overlap does not duplicate canonical works;
- `429`, transient `5xx`, timeout and malformed responses are handled.

## 3. arXiv

### Preferred incremental strategy
Use arXiv OAI-PMH harvesting when supported by the selected endpoint and metadata format. Use `from` and `until` datestamps with resumption tokens. Respect endpoint throttling and current arXiv usage guidance.

### Historical strategy
Harvest the required date range or categories in bounded batches. If API query search is used for backfill, document its result-window limitations and do not treat it as a complete historical export unless verified.

### Checkpoint
Persist the OAI-PMH date window, metadata format, set/category if used, resumption token, and successful completion datestamp. Tokens are temporary progress state, not permanent IDs. If a token expires, restart the affected bounded window safely and rely on idempotent upserts.

### Version handling
Preserve arXiv ID and version identifier. A revision to an existing paper is not automatically a new canonical publication. Store version observations/source metadata according to the approved schema. If the physical model cannot preserve version history, document the gap and add a compatible source-version table only with explicit migration and tests.

### Required checks
- OAI-PMH XML parsing handles namespaces;
- resumption token pagination works;
- deleted/withdrawn records follow a documented status policy;
- repeated versions do not duplicate the canonical work;
- endpoint throttling is respected.

## 4. DataCite

### Strategy
Prefer OAI-PMH datestamp harvesting for incremental changes when appropriate and available. REST API date filters may be used only after confirming current API syntax and behavior from official documentation. Support bounded backfill and cursor/resumption pagination.

### Identity and relationships
Preserve DataCite DOI, creators, resource type, related identifiers, publication year, dates, and provider record identifier. Related publications, datasets and software should be retained as typed relationships in staging even if Phase 2 warehouse scope limits which relationships are published.

### Checkpoint
Track date window, set/metadata format if used, resumption token, and completed-through datestamp. A failed OAI-PMH page prevents the window checkpoint from advancing.

### Required checks
- XML namespaces and optional elements are handled;
- deleted or tombstoned records follow a documented policy;
- DOI normalization is shared with other DOI sources;
- relationships are not mistaken for citations unless the relation type says so.

## 5. Zenodo

### Strategy
Use OAI-PMH for incremental metadata harvesting where supported. API search pagination may supplement or support bounded retrieval, but must obey current API limits and document any result-window cap.

### Token expiry
OAI-PMH resumption tokens may expire quickly. Persist tokens for diagnosis/resume, but if a token expires, restart the affected bounded date window from the beginning and rely on idempotent writes. Never mark the window complete just because a token was saved.

### Data and version handling
Preserve Zenodo record ID, DOI, concept DOI if present, version, creators, resource type, related identifiers, publication dates and updated dates. Keep versions distinguishable. Avoid downloading files; metadata only.

### Required checks
- resumption token handling and expiry recovery;
- page-level raw persistence;
- version/concept DOI distinction;
- record upsert and duplicate behavior;
- API throttling and transient failure handling.

## Shared incremental-state schema

The exact physical naming may adapt to the repository, but the concepts are mandatory:
- `source_name`
- `stream_or_partition`
- `sync_mode`
- `window_start`
- `window_end`
- `cursor_or_token` (encrypted only if it could contain secrets; preferably tokens are not secret but never assume)
- `last_successful_watermark`
- `last_attempt_at`
- `last_success_at`
- `run_id`
- `status`
- `pages_completed`
- `records_seen`
- `records_written`
- `records_quarantined`
- `error_code`
- `error_summary`
- `config_checksum`

Keep current in-progress cursor separate from the durable completed watermark.

## Required source capability matrix

Create and maintain a matrix with:
- source;
- endpoint/protocol;
- historical method;
- incremental method;
- pagination type;
- identifier;
- provider update timestamp availability;
- free-tier limitations;
- rate limits/usage policy;
- retry behavior;
- verified date and official documentation link;
- known gaps.

Use official provider documentation for final endpoint parameters. Never invent a URL, API parameter, rate limit, or capability.
