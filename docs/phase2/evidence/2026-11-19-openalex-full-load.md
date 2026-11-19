# Live evidence — OpenAlex full backfill 2026-11-17..18

Captured 2026-11-19 UTC with `PAPERSONAR_ADMIN` for SQL/task queries and
`PAPERSONAR_LOADER` for extraction. Query IDs are Snowflake `sfqid` values;
no credentials or account identifiers are recorded.

> **Scheduler note:** this run happened while the root still had a 03:00 UTC
> cron. The current version has no Snowflake `SCHEDULE`; GitHub Actions is the
> only scheduler. The graph execution and publication evidence remains valid.

## Extraction

Command:

```powershell
.venv\Scripts\python.exe -u -m runner.cli extract --source openalex --mode full --from 2026-11-17 --until 2026-11-18 --no-task --json
```

- Batch: `BATCH_07D9668D4CBED88D815D30CA`
- Mode: `full`; window `2026-11-17` through `2026-11-18`
- `FILE_COUNT = 5`
- `RECORD_COUNT = 168725`
- `CURSOR_END = NULL`
- `ERROR_SUMMARY = NULL`
- Local shard line counts: `34900`, `37000`, `37100`, `33500`, `26225`
- Unique local work IDs: `168725`; duplicates: `0`
- All 5 manifests: no missing DOI, publication dates inside the window,
  status `REGISTERED`, and local/staged counts match.
- Evidence log: `data/extract/logs/openalex-full-2026-11-17_2026-11-18-resume.log`

`--no-task` was intentional: it let the staged batch be verified before the SQL
task graph was executed. The graph was then triggered manually and drained to
publication.

## SQL task graph — final successful pass

`PROJECT_AUDIT.BATCH`: `PUBLISHED`, `5` files, `168725` records, `CURSOR_END`
`NULL`, `ERROR_SUMMARY` `NULL`. Batch query:
`01c8854f-0003-1d89-000f-64e20021dcde`.

`PUBLISHED_BATCH`:

| BATCH_ID | PUBLISHED_AT | DQ_SUMMARY |
|---|---|---|
| `BATCH_07D9668D4CBED88D815D30CA` | 2026-11-19 09:58:29.390 | `critical_failures=0;total_failures=2` |

Query: `01c8854f-0003-1d11-000f-64e200217002`.

Final successful `RUN_LOG` rows (stage, status, query ID):

| Stage | Status | Query ID |
|---|---|---|
| COPY | RUNNING (completed, no error) | `01c88534-0003-1d89-000f-64e20021dc12` |
| BRONZE | RUNNING (completed, no error) | `01c88535-0003-1d0f-000f-64e20021049a` |
| SILVER | RUNNING (completed, no error) | `01c88535-0003-1d11-000f-64e200216f2a` |
| CATEGORIZE | RUNNING (completed, no error) | `01c88535-0003-1d11-000f-64e200216f62` |
| DIMENSIONS | RUNNING (completed, no error) | `01c88535-0003-1d0f-000f-64e2002104e6` |
| FACTS | RUNNING (completed, no error) | `01c88535-0003-1d96-000f-64e20021a0aa` |
| DQ | RUNNING (completed, no error) | `01c88536-0003-1d89-000f-64e20021dc8e` |
| PUBLISH | SUCCEEDED | `01c88536-0003-1d11-000f-64e200216fc6` |
| FINALIZER | PUBLISHED (`ROW_COUNT = 2`) | no query ID (control row) |

Earlier failed attempts are retained in `RUN_LOG` and were fixed before this
pass: COPY bind variable/file format/metadata identifier, SILVER title
truncation, DIMENSIONS and FACTS JSON-null author keys.

All 10 `PROJECT_AUDIT.TASK_ELT_*` tasks report `state = started`. Query:
`01c8854f-0003-1d89-000f-64e20021dcea`.

## Data verification

| Check | Value | Query ID |
|---|---|---|
| `BRZ_OPENALEX_WORK` rows | `168725` | `01c8854f-0003-1d0f-000f-64e20021060a` |
| Distinct `SOURCE_RECORD_ID` | `168725` | same |
| Duplicate work IDs | `0` | same |
| `STG_OPENALEX_WORK` rows for batch | `168725` | `01c8854f-0003-1d89-000f-64e20021dce2` |
| `SLV_SOURCE_OBSERVATION` rows for batch | `168725` | `01c8854f-0003-1d89-000f-64e20021dce6` |
| `FILE_LOAD_LOG` status `MATCH` | `5` rows | `01c8854f-0003-1d11-000f-64e20021e006` |

Fact/bridge counts for the batch:

| Object | Rows |
|---|---|
| `FACT_RESEARCH_OUTPUT` | `168725` |
| `FACT_CITATION_SNAPSHOT` | `168725` |
| `FACT_OUTPUT_SOURCE_OBSERVATION` | `168725` |
| `FACT_OUTPUT_RELATION` | `665268` |
| `BRIDGE_OUTPUT_AUTHOR` | `341283` |
| `BRIDGE_OUTPUT_TOPIC_CATEGORY` | `168803` |
| `BRIDGE_AUTHOR_INSTITUTION` | `132574` |

Query: `01c8854f-0003-1d0f-000f-64e20021060e`.

## Data quality

All CRITICAL rules passed. Two WARNING rules failed, so publication proceeded
with `critical_failures=0`:

- `DQ-009` categorization coverage `0.034073` vs threshold `0.600000` (warning).
- `DQ-010` watermark freshness `999999` vs threshold `72` at DQ time. This is
  expected on the first backfill: DQ runs before PUBLISH, and no prior watermark
  existed. After publication the watermark is fresh (below).

Query: `01c8854f-0003-1d0f-000f-64e200210602`; DQ execution query in rows:
`01c88536-0003-1d89-000f-64e20021dc96`.

| Rule | Severity | Status |
|---|---|---|
| DQ-001 | CRITICAL | PASS |
| DQ-002 | CRITICAL | PASS |
| DQ-003 | CRITICAL | PASS |
| DQ-004 | CRITICAL | PASS |
| DQ-005 | CRITICAL | PASS |
| DQ-006 | CRITICAL | PASS |
| DQ-007 | CRITICAL | PASS |
| DQ-008 | WARNING | PASS |
| DQ-009 | WARNING | FAIL |
| DQ-010 | WARNING | FAIL |
| DQ-011 | CRITICAL | PASS |
| DQ-012 | CRITICAL | PASS |

## Watermark

`SOURCE_WATERMARK` after publication:

| SOURCE_NAME | ENTITY_NAME | WATERMARK_VALUE | WINDOW_START | WINDOW_END | LAST_BATCH_ID | STATUS |
|---|---|---|---|---|---|---|
| OPENALEX | WORK | `2026-11-19` | 2026-11-17 | 2026-11-18 | `BATCH_07D9668D4CBED88D815D30CA` | PUBLISHED |

`OVERLAP_DAYS = 0` in the published watermark row; the extractor config uses
`overlap_days: 1` for incremental windows. Query:
`01c8854f-0003-1d0f-000f-64e2002105fe`.

## Known limits of this evidence

- Live incremental OpenAlex extraction is **not** proven: `from_updated_date`
  returns HTTP 403 `Plan upgrade required` on the current plan. There is no
  fallback to publication dates.
- The zero-record/nothing-new path is covered by unit tests only, not by a live
  OpenAlex incremental request.
- `ACCOUNTADMIN` setup grants in `sql/00_setup/` were not applied to the account
  by this run; the inline JSON file format in `SP_COPY_BATCH` avoids requiring
  USAGE on `FF_NDJSON_GZ` for the service roles.
