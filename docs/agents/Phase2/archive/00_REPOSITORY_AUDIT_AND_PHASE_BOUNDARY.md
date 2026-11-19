# 00. Repository Audit and Phase Boundary

## Goal

Establish the actual repository state before implementing Phase 2. This prevents accidental replacement of valid Phase 1 work and prevents the agent from claiming features that do not exist.

## Required audit steps

1. Inspect all top-level directories and files.
2. Read the root README, requirements, project proposal, architecture diagrams, data dictionary, DDL/DBML, source register, sample retrieval records, and any existing ETL scripts.
3. Inspect dependency manifests, environment examples, Docker files, CI workflows, tests, migrations, and SQL.
4. Search for all occurrences of: `OpenAlex`, `Crossref`, `arXiv`, `DataCite`, `Zenodo`, `checkpoint`, `watermark`, `cursor`, `Snowflake`, `GitHub Actions`, `fact_publication`, `fact_work_snapshot`, `fact_citation`, `etl_run`.
5. Run existing tests using the repository's documented commands. Record command, result, and known environmental limitations.
6. Determine the actual current storage implementation (Snowflake, another database, SQLite, or files-only). Snowflake is the required Phase 2 production warehouse; any existing non-Snowflake target is development/test scaffolding only and must not become the production fallback.
7. Create `docs/phase2/REPOSITORY_AUDIT.md` with:
   - commit/hash if available;
   - repository tree summary;
   - current functional components;
   - missing components;
   - existing schema contracts;
   - existing tests and their results;
   - files to add/update;
   - any conflicts between repository and this pack.
8. Preserve all original user data and Phase 1 evidence. Never delete raw data or manifests during refactoring.
9. Create a backup branch or a clearly described checkpoint commit before large edits, where Git is available.

## Recovered project baseline

PaperSonar is a research-intelligence data warehouse. Its core value is reproducible analysis of scholarly metadata: publication growth, citation context, topic intersections, author/institution participation, venue, and open-access status. Sparse intersections are review signals, not proof of novelty.

Recovered design includes a 15-table dimensional constellation and 89-field data dictionary. Known table concepts:
- `etl_run`
- `dim_date`
- `dim_topic`
- `dim_venue`
- `dim_work_type`
- `dim_access_status`
- `dim_author`
- `dim_institution`
- `dim_work`
- `fact_publication`
- `fact_work_snapshot`
- `fact_citation`
- `bridge_work_topic`
- `bridge_work_author`
- `bridge_work_institution`

This list contains 15 entries. If the actual data dictionary differs, the repository's approved artifact is authoritative and the agent must document the difference instead of silently changing the model.

## Phase boundary

### In scope for Phase 2
- source adapters and metadata extraction;
- historical backfill;
- incremental synchronization;
- raw persistence and manifests;
- staging and validation;
- canonical identity resolution and conflict quarantine;
- warehouse schema and ETL loading;
- tests and data-quality checks;
- local development and deterministic tests;
- mandatory Snowflake production warehouse deployment and GitHub Actions connectivity;
- GitHub Actions automation for scheduled runs;
- operations documentation and observability.

### Out of scope: Phase 3
- Power BI dashboard authoring or publishing;
- new BI pages or dashboard visuals;
- web application or API product;
- subscription or user account features;
- novel research-gap scoring beyond required warehouse SQL;
- adding new sources;
- paid data providers or paid cloud services.

## Completion reporting

The final report must separate:
- Implemented and tested;
- Implemented but not tested due to missing credentials/network;
- Documented but not implemented;
- Blocked;
- Deliberately deferred to Phase 3.

No feature may be described as operational solely because a file or workflow exists.
