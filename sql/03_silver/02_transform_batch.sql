-- =============================================================================
-- Purpose: Transform one bronze batch into typed silver observations, assign
--          deterministic canonical output keys, update the canonical output,
--          quarantine invalid values, and log schema drift.
-- Inputs: five BRZ_* tables, CURRENT_BATCH, REF_EXPECTED_KEY.
-- Outputs: SLV_SOURCE_OBSERVATION, SLV_OUTPUT_CROSSWALK, SLV_RESEARCH_OUTPUT,
--          QUARANTINE_RECORD, SCHEMA_DRIFT_LOG, LINEAGE_EVENT.
-- Idempotent: Yes - batch rows are replaced; canonical output is upserted and
--            identity keys are deterministic.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None - the active batch comes from CURRENT_BATCH.
-- Cost: Five bronze scans plus one canonical MERGE; XS warehouse compute.
-- =============================================================================
-- VERIFY: XML extraction uses REGEXP_SUBSTR / REGEXP_SUBSTR_ALL with the 'e'
-- parameter. Confirm group extraction on the live arXiv/Zenodo XML samples. If
-- a construct is unsupported in the account, the fallback is the preserved
-- metadata_xml in bronze; no source data is lost.
--
-- Invalid DOI/date values are recorded in QUARANTINE_RECORD and still receive a
-- deterministic identity via the next available key (arXiv id or title/author
-- hash). They are classified, not silently replaced or dropped.

CREATE OR REPLACE PROCEDURE PAPERSONAR.PROJECT_SILVER.SP_TRANSFORM_BATCH()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  batch_id VARCHAR DEFAULT NULL;
  observation_count NUMBER DEFAULT 0;
  crosswalk_count NUMBER DEFAULT 0;
