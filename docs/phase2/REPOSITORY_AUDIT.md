# PaperSonar Phase 2 repository audit

**Audit date:** 2026-11-14
**Audit commit:** `e9f6420` on branch `phase2` (parent: `6b6ac3f` = `origin/main` tip after PR #1 merge).
**Checkpoint policy:** Phase 1 evidence is preserved on `main` and `phase1`. This `phase2` branch is the working checkpoint; no destructive rewrite of Phase 1 artifacts is planned.

## 1. Repository tree summary

| Path | Contents |
|---|---|
| `README.md` | Project overview, five-source plan, target architecture, course alignment, roadmap |
| `docs/` | Project scope, five-source strategy, architecture v2 + diagrams (PNG/PDF/SVG/DOT), requirements, 3 decision records, Phase 1 submission artifacts (`docs/submissions/phase-1/`), Phase 2 agent implementation pack (`docs/agents/Phase2/`) |
| `database/schema/001_initial_schema.sql` | Legacy publication-centered PostgreSQL schema (15 tables, pre-v2 model) |
| `data/samples/` | Small pilot: 20 OpenAlex works, one Crossref DOI record, one topic response, CSV sample, retrieval manifest |
| `config/corpus.example.json` | Non-runnable corpus/source design contract |
| `.env.example` | Phase 1-era placeholders (PG + optional Snowflake) |
| `.gitignore` | Already ignores `.env`, raw/staging data dirs, logs, Python caches |

**Key finding: this is a documentation-only repository.** There is no Python package, no source connector code, no tests, no CI workflow, no dependency manifest, and no Snowflake SQL. All Phase 2 components must be created.

## 2. Requirement search results (Playbook 00 step 4)

Searched across the repository for: `OpenAlex`, `Crossref`, `arXiv`, `DataCite`, `Zenodo`, `checkpoint`, `watermark`, `cursor`, `Snowflake`, `GitHub Actions`, `fact_publication`, `fact_work_snapshot`, `fact_citation`, `etl_run`.

- All five source names, plus `checkpoint`/`watermark`/`cursor`: appear **only in documentation** (`docs/sources.md`, `docs/requirements/incremental-ingestion-design.md`, agent pack).
- `Snowflake`: documentation only (`docs/decisions/002-...md`, architecture README). No connector code.
- `GitHub Actions`: no matches in workflows (no `.github/` directory exists).
- `fact_publication`, `fact_work_snapshot`, `fact_citation`, `etl_run`: present in `database/schema/001_initial_schema.sql` (legacy PostgreSQL DDL) and in the v2 data dictionary/diagrams. No loading code.
- **No occurrences of these terms in executable code** — there is no executable code.

## 3. Current functional components

- **None.** The repository contains design documentation, diagrams, one legacy SQL file, and pilot data samples only.

## 4. Existing schema contracts

| Artifact | State | Authority |
|---|---|---|
| `database/schema/001_initial_schema.sql` | Legacy publication-centered PostgreSQL DDL (15 tables: `etl_run`, `dim_date`, `dim_topic`, `dim_venue`, `dim_work_type`, `dim_access_status`, `dim_author`, `dim_institution`, `dim_work`, `fact_publication`, `fact_work_snapshot`, `fact_citation`, 3 bridges) | Reference only — not Snowflake-compatible, predates the v2 source-neutral model |
| `docs/architecture/papersonar.dbml` | DBML of the same legacy model | Reference only |
| `docs/submissions/phase-1/v2/data-dictionary-v2.xlsx` + v2 diagrams | Expanded Phase 1 design baseline (source-neutral logical entities) | **Authoritative model direction** for Phase 2 warehouse reconciliation |
| `config/corpus.example.json` | Corpus boundary / source filter design contract | Input to ingestion configuration |

The Phase 1 baseline lists the same 15 table concepts recovered in Playbook 00 ("Recovered project baseline"); no discrepancy in the table list was found.

## 5. Existing tests and results

- **No tests exist.** Nothing to run; no test runner is configured.
- Command attempted: `python -m pytest` → would collect 0 tests (repository has no `tests/` directory yet).
- Baseline environment: Windows 10 (win32), Python 3.12.10, pip 26.2.1, Git available.
- Known environmental limitation: no Snowflake account access has been provided to the agent yet; live Snowflake tests will be **BLOCKED / NOT TESTED** until the account owner supplies no-cost credentials.

## 6. Missing components (to be created in Phase 2)

1. Python package + dependency manifest + lock/pinned requirements.
2. Typed runtime configuration with fail-closed validation (production target fixed to `snowflake`).
3. Secret-safe logging (redaction).
4. Raw payload + manifest persistence (append-only, checksummed).
5. Five source adapters: OpenAlex, Crossref, arXiv (OAI-PMH), DataCite (OAI-PMH/REST), Zenodo (OAI-PMH).
6. Staging/validation/quarantine and canonical identity resolution (DOI crosswalk, conflict quarantine).
7. Snowflake operational-state + dimensional warehouse DDL as versioned, repeatable, non-destructive migrations; `MERGE`-based idempotent loaders; integrity checks.
8. Orchestration (`backfill`, `sync`, `validate`, `load`, replay), retry/backoff, checkpoint durability rules.
9. Deterministic test suite (unit/contract/integration with mocked Snowflake adapter) + live smoke tests (blocked pending credentials).
10. GitHub Actions workflow (schedule + dispatch, concurrency lock, secret validation, Snowflake connectivity test, sync only).
11. Documentation: source capability matrix, runbook, configuration reference, acceptance report, limitations.

## 7. Files to add/update

**Add:** `pyproject.toml`, `src/papersonar/**` (config, logging, identifiers, raw_store, staging, canonical, sources/*, warehouse/*, orchestrator, cli), `tests/**` (unit/contract/integration + fixtures), `.github/workflows/papersonar-ingestion.yml`, `docs/phase2/` (capability matrix, runbook, acceptance report).

**Update in place:** `.env.example` (Snowflake-first placeholders, remove production PG switch), root `README.md` + `docs/README.md` (Phase 2 implementation status) — updates will clearly mark the production-target change rather than silently rewriting Phase 1 history.

## 8. Conflicts between repository and this pack

| # | Conflict | Resolution |
|---|---|---|
| 1 | Phase 1 README/architecture say the mandatory reproducible path is **local PostgreSQL**, with Snowflake as an *optional* compatibility target. Playbook 06 declares **Snowflake is the mandatory production warehouse** with no production fallback. | Follow the pack for Phase 2: production target is fixed to `snowflake`; PostgreSQL remains the Phase 1 reproducibility/design reference and is never selected by production configuration or CI. Document both statements' scopes explicitly in README updates. |
| 2 | `.env.example` still lists `PG*` variables and labels Snowflake "optional only". | Rewrite `.env.example` in Step 1: Snowflake settings as the mandatory production block, PG block removed from production use (kept only if needed for legacy local tooling with an explicit non-production comment). |
| 3 | Legacy DDL (`001_initial_schema.sql`) is PostgreSQL-only and publication-centered. | Kept as reference; new Snowflake-compatible migrations under `src/papersonar/warehouse/migrations/` reconcile against the v2 dictionary; differences documented, grain unchanged. |
| 4 | Playbook expects "existing ETL scripts" inspection; none exist. | Recorded in §3; nothing to preserve from code; Phase 1 evidence (docs + pilot data) preserved as-is. |

## 9. Verification plan baseline

Acceptance reporting will use `PASS` / `FAIL` / `BLOCKED` / `NOT TESTED` per Playbook 09, with a separate machine-readable test report. Live Snowflake and live-workflow verification cannot be claimed until the account owner completes no-cost Snowflake setup and adds GitHub secrets.
