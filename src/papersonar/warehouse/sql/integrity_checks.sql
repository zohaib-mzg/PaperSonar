-- integrity_checks.sql
-- Deep cross-table integrity and quality SQL for LIVE Snowflake runs.
--
-- These statements are too rich for the mock warehouse's limited SELECT
-- parser, so the quality gate runs the COUNT-based subset (see
-- papersonar/warehouse/quality.py) in every environment, while these join-based
-- checks are executed by an operator (or the scheduled workflow's validate
-- mode) against real Snowflake. Each statement prints its result via SELECT;
-- a nonzero count or TRUE flag indicates an anomaly to investigate.
--
-- Run with:  USE ROLE PAPERSONAR_INGEST; then execute statements in order.

-- 01. Unknown member seeds exist for every dimension that reserves one
SELECT 'dim_date_unknown_seed'    AS check_name, COUNT(*) AS rows_found
FROM PROJECT_DW.DIM_DATE WHERE DATE_KEY = 0
UNION ALL
SELECT 'dim_work_type_unknown_seed', COUNT(*)
FROM PROJECT_DW.DIM_WORK_TYPE WHERE WORK_TYPE_KEY = '-1'
UNION ALL
SELECT 'dim_access_status_unknown_seed', COUNT(*)
FROM PROJECT_DW.DIM_ACCESS_STATUS WHERE ACCESS_STATUS_KEY = '-1'
UNION ALL
SELECT 'dim_topic_unknown_seed', COUNT(*)
FROM PROJECT_DW.DIM_TOPIC WHERE TOPIC_KEY = '-1'
UNION ALL
SELECT 'dim_venue_unknown_seed', COUNT(*)
FROM PROJECT_DW.DIM_VENUE WHERE VENUE_KEY = '-1'
UNION ALL
SELECT 'dim_author_unknown_seed', COUNT(*)
FROM PROJECT_DW.DIM_AUTHOR WHERE AUTHOR_KEY = '-1'
UNION ALL
SELECT 'dim_institution_unknown_seed', COUNT(*)
FROM PROJECT_DW.DIM_INSTITUTION WHERE INSTITUTION_KEY = '-1';

-- 01b. Surrogate mapping and dimension keys are complete and unique after
-- migration 005. Every result must be zero. Standard-table PK constraints are
-- informational, so these checks provide the actual uniqueness evidence.
SELECT 'dimension_key_map_duplicate_business_key' AS check_name, COUNT(*) AS rows_found
FROM (
  SELECT DIMENSION_NAME, BUSINESS_KEY
  FROM PROJECT_DW.DIMENSION_KEY_MAP
  GROUP BY DIMENSION_NAME, BUSINESS_KEY HAVING COUNT(*) > 1
)
UNION ALL
SELECT 'dimension_key_map_duplicate_surrogate_key', COUNT(*)
FROM (
  SELECT SURROGATE_KEY FROM PROJECT_DW.DIMENSION_KEY_MAP
  GROUP BY SURROGATE_KEY HAVING COUNT(*) > 1
)
UNION ALL
SELECT 'dim_work_null_or_duplicate_sk', COUNT(*) FROM (
  SELECT WORK_SK FROM PROJECT_DW.DIM_WORK GROUP BY WORK_SK HAVING WORK_SK IS NULL OR COUNT(*) > 1
)
UNION ALL
SELECT 'dim_date_null_or_duplicate_sk', COUNT(*) FROM (
  SELECT DATE_SK FROM PROJECT_DW.DIM_DATE GROUP BY DATE_SK HAVING DATE_SK IS NULL OR COUNT(*) > 1
)
UNION ALL
SELECT 'dim_topic_null_or_duplicate_sk', COUNT(*) FROM (
  SELECT TOPIC_SK FROM PROJECT_DW.DIM_TOPIC GROUP BY TOPIC_SK HAVING TOPIC_SK IS NULL OR COUNT(*) > 1
)
UNION ALL
SELECT 'dim_venue_null_or_duplicate_sk', COUNT(*) FROM (
  SELECT VENUE_SK FROM PROJECT_DW.DIM_VENUE GROUP BY VENUE_SK HAVING VENUE_SK IS NULL OR COUNT(*) > 1
)
UNION ALL
SELECT 'dim_work_type_null_or_duplicate_sk', COUNT(*) FROM (
  SELECT WORK_TYPE_SK FROM PROJECT_DW.DIM_WORK_TYPE GROUP BY WORK_TYPE_SK HAVING WORK_TYPE_SK IS NULL OR COUNT(*) > 1
)
UNION ALL
SELECT 'dim_access_status_null_or_duplicate_sk', COUNT(*) FROM (
  SELECT ACCESS_STATUS_SK FROM PROJECT_DW.DIM_ACCESS_STATUS GROUP BY ACCESS_STATUS_SK
  HAVING ACCESS_STATUS_SK IS NULL OR COUNT(*) > 1
)
UNION ALL
SELECT 'dim_author_null_or_duplicate_sk', COUNT(*) FROM (
  SELECT AUTHOR_SK FROM PROJECT_DW.DIM_AUTHOR GROUP BY AUTHOR_SK HAVING AUTHOR_SK IS NULL OR COUNT(*) > 1
)
UNION ALL
SELECT 'dim_institution_null_or_duplicate_sk', COUNT(*) FROM (
  SELECT INSTITUTION_SK FROM PROJECT_DW.DIM_INSTITUTION GROUP BY INSTITUTION_SK
  HAVING INSTITUTION_SK IS NULL OR COUNT(*) > 1
);

