# Decision 003: Five-source research-output scope

- **Status:** proposed Phase 1 design decision, 10 November 2026
- **Context:** a publication-only model and 20-record pilot are too narrow for a broader research/innovation intelligence product. Course Phase 2/3 implementation has not started.
- **Decision:** design around OpenAlex, Crossref, arXiv, DataCite and Zenodo; retain source-native records; introduce a canonical research-output entity and explicit typed relationships; keep a publication-focused analytics mart as a downstream view rather than the only warehouse entity.
- **Incremental policy:** independent source watermarks, fixed windows, overlap, durable page checkpoints, raw evidence, source-key upserts, change observations and periodic reconciliation.
- **Cost policy:** local PostgreSQL is the required zero-cost reference path. Snowflake is optional only under a genuinely no-cost trial/educational allowance and must not be a dependency.
- **Consequences:** the original 15-table publication-centered model and 89-field dictionary require reconciliation with the expanded logical model before physical implementation. DataCite/Zenodo overlap and arXiv version identity require explicit handling.
- **Rejected:** silently merging on title, adding source result counts to estimate unique outputs, treating absence from a page as deletion, claiming a sparse intersection proves novelty, or requiring Snowflake to reproduce results.
