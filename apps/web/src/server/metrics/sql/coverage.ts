import type { Filters } from "@/server/metrics/guards";
import { fixed, limitOf, numberFilter, stringFilter, text, type CompiledQuery } from "@/server/metrics/sql/shared";

type Binding = ReturnType<typeof text>;
const COVERAGE = "PAPERSONAR.PROJECT_REPORTING.VW_OUTPUT_COVERAGE";

function coverageWhere(filters: Filters, bindings: Binding[]): string {
  const parts = ["PUBLICATION_YEAR BETWEEN ? AND ?"];
  bindings.push(
    fixed(numberFilter(filters, "year_from", 2021)),
    fixed(numberFilter(filters, "year_to", 2025)),
  );
  const source = stringFilter(filters, "source_name");
  if (source) {
    parts.push("PRIMARY_SOURCE_NAME = ?");
    bindings.push(text(source));
  }
  return parts.join(" AND ");
}

export function sourceCoverage(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const where = coverageWhere(filters, bindings);
  return {
    templateId: "M07_SOURCE_COVERAGE_V1",
    sql: `SELECT PRIMARY_SOURCE_NAME, PUBLICATION_YEAR, OUTPUT_TYPE_NAME, OUTPUTS,
                 CATEGORIZED_OUTPUTS, CATEGORY_COVERAGE_RATIO, OUTPUTS_WITHOUT_DOI,
                 OUTPUTS_WITHOUT_VENUE, OUTPUTS_WITHOUT_ACCESS_STATUS, KNOWN_ACCESS_RATIO
          FROM ${COVERAGE} WHERE ${where}
          ORDER BY PUBLICATION_YEAR DESC, OUTPUTS DESC LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}

export function metadataCompleteness(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const where = coverageWhere(filters, bindings);
  return {
    templateId: "M08_METADATA_COMPLETENESS_V1",
    sql: `SELECT PRIMARY_SOURCE_NAME, PUBLICATION_YEAR, OUTPUT_TYPE_NAME, OUTPUTS,
                 OUTPUTS_WITHOUT_DOI, OUTPUTS_WITHOUT_VENUE, OUTPUTS_WITHOUT_ACCESS_STATUS,
                 KNOWN_ACCESS_RATIO
          FROM ${COVERAGE} WHERE ${where}
          ORDER BY OUTPUTS DESC LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}

export function outputTypeMix(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const where = coverageWhere(filters, bindings);
  return {
    templateId: "M13_OUTPUT_TYPE_MIX_V1",
    sql: `SELECT PRIMARY_SOURCE_NAME, PUBLICATION_YEAR, OUTPUT_TYPE_NAME,
                 SUM(OUTPUTS) AS OUTPUTS
          FROM ${COVERAGE} WHERE ${where}
          GROUP BY 1, 2, 3 ORDER BY OUTPUTS DESC LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}

export function crossSourceOverlap(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [
    fixed(numberFilter(filters, "year_from", 2021)),
    fixed(numberFilter(filters, "year_to", 2025)),
  ];
  const source = stringFilter(filters, "source_name");
  const sourceClause = source ? "AND observation.SOURCE_NAME = ?" : "";
  if (source) bindings.push(text(source));
  return {
    templateId: "M16_CROSS_SOURCE_OVERLAP_V1",
    sql: `SELECT output.OUTPUT_SK, output.PUBLICATION_YEAR,
                 COUNT(DISTINCT observation.SOURCE_NAME) AS SOURCE_COUNT,
                 COUNT(*) AS OBSERVATIONS
          FROM PAPERSONAR.PROJECT_REPORTING.VW_SOURCE_OBSERVATION observation
          JOIN PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
            ON output.OUTPUT_SK = observation.OUTPUT_SK
          WHERE output.PUBLICATION_YEAR BETWEEN ? AND ? ${sourceClause}
          GROUP BY output.OUTPUT_SK, output.PUBLICATION_YEAR
          HAVING COUNT(DISTINCT observation.SOURCE_NAME) >= 2
          ORDER BY SOURCE_COUNT DESC LIMIT ${limitOf(filters, 20)}`,
    bindings,
  };
}

export function sourceContribution(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [
    fixed(numberFilter(filters, "year_from", 2021)),
    fixed(numberFilter(filters, "year_to", 2025)),
  ];
  return {
    templateId: "M24_SOURCE_CONTRIBUTION_V1",
    sql: `SELECT observation.SOURCE_NAME, output.PUBLICATION_YEAR,
                 COUNT(DISTINCT output.OUTPUT_SK) AS CANONICAL_OUTPUTS,
                 COUNT(*) AS OBSERVATIONS
          FROM PAPERSONAR.PROJECT_REPORTING.VW_SOURCE_OBSERVATION observation
          JOIN PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
            ON output.OUTPUT_SK = observation.OUTPUT_SK
          WHERE output.PUBLICATION_YEAR BETWEEN ? AND ?
          GROUP BY observation.SOURCE_NAME, output.PUBLICATION_YEAR
          ORDER BY CANONICAL_OUTPUTS DESC LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}