-- 01c. Numeric fact/bridge references must resolve to the matching dimension
-- surrogate. Unresolved citation targets are excluded by design. Every count
-- below must be zero.
SELECT 'publication_work_sk_orphans' AS check_name, COUNT(*) AS rows_found
FROM PROJECT_DW.FACT_PUBLICATION f LEFT JOIN PROJECT_DW.DIM_WORK d ON f.WORK_SK = d.WORK_SK
WHERE d.WORK_SK IS NULL
UNION ALL SELECT 'publication_date_sk_orphans', COUNT(*)
FROM PROJECT_DW.FACT_PUBLICATION f LEFT JOIN PROJECT_DW.DIM_DATE d ON f.PUBLICATION_DATE_SK = d.DATE_SK
WHERE d.DATE_SK IS NULL
UNION ALL SELECT 'publication_type_sk_orphans', COUNT(*)
FROM PROJECT_DW.FACT_PUBLICATION f LEFT JOIN PROJECT_DW.DIM_WORK_TYPE d ON f.WORK_TYPE_SK = d.WORK_TYPE_SK
WHERE d.WORK_TYPE_SK IS NULL
UNION ALL SELECT 'publication_venue_sk_orphans', COUNT(*)
FROM PROJECT_DW.FACT_PUBLICATION f LEFT JOIN PROJECT_DW.DIM_VENUE d ON f.VENUE_SK = d.VENUE_SK
WHERE d.VENUE_SK IS NULL
UNION ALL SELECT 'publication_access_sk_orphans', COUNT(*)
FROM PROJECT_DW.FACT_PUBLICATION f LEFT JOIN PROJECT_DW.DIM_ACCESS_STATUS d
  ON f.ACCESS_STATUS_SK = d.ACCESS_STATUS_SK
WHERE d.ACCESS_STATUS_SK IS NULL
UNION ALL SELECT 'snapshot_work_sk_orphans', COUNT(*)
FROM PROJECT_DW.FACT_WORK_SNAPSHOT f LEFT JOIN PROJECT_DW.DIM_WORK d ON f.WORK_SK = d.WORK_SK
WHERE d.WORK_SK IS NULL
UNION ALL SELECT 'snapshot_date_sk_orphans', COUNT(*)
FROM PROJECT_DW.FACT_WORK_SNAPSHOT f LEFT JOIN PROJECT_DW.DIM_DATE d ON f.SNAPSHOT_DATE_SK = d.DATE_SK
WHERE d.DATE_SK IS NULL
UNION ALL SELECT 'snapshot_access_sk_orphans', COUNT(*)
FROM PROJECT_DW.FACT_WORK_SNAPSHOT f LEFT JOIN PROJECT_DW.DIM_ACCESS_STATUS d
  ON f.ACCESS_STATUS_SK = d.ACCESS_STATUS_SK
