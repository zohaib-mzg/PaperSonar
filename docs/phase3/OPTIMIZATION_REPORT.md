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

1. Run each statement three ways and save all three artefacts:
   * `EXPLAIN USING JSON <statement>` → `BENCHn_plan_before.json`
     (bytes scanned, partitions scanned and pruned)
   * `EXPLAIN ANALYZE <statement>` → `BENCHn_analyze_before.txt`
     (execution time)
   * `<statement>` → `BENCHn_before.csv` (the result, which must not change)
2. Apply the clustering keys from `sql/06_facts/03_phase3_clustering.sql`
   and wait for the re-clustering to finish.
3. Repeat step 1 with the `after` file names.
4. Keep the keys only if the measured execution time or bytes scanned
   improved on the hot statements. Otherwise run the rollback statement at
   the end of that file.

The measured statement is always the deployed statement: nothing is edited
between the before and the after run, because a benchmark that measures a
different query measures nothing.

## 3. Baseline artefacts

| Artefact | Content | Saved |
|---|---|---|
| `BENCH1_before.csv` | the topic growth scan result (48 topic rows with 2023/2025 counts) | `docs/phase3/evidence/03_optimization/BENCH1_before.csv` |
| `BENCH2_before.csv` | the intersection result (3 reportable topic pairs) | `docs/phase3/evidence/03_optimization/BENCH2_before.csv` |
| `BENCH1_plan_before.json`, `BENCH2_plan_before.json` | bytes scanned and partition pruning | *pending the after-run* |
| `BENCHn_analyze_before.txt` | execution time per statement | *pending the after-run* |

The two result files are committed now because they are also the evidence for
Q01 and Q05; the plan and timing artefacts are added when the owner runs the
measurement forms.

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

*Filled in from the measured artefacts after the after-run.*

| Benchmark | Execution time before | Execution time after | Delta | Bytes before | Bytes after | Delta | Partitions pruned before → after |
|---|---:|---:|---:|---:|---:|---:|---|
| BENCH1 | *pending* | *pending* | *pending* | *pending* | *pending* | *pending* | *pending* |
| BENCH2 | *pending* | *pending* | *pending* | *pending* | *pending* | *pending* | *pending* |
| BENCH3 | *pending* | *pending* | *pending* | *pending* | *pending* | *pending* | *pending* |
| BENCH4 | *pending* | *pending* | *pending* | *pending* | *pending* | *pending* | *pending* |

**Decision:** *pending the measurement.*

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
   `after` result files must be identical; if they are not, something else
   changed and the measurement is void.
5. **A negative result is a valid result.** If the measurement shows no
   improvement, the rollback in `sql/06_facts/03_phase3_clustering.sql` is
   the correct action and the report says so. The physical-design extras
   (materialized view, dynamic table) stay undeployed for the same reason:
   they are in `sql/07_reporting/02_physical_demos.sql`, marked
   `-- Deploy: manual`, and are never created without measured benefit.
