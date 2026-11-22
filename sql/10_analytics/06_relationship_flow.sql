-- =============================================================================
-- PaperSonar Phase 3 - Q11 citation flow between topic communities (READ-ONLY)
-- =============================================================================
-- Purpose: Answer the Phase 1 citation-flow question from the published
--          corpus.
--          Q11 Which selected topic communities cite one another.
-- Inputs: PROJECT_DW.FACT_OUTPUT_RELATION, BRIDGE_OUTPUT_TOPIC_CATEGORY,
--         FACT_RESEARCH_OUTPUT, PROJECT_AUDIT.PUBLISHED_BATCH.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/01_queries/Q11_topic_citation_flow.csv.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: year window 2021-2025 for the citing endpoint.
-- Cost: joins the relation fact (about 1.8m rows) to the primary category of
--       both endpoints; run on WH_PAPERSONAR_ELT outside peak time.
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================
-- The relation fact keeps unresolved targets as identifiers; only edges whose
-- target resolved to an admitted output are counted, and both endpoints must
-- be admitted. Direction is preserved: citing topic -> cited topic.

-- ---------------------------------------------------------------------------
-- Q11 - Which selected topic communities cite one another
-- Decision. Find intellectual links that a title search may miss.
-- Measure. Count current citation pairs with both endpoints admitted, grouped
--         by citing and cited primary topic. Keep direction.
-- Analysis. Filter citing year and inspect edge-level evidence.
-- Limit. This is an induced subgraph. It cannot reproduce global citation
--        totals.
-- ---------------------------------------------------------------------------
WITH published_output AS (
  SELECT DISTINCT fact.OUTPUT_SK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  JOIN PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    ON published.BATCH_ID = fact.LAST_BATCH_ID
),
primary_category AS (
  SELECT
    bridge.OUTPUT_SK,
    bridge.CATEGORY_KEY
  FROM PAPERSONAR.PROJECT_DW.BRIDGE_OUTPUT_TOPIC_CATEGORY bridge
  JOIN published_output output
    ON output.OUTPUT_SK = bridge.OUTPUT_SK
  WHERE bridge.IS_PRIMARY
    AND bridge.CATEGORY_KEY <> 'unclassified'
),
citing_output AS (
  SELECT
    relation.OUTPUT_SK       AS CITING_OUTPUT_SK,
    relation.TARGET_OUTPUT_SK AS CITED_OUTPUT_SK,
    fact.PUBLICATION_YEAR    AS CITING_YEAR,
    relation.SOURCE_NAME
  FROM PAPERSONAR.PROJECT_DW.FACT_OUTPUT_RELATION relation
  JOIN PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
    ON fact.OUTPUT_SK = relation.OUTPUT_SK
  JOIN published_output citing
    ON citing.OUTPUT_SK = relation.OUTPUT_SK
  JOIN published_output cited
    ON cited.OUTPUT_SK = relation.TARGET_OUTPUT_SK
  WHERE relation.RELATION_TYPE = 'REFERENCES'
    AND relation.TARGET_OUTPUT_SK IS NOT NULL
    AND fact.PUBLICATION_YEAR BETWEEN 2021 AND 2025
)
SELECT
  citing_category.CATEGORY_KEY      AS CITING_TOPIC,
  citing_category.CATEGORY_LABEL    AS CITING_TOPIC_LABEL,
  cited_category.CATEGORY_KEY       AS CITED_TOPIC,
  cited_category.CATEGORY_LABEL     AS CITED_TOPIC_LABEL,
  COUNT(*)                          AS CITATION_PAIRS,
  COUNT(DISTINCT citing.CITING_OUTPUT_SK) AS CITING_OUTPUTS,
  COUNT(DISTINCT citing.CITED_OUTPUT_SK)  AS CITED_OUTPUTS,
  CURRENT_DATE() AS RETRIEVED_ON
FROM citing_output citing
JOIN primary_category citing_category
  ON citing_category.OUTPUT_SK = citing.CITING_OUTPUT_SK
JOIN primary_category cited_category
  ON cited_category.OUTPUT_SK = citing.CITED_OUTPUT_SK
GROUP BY 1, 2, 3, 4
ORDER BY CITATION_PAIRS DESC;

-- ---------------------------------------------------------------------------
-- Q11 companion - the most frequent citing/cited output pairs behind a topic
--                  flow, for edge-level inspection
-- ---------------------------------------------------------------------------
WITH published_output AS (
  SELECT DISTINCT fact.OUTPUT_SK
  FROM PAPERSONAR.PROJECT_DW.FACT_RESEARCH_OUTPUT fact
  JOIN PAPERSONAR.PROJECT_AUDIT.PUBLISHED_BATCH published
    ON published.BATCH_ID = fact.LAST_BATCH_ID
),
edge AS (
  SELECT
    relation.OUTPUT_SK        AS CITING_OUTPUT_SK,
    relation.TARGET_OUTPUT_SK AS CITED_OUTPUT_SK
  FROM PAPERSONAR.PROJECT_DW.FACT_OUTPUT_RELATION relation
  JOIN published_output citing
    ON citing.OUTPUT_SK = relation.OUTPUT_SK
  JOIN published_output cited
    ON cited.OUTPUT_SK = relation.TARGET_OUTPUT_SK
  WHERE relation.RELATION_TYPE = 'REFERENCES'
    AND relation.TARGET_OUTPUT_SK IS NOT NULL
)
SELECT
  citing_output.OUTPUT_SK,
  citing_output.DOI_NORMALIZED  AS CITING_DOI,
  citing_output.CATEGORY_KEY    AS CITING_TOPIC,
  cited_output.OUTPUT_SK        AS CITED_OUTPUT_SK,
  cited_output.DOI_NORMALIZED  AS CITED_DOI,
  cited_output.CATEGORY_KEY     AS CITED_TOPIC
FROM edge
JOIN PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT citing_output
  ON citing_output.OUTPUT_SK = edge.CITING_OUTPUT_SK
JOIN PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT cited_output
  ON cited_output.OUTPUT_SK = edge.CITED_OUTPUT_SK
ORDER BY CITING_TOPIC, CITED_TOPIC, CITING_OUTPUT_SK
LIMIT 1000;
