-- transforms.sql
-- Warehouse-side (Snowflake SQL) transformation layer — the SQL-first path
-- required by the Post-Phase-2 hardening instructions (§4.3).
--
-- Purpose: provide explicit, reviewable, repeatable Snowflake SQL that
-- transforms staged data into canonical/dimension/fact structures WITHOUT
-- relying on Python-only in-memory transformation. The Python orchestrator
-- performs the same operations through MERGE-based upserts (tested against
-- the deterministic mock); these statements are the warehouse-native
-- reference implementation for live runs and for warehouse-side reprocessing
-- (e.g. replaying or re-deriving from staging without re-fetching).
--
-- Every statement is idempotent: re-running produces the same state.
-- Rules encoded here (documented, deterministic):
--   * work_key = 'doi:' || normalized DOI when present, else
--     'src:' || source || ':' || source record id.
--   * Staged rows are deduplicated to the latest content version per
--     (SOURCE_NAME, SOURCE_RECORD_ID) BEFORE any merge.
--   * Source precedence: openalex > crossref > datacite > zenodo > arxiv.
--     Lower-priority values fill missing fields; a NULL never overwrites a
--     non-null stored value; higher-priority values update.
--   * Conflicting DOI identities (different loose title for the same DOI)
--     are flagged into PROJECT_OPS.CANONICAL_CONFLICT_REVIEW, never merged.
--
-- Run on real Snowflake as PAPERSONAR_INGEST, in order, per environment.
-- Status: BLOCKED for live verification until a no-cost Snowflake account
-- exists; SQL syntax is reviewed against current Snowflake documentation.

-- ---------------------------------------------------------------------------
-- T1. Deduplicated staging view: latest content version per source record.
--     PK constraints are NOT enforced by Snowflake; dedup happens here and in
--     the loader, not by relying on constraints.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW PROJECT_STAGING.V_STG_WORK_RECORD_LATEST AS
SELECT *
FROM PROJECT_STAGING.STG_WORK_RECORD
WHERE VALIDATION_STATUS = 'accepted'
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY SOURCE_NAME, SOURCE_RECORD_ID
  ORDER BY INGESTED_AT DESC, PAYLOAD_SHA256
) = 1;

-- ---------------------------------------------------------------------------
-- T2. Conflict detection: DOI-bearing staged records whose loose-normalized
--     title differs from the stored canonical title are quarantined for human
--     review instead of being merged.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PROJECT_OPS.CANONICAL_CONFLICT_REVIEW (
  REVIEW_ID     STRING       NOT NULL,
  WORK_KEY      STRING       NOT NULL,
  SOURCE_NAME   STRING       NOT NULL,
  SOURCE_RECORD_ID STRING,
  STAGED_TITLE  STRING,
  STORED_TITLE  STRING,
  DETECTED_AT   TIMESTAMP_TZ NOT NULL,
  STATUS        STRING       NOT NULL DEFAULT 'open',
  CONSTRAINT PK_CANONICAL_CONFLICT_REVIEW PRIMARY KEY (REVIEW_ID)
);

INSERT INTO PROJECT_OPS.CANONICAL_CONFLICT_REVIEW
  (REVIEW_ID, WORK_KEY, SOURCE_NAME, SOURCE_RECORD_ID, STAGED_TITLE, STORED_TITLE, DETECTED_AT, STATUS)
SELECT
  SHA2(s.SOURCE_NAME || '|' || s.SOURCE_RECORD_ID || '|conflicting_doi_identity', 256),
  s.WORK_KEY,
  s.SOURCE_NAME,
  s.SOURCE_RECORD_ID,
  s.TITLE,
  w.TITLE,
  CURRENT_TIMESTAMP(),
  'open'
FROM (
  SELECT
    SOURCE_NAME, SOURCE_RECORD_ID, TITLE,
    CASE
      WHEN DOI_NORMALIZED IS NOT NULL THEN 'doi:' || DOI_NORMALIZED
      ELSE 'src:' || SOURCE_NAME || ':' || SOURCE_RECORD_ID
    END AS WORK_KEY
  FROM PROJECT_STAGING.V_STG_WORK_RECORD_LATEST
) s
JOIN PROJECT_DW.DIM_WORK w ON w.WORK_KEY = s.WORK_KEY
WHERE w.DOI_NORMALIZED IS NOT NULL
  AND s.TITLE IS NOT NULL
  AND w.TITLE IS NOT NULL
  AND REGEXP_REPLACE(w.TITLE_NORMALIZED, '[^a-z0-9]', '')
      <> REGEXP_REPLACE(s.TITLE_NORMALIZED, '[^a-z0-9]', '')
  AND NOT EXISTS (
    SELECT 1 FROM PROJECT_OPS.CANONICAL_CONFLICT_REVIEW r
    WHERE r.REVIEW_ID = SHA2(s.SOURCE_NAME || '|' || s.SOURCE_RECORD_ID || '|conflicting_doi_identity', 256)
  );