BEGIN
  SELECT BATCH_ID INTO :batch_id
  FROM PAPERSONAR.PROJECT_AUDIT.CURRENT_BATCH
  LIMIT 1;

  IF (batch_id IS NULL) THEN
    RETURN 'NO_BATCH';
  END IF;

  DELETE FROM PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION WHERE BATCH_ID = :batch_id;
  DELETE FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK WHERE BATCH_ID = :batch_id;

  INSERT INTO PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION (
    OBSERVATION_ID, SOURCE_NAME, ENTITY_NAME, SOURCE_RECORD_ID, RECORD_HASH,
    BATCH_ID, DOI_RAW, DOI_NORMALIZED, IS_DOI_VALID, ARXIV_ID, TITLE_RAW,
    TITLE_NORMALIZED, PUBLICATION_DATE_RAW, PUBLICATION_DATE, PUBLICATION_YEAR,
    OUTPUT_TYPE, VENUE_NAME, OA_IS_OA, OA_STATUS, CITED_BY_COUNT,
    FIRST_AUTHOR_NAME, FIRST_AUTHOR_ID, TOPICS, AUTHORS, REFERENCES_JSON,
    LANGUAGE, SOURCE_UPDATED_AT, PROVENANCE, INGESTED_AT
  )
  SELECT
    SHA2(BATCH_ID || '|' || SOURCE_NAME || '|' || ENTITY_NAME || '|' || SOURCE_RECORD_ID || '|' || RECORD_HASH, 256),
    SOURCE_NAME, ENTITY_NAME, SOURCE_RECORD_ID, RECORD_HASH, BATCH_ID,
    DOI_RAW,
    PAPERSONAR.PROJECT_SILVER.FN_NORMALIZE_DOI(DOI_RAW),
    PAPERSONAR.PROJECT_SILVER.FN_IS_VALID_DOI(PAPERSONAR.PROJECT_SILVER.FN_NORMALIZE_DOI(DOI_RAW)),
    ARXIV_ID, TITLE_RAW,
    PAPERSONAR.PROJECT_SILVER.FN_NORMALIZE_TITLE(TITLE_RAW),
    PUBLICATION_DATE_RAW, PUBLICATION_DATE, PUBLICATION_YEAR,
    OUTPUT_TYPE, VENUE_NAME, OA_IS_OA, OA_STATUS, CITED_BY_COUNT,
    FIRST_AUTHOR_NAME, FIRST_AUTHOR_ID, TOPICS, AUTHORS, REFERENCES_JSON,
    LANGUAGE, SOURCE_UPDATED_AT, PROVENANCE, CURRENT_TIMESTAMP()
  FROM (
    -- OpenAlex ---------------------------------------------------------------
    SELECT
      'OPENALEX' AS SOURCE_NAME,
      'WORK' AS ENTITY_NAME,
      REGEXP_REPLACE(b.PAYLOAD:id::STRING, '^https?://openalex[.]org/', '') AS SOURCE_RECORD_ID,
      b.RECORD_HASH,
      b.BATCH_ID,
      b.PAYLOAD:doi::STRING AS DOI_RAW,
      NULL AS ARXIV_ID,
      COALESCE(b.PAYLOAD:display_name::STRING, b.PAYLOAD:title::STRING) AS TITLE_RAW,
      LEFT(b.PAYLOAD:publication_date::STRING, 4000) AS PUBLICATION_DATE_RAW,
      TRY_TO_DATE(b.PAYLOAD:publication_date::STRING) AS PUBLICATION_DATE,
      TRY_TO_NUMBER(b.PAYLOAD:publication_year::STRING) AS PUBLICATION_YEAR,
      b.PAYLOAD:type::STRING AS OUTPUT_TYPE,
      COALESCE(
        b.PAYLOAD:primary_location.source.display_name::STRING,
        b.PAYLOAD:host_venue.display_name::STRING
      ) AS VENUE_NAME,
      TRY_TO_BOOLEAN(b.PAYLOAD:open_access.is_oa::STRING) AS OA_IS_OA,
      b.PAYLOAD:open_access.oa_status::STRING AS OA_STATUS,
      TRY_TO_NUMBER(b.PAYLOAD:cited_by_count::STRING) AS CITED_BY_COUNT,
      LEFT(b.PAYLOAD:authorships[0].author.display_name::STRING, 500) AS FIRST_AUTHOR_NAME,
      REGEXP_REPLACE(
        b.PAYLOAD:authorships[0].author.id::STRING,
        '^https?://openalex[.]org/',
        ''
      ) AS FIRST_AUTHOR_ID,
      b.PAYLOAD:topics AS TOPICS,
      b.PAYLOAD:authorships AS AUTHORS,
      b.PAYLOAD:referenced_works AS REFERENCES_JSON,
      b.PAYLOAD:language::STRING AS LANGUAGE,
      TRY_TO_TIMESTAMP_NTZ(b.PAYLOAD:updated_date::STRING) AS SOURCE_UPDATED_AT,
      OBJECT_CONSTRUCT(
        'file_name', b.FILE_NAME, 'batch_id', b.BATCH_ID,
        'record_hash', b.RECORD_HASH
      ) AS PROVENANCE
    FROM PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK b
    WHERE b.BATCH_ID = :batch_id

    UNION ALL

    -- Crossref ---------------------------------------------------------------
    SELECT
      'CROSSREF',
      'WORK',
      COALESCE(b.PAYLOAD:DOI::STRING, b.PAYLOAD:URL::STRING),
      b.RECORD_HASH,
      b.BATCH_ID,
      b.PAYLOAD:DOI::STRING,
      NULL,
      b.PAYLOAD:title[0]::STRING,
      b.PAYLOAD:issued."date-parts"[0]::STRING,
      CASE
        WHEN b.PAYLOAD:issued."date-parts"[0][0] IS NULL THEN NULL
        ELSE TRY_TO_DATE(
          LPAD(b.PAYLOAD:issued."date-parts"[0][0]::STRING, 4, '0') || '-' ||
          LPAD(COALESCE(b.PAYLOAD:issued."date-parts"[0][1]::STRING, '1'), 2, '0') || '-' ||
          LPAD(COALESCE(b.PAYLOAD:issued."date-parts"[0][2]::STRING, '1'), 2, '0')
        )
      END,
      TRY_TO_NUMBER(b.PAYLOAD:issued."date-parts"[0][0]::STRING),
      b.PAYLOAD:type::STRING,
      b.PAYLOAD:"container-title"[0]::STRING,
      NULL,
      NULL,
      TRY_TO_NUMBER(b.PAYLOAD:"is-referenced-by-count"::STRING),
      LEFT(
        NULLIF(
          TRIM(
            COALESCE(b.PAYLOAD:author[0].given::STRING, '') || ' ' ||
            COALESCE(b.PAYLOAD:author[0].family::STRING, '')
          ),
          ''
        ),
        500
      ),
      b.PAYLOAD:author[0].ORCID::STRING,
      b.PAYLOAD:subject,
      b.PAYLOAD:author,
      b.PAYLOAD:reference,
      b.PAYLOAD:language::STRING,
      COALESCE(
        TRY_TO_TIMESTAMP_NTZ(b.PAYLOAD:indexed."date-time"::STRING),
        TRY_TO_TIMESTAMP_NTZ(b.PAYLOAD:created."date-time"::STRING)
      ),
      OBJECT_CONSTRUCT(
        'file_name', b.FILE_NAME, 'batch_id', b.BATCH_ID,
        'record_hash', b.RECORD_HASH
      )
    FROM PAPERSONAR.PROJECT_BRONZE.BRZ_CROSSREF_WORK b
    WHERE b.BATCH_ID = :batch_id

    UNION ALL

    -- arXiv (raw OAI XML preserved) -----------------------------------------
    SELECT
      'ARXIV',
      'RECORD',
      b.PAYLOAD:identifier::STRING,
      b.RECORD_HASH,
      b.BATCH_ID,
      REGEXP_SUBSTR(
        b.PAYLOAD:metadata_xml::STRING,
        '<([A-Za-z0-9_]+:)?doi[^>]*>([^<]+)<', 1, 1, 'e', 2
      ),
      COALESCE(
        REGEXP_SUBSTR(
          b.PAYLOAD:metadata_xml::STRING,
          '<([A-Za-z0-9_]+:)?id[^>]*>([^<]+)<', 1, 1, 'e', 2
        ),
        SPLIT_PART(b.PAYLOAD:identifier::STRING, ':', -1)
      ),
      REGEXP_SUBSTR(
        b.PAYLOAD:metadata_xml::STRING,
        '<([A-Za-z0-9_]+:)?title[^>]*>([^<]+)<', 1, 1, 'e', 2
      ),
      REGEXP_SUBSTR(
        b.PAYLOAD:metadata_xml::STRING,
        '<([A-Za-z0-9_]+:)?created[^>]*>([^<]+)<', 1, 1, 'e', 2
      ),
      TRY_TO_DATE(
        REGEXP_SUBSTR(
          b.PAYLOAD:metadata_xml::STRING,
          '<([A-Za-z0-9_]+:)?created[^>]*>([^<]+)<', 1, 1, 'e', 2
        )
      ),
      YEAR(
        TRY_TO_DATE(
          REGEXP_SUBSTR(
            b.PAYLOAD:metadata_xml::STRING,
            '<([A-Za-z0-9_]+:)?created[^>]*>([^<]+)<', 1, 1, 'e', 2
          )
        )
      ),
      'preprint',
      'arXiv',
      TRUE,
      'green',
      NULL,
      LEFT(
        GET(
          REGEXP_SUBSTR_ALL(
            b.PAYLOAD:metadata_xml::STRING,
            '<([A-Za-z0-9_]+:)?author[^>]*>([^<]+)<', 1, 1, 'e', 2
          ),
          0
        )::STRING,
        500
      ),
      NULL,
      SPLIT(
        REGEXP_SUBSTR(
          b.PAYLOAD:metadata_xml::STRING,
          '<([A-Za-z0-9_]+:)?categories[^>]*>([^<]+)<', 1, 1, 'e', 2
        ),
        ' '
      ),
      REGEXP_SUBSTR_ALL(
        b.PAYLOAD:metadata_xml::STRING,
        '<([A-Za-z0-9_]+:)?author[^>]*>([^<]+)<', 1, 1, 'e', 2
      ),
      NULL,
      NULL,
      TRY_TO_TIMESTAMP_NTZ(b.PAYLOAD:datestamp::STRING),
      OBJECT_CONSTRUCT(
        'file_name', b.FILE_NAME, 'batch_id', b.BATCH_ID,
        'record_hash', b.RECORD_HASH, 'metadata_prefix', b.PAYLOAD:metadata_prefix::STRING
      )
    FROM PAPERSONAR.PROJECT_BRONZE.BRZ_ARXIV_RECORD b
    WHERE b.BATCH_ID = :batch_id

    UNION ALL

    -- DataCite ---------------------------------------------------------------
    SELECT
      'DATACITE',
      'DOI',
      COALESCE(b.PAYLOAD:attributes.doi::STRING, b.PAYLOAD:id::STRING),
      b.RECORD_HASH,
      b.BATCH_ID,
      b.PAYLOAD:attributes.doi::STRING,
      NULL,
      b.PAYLOAD:attributes.titles[0].title::STRING,
      b.PAYLOAD:attributes.dates[0].date::STRING,
      TRY_TO_DATE(b.PAYLOAD:attributes.dates[0].date::STRING),
      TRY_TO_NUMBER(b.PAYLOAD:attributes.publicationYear::STRING),
      b.PAYLOAD:attributes.types.resourceTypeGeneral::STRING,
      b.PAYLOAD:attributes.publisher::STRING,
      NULL,
      NULL,
      NULL,
      LEFT(b.PAYLOAD:attributes.creators[0].name::STRING, 500),
      b.PAYLOAD:attributes.creators[0].nameIdentifiers[0].nameIdentifier::STRING,
      b.PAYLOAD:attributes.subjects,
      b.PAYLOAD:attributes.creators,
      b.PAYLOAD:attributes.relatedIdentifiers,
      b.PAYLOAD:attributes.language::STRING,
      TRY_TO_TIMESTAMP_NTZ(b.PAYLOAD:attributes.updated::STRING),
      OBJECT_CONSTRUCT(
        'file_name', b.FILE_NAME, 'batch_id', b.BATCH_ID,
        'record_hash', b.RECORD_HASH
      )
    FROM PAPERSONAR.PROJECT_BRONZE.BRZ_DATACITE_DOI b
    WHERE b.BATCH_ID = :batch_id

    UNION ALL

    -- Zenodo (raw OAI DataCite XML preserved) --------------------------------
    SELECT
      'ZENODO',
      'RECORD',
      b.PAYLOAD:identifier::STRING,
      b.RECORD_HASH,
      b.BATCH_ID,
      REGEXP_SUBSTR(
        b.PAYLOAD:metadata_xml::STRING,
        '<([A-Za-z0-9_]+:)?identifier[^>]*>([^<]+)<', 1, 1, 'e', 2
      ),
      NULL,
      REGEXP_SUBSTR(
        b.PAYLOAD:metadata_xml::STRING,
        '<([A-Za-z0-9_]+:)?title[^>]*>([^<]+)<', 1, 1, 'e', 2
      ),
      COALESCE(
        REGEXP_SUBSTR(
          b.PAYLOAD:metadata_xml::STRING,
          '<([A-Za-z0-9_]+:)?date[^>]*dateType="Issued"[^>]*>([^<]+)<', 1, 1, 'e', 2
        ),
        REGEXP_SUBSTR(
          b.PAYLOAD:metadata_xml::STRING,
          '<([A-Za-z0-9_]+:)?date[^>]*>([^<]+)<', 1, 1, 'e', 2
        )
      ),
      TRY_TO_DATE(
        COALESCE(
          REGEXP_SUBSTR(
            b.PAYLOAD:metadata_xml::STRING,
            '<([A-Za-z0-9_]+:)?date[^>]*dateType="Issued"[^>]*>([^<]+)<', 1, 1, 'e', 2
          ),
          REGEXP_SUBSTR(
            b.PAYLOAD:metadata_xml::STRING,
            '<([A-Za-z0-9_]+:)?date[^>]*>([^<]+)<', 1, 1, 'e', 2
          )
        )
      ),
      TRY_TO_NUMBER(
        REGEXP_SUBSTR(
          b.PAYLOAD:metadata_xml::STRING,
          '<([A-Za-z0-9_]+:)?publicationYear[^>]*>([^<]+)<', 1, 1, 'e', 2
        )
      ),
      REGEXP_SUBSTR(
        b.PAYLOAD:metadata_xml::STRING,
        'resourceTypeGeneral="([^"]+)"', 1, 1, 'e', 1
      ),
      REGEXP_SUBSTR(
        b.PAYLOAD:metadata_xml::STRING,
        '<([A-Za-z0-9_]+:)?publisher[^>]*>([^<]+)<', 1, 1, 'e', 2
      ),
      NULL,
      NULL,
      NULL,
      LEFT(
        GET(
          REGEXP_SUBSTR_ALL(
            b.PAYLOAD:metadata_xml::STRING,
            '<([A-Za-z0-9_]+:)?creatorName[^>]*>([^<]+)<', 1, 1, 'e', 2
          ),
          0
        )::STRING,
        500
      ),
      NULL,
      REGEXP_SUBSTR_ALL(
        b.PAYLOAD:metadata_xml::STRING,
        '<([A-Za-z0-9_]+:)?subject[^>]*>([^<]+)<', 1, 1, 'e', 2
      ),
      REGEXP_SUBSTR_ALL(
        b.PAYLOAD:metadata_xml::STRING,
        '<([A-Za-z0-9_]+:)?creatorName[^>]*>([^<]+)<', 1, 1, 'e', 2
      ),
      NULL,
      NULL,
      TRY_TO_TIMESTAMP_NTZ(b.PAYLOAD:datestamp::STRING),
      OBJECT_CONSTRUCT(
        'file_name', b.FILE_NAME, 'batch_id', b.BATCH_ID,
        'record_hash', b.RECORD_HASH, 'metadata_prefix', b.PAYLOAD:metadata_prefix::STRING
      )
    FROM PAPERSONAR.PROJECT_BRONZE.BRZ_ZENODO_RECORD b
    WHERE b.BATCH_ID = :batch_id
  ) b;

  observation_count := SQLROWCOUNT;

  -- Quarantine classified defects (rows remain available to silver) ----------
  INSERT INTO PAPERSONAR.PROJECT_AUDIT.QUARANTINE_RECORD (
    QUARANTINE_ID, BATCH_ID, SOURCE_NAME, ENTITY_NAME, SOURCE_RECORD_ID,
    RECORD_HASH, REASON_CODE, DETAIL, RAW_REFERENCE, CREATED_AT
  )
  SELECT
    SHA2(q.BATCH_ID || '|' || q.OBSERVATION_ID || '|' || q.REASON_CODE, 256),
    q.BATCH_ID, q.SOURCE_NAME, q.ENTITY_NAME, q.SOURCE_RECORD_ID,
    q.RECORD_HASH, q.REASON_CODE,
    OBJECT_CONSTRUCT(
      'doi_raw', q.DOI_RAW,
      'publication_date_raw', q.PUBLICATION_DATE_RAW,
      'title_raw', q.TITLE_RAW,
      'observation_id', q.OBSERVATION_ID
    ),
    q.PROVENANCE:file_name::STRING,
    CURRENT_TIMESTAMP()
  FROM (
    SELECT
      o.*,
      'INVALID_DOI' AS REASON_CODE
    FROM PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION o
    WHERE o.BATCH_ID = :batch_id
      AND o.DOI_RAW IS NOT NULL
      AND NOT o.IS_DOI_VALID

    UNION ALL

    SELECT
      o.*,
      'INVALID_DATE' AS REASON_CODE
    FROM PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION o
    WHERE o.BATCH_ID = :batch_id
      AND o.PUBLICATION_DATE IS NULL
      AND o.PUBLICATION_DATE_RAW IS NOT NULL
      AND TRIM(o.PUBLICATION_DATE_RAW) <> ''

    UNION ALL

    SELECT
      o.*,
      'UNSUPPORTED_SHAPE' AS REASON_CODE
    FROM PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION o
    WHERE o.BATCH_ID = :batch_id
      AND PAPERSONAR.PROJECT_SILVER.FN_OUTPUT_BK(
            o.DOI_NORMALIZED, o.ARXIV_ID, o.TITLE_NORMALIZED,
            o.PUBLICATION_YEAR, o.FIRST_AUTHOR_NAME
          ) IS NULL
  ) q
  WHERE NOT EXISTS (
    SELECT 1
    FROM PAPERSONAR.PROJECT_AUDIT.QUARANTINE_RECORD existing
    WHERE existing.QUARANTINE_ID = SHA2(q.BATCH_ID || '|' || q.OBSERVATION_ID || '|' || q.REASON_CODE, 256)
  );

  -- Deterministic identity crosswalk -----------------------------------------
  INSERT INTO PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK (
    SOURCE_NAME, ENTITY_NAME, SOURCE_RECORD_ID, RECORD_HASH, OUTPUT_BK,
    MATCH_METHOD, CONFIDENCE, RULE_VERSION, BATCH_ID, CREATED_AT
  )
  SELECT
    o.SOURCE_NAME,
    o.ENTITY_NAME,
    o.SOURCE_RECORD_ID,
    o.RECORD_HASH,
    PAPERSONAR.PROJECT_SILVER.FN_OUTPUT_BK(
      o.DOI_NORMALIZED, o.ARXIV_ID, o.TITLE_NORMALIZED,
      o.PUBLICATION_YEAR, o.FIRST_AUTHOR_NAME
    ) AS OUTPUT_BK,
    CASE
      WHEN o.DOI_NORMALIZED IS NOT NULL AND o.IS_DOI_VALID THEN 'DOI'
      WHEN o.ARXIV_ID IS NOT NULL AND TRIM(o.ARXIV_ID) <> '' THEN 'ARXIV'
      ELSE 'TITLE_AUTHOR_YEAR'
    END AS MATCH_METHOD,
    CASE
      WHEN o.DOI_NORMALIZED IS NOT NULL AND o.IS_DOI_VALID THEN 1.0000
      WHEN o.ARXIV_ID IS NOT NULL AND TRIM(o.ARXIV_ID) <> '' THEN 0.9500
      ELSE 0.7000
    END AS CONFIDENCE,
    'identity-v1',
    o.BATCH_ID,
    CURRENT_TIMESTAMP()
  FROM PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION o
  WHERE o.BATCH_ID = :batch_id
    AND COALESCE(o.SOURCE_RECORD_ID, '') <> ''
    AND PAPERSONAR.PROJECT_SILVER.FN_OUTPUT_BK(
          o.DOI_NORMALIZED, o.ARXIV_ID, o.TITLE_NORMALIZED,
          o.PUBLICATION_YEAR, o.FIRST_AUTHOR_NAME
        ) IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY o.SOURCE_NAME, o.ENTITY_NAME, o.SOURCE_RECORD_ID, o.RECORD_HASH
    ORDER BY o.INGESTED_AT DESC
  ) = 1;

  crosswalk_count := SQLROWCOUNT;

  -- Canonical output with source-precedence survivorship ----------------------
  MERGE INTO PAPERSONAR.PROJECT_SILVER.SLV_RESEARCH_OUTPUT t
  USING (
    SELECT
      OUTPUT_BK,
      MAX(IFF(rn = 1, DOI_NORMALIZED, NULL)) AS DOI_NORMALIZED,
      MAX(IFF(rn = 1, TITLE_RAW, NULL)) AS TITLE,
      MAX(IFF(rn = 1, PUBLICATION_DATE, NULL)) AS PUBLICATION_DATE,
      MAX(IFF(rn = 1, PUBLICATION_YEAR, NULL)) AS PUBLICATION_YEAR,
      MAX(IFF(rn = 1, OUTPUT_TYPE, NULL)) AS OUTPUT_TYPE,
      MAX(IFF(rn = 1, VENUE_NAME, NULL)) AS VENUE_NAME,
      MAX(IFF(rn = 1, IFF(OA_IS_OA, 1, 0), NULL)) AS OA_FLAG,
      MAX(IFF(rn = 1, OA_STATUS, NULL)) AS OA_STATUS,
      MAX(IFF(rn = 1, CITED_BY_COUNT, NULL)) AS CITED_BY_COUNT,
      MAX(IFF(rn = 1, LANGUAGE, NULL)) AS LANGUAGE,
      MAX(IFF(rn = 1, SOURCE_NAME, NULL)) AS PRIMARY_SOURCE_NAME,
      MIN(INGESTED_AT) AS FIRST_SEEN_AT,
      MAX(INGESTED_AT) AS LAST_SEEN_AT
    FROM (
      SELECT
        c.OUTPUT_BK,
        o.SOURCE_NAME,
        o.DOI_NORMALIZED,
        o.TITLE_RAW,
        o.PUBLICATION_DATE,
        o.PUBLICATION_YEAR,
        o.OUTPUT_TYPE,
        o.VENUE_NAME,
        o.OA_IS_OA,
        o.OA_STATUS,
        o.CITED_BY_COUNT,
        o.LANGUAGE,
        o.INGESTED_AT,
        ROW_NUMBER() OVER (
          PARTITION BY c.OUTPUT_BK
          ORDER BY
            PAPERSONAR.PROJECT_SILVER.FN_SOURCE_PRIORITY(o.SOURCE_NAME),
            o.INGESTED_AT DESC,
            o.SOURCE_RECORD_ID
        ) AS rn
      FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK c
      JOIN PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION o
        ON o.SOURCE_NAME = c.SOURCE_NAME
       AND o.ENTITY_NAME = c.ENTITY_NAME
       AND o.SOURCE_RECORD_ID = c.SOURCE_RECORD_ID
       AND o.RECORD_HASH = c.RECORD_HASH
       AND o.BATCH_ID = c.BATCH_ID
      WHERE c.BATCH_ID = :batch_id
    )
    GROUP BY OUTPUT_BK
  ) s
  ON t.OUTPUT_BK = s.OUTPUT_BK
  WHEN MATCHED THEN UPDATE SET
    t.DOI_NORMALIZED = COALESCE(s.DOI_NORMALIZED, t.DOI_NORMALIZED),
    t.TITLE = COALESCE(s.TITLE, t.TITLE),
    t.PUBLICATION_DATE = COALESCE(s.PUBLICATION_DATE, t.PUBLICATION_DATE),
    t.PUBLICATION_YEAR = COALESCE(s.PUBLICATION_YEAR, t.PUBLICATION_YEAR),
    t.OUTPUT_TYPE = COALESCE(s.OUTPUT_TYPE, t.OUTPUT_TYPE),
    t.VENUE_NAME = COALESCE(s.VENUE_NAME, t.VENUE_NAME),
    t.OA_IS_OA = COALESCE(s.OA_FLAG = 1, t.OA_IS_OA),
    t.OA_STATUS = COALESCE(s.OA_STATUS, t.OA_STATUS),
    t.CITED_BY_COUNT = COALESCE(s.CITED_BY_COUNT, t.CITED_BY_COUNT),
    t.LANGUAGE = COALESCE(s.LANGUAGE, t.LANGUAGE),
    t.PRIMARY_SOURCE_NAME = COALESCE(s.PRIMARY_SOURCE_NAME, t.PRIMARY_SOURCE_NAME),
    t.FIRST_SEEN_AT = COALESCE(LEAST(t.FIRST_SEEN_AT, s.FIRST_SEEN_AT), s.FIRST_SEEN_AT),
    t.LAST_SEEN_AT = COALESCE(GREATEST(t.LAST_SEEN_AT, s.LAST_SEEN_AT), s.LAST_SEEN_AT),
    t.LAST_BATCH_ID = :batch_id
  WHEN NOT MATCHED THEN INSERT (
    OUTPUT_BK, DOI_NORMALIZED, TITLE, PUBLICATION_DATE, PUBLICATION_YEAR,
    OUTPUT_TYPE, VENUE_NAME, OA_IS_OA, OA_STATUS, CITED_BY_COUNT, LANGUAGE,
    PRIMARY_SOURCE_NAME, FIRST_SEEN_AT, LAST_SEEN_AT, LAST_BATCH_ID
  )
  VALUES (
    s.OUTPUT_BK, s.DOI_NORMALIZED, s.TITLE, s.PUBLICATION_DATE, s.PUBLICATION_YEAR,
    s.OUTPUT_TYPE, s.VENUE_NAME, s.OA_FLAG = 1, s.OA_STATUS, s.CITED_BY_COUNT,
    s.LANGUAGE, s.PRIMARY_SOURCE_NAME, s.FIRST_SEEN_AT, s.LAST_SEEN_AT, :batch_id
  );

  -- Schema drift: required key missing in any payload of the batch ------------
  INSERT INTO PAPERSONAR.PROJECT_AUDIT.SCHEMA_DRIFT_LOG (
    DRIFT_ID, BATCH_ID, SOURCE_NAME, ENTITY_NAME, KEY_NAME, DRIFT_TYPE,
    IS_REQUIRED, FIRST_SEEN_AT
  )
  SELECT
    SHA2(
      d.SOURCE_NAME || '|' || d.ENTITY_NAME || '|' || d.BATCH_ID || '|' ||
      d.KEY_NAME || '|MISSING_REQUIRED',
      256
    ),
    d.BATCH_ID, d.SOURCE_NAME, d.ENTITY_NAME, d.KEY_NAME,
    'MISSING_REQUIRED', TRUE, CURRENT_TIMESTAMP()
  FROM (
    SELECT
      b.SOURCE_NAME,
      b.ENTITY_NAME,
      b.BATCH_ID,
      e.KEY_NAME,
      COUNT(*) AS TOTAL_ROWS,
      COUNT_IF(
        ARRAY_CONTAINS(TO_VARIANT(e.KEY_NAME), OBJECT_KEYS(b.PAYLOAD))
      ) AS PRESENT_ROWS
    FROM (
      SELECT 'OPENALEX' AS SOURCE_NAME, 'WORK' AS ENTITY_NAME, BATCH_ID, PAYLOAD
      FROM PAPERSONAR.PROJECT_BRONZE.BRZ_OPENALEX_WORK WHERE BATCH_ID = :batch_id
      UNION ALL
      SELECT 'CROSSREF', 'WORK', BATCH_ID, PAYLOAD
      FROM PAPERSONAR.PROJECT_BRONZE.BRZ_CROSSREF_WORK WHERE BATCH_ID = :batch_id
      UNION ALL
      SELECT 'ARXIV', 'RECORD', BATCH_ID, PAYLOAD
      FROM PAPERSONAR.PROJECT_BRONZE.BRZ_ARXIV_RECORD WHERE BATCH_ID = :batch_id
      UNION ALL
      SELECT 'DATACITE', 'DOI', BATCH_ID, PAYLOAD
      FROM PAPERSONAR.PROJECT_BRONZE.BRZ_DATACITE_DOI WHERE BATCH_ID = :batch_id
      UNION ALL
      SELECT 'ZENODO', 'RECORD', BATCH_ID, PAYLOAD
      FROM PAPERSONAR.PROJECT_BRONZE.BRZ_ZENODO_RECORD WHERE BATCH_ID = :batch_id
    ) b
    JOIN PAPERSONAR.PROJECT_REF.REF_EXPECTED_KEY e
      ON e.SOURCE_NAME = b.SOURCE_NAME
     AND e.ENTITY_NAME = b.ENTITY_NAME
     AND e.IS_REQUIRED
    GROUP BY b.SOURCE_NAME, b.ENTITY_NAME, b.BATCH_ID, e.KEY_NAME
  ) d
  WHERE d.PRESENT_ROWS < d.TOTAL_ROWS
    AND NOT EXISTS (
      SELECT 1
      FROM PAPERSONAR.PROJECT_AUDIT.SCHEMA_DRIFT_LOG existing
      WHERE existing.DRIFT_ID = SHA2(
        d.SOURCE_NAME || '|' || d.ENTITY_NAME || '|' || d.BATCH_ID || '|' ||
        d.KEY_NAME || '|MISSING_REQUIRED',
        256
      )
    );

  MERGE INTO PAPERSONAR.PROJECT_AUDIT.LINEAGE_EVENT t
  USING (
    SELECT
      SHA2(:batch_id || '|SILVER|OBSERVATION', 256) AS EVENT_ID,
      :batch_id AS BATCH_ID,
      'SILVER' AS LAYER,
      'SLV_SOURCE_OBSERVATION' AS OBJECT_NAME,
      'TRANSFORM' AS EVENT_TYPE,
      (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_SOURCE_OBSERVATION
        WHERE BATCH_ID = :batch_id) AS INPUT_COUNT,
      (SELECT COUNT(*) FROM PAPERSONAR.PROJECT_SILVER.SLV_OUTPUT_CROSSWALK
        WHERE BATCH_ID = :batch_id) AS OUTPUT_COUNT
  ) s
  ON t.EVENT_ID = s.EVENT_ID
  WHEN MATCHED THEN UPDATE SET
    t.INPUT_COUNT = s.INPUT_COUNT,
    t.OUTPUT_COUNT = s.OUTPUT_COUNT,
    t.EVENT_AT = CURRENT_TIMESTAMP()
  WHEN NOT MATCHED THEN INSERT
    (EVENT_ID, BATCH_ID, LAYER, OBJECT_NAME, EVENT_TYPE, INPUT_COUNT,
     OUTPUT_COUNT, EVENT_AT)
    VALUES (s.EVENT_ID, s.BATCH_ID, s.LAYER, s.OBJECT_NAME, s.EVENT_TYPE,
            s.INPUT_COUNT, s.OUTPUT_COUNT, CURRENT_TIMESTAMP());

  RETURN 'SILVER_OK:' || observation_count || ':' || crosswalk_count;
END;
$$;

COMMENT ON PROCEDURE PAPERSONAR.PROJECT_SILVER.SP_TRANSFORM_BATCH()
  IS 'Typed silver projection, deterministic identity crosswalk and canonical merge';
