# PaperSonar project scope v2

**Design date:** 10 November 2026  
**Current phase:** Phase 1 design update. Phase 2 and Phase 3 implementation have not started.

## Vision

PaperSonar is a Research & Innovation Intelligence Warehouse. It connects scholarly publications, preprints, datasets, research software and related outputs so researchers can compare directions using repeatable measures and inspectable evidence. It is not a novelty detector and does not replace literature review.

## Business problem

A researcher needs to compare directions across publication activity, citation context, topic intersections, creators, institutions, access status and supporting datasets/software. Existing discovery services help find items, but the proposed PaperSonar workflow focuses on reproducible comparisons with explicit corpus boundaries, cutoffs, denominators, source coverage and caveats.

## Users and outcomes

| User | Need | Proposed output |
|---|---|---|
| Researcher/student | Compare potential research directions | Growth, citation cohorts, intersections, supporting papers/artifacts |
| Supervisor | Assess alternatives with traceable evidence | Dated comparison dossier and coverage indicators |
| Small R&D group | Track a technical area | Repeatable corpus, change observations and evidence exports |
| Research support/library staff | Understand output coverage | Source-match rates, repository/data/software links and metadata quality |

## Scope

### Included in the target design

- Five sources only: OpenAlex, Crossref, arXiv, DataCite and Zenodo.
- Publication, preprint, dataset, software, report and other research-output resource families.
- Source-native identifiers and source-record crosswalks.
- Canonical research-output identity, version history, typed relationships, creator/topic/institution/funder/venue/access dimensions.
- Independent source sync state, durable page checkpoints, overlap windows, immutable raw evidence, source-specific quotas and quarantine.
- A publication-centered analytics mart retained as one downstream view, not the only canonical entity.
- 18 candidate analytical questions; final questions and thresholds require approval after source profiling.
- Local PostgreSQL as the required zero-cost reference deployment; optional Snowflake compatibility only if a no-cost trial/educational allowance is available.

### Out of scope for the first warehouse release

- Full-text PDF collection and copyrighted abstract redistribution.
- Automatic scientific gap verification, researcher quality scoring, grant outcome prediction or causal claims.
- Real-time streaming, guaranteed immediate source updates or provider-independent point-in-time history.
- Paid APIs, paid infrastructure, mandatory Snowflake, paid Power BI sharing, paid model APIs or GPUs.
- Public multi-tenant web app until the warehouse and metrics are validated.

## Sources and initial corpus

OpenAlex is the scholarly graph source; Crossref supports DOI metadata and index-date changes; arXiv adds preprints and versions; DataCite adds registered datasets/software and other research objects; Zenodo adds repositories and versioned outputs. The source strategy is in `docs/sources.md`.

The candidate OpenAlex topic IDs `T10743`, `T12423`, and `T12479` are not final. The proposed 2016–2025 baseline and 2026 partial period remain proposals until source profiling confirms counts and relevance. The 30,000–60,000 target is an engineering target, not a verified count or hard cap. Do not sum source counts as unique records because the sources overlap.

## Architecture

Five independent connectors feed immutable raw landing and manifests, then staging/validation/quarantine, source identity resolution, a canonical research-output warehouse, a PaperSonar analytical mart, reporting views and local BI. The target architecture is `docs/architecture/diagrams/07_Target_architecture_v2.png`.

## Data model direction

The existing 15-table/89-field publication model is retained as a legacy first mart. It does not alone represent all five sources. Before Phase 2, approve the source-neutral entities `research_output`, `source_record`, `output_version`, `output_relationship`, `output_observation`, `source_sync_state`, and topic/creator/institution/funder bridges. See the v2 data dictionary and architecture notes.

## Analytical questions

The v2 dictionary contains 18 candidate questions, including publication/output growth, share, citation cohorts and gains, topic intersections, venue/repository activity, institutional concentration, OA coverage, creator activity, citation/relationship flows, metadata coverage, counting sensitivity, partial-year comparisons, linked datasets/software, cross-source matching, preprint version evolution and funder participation. Queries and dashboards are not implemented.

## Non-functional requirements

- Free-only, local-first reproducibility.
- Source-native IDs and DOI normalization; no title-only automatic merge.
- Source provenance, extraction manifests, checksums and versioned configurations.
- Idempotent replay, independent source watermarks, overlap and periodic reconciliation.
- A partial or failed source run cannot publish a warehouse snapshot or advance a watermark.
- Missing metadata is not zero; absence from a partial page is not deletion.
- Resource limits and free quotas are measured before the full corpus is committed.
- Every comparison shows cutoff, corpus version, observation date, counting method and known limitations.

## Delivery phases

1. **Phase 1 (30%):** design and documents. Expanded source and architecture design is prepared; the old individual documents must be reconciled with the v2 baseline before final submission.
2. **Phase 2 (40%, not started):** implement source harvesters, staging/DW/reporting schemas, data cleaning, surrogate-key loads, 100+ dimension records, 10,000+ fact records, and quality reports.
3. **Phase 3 (30%, not started):** implement analytical SQL, ROLLUP, CUBE, reporting views, query-plan/index comparison, Power BI pages, screenshots, insights report and presentation.

## Success conditions

- Source profiling yields a defensible, versioned corpus boundary.
- Five source connectors each have documented, tested pagination, watermark, replay and quota behaviour before full harvest.
- Canonical matching conflicts are visible and never silently merged.
- Warehouse grains and counts reconcile, with measurable coverage and data-quality outputs.
- Analytical metrics can be traced to source records and have explicit denominators.
- Full required evaluation deliverables can be reproduced without a paid service.

## Main limitations

Source coverage is uneven and overlapping; topic taxonomies and metadata change; citation history begins at local observation; Crossref is not independent citation ground truth from OpenAlex; arXiv version/preprint identity needs care; DataCite and Zenodo overlap; creator/institution identity can be missing; source updates are not instantaneous; and a sparse intersection is not proof of novelty.
