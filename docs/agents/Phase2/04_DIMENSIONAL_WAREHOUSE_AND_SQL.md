# 04. Dimensional Warehouse and SQL Loading

## Authority of the model

The repository's approved physical data dictionary, DDL and model diagram are authoritative. This specification gives expected grains and rules. The agent must compare actual DDL to the dictionary before implementation and must not silently replace field names or types.

## Expected dimensional model

Operational table:
- `etl_run`: one ETL/pipeline execution, with run status, start/end timestamps, source outcomes, configuration/model versions, row counts, manifest references, and error summary.

Dimensions:
- `dim_date`: one calendar date plus reserved unknown key 0;
- `dim_topic`: one stable topic identity and descriptive attributes;
- `dim_venue`: one source/venue identity;
- `dim_work_type`: one normalized type;
- `dim_access_status`: one access classification;
- `dim_author`: one stable source-author identity or canonical author identity according to the approved dictionary;
- `dim_institution`: one stable institution identity;
- `dim_work`: one canonical scholarly work, including title/date/DOI and stable canonical identity.

Facts:
- `fact_publication`: one admitted canonical work; `publication_count = 1` if the approved schema uses that measure;
- `fact_work_snapshot`: one canonical work × successful observation date/run, containing values that can change, such as observed citation count and access status;
- `fact_citation`: one distinct directed citing-work/cited-work pair. Do not duplicate the same directed pair;
- bridges:
  - `bridge_work_topic`: one work × topic;
  - `bridge_work_author`: one work × author;
  - `bridge_work_institution`: one work × institution.

## Surrogate keys and unknown member

- Use integer/bigint surrogate keys for dimensions where the approved schema specifies them.
- Reserve key 0 for the unknown/unspecified dimension member when that matches the physical model.
- Seed key 0 explicitly and idempotently.
- Unknown member does not mean the real value is zero. Preserve missingness indicators where the dictionary requires them.
- Every fact foreign key must resolve to a valid dimension row.
- Never use a display name as a dimension key.

## Fact grain protections

### Publication
One admitted canonical work. Duplicate source records must not create multiple publication fact rows.

### Snapshot
One canonical work × successful observation date/run according to the approved grain. If reruns occur on the same date, follow the approved run/date grain and use a deterministic uniqueness constraint. Do not add a snapshot for a failed or partial observation of that work.

### Citation
Directed edge from citing work to cited work. Do not reverse direction or count one edge twice. Reference endpoints that are outside the admitted corpus may be represented as reference stubs only if the approved model supports them. Document whether analytics use only edges with both endpoints admitted.

### Bridges
One work × linked entity pair. Preserve all valid assignments. If allocation weights exist, validate them against the data dictionary's formula. Do not invent an allocation formula when one already exists.

## Loading order

1. Seed unknown dimension rows.
2. Load/merge `dim_date`.
3. Load canonical work and entity dimensions.
4. Resolve source IDs to surrogate keys.
5. Load `fact_publication` with a unique canonical-work constraint.
6. Load successful `fact_work_snapshot` observations.
7. Load directed `fact_citation` edges.
8. Load topic/author/institution bridges.
9. Run integrity checks.
10. Mark the warehouse publication stage successful only if required checks pass.

Use transactions where supported. If the database cannot transactionally wrap all stages, use stage-level commits plus run status and idempotent reruns.

## Required integrity checks

- No duplicate fact-publication canonical work key.
- No duplicate snapshot at its defined grain.
- No duplicate directed citation edge.
- No duplicate bridge pair.
- All fact foreign keys resolve.
- All dimension unknown keys exist.
- No negative source citation counts.
- No invalid dates silently converted to arbitrary values.
- Allocation weights obey the approved rules.
- Fact counts reconcile to admitted staging records, with documented exclusions.
- `etl_run` records start/end status and row counts even when a run fails.
- Every warehouse record can be traced to source/provenance records.

## Mandatory Snowflake warehouse

Snowflake is the required production warehouse and the only approved production target for Phase 2. Implement Snowflake-compatible DDL, `MERGE`-based idempotent loads, transaction-aware checkpoint updates, and migrations. Existing PostgreSQL/SQLite code may be retained only for isolated legacy tests or migration reference; it must not be selected by production configuration or GitHub Actions. Unit tests may mock the Snowflake adapter, but acceptance requires a real Snowflake connectivity and warehouse smoke test. If Snowflake credentials or account access are unavailable, mark acceptance as BLOCKED rather than declaring Phase 2 complete or switching databases.

## SQL analytics

Phase 2 may implement the approved SQL analytical questions and views if required by the course model. Use the recovered Q01–Q14 definitions in the project context. Preserve caveats:
- cohort citation comparisons must use comparable publication years/types;
- partial 2026 must not be compared with complete 2025;
- sparse intersections are candidate signals, not proof of novelty;
- missing values are not zeros;
- source coverage limits must be visible.
Do not build dashboards in this phase.
