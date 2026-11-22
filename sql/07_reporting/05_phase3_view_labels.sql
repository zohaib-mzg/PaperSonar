-- =============================================================================
-- PaperSonar Phase 3 - category label lookup for the BI layer (DEPLOYABLE)
-- =============================================================================
-- Purpose: Provide the category key to label mapping that the BI model needs
--          for VW_TOPIC_INTERSECTIONS, which carries the two category keys of
--          a pair but no labels. The lookup is a separate small table so the
--          Power BI model can label both sides of a pair without changing the
--          grain of the pair view.
-- Inputs: PROJECT_DW.DIM_CATEGORY.
-- Outputs: PROJECT_REPORTING.VW_CATEGORY_LABEL and the reporter grant.
-- Idempotent: Yes - CREATE OR REPLACE SECURE VIEW and GRANT are repeatable.
-- Owner: PAPERSONAR_ADMIN
-- Parameters: None.
-- Cost: query-time only; the view reads one small dimension.
-- =============================================================================

CREATE OR REPLACE SECURE VIEW PAPERSONAR.PROJECT_REPORTING.VW_CATEGORY_LABEL AS
SELECT
  category.CATEGORY_SK,
  category.CATEGORY_KEY,
  category.LABEL AS CATEGORY_LABEL,
  category.PARENT_KEY,
  category.TAXONOMY_VERSION,
  category.IS_UNKNOWN,
  CURRENT_DATE() AS RETRIEVED_ON
FROM PAPERSONAR.PROJECT_DW.DIM_CATEGORY category;

GRANT SELECT ON VIEW PAPERSONAR.PROJECT_REPORTING.VW_CATEGORY_LABEL
  TO ROLE PAPERSONAR_REPORTER;
