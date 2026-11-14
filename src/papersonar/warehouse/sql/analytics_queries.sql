-- analytics_queries.sql
-- Demonstration analytical queries proving the warehouse is queryable.
-- They run on real Snowflake against PROJECT_REPORTING views (migration 003)
-- and PROJECT_DW tables. Queries that depend on fields not yet populated are
-- labeled; until a live account exists their live execution is BLOCKED.
-- No result in this file is a claimed real-world count.

-- ---------------------------------------------------------------------------
-- Q1. Publications by publication year (uses VW_PUBLICATION_BY_YEAR)
--     Depends on: publication_year (populated by all sources when present).
-- ---------------------------------------------------------------------------
SELECT * FROM PROJECT_REPORTING.VW_PUBLICATION_BY_YEAR ORDER BY PUB_YEAR;

-- ---------------------------------------------------------------------------
-- Q2. Publications and open-access mix by winning source
--     Depends on: oa_status (OpenAlex/Crossref supply it; arXiv partially).
-- ---------------------------------------------------------------------------
SELECT * FROM PROJECT_REPORTING.VW_PUBLICATION_BY_SOURCE ORDER BY SOURCE_NAME, OA_STATUS;

-- ---------------------------------------------------------------------------
-- Q3. Topic activity over time: works per topic with publication-year span
--     Depends on: topics (OpenAlex primary topics; Crossref subjects).
-- ---------------------------------------------------------------------------
SELECT * FROM PROJECT_REPORTING.VW_TOPIC_ACTIVITY ORDER BY WORK_COUNT DESC;

-- ---------------------------------------------------------------------------
-- Q4. Open-access status distribution
-- ---------------------------------------------------------------------------
SELECT * FROM PROJECT_REPORTING.VW_OPENACCESS_STATUS ORDER BY WORK_COUNT DESC;

-- ---------------------------------------------------------------------------
-- Q5. Top venues by output volume
-- Depends on: venue_name (Crossref/OpenAlex; arXiv/Zenodo may be sparse —
-- see the missingness query in integrity_checks.sql check 12).
-- ---------------------------------------------------------------------------
SELECT * FROM PROJECT_REPORTING.VW_VENUE_OUTPUT ORDER BY WORK_COUNT DESC LIMIT 25;

-- ---------------------------------------------------------------------------
-- Q6. Citation-graph health: resolved vs unresolved reference edges by source
-- ---------------------------------------------------------------------------
SELECT * FROM PROJECT_REPORTING.VW_CITATION_RESOLUTION ORDER BY CITATION_EDGES DESC;

-- ---------------------------------------------------------------------------
-- Q7. Dataset/software outputs via DOI cross-source overlap:
--     canonical works whose DOI appears both as a publication (Crossref/
--     OpenAlex) and as a DataCite/Zenodo record — research-output linkage.
--     Depends on: DataCite/Zenodo ingestion having populated the crosswalk.
-- ---------------------------------------------------------------------------
SELECT
  w.DOI_NORMALIZED,
  COUNT(DISTINCT x.SOURCE_NAME) AS SOURCE_COUNT,
  LISTAGG(DISTINCT x.SOURCE_NAME, ', ') WITHIN GROUP (ORDER BY x.SOURCE_NAME) AS SOURCES_SEEN,
  w.TITLE
FROM PROJECT_DW.DIM_WORK w
JOIN PROJECT_DW.WORK_SOURCE_XW x ON x.DOI_NORMALIZED = w.DOI_NORMALIZED
WHERE w.DOI_NORMALIZED IS NOT NULL
GROUP BY w.DOI_NORMALIZED, w.TITLE
HAVING COUNT(DISTINCT x.SOURCE_NAME) >= 2
ORDER BY SOURCE_COUNT DESC, w.TITLE
LIMIT 100;

-- ---------------------------------------------------------------------------
-- Q8. Institution participation: canonical works per institution
--     Depends on: authorships with institution fields (OpenAlex supplies
--     these; other sources mostly do not).
-- ---------------------------------------------------------------------------
SELECT
  i.INSTITUTION_NAME,
  i.SOURCE_NAME AS INSTITUTION_SOURCE,
  COUNT(DISTINCT b.WORK_KEY) AS WORK_COUNT
FROM PROJECT_DW.BRIDGE_WORK_INSTITUTION b
JOIN PROJECT_DW.DIM_INSTITUTION i ON i.INSTITUTION_KEY = b.INSTITUTION_KEY
GROUP BY i.INSTITUTION_NAME, i.SOURCE_NAME
ORDER BY WORK_COUNT DESC
LIMIT 50;

-- ---------------------------------------------------------------------------
-- Q9. Operational: run history and per-source freshness for the last 7 days
-- ---------------------------------------------------------------------------
SELECT * FROM PROJECT_REPORTING.VW_INGEST_RUN_HISTORY ORDER BY STARTED_AT DESC LIMIT 20;

SELECT * FROM PROJECT_REPORTING.VW_SOURCE_SYNC_HEALTH ORDER BY SOURCE_NAME, STREAM_NAME;

-- ---------------------------------------------------------------------------
-- Q10. Quarantine review queue by reason (what needs human review today)
-- ---------------------------------------------------------------------------
SELECT * FROM PROJECT_REPORTING.VW_QUARANTINE_SUMMARY ORDER BY OPEN_ITEMS DESC;

-- ---------------------------------------------------------------------------
-- Q11. Publication counts by year AND source (single-query cross-cut)
-- ---------------------------------------------------------------------------
SELECT
  f.PUBLICATION_YEAR AS PUB_YEAR,
  f.SOURCE_PRIORITY  AS SOURCE_NAME,
  COUNT(*)           AS WORK_COUNT
FROM PROJECT_DW.FACT_PUBLICATION f
GROUP BY f.PUBLICATION_YEAR, f.SOURCE_PRIORITY
ORDER BY PUB_YEAR, SOURCE_NAME;
