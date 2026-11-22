# Phase 3 Optimization Report — measured before and after clustering

**Date:** 2026-11-22 · **Branch:** `phase3` · **Account:** NI15271 · **Warehouse:** `WH_PAPERSONAR_ELT` (X-Small, 60-second auto-suspend)

---

## 1. What was measured and why

Four representative statements were measured, because they are the statements
the project actually runs:

| Benchmark | Statement | Why it is representative | Cost driver |
|---|---|---|---|
| BENCH1 | topic growth scan (Q01) | the BI page 1 statement | two passes over the published output view (296,299 rows) |
| BENCH2 | topic intersection self-join (Q05) | the sparsest and most selective analytical query | self-join over the category bridge (894,545 rows) |
| BENCH3 | directed topic citation flow (Q11) | the largest join in the project | 2,557,842 relation rows, 94,912 with a resolved target |
| BENCH4 | `VW_RESEARCH_COMMUNITY` | the heaviest reporting view (BI page 3) | author bridge (712,088 rows) joined to the institution bridge (193,786 rows) |

The baseline layout is **cluster-free**. That is deliberate: with a corpus of
this size the benefit of clustering has to be measured, not assumed.

## 2. Method

1. Run each statement and save the artefacts:
   * `<statement>` → `BENCHn_before.csv` (the result, which must not change)
   * `EXPLAIN USING JSON <statement>` → `BENCHn_plan_before.csv`
     (the logical operator tree)
   * the Snowsight query profile → compilation, queueing, execution and total
     time, recorded in `BENCH_TIMINGS.csv`. `EXPLAIN ANALYZE` is not available
     in this account, so the profile is the timing measurement of record.
2. Apply the clustering keys from `sql/06_facts/03_phase3_clustering.sql`
   and wait for the re-clustering to finish.
3. Repeat step 1 with the `after` file names.
4. Keep the keys only if the measured execution time or bytes scanned
   improved on the hot statements. Otherwise run the rollback statement at
   the end of that file.

The measured statement is always the deployed statement: nothing is edited
between the before and the after run, because a benchmark that measures a
different query measures nothing.

## 3. Artefacts

All sixteen artefacts are committed under `docs/phase3/evidence/03_optimization/`:

| Artefact | Content |
|---|---|
| `BENCHn_before.csv`, `BENCHn_after.csv` | the result of the plain statement, before and after the change (n = 1…4) |
| `BENCHn_plan_before.csv`, `BENCHn_plan_after.csv` | the `EXPLAIN USING JSON` operator tree, before and after (the JSON plan inside a CSV cell, as Snowsight downloads it) |
| `BENCH_TIMINGS.csv` | the measured compilation, queueing, execution and total times for both runs |
| `BENCH1_before.csv`, `BENCH2_before.csv` | the same two result files as the evidence for Q01 and Q05 |

`EXPLAIN ANALYZE` is not available in this account, so the timing comes from
the Snowsight query profile panel instead: compilation time, queued
provisioning time, execution time and total time. The JSON plan is the
logical operator tree above the secure views and reports `bytesAssigned: 0`,
so bytes scanned could not be read from it — the profile is the measurement of
record for this report.

**Validity of the pair.** The four plan files are byte-identical before and
after, and each result pair contains exactly the same rows with the same
values: BENCH1 81 rows, BENCH2 4 rows, BENCH3 725 rows, BENCH4 58,421 rows.
Only the order of rows with equal sort keys differs (for example the two topic
pairs with 9 joint works swap places), which is the expected non-deterministic
tie-break of `ORDER BY`. The physical change moved no data and changed no
result.

## 4. The change under test

```sql
ALTER TABLE PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT
  CLUSTER BY (PUBLICATION_YEAR, SOURCE_NAME);

ALTER TABLE PAPERSONAR.PROJECT_DW.FACT_OUTPUT_RELATION
  CLUSTER BY (RELATION_TYPE, OUTPUT_SK);

ALTER TABLE PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY
  CLUSTER BY (OUTPUT_SK, CATEGORY_KEY);
```

| Table | Rows | Key | Rationale |
|---|---:|---|---|
| `FACT_RESEARCH_OUTPUT` | 296,299 | publication year, source | every analytical statement filters on the year and groups by the source |
| `FACT_OUTPUT_RELATION` | 2,557,842 | relation type, output key | the citation flow filters on the relation type and joins on the output key |
| `BRIDGE_OUTPUT_TOPIC_CATEGORY` | 894,545 | output key, category key | the intersection statement joins the bridge to itself on the output key |

**Cost of the change:** re-clustering rewrites the three tables and consumes
credits once. That is why the decision is measurement-driven and why the
rollback statement ships in the same file.

## 5. Result

### 5.1 The measured numbers

Single run of each statement, same X-Small warehouse, same data snapshot,
before and after the three clustering keys were applied.

| Benchmark | Result rows | Execution before | Execution after | Δ execution | Total before | Total after | Δ total |
|---|---:|---:|---:|---:|---:|---:|---:|
| BENCH1 topic growth | 81 | 2 ms | 1,000 ms | +998 ms | 1,200 ms | 1,600 ms | +400 ms |
| BENCH2 intersections | 4 | 531 ms | 570 ms | +39 ms (+7%) | 1,200 ms | 1,500 ms | +300 ms |
| BENCH3 citation flow | 725 | 789 ms | 890 ms | +101 ms (+13%) | 1,200 ms | 1,200 ms | 0 ms |
| BENCH4 community view | 58,421 | 2 ms | 1,600 ms | +1,598 ms | 562 ms | 1,900 ms | +1,338 ms |

### 5.2 Reading the numbers

**No statement got faster.** The two statements that ran for real before the
change (BENCH2 and BENCH3) got 7% and 13% slower after it, and the two that
finished in 2 ms before the change were the two that took seconds after it.