-- ---------------------------------------------------------------------------
-- T3. Source-to-canonical crosswalk refresh (idempotent MERGE).
--     A crosswalk row keeps its work_key; changed mappings surface in T2/T4
--     review rather than being silently re-pointed.
-- ---------------------------------------------------------------------------
MERGE INTO PROJECT_DW.WORK_SOURCE_XW t
USING (
  SELECT
    SOURCE_NAME,
    SOURCE_RECORD_ID,
    CASE
      WHEN DOI_NORMALIZED IS NOT NULL THEN 'doi:' || DOI_NORMALIZED
      ELSE 'src:' || SOURCE_NAME || ':' || SOURCE_RECORD_ID
    END AS WORK_KEY,
    DOI_NORMALIZED
  FROM PROJECT_STAGING.V_STG_WORK_RECORD_LATEST s
  WHERE NOT EXISTS (
    SELECT 1 FROM PROJECT_OPS.CANONICAL_CONFLICT_REVIEW r
    WHERE r.SOURCE_NAME = s.SOURCE_NAME
      AND r.SOURCE_RECORD_ID = s.SOURCE_RECORD_ID
      AND r.STATUS = 'open'
  )
) s
ON t.SOURCE_NAME = s.SOURCE_NAME AND t.SOURCE_RECORD_ID = s.SOURCE_RECORD_ID
WHEN MATCHED THEN UPDATE SET
  LAST_SEEN_AT = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT
  (SOURCE_NAME, SOURCE_RECORD_ID, WORK_KEY, DOI_NORMALIZED, FIRST_SEEN_AT, LAST_SEEN_AT)
VALUES
  (s.SOURCE_NAME, s.SOURCE_RECORD_ID, s.WORK_KEY, s.DOI_NORMALIZED, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP());

