# 01. Target Architecture and Requirements

## Target flow

Approved sources → source-specific extraction → raw payloads and manifests → staging and validation → canonical identity resolution → dimensional warehouse → quality gates and operational logs.

Reporting/dashboard implementation belongs to Phase 3. Phase 2 may provide SQL-ready tables and views required by the approved analytical questions, but must not build the dashboard.

## Components

### A. Source adapters
Each source adapter must implement the same internal interface while retaining its own API rules:
- validate configuration;
- fetch a bounded page/window;
- parse source response;
- expose stable source identifier and source update timestamp when available;
- write raw response and manifest;
- report next-page or resumption token;
- return retryable versus permanent errors;
- provide source-specific checkpoint semantics.

A shared interface does not mean shared pagination logic.

### B. Raw layer
Raw payloads are append-only. Each response or batch must be stored with:
- source name;
- retrieval timestamp in UTC;
- request/window descriptor with secrets removed;
- page number/cursor/resumption token metadata where safe;
- response status;
- payload checksum;
- record count where measurable;
- schema/parser version;
- run ID;
- completion marker.

Do not include API secrets in raw request descriptors or logs. Use JSON/JSONL or the existing repository's suitable format. Avoid committing large generated raw files unless the existing repository explicitly tracks small test fixtures.

### C. Staging layer
Staging retains source-specific fields and normalized common fields. Validation must be non-destructive:
- valid rows proceed;
- invalid rows receive a reason code and are quarantined;
- raw data remains available for replay;
- unknown optional values remain null, not zero;
- dates and identifiers are normalized consistently.

### D. Canonical model
The canonical work represents a deduplicated scholarly output. Keep source identifiers in a crosswalk rather than assuming every provider's ID is interchangeable. Normalize DOI values by trimming whitespace, removing DOI URL/prefix forms, and lowercasing for comparison. Preserve the original DOI string in source payloads.

Conflict policy:
- same normalized DOI and compatible identity: merge source references and retain provenance;
- DOI points to materially conflicting records: quarantine for review;
- no DOI: use stable source identifier; do not merge by title alone without a documented conservative matching policy;
- do not delete a source record merely because another source has richer metadata.

### E. Dimensional warehouse
The warehouse must follow the approved data dictionary and physical model. Do not change fact grain without documenting a migration and updating tests. Expected grains:
- `fact_publication`: one admitted canonical work;
- `fact_work_snapshot`: one canonical work × successful observation date/run;
- `fact_citation`: one distinct directed citing-work/cited-work pair;
- `bridge_work_topic`: one work × topic;
- `bridge_work_author`: one work × author;
- `bridge_work_institution`: one work × institution.

A source's cumulative current citation count is not historical citation history. Snapshot history begins with the first successful local observation.

### F. Orchestration
Run modes:
- `backfill`: finite historical extraction;
- `sync`: incremental windows plus source-specific reconciliation;
- `validate`: no source requests unless explicitly needed; run quality checks against fixtures or the configured Snowflake warehouse;
- `load`: process already persisted raw batches into staging/warehouse;
- `full`: only when explicitly configured, perform an ordered safe run.

Each source has independent state and status. A Crossref failure must not erase successful arXiv progress. The global run can be partial even if some sources succeeded.

## Architecture rules

1. Raw data is durable before a checkpoint can advance.
2. Staging and warehouse loads are idempotent.
3. Checkpoints are source-specific and versioned.
4. Run state records `started`, `succeeded`, `partial`, `failed`, or `cancelled`.
5. Every admitted warehouse row must be traceable to source IDs and extraction runs.
6. Quarantine must be queryable and include a reason code.
7. Warehouse publication occurs only after relevant checks pass.
8. Use UTC for timestamps; retain source-local dates only when the source semantics require them.
9. Separate event date (publication date), provider update date, extraction time, and observation date.
10. Keep unit tests and local development possible with mocked Snowflake connections, but production ingestion and warehouse loading must require a successful Snowflake connection. Never silently switch production runs to another database.

## Required documentation artifacts

- architecture diagram with actual implemented components;
- source capability matrix;
- schema/data dictionary;
- runbook;
- configuration reference;
- troubleshooting guide;
- acceptance evidence report;
- a clear list of known limitations.
