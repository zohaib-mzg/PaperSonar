# 07. Testing, Data Quality, and Acceptance Criteria

## Test layers

### Unit tests
- DOI normalization;
- provider ID normalization;
- date parsing and timezone handling;
- OpenAlex cursor parsing;
- Crossref cursor and index-date window handling;
- arXiv OAI-PMH XML namespaces and resumption tokens;
- DataCite OAI-PMH/REST response parsing;
- Zenodo OAI-PMH token expiry and API pagination;
- hash stability;
- conflict detection;
- retry/backoff decisions;
- redaction of secrets from logs.

### Contract tests
Use small, checked-in, sanitized fixtures. Do not depend on live API availability for every unit test. Validate that each adapter returns the common internal record shape and preserves source-specific identity and provenance.

### Integration tests
- raw batch write plus manifest;
- staging upsert;
- quarantine write;
- canonical work crosswalk;
- dimensions and facts load;
- unknown member seed;
- duplicate handling;
- checkpoint transaction;
- run status update.

### End-to-end smoke tests
Use small bounded requests. Do not trigger a large backfill in CI. Live external-source API checks must be explicitly invoked, rate-limited, and clearly separated from deterministic tests. A real Snowflake connectivity and warehouse smoke test is mandatory for Phase 2 acceptance; mocked tests alone are insufficient.

## Required quality metrics

At minimum record:
- records seen, accepted, rejected and quarantined per source;
- missing DOI percentage;
- missing title percentage;
- missing publication date percentage;
- missing topic, venue, author, institution and access status where applicable;
- duplicate source records;
- duplicate canonical DOI candidates;
- unresolved DOI conflicts;
- percentage of records with source provenance;
- fact and bridge counts;
- unresolved foreign keys;
- invalid/negative counts;
- checkpoint before and after;
- freshness of last successful source sync;
- failed partitions/windows.

Missing data is not automatically a failed record. Define fatal versus warning thresholds in configuration and document why. Do not silently replace nulls with zero.

## Mandatory warehouse checks

1. Unknown dimension member exists for each relevant dimension if key 0 is part of the model.
2. Every fact foreign key resolves.
3. `fact_publication` has one row per admitted canonical work.
4. Snapshot rows match the approved grain and originate only from successful observations.
5. Citation edges are directed, unique, and non-self-referential unless source/model rules explicitly allow self-citation.
6. Bridges contain unique pairs and valid surrogate keys.
7. Allocation weights satisfy the approved data dictionary.
8. No negative citation counts.
9. No raw batch marked complete if pages failed.
10. No checkpoint advances for incomplete windows.
11. Rerunning the same input does not increase duplicate counts.
12. `etl_run` status and counts are recorded for failures as well as successes.

## Required test scenarios

- same batch loaded twice;
- same DOI from two sources;
- conflicting titles for one DOI;
- record with no DOI;
- missing optional author or venue;
- cursor page fails;
- OAI-PMH token expires;
- API rate limit response;
- transient server error;
- permanent bad request;
- database failure before commit;
- workflow missing secrets;
- production startup fails clearly when mandatory Snowflake configuration is missing;
- mocked adapter tests run without a live account;
- live Snowflake connectivity and warehouse smoke tests pass before acceptance;
- source A succeeds and source B fails;
- scheduled workflow runs with no new records;
- replay from raw payload without network access.

## Acceptance evidence

The agent must provide a machine-readable and human-readable test report:
- command executed;
- pass/fail;
- number of tests;
- tests skipped and reason;
- environment limitations;
- sample run ID;
- source-level result;
- warehouse row counts;
- quality gate result;
- proof that a rerun is idempotent;
- proof that a checkpoint did not advance after a forced failure.

Never make up row counts or test results. If external credentials are unavailable, report the relevant deployment test as blocked, not passed.

## Course-scale targets

The recovered project context includes targets of 30,000–60,000 admitted works and the course requires at least 100 dimension records and 10,000 fact records. Treat these as targets/acceptance requirements to verify against the official course document and actual corpus. Do not fabricate counts or force bad data into the warehouse just to meet a number. Report actual loaded counts and the safe steps needed to reach the target.
