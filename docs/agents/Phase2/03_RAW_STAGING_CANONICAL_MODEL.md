# 03. Raw, Staging, Canonicalization, and Provenance

## Raw layer contract

Raw payloads are immutable. Re-fetching the same record creates a new observation or raw batch rather than overwriting historical raw evidence. If storage pressure requires compaction, retain checksums and manifests and document the process.

Each manifest should contain:
- `run_id`;
- `source_name`;
- `batch_id`;
- `retrieved_at_utc`;
- `request_descriptor_redacted`;
- `http_status`;
- `page_or_token_sequence`;
- `payload_path`;
- `payload_sha256`;
- `records_seen`;
- `parser_version`;
- `schema_version`;
- `window_start` and `window_end` when relevant;
- `complete` flag;
- error details without secrets.

Do not store API keys in payload paths, query descriptors, exceptions, or logs.

## Staging

Create source-specific staging tables or equivalent typed staging files. Preserve provider-specific columns needed for later reconciliation. Add normalized columns:
- source name and source record ID;
- normalized DOI;
- normalized title;
- publication date/year;
- provider-created/updated/index date when available;
- raw batch ID and run ID;
- payload hash;
- validation status and reason;
- ingestion timestamp.

Use the existing approved dictionary if it already defines these fields. Extend it through a documented migration if necessary.

## Validation and quarantine

Examples of quarantine reasons:
- missing stable source identifier;
- invalid date;
- malformed identifier;
- impossible negative count;
- structurally invalid payload;
- conflicting DOI identity;
- unsupported source status;
- parser/schema mismatch.

Not all missing fields are fatal. DOI, abstract, venue, author or institution can legitimately be absent. Record missingness and allow the row when identity and minimum schema requirements pass.

Quarantine records must include a stable reason code, source identity, raw batch reference, first-seen time, last-seen time, and resolution status. Never silently discard rejected records.

## Canonical identity

1. Normalize DOI for comparison only. Preserve original value.
2. Keep source crosswalks: source name + source record ID → canonical work ID.
3. Prefer stable provider IDs over title text.
4. DOI matching can merge records only when supporting fields do not indicate a material conflict.
5. If two records share a DOI but have incompatible titles, types or dates, quarantine the conflict for review.
6. If DOI is missing, do not merge based only on a fuzzy title match without a documented threshold, explainable evidence, and tests.
7. Keep the original source values and field-level provenance. For canonical values, record which source and run supplied the selected value where practical.
8. Do not let a sparse Crossref record overwrite richer OpenAlex fields with nulls.
9. Apply deterministic field precedence and make it configurable/documented. Precedence must not be represented as universal truth.
10. Upsert by stable keys and test repeatability.

## Provenance

For every canonical work and important relationship, preserve:
- source name;
- source record ID;
- raw batch ID;
- run ID;
- extraction timestamp;
- payload hash;
- parser/schema version.

## Relationship staging

Preserve typed relationships from provider metadata, including:
- citation/reference relationship;
- dataset/software related work;
- version/concept DOI relationship;
- author/institution affiliation;
- topic assignment.

Do not treat every `related identifier` as a citation. Retain the source relation type and normalize it to a controlled relation vocabulary.

## Data policy

- Metadata only. Do not fetch full-text PDFs.
- Avoid storing full abstracts unless permitted by the relevant source terms and project policy; if abstracts are collected, document the source's rights/terms and provide an option to disable them.
- Keep public metadata attribution and source links.
- Do not scrape behind logins or bypass provider controls.
- Do not publish provider data in a way that violates license/terms.
