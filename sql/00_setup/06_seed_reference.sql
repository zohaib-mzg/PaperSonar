-- =============================================================================
-- Purpose: Seed source precedence and expected top-level payload keys.
-- Inputs: PROJECT_REF tables.
-- Outputs: REF_SOURCE and REF_EXPECTED_KEY rows.
-- Idempotent: Yes - MERGE on the declared business keys.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None.
-- Cost: Metadata only.
-- =============================================================================
-- VERIFY: confirm the required keys against the actual API responses for the
-- chosen windows. Missing optional keys are not failures; missing required keys
-- are critical (DQ-011).

MERGE INTO PAPERSONAR.PROJECT_REF.REF_SOURCE t
USING (
  SELECT column1 AS SOURCE_NAME, column2 AS ENTITY_NAME, column3 AS SOURCE_PRIORITY
  FROM VALUES
    ('OPENALEX', 'WORK', 1),
    ('CROSSREF', 'WORK', 2),
    ('ARXIV', 'RECORD', 3),
    ('DATACITE', 'DOI', 4),
    ('ZENODO', 'RECORD', 5)
) s
ON t.SOURCE_NAME = s.SOURCE_NAME AND t.ENTITY_NAME = s.ENTITY_NAME
WHEN MATCHED THEN UPDATE SET t.SOURCE_PRIORITY = s.SOURCE_PRIORITY, t.IS_ACTIVE = TRUE
WHEN NOT MATCHED THEN INSERT (SOURCE_NAME, ENTITY_NAME, SOURCE_PRIORITY, IS_ACTIVE)
  VALUES (s.SOURCE_NAME, s.ENTITY_NAME, s.SOURCE_PRIORITY, TRUE);

MERGE INTO PAPERSONAR.PROJECT_REF.REF_EXPECTED_KEY t
USING (
  SELECT column1 AS SOURCE_NAME, column2 AS ENTITY_NAME, column3 AS KEY_NAME,
         column4 AS IS_REQUIRED
  FROM VALUES
    ('OPENALEX', 'WORK', 'id', TRUE),
    ('OPENALEX', 'WORK', 'display_name', FALSE),
    ('OPENALEX', 'WORK', 'publication_date', FALSE),
    ('OPENALEX', 'WORK', 'authorships', FALSE),
    ('CROSSREF', 'WORK', 'DOI', FALSE),
    ('CROSSREF', 'WORK', 'title', FALSE),
    ('CROSSREF', 'WORK', 'issued', FALSE),
    ('CROSSREF', 'WORK', 'author', FALSE),
    ('DATACITE', 'DOI', 'id', TRUE),
    ('DATACITE', 'DOI', 'attributes', FALSE),
    ('ARXIV', 'RECORD', 'identifier', TRUE),
    ('ARXIV', 'RECORD', 'metadata_xml', TRUE),
    ('ZENODO', 'RECORD', 'identifier', TRUE),
    ('ZENODO', 'RECORD', 'metadata_xml', TRUE)
) s
ON t.SOURCE_NAME = s.SOURCE_NAME AND t.ENTITY_NAME = s.ENTITY_NAME
   AND t.KEY_NAME = s.KEY_NAME
WHEN MATCHED THEN UPDATE SET t.IS_REQUIRED = s.IS_REQUIRED
WHEN NOT MATCHED THEN INSERT (SOURCE_NAME, ENTITY_NAME, KEY_NAME, IS_REQUIRED, SCHEMA_VERSION)
  VALUES (s.SOURCE_NAME, s.ENTITY_NAME, s.KEY_NAME, s.IS_REQUIRED, 'v1');