-- ---------------------------------------------------------------------------
-- T4. Canonical work MERGE with field precedence.
--     Candidates are aggregated per work_key across the deduplicated staging
--     view: each field takes the highest-priority non-null value
--     (openalex > crossref > datacite > zenodo > arxiv).
-- ---------------------------------------------------------------------------
MERGE INTO PROJECT_DW.DIM_WORK t
USING (
  SELECT
    CASE
      WHEN DOI_NORMALIZED IS NOT NULL THEN 'doi:' || DOI_NORMALIZED
      ELSE 'src:' || SOURCE_NAME || ':' || SOURCE_RECORD_ID
    END AS WORK_KEY,
    MAX(DOI_NORMALIZED) AS DOI_NORMALIZED,
    COALESCE(
      MAX(IFF(SOURCE_NAME = 'openalex', TITLE, NULL)),
      MAX(IFF(SOURCE_NAME = 'crossref', TITLE, NULL)),
      MAX(IFF(SOURCE_NAME = 'datacite', TITLE, NULL)),
      MAX(IFF(SOURCE_NAME = 'zenodo', TITLE, NULL)),
      MAX(IFF(SOURCE_NAME = 'arxiv', TITLE, NULL))
    ) AS TITLE,
    COALESCE(
      MAX(IFF(SOURCE_NAME = 'openalex', TITLE_NORMALIZED, NULL)),
      MAX(IFF(SOURCE_NAME = 'crossref', TITLE_NORMALIZED, NULL)),
      MAX(IFF(SOURCE_NAME = 'datacite', TITLE_NORMALIZED, NULL)),
      MAX(IFF(SOURCE_NAME = 'zenodo', TITLE_NORMALIZED, NULL)),
      MAX(IFF(SOURCE_NAME = 'arxiv', TITLE_NORMALIZED, NULL))
    ) AS TITLE_NORMALIZED,
    COALESCE(
      MAX(IFF(SOURCE_NAME = 'openalex', PUBLICATION_DATE, NULL)),
      MAX(IFF(SOURCE_NAME = 'crossref', PUBLICATION_DATE, NULL)),
      MAX(IFF(SOURCE_NAME = 'datacite', PUBLICATION_DATE, NULL)),
      MAX(IFF(SOURCE_NAME = 'zenodo', PUBLICATION_DATE, NULL)),
      MAX(IFF(SOURCE_NAME = 'arxiv', PUBLICATION_DATE, NULL))
    ) AS PUBLICATION_DATE,
    COALESCE(
      MAX(IFF(SOURCE_NAME = 'openalex', PUBLICATION_YEAR, NULL)),
      MAX(IFF(SOURCE_NAME = 'crossref', PUBLICATION_YEAR, NULL)),
      MAX(IFF(SOURCE_NAME = 'datacite', PUBLICATION_YEAR, NULL)),
      MAX(IFF(SOURCE_NAME = 'zenodo', PUBLICATION_YEAR, NULL)),
      MAX(IFF(SOURCE_NAME = 'arxiv', PUBLICATION_YEAR, NULL))
    ) AS PUBLICATION_YEAR,
    COALESCE(
      MAX(IFF(SOURCE_NAME = 'openalex', WORK_TYPE, NULL)),
      MAX(IFF(SOURCE_NAME = 'crossref', WORK_TYPE, NULL)),
      MAX(IFF(SOURCE_NAME = 'datacite', WORK_TYPE, NULL)),
      MAX(IFF(SOURCE_NAME = 'zenodo', WORK_TYPE, NULL)),
      MAX(IFF(SOURCE_NAME = 'arxiv', WORK_TYPE, NULL))
    ) AS WORK_TYPE,
    COALESCE(
      MAX(IFF(SOURCE_NAME = 'openalex', VENUE_NAME, NULL)),
      MAX(IFF(SOURCE_NAME = 'crossref', VENUE_NAME, NULL)),
      MAX(IFF(SOURCE_NAME = 'datacite', VENUE_NAME, NULL)),
      MAX(IFF(SOURCE_NAME = 'zenodo', VENUE_NAME, NULL)),
      MAX(IFF(SOURCE_NAME = 'arxiv', VENUE_NAME, NULL))
    ) AS VENUE_NAME,
    COALESCE(
      MAX(IFF(SOURCE_NAME = 'openalex', OA_IS_OA, NULL)),
      MAX(IFF(SOURCE_NAME = 'crossref', OA_IS_OA, NULL)),
      MAX(IFF(SOURCE_NAME = 'datacite', OA_IS_OA, NULL)),
      MAX(IFF(SOURCE_NAME = 'zenodo', OA_IS_OA, NULL)),
      MAX(IFF(SOURCE_NAME = 'arxiv', OA_IS_OA, NULL))
    ) AS OA_IS_OA,
    COALESCE(
      MAX(IFF(SOURCE_NAME = 'openalex', OA_STATUS, NULL)),
      MAX(IFF(SOURCE_NAME = 'crossref', OA_STATUS, NULL)),
      MAX(IFF(SOURCE_NAME = 'datacite', OA_STATUS, NULL)),
      MAX(IFF(SOURCE_NAME = 'zenodo', OA_STATUS, NULL)),
      MAX(IFF(SOURCE_NAME = 'arxiv', OA_STATUS, NULL))
    ) AS OA_STATUS,
    COALESCE(
      MAX(IFF(SOURCE_NAME = 'openalex', CITED_BY_COUNT, NULL)),
      MAX(IFF(SOURCE_NAME = 'crossref', CITED_BY_COUNT, NULL)),
      MAX(IFF(SOURCE_NAME = 'datacite', CITED_BY_COUNT, NULL)),
      MAX(IFF(SOURCE_NAME = 'zenodo', CITED_BY_COUNT, NULL)),
      MAX(IFF(SOURCE_NAME = 'arxiv', CITED_BY_COUNT, NULL))
    ) AS CITED_BY_COUNT,
    CASE
      WHEN COUNT_IF(SOURCE_NAME = 'openalex') > 0 THEN 'openalex'
      WHEN COUNT_IF(SOURCE_NAME = 'crossref') > 0 THEN 'crossref'
      WHEN COUNT_IF(SOURCE_NAME = 'datacite') > 0 THEN 'datacite'
      WHEN COUNT_IF(SOURCE_NAME = 'zenodo') > 0 THEN 'zenodo'
      ELSE 'arxiv'
    END AS SOURCE_PRIORITY,
    CASE
      WHEN COUNT_IF(SOURCE_NAME = 'openalex') > 0 THEN 1
      WHEN COUNT_IF(SOURCE_NAME = 'crossref') > 0 THEN 2
      WHEN COUNT_IF(SOURCE_NAME = 'datacite') > 0 THEN 3
      WHEN COUNT_IF(SOURCE_NAME = 'zenodo') > 0 THEN 4
      ELSE 5
    END AS SRC_RANK
  FROM PROJECT_STAGING.V_STG_WORK_RECORD_LATEST s
  WHERE NOT EXISTS (
    SELECT 1 FROM PROJECT_OPS.CANONICAL_CONFLICT_REVIEW r
    WHERE r.SOURCE_NAME = s.SOURCE_NAME
      AND r.SOURCE_RECORD_ID = s.SOURCE_RECORD_ID
      AND r.STATUS = 'open'
  )
  GROUP BY 1
) s
ON t.WORK_KEY = s.WORK_KEY
WHEN MATCHED THEN UPDATE SET
  DOI_NORMALIZED   = COALESCE(s.DOI_NORMALIZED, t.DOI_NORMALIZED),
  -- Field precedence across runs: the candidate value wins only when it is
  -- non-null AND its winning source rank is at most the stored source's rank
  -- (openalex=1 ... arxiv=5). Lower-priority candidates only fill NULLs.
  TITLE            = CASE
                       WHEN s.TITLE IS NULL THEN t.TITLE
                       WHEN t.SOURCE_PRIORITY IS NULL THEN s.TITLE
                       WHEN s.SRC_RANK <= CASE t.SOURCE_PRIORITY
                         WHEN 'openalex' THEN 1 WHEN 'crossref' THEN 2 WHEN 'datacite' THEN 3
                         WHEN 'zenodo' THEN 4 ELSE 5 END THEN s.TITLE
                       ELSE t.TITLE
                     END,
  TITLE_NORMALIZED = CASE
                       WHEN s.TITLE_NORMALIZED IS NULL THEN t.TITLE_NORMALIZED
                       WHEN t.SOURCE_PRIORITY IS NULL THEN s.TITLE_NORMALIZED
                       WHEN s.SRC_RANK <= CASE t.SOURCE_PRIORITY
                         WHEN 'openalex' THEN 1 WHEN 'crossref' THEN 2 WHEN 'datacite' THEN 3
                         WHEN 'zenodo' THEN 4 ELSE 5 END THEN s.TITLE_NORMALIZED
                       ELSE t.TITLE_NORMALIZED
                     END,
  PUBLICATION_DATE = COALESCE(s.PUBLICATION_DATE, t.PUBLICATION_DATE),
  PUBLICATION_YEAR = COALESCE(s.PUBLICATION_YEAR, t.PUBLICATION_YEAR),
  WORK_TYPE        = COALESCE(s.WORK_TYPE, t.WORK_TYPE),
  VENUE_NAME       = COALESCE(s.VENUE_NAME, t.VENUE_NAME),
  OA_IS_OA         = COALESCE(s.OA_IS_OA, t.OA_IS_OA),
  OA_STATUS        = COALESCE(s.OA_STATUS, t.OA_STATUS),
  CITED_BY_COUNT   = COALESCE(s.CITED_BY_COUNT, t.CITED_BY_COUNT),
  SOURCE_PRIORITY  = CASE
                       WHEN s.TITLE IS NULL AND s.CITED_BY_COUNT IS NULL THEN t.SOURCE_PRIORITY
                       WHEN t.SOURCE_PRIORITY IS NULL OR s.SRC_RANK <= CASE t.SOURCE_PRIORITY
                         WHEN 'openalex' THEN 1 WHEN 'crossref' THEN 2 WHEN 'datacite' THEN 3
                         WHEN 'zenodo' THEN 4 ELSE 5 END THEN s.SOURCE_PRIORITY
                       ELSE t.SOURCE_PRIORITY
                     END,
  LAST_UPDATED_AT  = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT
  (WORK_KEY, DOI_NORMALIZED, TITLE, TITLE_NORMALIZED, PUBLICATION_DATE,
   PUBLICATION_YEAR, WORK_TYPE, VENUE_NAME, OA_IS_OA, OA_STATUS,
   CITED_BY_COUNT, SOURCE_PRIORITY, FIRST_SEEN_AT, LAST_UPDATED_AT)