WHERE d.ACCESS_STATUS_SK IS NULL
UNION ALL SELECT 'citation_citing_work_sk_orphans', COUNT(*)
FROM PROJECT_DW.FACT_CITATION f LEFT JOIN PROJECT_DW.DIM_WORK d ON f.WORK_SK = d.WORK_SK
WHERE d.WORK_SK IS NULL
UNION ALL SELECT 'citation_cited_work_sk_orphans', COUNT(*)
FROM PROJECT_DW.FACT_CITATION f LEFT JOIN PROJECT_DW.DIM_WORK d ON f.CITED_WORK_SK = d.WORK_SK
WHERE f.CITED_WORK_KEY != '' AND d.WORK_SK IS NULL
UNION ALL SELECT 'topic_bridge_work_sk_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_TOPIC b LEFT JOIN PROJECT_DW.DIM_WORK d ON b.WORK_SK = d.WORK_SK
WHERE d.WORK_SK IS NULL
UNION ALL SELECT 'topic_bridge_topic_sk_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_TOPIC b LEFT JOIN PROJECT_DW.DIM_TOPIC d ON b.TOPIC_SK = d.TOPIC_SK
WHERE d.TOPIC_SK IS NULL
UNION ALL SELECT 'author_bridge_work_sk_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_AUTHOR b LEFT JOIN PROJECT_DW.DIM_WORK d ON b.WORK_SK = d.WORK_SK
WHERE d.WORK_SK IS NULL
UNION ALL SELECT 'author_bridge_author_sk_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_AUTHOR b LEFT JOIN PROJECT_DW.DIM_AUTHOR d ON b.AUTHOR_SK = d.AUTHOR_SK
WHERE d.AUTHOR_SK IS NULL
UNION ALL SELECT 'institution_bridge_work_sk_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_INSTITUTION b LEFT JOIN PROJECT_DW.DIM_WORK d ON b.WORK_SK = d.WORK_SK
WHERE d.WORK_SK IS NULL
UNION ALL SELECT 'institution_bridge_institution_sk_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_INSTITUTION b
LEFT JOIN PROJECT_DW.DIM_INSTITUTION d ON b.INSTITUTION_SK = d.INSTITUTION_SK
WHERE d.INSTITUTION_SK IS NULL
UNION ALL SELECT 'institution_bridge_author_sk_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_INSTITUTION b LEFT JOIN PROJECT_DW.DIM_AUTHOR d ON b.AUTHOR_SK = d.AUTHOR_SK
WHERE d.AUTHOR_SK IS NULL;

-- 02. Every fact foreign key resolves (orphans must be 0)
SELECT 'fact_publication_unknown_work' AS check_name, COUNT(*) AS rows_found
FROM PROJECT_DW.FACT_PUBLICATION f
LEFT JOIN PROJECT_DW.DIM_WORK w ON w.WORK_KEY = f.WORK_KEY
WHERE w.WORK_KEY IS NULL
UNION ALL
SELECT 'fact_publication_unknown_work_type', COUNT(*)
FROM PROJECT_DW.FACT_PUBLICATION f
LEFT JOIN PROJECT_DW.DIM_WORK_TYPE d ON d.WORK_TYPE_KEY = f.WORK_TYPE_KEY
WHERE f.WORK_TYPE_KEY IS NOT NULL AND d.WORK_TYPE_KEY IS NULL
UNION ALL
SELECT 'fact_publication_unknown_venue', COUNT(*)
FROM PROJECT_DW.FACT_PUBLICATION f
LEFT JOIN PROJECT_DW.DIM_VENUE d ON d.VENUE_KEY = f.VENUE_KEY
WHERE f.VENUE_KEY IS NOT NULL AND d.VENUE_KEY IS NULL
UNION ALL
SELECT 'fact_publication_unknown_access', COUNT(*)
FROM PROJECT_DW.FACT_PUBLICATION f
LEFT JOIN PROJECT_DW.DIM_ACCESS_STATUS d ON d.ACCESS_STATUS_KEY = f.ACCESS_STATUS_KEY
WHERE f.ACCESS_STATUS_KEY IS NOT NULL AND d.ACCESS_STATUS_KEY IS NULL
UNION ALL
SELECT 'fact_citation_unknown_citing_work', COUNT(*)
FROM PROJECT_DW.FACT_CITATION c
LEFT JOIN PROJECT_DW.DIM_WORK w ON w.WORK_KEY = c.WORK_KEY
WHERE w.WORK_KEY IS NULL
UNION ALL
SELECT 'bridge_work_topic_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_TOPIC b
LEFT JOIN PROJECT_DW.DIM_WORK w ON w.WORK_KEY = b.WORK_KEY
LEFT JOIN PROJECT_DW.DIM_TOPIC t ON t.TOPIC_KEY = b.TOPIC_KEY
WHERE w.WORK_KEY IS NULL OR t.TOPIC_KEY IS NULL
UNION ALL
SELECT 'bridge_work_author_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_AUTHOR b
LEFT JOIN PROJECT_DW.DIM_WORK w ON w.WORK_KEY = b.WORK_KEY
LEFT JOIN PROJECT_DW.DIM_AUTHOR a ON a.AUTHOR_KEY = b.AUTHOR_KEY
WHERE w.WORK_KEY IS NULL OR a.AUTHOR_KEY IS NULL
UNION ALL
SELECT 'bridge_work_institution_orphans', COUNT(*)
FROM PROJECT_DW.BRIDGE_WORK_INSTITUTION b
LEFT JOIN PROJECT_DW.DIM_WORK w ON w.WORK_KEY = b.WORK_KEY
LEFT JOIN PROJECT_DW.DIM_INSTITUTION i ON i.INSTITUTION_KEY = b.INSTITUTION_KEY
WHERE w.WORK_KEY IS NULL OR i.INSTITUTION_KEY IS NULL;

