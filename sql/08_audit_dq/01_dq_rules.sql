-- =============================================================================
-- Purpose: Seed the DQ rule inventory that the runner and DQ procedure use as
--          the authoritative severity/description contract. Mirrors
--          config/quality_rules.yml.
-- Inputs: PROJECT_REF.REF_DQ_RULE.
-- Outputs: 12 active DQ rule rows.
-- Idempotent: Yes - MERGE on RULE_ID.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None.
-- Cost: Metadata only.
-- =============================================================================

MERGE INTO PAPERSONAR.PROJECT_REF.REF_DQ_RULE t
USING (
  SELECT column1 AS RULE_ID, column2 AS DESCRIPTION, column3 AS SEVERITY,
         column4 AS THRESHOLD_VALUE
  FROM VALUES
    ('DQ-001',
     'Every registered manifest file has a staging row count equal to its manifest record count.',
     'CRITICAL', 0),
    ('DQ-002',
     'Bronze observations for the batch equal the distinct staged (source, record id) keys.',
     'CRITICAL', 0),
    ('DQ-003',
     'Silver crosswalk rows plus quarantined rows reconcile to bronze observations for the batch.',
     'CRITICAL', 0),
    ('DQ-004',
     'Every fact grain (OUTPUT_SK) is unique in FACT_RESEARCH_OUTPUT.',
     'CRITICAL', 0),
    ('DQ-005',
     'Facts have no orphan or null dimension references (date, type, venue, access).',
     'CRITICAL', 0),
    ('DQ-006',
     'Bridge rows have no orphan author/topic/category dimension references.',
     'CRITICAL', 0),
    ('DQ-007',
     'Exactly one current SCD2 row exists per DIM_AUTHOR business key.',
     'CRITICAL', 0),
    ('DQ-008',
     'Invalid DOI values are visible in quarantine and never silently replaced.',
     'WARNING', 0),
    ('DQ-009',
     'Categorized outputs meet the configured minimum coverage ratio.',
     'WARNING', 0.60),
    ('DQ-010',
     'Source watermark freshness is within the configured maximum age.',
     'WARNING', 72),
    ('DQ-011',
     'Required top-level payload keys are present; missing required keys block publication.',
     'CRITICAL', 0),
    ('DQ-012',
     'Every output touched by the batch has exactly one primary category assignment.',
     'CRITICAL', 0)
) s
ON t.RULE_ID = s.RULE_ID
WHEN MATCHED THEN UPDATE SET
  t.DESCRIPTION = s.DESCRIPTION,
  t.SEVERITY = s.SEVERITY,
  t.THRESHOLD_VALUE = s.THRESHOLD_VALUE,
  t.IS_ACTIVE = TRUE,
  t.RULE_VERSION = 'v1'
WHEN NOT MATCHED THEN INSERT
  (RULE_ID, DESCRIPTION, SEVERITY, THRESHOLD_VALUE, IS_ACTIVE, RULE_VERSION)
  VALUES (s.RULE_ID, s.DESCRIPTION, s.SEVERITY, s.THRESHOLD_VALUE, TRUE, 'v1');
