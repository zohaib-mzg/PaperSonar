# Incremental ingestion design and recovery specification

**Design only.** This file specifies behaviour for future Phase 2 implementation. No ingestion code is included in Phase 1.

## State per source

| Field | Purpose |
|---|---|
| `source_name` | Stable connector name: openalex, crossref, arxiv, datacite, zenodo |
| `last_successful_watermark` | Last fully processed end timestamp/date |
| `window_start`, `window_end` | Fixed source-specific window, including configured overlap |
| `cursor_or_resumption_token` | Durable page checkpoint, written only after raw page storage succeeds |
| `last_successful_run_id` | Last validated run, not last started run |
| `source_updated_at` | Provider's update time when supplied |
| `first_seen_at`, `last_seen_at` | Local observation timestamps |
| `payload_sha256` | Change detection on normalized source payload |
| `status`, `error_code`, `retry_count` | Operations and recovery evidence |

## Source-specific watermark logic

- **OpenAlex:** free API key for large cursor traversals; no assumption of paid sync filters. Use bounded full refreshes plus limited overlap queries; periodic complete reconciliation. Keep snapshot releases as a separately evaluated bulk option, not a required download.
- **Crossref:** `from-index-date` and `until-index-date` define a fixed window. Use cursor paging and overlap because the index can change during a large harvest. Store `next-cursor` with each durable page. If a run fails, resume/replay the fixed window, not a new moving window.
- **arXiv:** OAI-PMH datestamp window with `from` and `until`, using resumption tokens. Keep source version identifiers and version update history. The API query endpoint can be used for targeted backfill, not as the only all-history ledger.
- **DataCite:** use public REST query filters for updated-date windows or OAI-PMH for harvesting. Validate actual returned `updated` semantics and pagination before selecting the connector path. Use overlap and periodic re-scan.
- **Zenodo:** OAI-PMH datestamp windows are a candidate incremental path; API pagination supports details/backfill. Resumption tokens may expire quickly, so fetch/store pages promptly and restart the window if a token expires.

## Upsert and history policy

1. Uniqueness is source-native: `(source_name, source_native_id)`.
2. Keep immutable raw payloads, plus normalized current rows and change-observation history.
3. A changed payload hash creates a new observation/version. Do not overwrite the only evidence of the previous version.
4. Canonical matching uses persistent identifiers and explicit relationships. DOI conflicts go to quarantine; title similarity is only a human-review aid.
5. Source records from multiple registries can map to one canonical research output, but source records remain separate.
6. A deletion candidate requires a completed source reconciliation and a source-specific deletion/withdrawal policy. Missing from a page is never sufficient.
7. `source_sync_state` advances only after all pages, validation checks, reconciliation, and manifest finalization succeed.

## Required validation gates before publishing

- Every requested partition has a terminal page marker or documented complete count.
- Page sequence has no gaps; checksums and manifests exist.
- No duplicate source-native key after normalization.
- DOI normalization and collision report produced.
- Required fields and source-specific type mappings measured.
- Source-native to canonical crosswalk has no unresolved auto-merge conflict.
- Fact and bridge grains pass uniqueness checks.
- Allocation weights meet the chosen per-output policy.
- Record counts reconcile to source totals within a documented explanation for exclusions.
- A failed gate prevents snapshot publication and watermark advancement.

## Acceptance tests to implement later

- Replaying the same window creates no duplicate source records or facts.
- A changed record updates the active representation and preserves the prior observation.
- A failed page does not advance the watermark.
- Expired OAI token restarts the fixed window without losing or duplicating records.
- Overlapping date windows deduplicate by source-native ID.
- A DOI collision is quarantined rather than merged.
- A partial run does not appear as a valid snapshot date.
- A record absent from a partial response is not marked deleted.
- Restarting after process termination resumes from the last durable page.