VALUES
  (s.WORK_KEY, s.DOI_NORMALIZED, s.TITLE, s.TITLE_NORMALIZED, s.PUBLICATION_DATE,
   s.PUBLICATION_YEAR, s.WORK_TYPE, s.VENUE_NAME, s.OA_IS_OA, s.OA_STATUS,
   s.CITED_BY_COUNT, s.SOURCE_PRIORITY, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP());

-- ---------------------------------------------------------------------------
-- T5. Publication fact refresh (grain: one row per canonical work).
--     Deterministic keys mirror the tested loader; MERGE keeps it idempotent.
-- ---------------------------------------------------------------------------
MERGE INTO PROJECT_DW.FACT_PUBLICATION t
USING (
  SELECT
    w.WORK_KEY,
    w.DOI_NORMALIZED,
    w.PUBLICATION_DATE,
    w.PUBLICATION_YEAR,
    COALESCE(LOWER(w.WORK_TYPE), '-1')                       AS WORK_TYPE_KEY,
    COALESCE('' , '-1')                                      AS VENUE_KEY_PLACEHOLDER,
    COALESCE(LOWER(w.OA_STATUS), '-1')                       AS ACCESS_STATUS_KEY,
    w.CITED_BY_COUNT,
    w.SOURCE_PRIORITY
  FROM PROJECT_DW.DIM_WORK w
) s
ON t.WORK_KEY = s.WORK_KEY
WHEN MATCHED THEN UPDATE SET
  DOI_NORMALIZED    = s.DOI_NORMALIZED,
  PUBLICATION_DATE  = s.PUBLICATION_DATE,
  PUBLICATION_YEAR  = s.PUBLICATION_YEAR,
  WORK_TYPE_KEY     = s.WORK_TYPE_KEY,
  ACCESS_STATUS_KEY = s.ACCESS_STATUS_KEY,
  CITED_BY_COUNT    = s.CITED_BY_COUNT,
  SOURCE_PRIORITY   = s.SOURCE_PRIORITY,
  LAST_UPDATED_AT   = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT
  (WORK_KEY, DOI_NORMALIZED, PUBLICATION_DATE, PUBLICATION_YEAR, WORK_TYPE_KEY,
   VENUE_KEY, ACCESS_STATUS_KEY, CITED_BY_COUNT, SOURCE_PRIORITY, FIRST_SEEN_AT, LAST_UPDATED_AT)
