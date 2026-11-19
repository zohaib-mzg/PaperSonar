# PaperSonar Pipeline Flow — Plain Language Guide

This document explains the **whole data journey** without going into code details:
when new data arrives, who starts the work, where the data lands first, how it
moves through Snowflake, and where the final usable data is stored.

If you only remember one thing:

> **GitHub Actions is the only scheduler. It wakes up every day at 02:30 UTC,
> fetches new/changed research records, puts them into Snowflake, and then asks
> Snowflake to process them. Snowflake does not wake itself up.**

---

## 1. The short answer

| Question | Answer |
|---|---|
| When does incremental load come? | Every day at **02:30 UTC** through GitHub Actions. Manual runs are also possible. |
| Is there a Snowflake schedule? | **No.** The Snowflake root task is deliberately suspended and is started only by GitHub. |
| What is a “full load”? | A one-time large initial load. It is **not** part of the daily schedule. |
| What does incremental mean here? | Fetch only records that were **created or changed recently**, using each source’s update/change information. It does **not** use publication dates for daily loading. |
| Where does data land first? | On the GitHub runner as compressed raw files, then in Snowflake’s internal **RAW_STAGE**. |
| Where does final data land? | In Snowflake reporting views, backed by finished fact/dimension tables. Only published batches are visible there. |
| Does every run insert new rows? | No. A run can find zero new/changed records and still finish cleanly with zero rows loaded. |
| Can the same record be fetched twice? | Yes, on purpose, because sources can be late. Bronze updates the existing record instead of creating a duplicate. |

---

## 2. The main players

| Player | Plain-language job |
|---|---|
| **GitHub Actions** | The traffic controller. It runs on a timer, calls the source APIs, uploads files, and starts the Snowflake processing chain. |
| **Python runner** | The courier. It only fetches raw records, writes compressed files, uploads them, and records what was delivered. It does not clean or reshape research data. |
| **Snowflake RAW_STAGE** | The loading dock. Raw compressed files wait here before Snowflake reads them. |
| **Snowflake task graph** | The assembly line. A fixed sequence of Snowflake steps transforms raw data into trusted tables. |
| **Audit tables** | The logbook. They remember each batch, which files arrived, which steps ran, which checks passed, and what was published. |
| **Reporting views** | The shop window. They show only data from batches that passed the quality gate and were published. |

---

## 3. The full journey in one picture

```text
OpenAlex / Crossref / arXiv / DataCite / Zenodo APIs
                 |
                 |  GitHub runner asks for records in a date window
                 v
Compressed raw files on the GitHub runner
(data/extract, not committed to Git)
                 |
                 |  PUT upload
                 v
Snowflake internal RAW_STAGE
(raw gzip files + manifest)
                 |
                 |  COPY
                 v
PROJECT_STAGING
(raw rows in STG_* tables, still unchanged)
                 |
                 |  Bronze merge
                 v
PROJECT_BRONZE
(one current row per source record id)
                 |
                 |  Silver projection + cleanup + identity matching
                 v
PROJECT_SILVER
(clean canonical outputs, source observations, crosswalks)
                 |
                 |  Categorization
                 v
Taxonomy assignments
                 |
                 |  Dimensions + facts
                 v
PROJECT_DW
(DIM_* dimensions, FACT_* facts, BRIDGE_* link tables)
                 |
                 |  Data quality gate
                 v
PROJECT_AUDIT
(DQ_RESULT, RUN_LOG, BATCH, PUBLISHED_BATCH, SOURCE_WATERMARK)
                 |
                 |  Publication
                 v
PROJECT_REPORTING
(views that expose only published batches)
```

Alongside this route, `PROJECT_REF` holds reference data such as taxonomy rules,
category keywords, expected keys, and DQ rule definitions.

---

## 4. When does the incremental load come?

### Automatic daily run

- GitHub Actions runs `extract-load.yml` at `30 2 * * *`, which means
  **02:30 UTC every day**.
- The workflow automatically uses:
  - `source = all`
  - `mode = incremental`
- It processes the enabled sources in this order:

```text
OpenAlex → Crossref → arXiv → DataCite → Zenodo
```

If OpenAlex is not confirmed as available for daily sync, it is skipped and the
other four sources still run.

Cron timing is not exact to the second. GitHub can delay a scheduled run slightly
during busy periods, but the intended time is 02:30 UTC.

### Manual run

You can also start it yourself:

**GitHub → Actions → extract-load → Run workflow**

Useful manual choices:

| Purpose | Settings |
|---|---|
| Safe check | `dry_run = true` |
| Real daily-style load | `mode = incremental`, `source = all` |
| One source only | Pick that source in `source` |
| One-time historical backfill | `mode = full` with explicit dates — use carefully, not daily |

### Important OpenAlex condition

OpenAlex incremental loading uses OpenAlex’s **updated-date feed**. That requires
an OpenAlex **Member+/Partner daily sync** entitlement.

- If `OPENALEX_DAILY_SYNC=true` is set as a GitHub repository variable (or passed
  as the workflow input), OpenAlex is included.
- If it is not set, OpenAlex is skipped in an all-source run with a warning.
- If someone explicitly chooses `source = openalex` and `mode = incremental`
  without confirmation, the workflow fails closed.

There is **no publication-date fallback** for OpenAlex incremental loading.

---

## 5. Full load vs incremental load

| Type | When to use | Date logic | Size | Scheduled? |
|---|---|---|---|---|
| **Full / backfill** | One-time initial load only | Publication-date range, exactly as given | Large: 100,000+ records possible | No |
| **Incremental** | Every day | Change/update dates plus a small overlap window | Usually small; can be zero | Yes, 02:30 UTC |

The completed OpenAlex full load was:

- Window: `2026-11-17` to `2026-11-18`
- Files: 5
- Records: 168,725
- Batch: `BATCH_07D9668D4CBED88D815D30CA`
- Final status: `PUBLISHED`

That was the one-time foundation load. Daily runs are different: they fetch what
changed since the last good point.

---

## 6. What “incremental” means for each source

Each source has its own way of saying “this record changed.” PaperSonar also
re-reads a small overlap window so late-arriving updates are not missed.

| Source | Change signal used | Look-back overlap |
|---|---|---|
| **OpenAlex** | `updated_date` | 1 day |
| **Crossref** | Indexed date | 2 days |
| **arXiv** | OAI record updates | 7 days |
| **DataCite** | Updated range | 2 days |
| **Zenodo** | OAI record updates | 7 days |

Example: if the last good OpenAlex point was 2026-11-19, the next run may re-read
part of 2026-11-18 as well. If a work changed again, Bronze updates the existing
row instead of adding another copy.

---

## 7. What is a batch?

A **batch** is one delivery unit:

```text
one source + one date window + one set of compressed files
```

Every batch gets a deterministic ID. If a run is interrupted and restarted, it
returns to the same batch rather than creating a new one.

A batch status usually moves like this:

```text
REGISTERED → LOADED → PROCESSING → PUBLISHED
```

If something serious fails, it does not reach `PUBLISHED`. The failure is written
to the audit tables.

### What are shards?

Large windows are split into several compressed files called **shards**. This is
like splitting a big delivery into numbered boxes. If the process stops after box
3, it can resume from box 4 instead of starting again from box 1.

---

## 8. Where data lands, step by step

### Step 1 — Source APIs

GitHub asks each source for records in the current window.

Only raw source records are collected. Python does not clean fields, assign keys,
deduplicate, categorize, or decide what is important.

### Step 2 — Local temporary files on the GitHub runner

The runner writes gzip-compressed NDJSON files under:

```text
data/extract/
```

These files are temporary working files and are ignored by Git. They are not the
final store.

### Step 3 — Snowflake internal RAW_STAGE

The files are uploaded to Snowflake’s internal stage:

```text
@PAPERSONAR.PROJECT_STAGING.RAW_STAGE
```

A manifest is also registered so Snowflake knows exactly which files belong to
which batch and how many records they should contain.

At this point the batch is marked `LOADED`.

### Step 4 — STAGING tables

