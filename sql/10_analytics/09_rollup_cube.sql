-- =============================================================================
-- PaperSonar Phase 3 - WP3 OLAP: ROLLUP, CUBE and GROUPING SETS (READ-ONLY)
-- =============================================================================
-- Purpose: Provide the three OLAP aggregations the Phase 3 matrix asks for on
--          the published corpus:
--            OLP1 taxonomy x publication year, aggregated with ROLLUP.
--            OLP2 output type x primary source, aggregated with CUBE.
--            OLP3 topic x access status x publication year, aggregated with
--                 GROUPING SETS.
--          Every result set emits GROUPING_ID plus explicit subtotal flags so
--          a reader cannot mistake an aggregate row for a member row.
-- Inputs: PROJECT_REPORTING.VW_RESEARCH_OUTPUT (published outputs only),
--         PROJECT_DW.DIM_CATEGORY.
-- Outputs: result sets only; save as
--          docs/phase3/evidence/02_olap/OLP1_rollup_category_year.csv,
--          docs/phase3/evidence/02_olap/OLP2_cube_output_type_source.csv and
--          docs/phase3/evidence/02_olap/OLP3_grouping_sets_topic_access.csv.
-- Idempotent: Yes - SELECT only.
-- Owner: PAPERSONAR_REPORTER (read-only).
-- Parameters: OLP1 uses the primary category of every published output and
--             excludes 'unclassified' from the hierarchy; OLP2 uses the output
--             type and the primary source; OLP3 uses the primary category and
--             the access status. The year scope is the whole published corpus
--             because a rollup over a truncated year window would hide the
--             hierarchy it is meant to show.
-- Cost: each analysis scans VW_RESEARCH_OUTPUT once (about 296k rows).
-- Deploy: manual - analytical query, run it from a worksheet.
-- =============================================================================
-- The reporting view already enforces the publication contract: only outputs
-- whose LAST_BATCH_ID is in PROJECT_AUDIT.PUBLISHED_BATCH are visible.
--
-- Reading the flags:
--   GROUPING_ID = bitmask of the grouped-out columns, 0 means "member row".
--   IS_MEMBER  = both dimensions present, a real data point.
--   IS_SUBTOTAL = one dimension grouped out, a partial aggregate.
--   IS_GRAND_TOTAL = every dimension grouped out, the cube total.
-- GROUPING() is used next to GROUPING_ID because it states each grouped-out
-- column explicitly and does not depend on the bit order of GROUPING_ID.

-- ---------------------------------------------------------------------------
-- OLP1 - ROLLUP over category and publication year
-- The hierarchy is category -> year -> all years, so ROLLUP(CATEGORY_KEY,
-- PUBLICATION_YEAR) produces member rows, one subtotal per category and one
-- grand total for the whole classified corpus.
-- ---------------------------------------------------------------------------
WITH category_year AS (
  SELECT
    output.CATEGORY_KEY,
    output.CATEGORY_LABEL,
    output.PUBLICATION_YEAR,
    COUNT(DISTINCT output.OUTPUT_SK) AS WORKS
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.CATEGORY_KEY <> 'unclassified'
    AND output.PUBLICATION_YEAR IS NOT NULL
  GROUP BY 1, 2, 3
)
SELECT
  IFF(GROUPING(CATEGORY_KEY) = 1, NULL, CATEGORY_KEY)     AS CATEGORY_KEY,
  IFF(GROUPING(CATEGORY_KEY) = 1, NULL, MAX(CATEGORY_LABEL)) AS CATEGORY_LABEL,
  IFF(GROUPING(PUBLICATION_YEAR) = 1, NULL, PUBLICATION_YEAR) AS PUBLICATION_YEAR,
  SUM(WORKS) AS WORKS,
  GROUPING_ID(CATEGORY_KEY, PUBLICATION_YEAR) AS GROUPING_ID,
  IFF(GROUPING(CATEGORY_KEY) = 0 AND GROUPING(PUBLICATION_YEAR) = 0, TRUE, FALSE)
    AS IS_MEMBER,
  IFF(GROUPING(CATEGORY_KEY) = 0 AND GROUPING(PUBLICATION_YEAR) = 1, TRUE, FALSE)
    AS IS_SUBTOTAL,
  IFF(GROUPING(CATEGORY_KEY) = 1 AND GROUPING(PUBLICATION_YEAR) = 1, TRUE, FALSE)
    AS IS_GRAND_TOTAL
FROM category_year
GROUP BY ROLLUP(CATEGORY_KEY, PUBLICATION_YEAR)
ORDER BY IS_GRAND_TOTAL, IS_SUBTOTAL, CATEGORY_KEY, PUBLICATION_YEAR;