The 2 ms executions are the signature of a Snowflake **result-cache hit**: the
identical statement had already been run against unchanged data, so Snowflake
returned the cached result. `ALTER TABLE … CLUSTER BY` rewrites the physical
layout of the table and invalidates the cached results that depend on it, so
the after-run had to execute the query for real. The before-run was therefore
not a cold measurement of the same work — it was a cache lookup — and the
comparison overstates the cost of the change rather than measuring it.

The two honest numbers are BENCH2 and BENCH3, where both runs executed:
**+39 ms and +101 ms**. Both statements are the ones that touch the clustered
tables (`BRIDGE_OUTPUT_TOPIC_CATEGORY` and `FACT_OUTPUT_RELATION`), and both
got slower, by an amount small enough to be noise on a shared trial warehouse
but certainly not an improvement.

### 5.3 Why the change cannot pay off at this scale

- The whole fact table is 296,299 rows, the bridge 894,545 rows and the
  relation fact 2,557,842 rows. On an X-Small warehouse those are scanned in
  hundreds of milliseconds, so the pruning that clustering buys cannot repay
  the re-clustering cost.
- Two of the four statements read through a **secure view**
  (`VW_RESEARCH_OUTPUT`, `VW_RESEARCH_COMMUNITY`). Snowflake's clustering
  pruning is applied to the physical tables underneath; the benefit reaches
  the query only if the predicates line up with the clustering key, and the
  JSON plan shows no predicate push-down into the view at all.
- Clustering keys are a continuous cost as well as a one-off one: every later
  write that does not match the key order triggers background re-clustering,
  and on a 2.5-million-row table that is real warehouse time on a trial
  account with 23 days and $328 of credits left.

### 5.4 Decision

**The clustering keys are rolled back.** The rule fixed before the measurement
was "keep the keys only if the measured execution time or bytes scanned
improved on the hot statements"; they did not improve on any statement, so the
project keeps the simpler cluster-free layout and records the negative result
instead of hiding it.

The rollback statements are at the end of `sql/06_facts/03_phase3_clustering.sql`
and in §7 below. Rolling back restores the baseline layout and does not change
a single row of data.

**When to revisit this decision.** Clustering is not a bad idea in general; it
is a bad deal at this size. The trigger for re-measuring is corpus growth:
when `FACT_OUTPUT_RELATION` passes roughly 25 million rows or the analytical
tables pass five million, the pruning effect becomes visible and the same
before/after measurement should be run again with three repetitions per
statement and a cold warehouse, so that the result cache cannot distort it.

## 6. Caveats that apply to whatever the measurement says

1. **Hardware.** Everything ran on one X-Small warehouse with a 60-second
   auto-suspend, on a trial account. A larger warehouse would change the
   absolute numbers; only the relative before/after comparison on the same
   warehouse is meaningful.
2. **Data volume.** 296,299 outputs, 894,545 category assignments and
   2,557,842 relation rows. Clustering pays off by pruning micro-partitions,
   so the benefit scales with the size of the table and the selectivity of
   the predicate. At this volume the effect is expected to be modest, and a
   modest measured effect is reported as a modest effect.
3. **Single environment.** There is one account, one warehouse size and one
   data snapshot. No result is generalized beyond that environment.
4. **Clustering is a physical layout change, not a logical one.** It changes
   how the same query is executed, never what it returns. The `before` and
   `after` result files contain the same rows and the same values; only the
   order of tied rows differs, which is the expected non-deterministic
   tie-break of `ORDER BY`. If a row or a value had differed, the measurement
   would have been void.
5. **A negative result is a valid result.** The measurement showed no
   improvement, so the rollback in `sql/06_facts/03_phase3_clustering.sql` is
   the action taken and this report says so. The physical-design extras
   (materialized view, dynamic table) stay undeployed for the same reason:
   they are in `sql/07_reporting/02_physical_demos.sql`, marked
   `-- Deploy: manual`, and are never created without measured benefit.
6. **One run per statement.** Each statement was measured once, on a trial
   warehouse that is shared and that suspends after 60 seconds, so the
   absolute numbers carry single-run noise. The before-run was further
   distorted by the result cache (§5.2). The conclusion rests on the
   direction of every difference — slower in all four cases — and not on the
   size of any single delta.
7. **The `ALTER TABLE` was asynchronous.** Snowflake re-clusters in the
   background, so the after-run may have overlapped with background
   re-clustering work. That can only make the after-run look worse, not
   better, which is consistent with the measured direction but does not
   exclude a small benefit once the re-clustering has settled.

## 7. The rollback

```sql
USE ROLE PAPERSONAR_ADMIN;
USE WAREHOUSE WH_PAPERSONAR_ELT;

ALTER TABLE PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT
  DROP CLUSTERING KEY;

ALTER TABLE PAPERSONAR.PROJECT_DW.FACT_OUTPUT_RELATION
  DROP CLUSTERING KEY;

ALTER TABLE PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY
  DROP CLUSTERING KEY;

SHOW TABLES LIKE 'FACT_RESEARCH_OUTPUT' IN SCHEMA PAPERSONAR.PROJECT_DW;
SHOW TABLES LIKE 'FACT_OUTPUT_RELATION' IN SCHEMA PAPERSONAR.PROJECT_DW;
SHOW TABLES LIKE 'BRIDGE_OUTPUT_TOPIC_CATEGORY' IN SCHEMA PAPERSONAR.PROJECT_DW;
```

The three `SHOW TABLES` statements must report `clustering_key` as empty for
every table. The rollback changes the physical layout only; the row counts,
the query results and the published batches stay exactly as they are, and
`docs/phase3/evidence/03_optimization/` keeps the before-and-after evidence
of the change that was tested and rejected.