Snowflake copies the raw files into staging tables such as:

- `STG_OPENALEX_WORK`
- `STG_CROSSREF_WORK`
- `STG_ARXIV_RECORD`
- `STG_DATACITE_DOI`
- `STG_ZENODO_RECORD`

These tables hold raw JSON envelopes plus file name, row number, and batch ID.
They are transient and reloadable from the raw stage.

### Step 5 — BRONZE tables

Bronze stores the current state of each source record, for example:

- `BRZ_OPENALEX_WORK`
- `BRZ_CROSSREF_WORK`
- `BRZ_ARXIV_RECORD`
- `BRZ_DATACITE_DOI`
- `BRZ_ZENODO_RECORD`

The important rule is: **one current row per source record id**.

If OpenAlex returns the same work again with a newer update, the existing bronze
row is updated. This is why overlap re-reading is safe.

### Step 6 — SILVER tables

Silver turns raw source shapes into a common research model:

- `SLV_SOURCE_OBSERVATION` — where the record was observed and from which source
- `SLV_OUTPUT_CROSSWALK` — links different source identifiers that seem to refer to the same output
- `SLV_RESEARCH_OUTPUT` — the clean, canonical research output record

Bad or unusable records are not silently dropped. They are quarantined or logged.

### Step 7 — Taxonomy / categorization

The system assigns research categories using the reference taxonomy and
deterministic rules. Category overrides can be applied from reference data.

This produces category assignments that later feed the bridge tables and
reporting views.

### Step 8 — Dimensions

Dimensions are the “lookup lists” and descriptive sides of the warehouse:

- date, source, output type, venue, access status, language, country, topic, category
- author and institution
- author history over time

Dimensions are **not truncated and reloaded**. Existing keys are kept stable.
Author changes can be tracked over time.

### Step 9 — Facts and bridges

Facts are the measurable core:

- `FACT_RESEARCH_OUTPUT` — one row per canonical research output
- `FACT_CITATION_SNAPSHOT` — citation counts at a point in time
- `FACT_OUTPUT_SOURCE_OBSERVATION` — which sources observed the output
- `FACT_OUTPUT_RELATION` — relationships between outputs, such as referenced works

Bridges connect outputs to many-valued things:

- `BRIDGE_OUTPUT_AUTHOR`
- `BRIDGE_OUTPUT_TOPIC_CATEGORY`
- `BRIDGE_AUTHOR_INSTITUTION`

### Step 10 — Data quality gate

Before anything is published, Snowflake runs the DQ rules.

- **Critical failures** block publication.
- **Warnings** are recorded but do not block.
- Counts are reconciled between staged files, staging tables, bronze, silver, and facts.

The live OpenAlex full load had **0 critical failures** and **2 warnings** related
to coverage and first-backfill freshness.

### Step 11 — Publication

If the DQ gate passes, the batch is published:

- `PUBLISHED_BATCH` gets a row.
- The batch becomes `PUBLISHED`.
- The source watermark advances to the last good change point **only for a complete window**.
- Reporting views can now expose the data.

For a full/backfill batch, the watermark is stamped with the current publication
date instead of the publication-date window end, because a publication-date range
is not a change-feed position. A batch stopped early by `max_records` has
`IS_CAPPED = TRUE` and is published for visibility, but its watermark does not
move; the unread remainder is never treated as processed.

### Step 12 — Finalizer

The finalizer records the final outcome in `RUN_LOG` and releases the batch claim.
It runs even when an earlier step fails, so failures are visible instead of
silently hanging.

---

## 9. How the Snowflake task graph runs

GitHub does not run each SQL file manually every day. Instead:

1. The SQL files create tables, procedures, and tasks inside Snowflake.
2. The task graph knows the order of the stages.
3. GitHub starts the root task once after all source batches are `LOADED`.
4. Snowflake then runs the chain automatically.

The chain is:

```text
Root: claim a LOADED batch
  → COPY
  → BRONZE
  → SILVER
  → CATEGORIZE
  → DIMENSIONS
  → FACTS
  → DQ
  → PUBLISH
  → FINALIZER (always runs)
```

