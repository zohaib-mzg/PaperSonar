# Phase 2 Implementation Plan

## Gate 0 — Repository inspection
- Read Phase 1 architecture, requirements, data dictionary, and submission evidence.
- Record conflicts and confirm the canonical model.
- Inventory current files and identify disposable Phase 2 code.
- Preserve Phase 1 artifacts.
Exit: signed-off field map and backup plan.

## Gate 1 — Account and security
- Verify trial expiry, credits, edition, features, and authentication.
- Create database/schemas, roles, service identity, warehouse, resource monitor.
- Test key-pair connection and least privilege.
Exit: cost controls and secure connection verified before heavy compute.

## Gate 2 — Extraction foundation
- Implement shared adapter contract and source adapters.
- Add pagination, retry/backoff, resumability, deterministic file layout, checksums, manifests.
- Test mocked responses and one live small-window extraction per source.
Exit: all five sources have a documented and tested extraction path.

## Gate 3 — Stage and bronze
- Create explicit file formats and staging DDL.
- Implement COPY and metadata capture.
- Implement bronze insert-only MERGE with source dedupe.
- Implement schema drift and oversize/error logging.
Exit: rerun produces no duplicate logical bronze observations.

## Gate 4 — Silver and identity
- Create typed silver DDL.
- Implement set-based casts, standardization, dedupe, quarantine, crosswalk, survivorship.
- Implement source-to-canonical identity resolution.
Exit: accepted/rejected counts reconcile and provenance is queryable.

## Gate 5 — Categorization
- Seed taxonomy and weighted rules.
- Add source taxonomy mappings and overrides.
- Evaluate approximately 200 hand-labeled records.
- Keep Cortex disabled unless separately approved and budgeted.
Exit: versioned assignments and evaluation evidence exist.

## Gate 6 — Dimensions and facts
- Implement dimension sequences/identity strategy and unknown members.
- Implement Type 1/2 where justified.
- Load facts and bridges by set-based surrogate-key joins.
- Implement inferred members/deferred repair.
Exit: stable keys, unique fact grains, zero orphans.

## Gate 7 — Orchestration, DQ, reporting
- Implement task graph and finalizer.
- Add critical DQ gate and publication rules.
- Create basic reporting views.
- Add physical-design demonstrations only after account verification.
Exit: a complete batch can publish; failed batch cannot.

## Gate 8 — Backfill and incremental proof
- Compare API vs bulk backfill options and choose within cost/time budget.
- Complete selected full load.
- Run incremental window with overlap.
- Prove idempotency and watermark advancement.
Exit: >=100 dimension records, >=10,000 fact records, zero orphans.

## Gate 9 — Acceptance and release
- Run acceptance SQL and generate reports.
- Capture live Snowflake evidence and backup exports.
- Run CI and inspect repository diff.
- Tag Phase 1 and back up legacy Phase 2 before force-with-lease push.
Exit: documented repository state, live evidence, and known residual risks.

## Stop conditions
Stop expensive backfill if credit budget threshold is reached, API terms/rate limits are unclear, account feature assumptions fail, or required acceptance evidence is at risk. Preserve checkpoint and audit state before resuming.

## References
- Snowflake tasks: https://docs.snowflake.com/en/user-guide/tasks-intro
- GitHub Actions: https://docs.github.com/en/actions
- OpenAlex: https://docs.openalex.org/
- Crossref: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- arXiv: https://info.arxiv.org/help/api/user-manual.html
- DataCite: https://support.datacite.org/docs/api
- Zenodo: https://developers.zenodo.org/