-- 03. fact_publication grain: one row per admitted canonical work
--     (duplicate work keys must be 0)
SELECT 'fact_publication_duplicate_work_keys' AS check_name, COUNT(*) AS rows_found
FROM (
  SELECT WORK_KEY FROM PROJECT_DW.FACT_PUBLICATION GROUP BY WORK_KEY HAVING COUNT(*) > 1
);

-- 04. Snapshot grain: one row per work per snapshot date (duplicates = 0)
SELECT 'fact_snapshot_duplicate_grain' AS check_name, COUNT(*) AS rows_found
FROM (
  SELECT WORK_KEY, SNAPSHOT_DATE_KEY
  FROM PROJECT_DW.FACT_WORK_SNAPSHOT
  GROUP BY WORK_KEY, SNAPSHOT_DATE_KEY HAVING COUNT(*) > 1
);

-- 05. Citation edges: unique, directed, non-self-referential
SELECT 'fact_citation_self_edges' AS check_name, COUNT(*) AS rows_found
FROM PROJECT_DW.FACT_CITATION
WHERE CITED_WORK_KEY = WORK_KEY AND CITED_WORK_KEY <> ''
UNION ALL
SELECT 'fact_citation_duplicate_edges', COUNT(*)
FROM (
  SELECT WORK_KEY, CITED_DOI, CITED_PROVIDER_ID, SOURCE_NAME
  FROM PROJECT_DW.FACT_CITATION
  GROUP BY WORK_KEY, CITED_DOI, CITED_PROVIDER_ID, SOURCE_NAME HAVING COUNT(*) > 1
);

-- 06. Bridges: unique pairs (duplicates = 0)
SELECT 'bridge_topic_duplicate_pairs' AS check_name, COUNT(*) AS rows_found
FROM (
  SELECT WORK_KEY, TOPIC_KEY, SOURCE_NAME
  FROM PROJECT_DW.BRIDGE_WORK_TOPIC
  GROUP BY WORK_KEY, TOPIC_KEY, SOURCE_NAME HAVING COUNT(*) > 1
)
UNION ALL
SELECT 'bridge_author_duplicate_pairs', COUNT(*)
FROM (
  SELECT WORK_KEY, AUTHOR_KEY, SOURCE_NAME
  FROM PROJECT_DW.BRIDGE_WORK_AUTHOR
  GROUP BY WORK_KEY, AUTHOR_KEY, SOURCE_NAME HAVING COUNT(*) > 1
)
UNION ALL
SELECT 'bridge_institution_duplicate_pairs', COUNT(*)
FROM (
  SELECT WORK_KEY, INSTITUTION_KEY, AUTHOR_KEY, SOURCE_NAME
  FROM PROJECT_DW.BRIDGE_WORK_INSTITUTION
  GROUP BY WORK_KEY, INSTITUTION_KEY, AUTHOR_KEY, SOURCE_NAME HAVING COUNT(*) > 1
);

-- 07. No negative citation counts anywhere
SELECT 'negative_cited_by_count_dim' AS check_name, COUNT(*) AS rows_found
FROM PROJECT_DW.DIM_WORK WHERE CITED_BY_COUNT < 0
UNION ALL
SELECT 'negative_cited_by_count_fact', COUNT(*)
FROM PROJECT_DW.FACT_PUBLICATION WHERE CITED_BY_COUNT < 0
UNION ALL
SELECT 'negative_cited_by_count_snapshot', COUNT(*)
FROM PROJECT_DW.FACT_WORK_SNAPSHOT WHERE CITED_BY_COUNT < 0;