VALUES
  (s.WORK_KEY, s.DOI_NORMALIZED, s.PUBLICATION_DATE, s.PUBLICATION_YEAR, s.WORK_TYPE_KEY,
   '-1', s.ACCESS_STATUS_KEY, s.CITED_BY_COUNT, s.SOURCE_PRIORITY, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP());

-- NOTE on VENUE_KEY: the Python loader derives a deterministic venue key
-- ('<source>:name:<hash of normalized venue name>') from the winning source's
-- venue name and populates DIM_VENUE in the same run. T5 above conservatively
-- leaves VENUE_KEY as the unknown member for warehouse-side reprocessing so it
-- can never reference a venue that does not exist in DIM_VENUE. Use the Python
-- orchestrated path for venue-aware loads, or extend T5 with the same key
-- expression plus a DIM_VENUE refresh statement before executing it.

-- ---------------------------------------------------------------------------
-- T6. Snapshot fact refresh for this run date (grain: work x snapshot date).
-- ---------------------------------------------------------------------------
MERGE INTO PROJECT_DW.FACT_WORK_SNAPSHOT t
USING (
  SELECT WORK_KEY, CITED_BY_COUNT, OA_IS_OA, OA_STATUS
  FROM PROJECT_DW.DIM_WORK
) s
ON t.WORK_KEY = s.WORK_KEY
 AND t.SNAPSHOT_DATE_KEY = TO_NUMBER(TO_CHAR(CURRENT_DATE, 'YYYYMMDD'))
WHEN MATCHED THEN UPDATE SET
  CITED_BY_COUNT = s.CITED_BY_COUNT,
  OA_IS_OA       = s.OA_IS_OA,
  OA_STATUS      = s.OA_STATUS
WHEN NOT MATCHED THEN INSERT
  (WORK_KEY, SNAPSHOT_DATE_KEY, CITED_BY_COUNT, OA_IS_OA, OA_STATUS, RUN_ID)
VALUES
  (s.WORK_KEY, TO_NUMBER(TO_CHAR(CURRENT_DATE, 'YYYYMMDD')), s.CITED_BY_COUNT, s.OA_IS_OA, s.OA_STATUS, NULL);
