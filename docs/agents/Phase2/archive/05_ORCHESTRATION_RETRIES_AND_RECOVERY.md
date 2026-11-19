# 05. Orchestration, Retries, Checkpoints, and Recovery

## Run design

Every run receives a unique run ID and records:
- requested mode;
- start/end UTC timestamps;
- code version/commit if available;
- configuration checksum;
- source-level status;
- raw/staging/warehouse row counts;
- quarantined count;
- retry count;
- quality-gate result;
- error summary;
- final status: `succeeded`, `partial`, `failed`, or `cancelled`.

A global run can be partial when one source fails while other source results remain valid. Never label partial as fully successful.

## Checkpoint rules

- Store checkpoints in durable storage, not only process memory or GitHub Actions workspace.
- Use one checkpoint namespace per source and stream/partition.
- Keep in-progress pagination state separate from completed watermark.
- Advance completed watermark only after all pages in a bounded window have been persisted and validated to the defined threshold.
- Save raw payloads before marking pages complete.
- Use overlap windows for date-based APIs to tolerate delayed indexing.
- Reprocessing an overlap must be safe due to idempotent upserts.
- Do not use extraction time as a substitute for a provider's update timestamp.
- If a source has no reliable free update feed, record the reconciliation policy and its coverage limitations.

## Retries

Retry only transient failures:
- connection reset;
- timeout;
- HTTP 429;
- temporary HTTP 5xx;
- transient provider service errors.

Use bounded exponential backoff with jitter and respect `Retry-After` when provided. Do not endlessly retry:
- invalid credentials;
- invalid query parameters;
- unsupported API response;
- permanent 4xx errors other than 429;
- schema validation errors caused by bad configuration.

Log the retry attempt and final failure reason, but redact credentials and sensitive query parameters.

## Partial failures

- A failed source must not roll back other sources' already durable raw batches.
- Do not advance that source's watermark.
- Mark the source status as failed or partial.
- Permit a rerun of the failed window.
- A later successful rerun should close the gap without duplicating records.
- Warehouse publication must not claim full completeness if required sources are missing.
- Document whether analytical views use the latest successful per-source data or require a synchronized common cutoff.

## GitHub Actions overlap prevention

Scheduled jobs can overlap if one run is slow. Configure workflow concurrency so only one ingestion run for the same environment executes at a time. Choose a clear policy: cancel an older run only if cancellation is safe; otherwise queue/prevent overlap. The default recommendation is to prevent overlapping runs and avoid cancelling a run after it has started writing data.

## Observability

Produce structured logs and a compact run summary:
- source;
- run ID;
- pages requested/completed;
- records seen/written/updated/quarantined;
- watermark before/after;
- window start/end;
- elapsed time;
- retries;
- error codes;
- quality-gate status.

Do not print full payloads or secrets to logs.

## Replay

Provide a documented replay command or equivalent that:
- takes source, batch/window, and mode;
- reads stored raw payloads;
- does not require re-querying the API;
- reruns parser/staging/warehouse loads idempotently;
- records replay lineage and parser version.

## Recovery drills

Automated tests must simulate:
1. crash after raw write but before checkpoint;
2. failure midway through cursor pagination;
3. expired OAI-PMH token;
4. HTTP 429 with `Retry-After`;
5. database failure during upsert;
6. malformed single record in otherwise valid batch;
7. rerunning a completed window;
8. one source fails while other sources succeed.

Acceptance requires no lost completed data, no duplicate fact rows, and no incorrect watermark advancement.