-- 08. No raw batch marked complete while its fetch/parse failed
--     (a completed batch must have RECORDS_SEEN >= 0 and a payload registered)
SELECT 'raw_batch_complete_without_records' AS check_name, COUNT(*) AS rows_found
FROM PROJECT_OPS.RAW_BATCH
WHERE STATUS = 'complete' AND (RECORDS_SEEN IS NULL OR RECORDS_SEEN < 0);

-- 09. No checkpoint advanced for incomplete windows: every succeeded sync
--     state row must carry a watermark and a success timestamp
SELECT 'sync_state_succeeded_without_watermark' AS check_name, COUNT(*) AS rows_found
FROM PROJECT_OPS.SOURCE_SYNC_STATE
WHERE STATUS = 'succeeded'
  AND (LAST_SUCCESSFUL_WATERMARK IS NULL OR LAST_SUCCESS_AT IS NULL);

-- 10. Rerunning the same input does not increase duplicates:
--     staging PK (source, record, payload hash) must be unique
SELECT 'staging_duplicate_versions' AS check_name, COUNT(*) AS rows_found
FROM (
  SELECT SOURCE_NAME, SOURCE_RECORD_ID, PAYLOAD_SHA256
  FROM PROJECT_STAGING.STG_WORK_RECORD
  GROUP BY SOURCE_NAME, SOURCE_RECORD_ID, PAYLOAD_SHA256 HAVING COUNT(*) > 1
);

-- 11. Open quarantine items by reason code (review queue)
SELECT REASON_CODE, COUNT(*) AS open_items
FROM PROJECT_STAGING.STG_QUARANTINE
WHERE RESOLUTION_STATUS = 'open'
GROUP BY REASON_CODE
ORDER BY open_items DESC;

-- 12. Required quality metrics (missingness percentages, per source)
--     Missing data is a warning, never silently replaced with zero.
SELECT SOURCE_NAME,
       COUNT(*) AS staging_rows,
       ROUND(100.0 * SUM(IFF(DOI_NORMALIZED IS NULL, 1, 0)) / COUNT(*), 2) AS missing_doi_pct,
       ROUND(100.0 * SUM(IFF(TITLE IS NULL, 1, 0)) / COUNT(*), 2) AS missing_title_pct,
       ROUND(100.0 * SUM(IFF(PUBLICATION_DATE IS NULL AND PUBLICATION_YEAR IS NULL, 1, 0)) / COUNT(*), 2) AS missing_date_pct,
       ROUND(100.0 * SUM(IFF(TOPICS IS NULL, 1, 0)) / COUNT(*), 2) AS missing_topics_pct,
       ROUND(100.0 * SUM(IFF(AUTHORSHIPS IS NULL, 1, 0)) / COUNT(*), 2) AS missing_authors_pct,
       ROUND(100.0 * SUM(IFF(VENUE_NAME IS NULL, 1, 0)) / COUNT(*), 2) AS missing_venue_pct,
       ROUND(100.0 * SUM(IFF(OA_STATUS IS NULL, 1, 0)) / COUNT(*), 2) AS missing_access_status_pct
FROM PROJECT_STAGING.STG_WORK_RECORD
WHERE VALIDATION_STATUS = 'accepted'
GROUP BY SOURCE_NAME
ORDER BY SOURCE_NAME;

-- 13. Freshness of last successful sync per source (freshness monitoring)
SELECT SOURCE_NAME,
       MAX(LAST_SUCCESS_AT) AS last_successful_sync,
       DATEDIFF('hour', MAX(LAST_SUCCESS_AT), CURRENT_TIMESTAMP()) AS hours_stale
FROM PROJECT_OPS.SOURCE_SYNC_STATE
WHERE STATUS = 'succeeded'
GROUP BY SOURCE_NAME
ORDER BY SOURCE_NAME;

-- 14. Failed partitions/windows by source (operational watch)
SELECT SOURCE_NAME, STREAM_NAME, STATUS, ERROR_CODE, ERROR_SUMMARY, LAST_ATTEMPT_AT
FROM PROJECT_OPS.SOURCE_SYNC_STATE
WHERE STATUS <> 'succeeded'
ORDER BY LAST_ATTEMPT_AT DESC;