Only one batch is claimed at a time. This prevents two runs from processing the
same global batch pointer.

### Why the root task is suspended

Snowflake will not allow a root task with no schedule/trigger to be resumed.
Because GitHub is the only scheduler, the root intentionally has no Snowflake
cron and stays **suspended**.

That is not a problem: Snowflake allows `EXECUTE TASK` to run a suspended root
task. The child tasks are resumed at deployment time so they can run when the
root is triggered.

**Do not manually resume the root task.**

---

## 10. How SQL files get into Snowflake

There are two different moments: **deployment** and **daily data processing**.

### Deployment — only when SQL/config/runner code changes

Deployment can happen through:

- GitHub Actions → `deploy-ci` → `DEPLOY`, or
- `python -m runner.cli deploy --sql-dir sql --yes`

During deployment:

1. SQL files are uploaded into Snowflake’s internal stage.
2. They are executed so tables, procedures, tasks, grants, and views exist.
3. One-time setup files are skipped because they require `ACCOUNTADMIN`.
4. Manual-only SQL files are skipped.
5. The task graph is recreated, child tasks are resumed, and the root is left suspended.

After deployment, check:

```sql
SHOW TASKS IN SCHEMA PAPERSONAR.PROJECT_AUDIT;
```

Expected state:

- 9 child/finalizer tasks: `started`
- `TASK_ELT_ROOT`: `suspended` — correct by design

### Daily data processing

Daily runs do not re-upload or re-read the SQL files. They call the procedures
that deployment already created.

So the daily flow is:

```text
GitHub timer → extraction → upload → batch LOADED → EXECUTE TASK root → SQL stages → published data
```

---

## 11. Where to look when you want to know “did it come?”

| Question | Where to look |
|---|---|
| Did GitHub run? | GitHub Actions → `extract-load` run history |
| Did files arrive? | `PROJECT_AUDIT.BATCH_MANIFEST`, `PROJECT_AUDIT.FILE_LOAD_LOG` |
| What is the batch status? | `PROJECT_AUDIT.BATCH` |
| Which stages ran? | `PROJECT_AUDIT.RUN_LOG` |
| Did quality checks pass? | `PROJECT_AUDIT.DQ_RESULT` |
| Was data published? | `PROJECT_AUDIT.PUBLISHED_BATCH` |
| Where is the next starting point? | `PROJECT_AUDIT.SOURCE_WATERMARK` |
| What is visible to users? | `PROJECT_REPORTING` views |

Useful check:

```sql
SELECT BATCH_ID, SOURCE_NAME, EXTRACTION_MODE, STATUS, RECORD_COUNT, FILE_COUNT
FROM PAPERSONAR.PROJECT_AUDIT.BATCH
ORDER BY CREATED_AT DESC
LIMIT 10;
```

---

## 12. Common situations

| Situation | What happens |
|---|---|
| No new records | Batch can load 0 rows and still finish cleanly. |
| A record was fetched before | Bronze updates the current row; no duplicate is added. |
| One source is late | Overlap windows re-read recent days to catch it. |
| OpenAlex plan is not active | OpenAlex is skipped in all-source runs; other sources still run. |
| Critical DQ rule fails | Batch is not published; reporting views do not show it. |
| A child task fails | Finalizer records the failure; inspect `RUN_LOG` and `DQ_RESULT`. |
| Someone resumes the Snowflake root | Not needed and can create a second scheduler. Leave it suspended. |
| Full/backfill is run again | Treat as exceptional; it is a large one-time-style load, not the daily path. |

---

## 13. Current live status

- The OpenAlex 2026-11-17..18 full load is `PUBLISHED`.
- It produced 168,725 unique work records with 0 duplicates.
- The Snowflake task graph was proven live.
- GitHub is now the only scheduler.
- OpenAlex incremental still requires Member+/Partner daily sync confirmation.
- The root task should remain suspended and be started only by GitHub.

More detail: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) and
[evidence/2026-11-19-openalex-full-load.md](evidence/2026-11-19-openalex-full-load.md).