-- ---------------------------------------------------------------------------
-- OLP2 - CUBE over output type and primary source
-- The cube has two dimensions and therefore four aggregation levels: the
-- member rows, one subtotal per output type, one subtotal per source and the
-- grand total. It is deliberately not a cube over more dimensions: the
-- published corpus is one taxonomy, one type vocabulary and one source list,
-- so a wider cube would multiply rows without adding an analysis the course
-- questions ask for.
-- ---------------------------------------------------------------------------
WITH type_source AS (
  SELECT
    output.OUTPUT_TYPE_NAME,
    output.PRIMARY_SOURCE_NAME,
    COUNT(DISTINCT output.OUTPUT_SK) AS WORKS
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  GROUP BY 1, 2
)
SELECT
  IFF(GROUPING(OUTPUT_TYPE_NAME) = 1, NULL, OUTPUT_TYPE_NAME) AS OUTPUT_TYPE_NAME,
  IFF(GROUPING(PRIMARY_SOURCE_NAME) = 1, NULL, PRIMARY_SOURCE_NAME)
    AS PRIMARY_SOURCE_NAME,
  SUM(WORKS) AS WORKS,
  GROUPING_ID(OUTPUT_TYPE_NAME, PRIMARY_SOURCE_NAME) AS GROUPING_ID,
  IFF(GROUPING(OUTPUT_TYPE_NAME) = 0 AND GROUPING(PRIMARY_SOURCE_NAME) = 0, TRUE, FALSE)
    AS IS_MEMBER,
  IFF(GROUPING(OUTPUT_TYPE_NAME) = 0 AND GROUPING(PRIMARY_SOURCE_NAME) = 1, TRUE, FALSE)
    AS IS_TYPE_SUBTOTAL,
  IFF(GROUPING(OUTPUT_TYPE_NAME) = 1 AND GROUPING(PRIMARY_SOURCE_NAME) = 0, TRUE, FALSE)
    AS IS_SOURCE_SUBTOTAL,
  IFF(GROUPING(OUTPUT_TYPE_NAME) = 1 AND GROUPING(PRIMARY_SOURCE_NAME) = 1, TRUE, FALSE)
    AS IS_GRAND_TOTAL
FROM type_source
GROUP BY CUBE(OUTPUT_TYPE_NAME, PRIMARY_SOURCE_NAME)
ORDER BY IS_GRAND_TOTAL, OUTPUT_TYPE_NAME, PRIMARY_SOURCE_NAME;

-- ---------------------------------------------------------------------------
-- OLP3 - GROUPING SETS over topic, access status and publication year
-- GROUPING SETS states the analysis levels explicitly instead of implying a
-- hierarchy: full detail, topic x access, topic x year, access x year, and
-- the three single-dimension totals. Each row carries the set it belongs to
-- through the flags, so a partial aggregate is never read as a member.
-- ---------------------------------------------------------------------------
WITH topic_access_year AS (
  SELECT
    output.CATEGORY_KEY,
    output.ACCESS_STATUS_NAME,
    output.PUBLICATION_YEAR,
    COUNT(DISTINCT output.OUTPUT_SK) AS WORKS
  FROM PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
  WHERE output.CATEGORY_KEY <> 'unclassified'
    AND output.PUBLICATION_YEAR IS NOT NULL
  GROUP BY 1, 2, 3
)
SELECT
  IFF(GROUPING(CATEGORY_KEY) = 1, NULL, CATEGORY_KEY) AS CATEGORY_KEY,
  IFF(GROUPING(ACCESS_STATUS_NAME) = 1, NULL, ACCESS_STATUS_NAME) AS ACCESS_STATUS_NAME,
  IFF(GROUPING(PUBLICATION_YEAR) = 1, NULL, PUBLICATION_YEAR) AS PUBLICATION_YEAR,
  SUM(WORKS) AS WORKS,
  GROUPING_ID(CATEGORY_KEY, ACCESS_STATUS_NAME, PUBLICATION_YEAR) AS GROUPING_ID,
  IFF(GROUPING(CATEGORY_KEY) = 0 AND GROUPING(ACCESS_STATUS_NAME) = 0
      AND GROUPING(PUBLICATION_YEAR) = 0, TRUE, FALSE) AS IS_MEMBER,
  IFF(GROUPING(CATEGORY_KEY) = 0 AND GROUPING(ACCESS_STATUS_NAME) = 0
      AND GROUPING(PUBLICATION_YEAR) = 1, TRUE, FALSE) AS IS_TOPIC_ACCESS_SUBTOTAL,
  IFF(GROUPING(CATEGORY_KEY) = 1 AND GROUPING(ACCESS_STATUS_NAME) = 0
      AND GROUPING(PUBLICATION_YEAR) = 0, TRUE, FALSE) AS IS_ACCESS_YEAR_SUBTOTAL,
  IFF(GROUPING(CATEGORY_KEY) = 0 AND GROUPING(ACCESS_STATUS_NAME) = 1
      AND GROUPING(PUBLICATION_YEAR) = 0, TRUE, FALSE) AS IS_TOPIC_YEAR_SUBTOTAL,
  IFF(GROUPING(CATEGORY_KEY) = 1 AND GROUPING(ACCESS_STATUS_NAME) = 1
      AND GROUPING(PUBLICATION_YEAR) = 1, TRUE, FALSE) AS IS_GRAND_TOTAL
FROM topic_access_year
GROUP BY GROUPING SETS (
  (CATEGORY_KEY, ACCESS_STATUS_NAME, PUBLICATION_YEAR),
  (CATEGORY_KEY, ACCESS_STATUS_NAME),
  (CATEGORY_KEY, PUBLICATION_YEAR),
  (ACCESS_STATUS_NAME, PUBLICATION_YEAR),
  (CATEGORY_KEY),
  (PUBLICATION_YEAR),
  ()
)
ORDER BY IS_GRAND_TOTAL, CATEGORY_KEY, ACCESS_STATUS_NAME, PUBLICATION_YEAR;
