# AGENTS.md — PaperSonar Phase 2 Agent Contract

## Before coding
1. Read every file in `docs/phase2/` and Phase 1 artifacts.
2. Treat `01_ARCHITECTURE_AND_NAMING.md` as the object-naming authority.
3. Report conflicts with the Phase 1 data dictionary before changing the model.
4. Inspect the repository, account configuration, and existing branch state.
5. Preserve Phase 1 documents and evidence.

## Non-negotiable implementation rules
- Phase 2 only. No Phase 3 analytics, dashboards, advanced aggregate queries, benchmark comparisons, or business-insight report.
- Strict ELT: Python extracts/uploads raw records; Snowflake SQL transforms.
- No Python data cleaning, categorization, deduplication, or surrogate-key assignment.
- No inferred schemas or `INFER_SCHEMA`; all tables have explicit DDL.
- Five sources: OpenAlex, Crossref, arXiv, DataCite, Zenodo.
- Use the defined Snowflake database/schemas and naming.
- Every MERGE source must be deduplicated to one row per target key.
- Dimensions must not be truncated and reloaded.
- Stable surrogate keys use business-key MERGE logic.
- Watermarks advance only after durable bronze commit.
- A missing source record does not imply deletion.
- Critical DQ failure blocks publication.
- Do not silently discard malformed, oversized, or invalid records.
- Do not claim live acceptance from mocked tests.
- Mark unverified product/API behavior `VERIFY:` and link the official documentation.

## SQL file requirements
Every SQL file header states purpose, inputs, outputs, idempotency, owner, parameters, and cost impact. Scripts must be safely rerunnable where specified. Use explicit columns, transactions where supported and tested, bounded batch scopes, and deterministic ordering.

## Security and cost
Never commit secrets or print credentials. Do not use ACCOUNTADMIN in normal workflows. Verify the actual trial credits/expiry/features. Resource controls must precede compute. Cortex remains OFF by default.

## Testing
Run lint, Python unit tests, SQL checks, live Snowflake smoke tests, idempotency tests, incremental/full tests, SCD2 tests, DQ gate tests, and acceptance SQL. Save sanitized evidence. Live Snowflake proof is required.

## Git and release
Before any force push, tag intended Phase 1 commit, back up old Phase 2 branch, inspect the diff, confirm target branch, and use `--force-with-lease` only with authorization. Preserve Phase 1 artifacts.

## Stop conditions
Stop and report before destructive actions, unapproved force pushes, unknown trial charges, secret exposure, unverified feature dependencies, or any change that violates Phase 1 requirements.

## References
- Project repository: https://github.com/zohaib-mzg/PaperSonar
- Snowflake documentation: https://docs.snowflake.com/
- GitHub Actions documentation: https://docs.github.com/en/actions
