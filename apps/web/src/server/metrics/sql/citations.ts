import type { Filters } from "@/server/metrics/guards";
import {
  dateBinding,
  limitOf,
  stringFilter,
  text,
  type CompiledQuery,
} from "@/server/metrics/sql/shared";

type Binding = ReturnType<typeof text>;

export function topicCitations(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const snapshot = stringFilter(filters, "snapshot_date");
  const parts = ["CATEGORY_KEY <> 'unclassified'"];
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  if (snapshot) {
    parts.push("SNAPSHOT_DATE = ?");
    bindings.push(dateBinding(snapshot));
  }
  return {
    templateId: "M04_TOPIC_CITATIONS_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR, SNAPSHOT_DATE, COHORT_SIZE,
                 OBSERVED_WORKS, TOTAL_CITATIONS, AVG_CITED_BY, MEDIAN_CITED_BY,
                 MIN_CITED_BY, MAX_CITED_BY, ZERO_CITATION_WORKS
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_CITATIONS
          WHERE ${parts.join(" AND ")}
          QUALIFY ROW_NUMBER() OVER (
            PARTITION BY CATEGORY_KEY, PUBLICATION_YEAR ORDER BY SNAPSHOT_DATE DESC
          ) = 1
          ORDER BY PUBLICATION_YEAR LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}

export function citationGains(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const source = stringFilter(filters, "source_name");
  const pairedParts: string[] = [];
  const finalParts: string[] = [];

  if (category) {
    pairedParts.push("output.CATEGORY_KEY = ?");
    finalParts.push("output.CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  if (source) {
    pairedParts.push("snapshot.SOURCE_NAME = ?");
    finalParts.push("paired.SOURCE_NAME = ?");
    bindings.push(text(source));
  }
  if (category) bindings.push(text(category));
  if (source) bindings.push(text(source));

  return {
    templateId: "M05_CITATION_GAINS_V1",
    sql: `WITH dates AS (
            SELECT DISTINCT SNAPSHOT_DATE
            FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_SNAPSHOT
            ORDER BY SNAPSHOT_DATE DESC LIMIT 2
          ), paired AS (
            SELECT snapshot.OUTPUT_SK, snapshot.SOURCE_NAME,
                   MIN(snapshot.CITED_BY_COUNT) AS EARLY_CITED_BY,
                   MAX(snapshot.CITED_BY_COUNT) AS LATE_CITED_BY
            FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_SNAPSHOT snapshot
            JOIN dates ON dates.SNAPSHOT_DATE = snapshot.SNAPSHOT_DATE
            JOIN PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
              ON output.OUTPUT_SK = snapshot.OUTPUT_SK
            ${pairedParts.length ? `WHERE ${pairedParts.join(" AND ")}` : ""}
            GROUP BY snapshot.OUTPUT_SK, snapshot.SOURCE_NAME
            HAVING COUNT(DISTINCT snapshot.SNAPSHOT_DATE) = 2
          )
          SELECT paired.OUTPUT_SK, paired.SOURCE_NAME, output.CATEGORY_KEY,
                 output.CATEGORY_LABEL, paired.EARLY_CITED_BY, paired.LATE_CITED_BY,
                 paired.LATE_CITED_BY - paired.EARLY_CITED_BY AS CITATION_CHANGE
          FROM paired
          JOIN PAPERSONAR.PROJECT_REPORTING.VW_RESEARCH_OUTPUT output
            ON output.OUTPUT_SK = paired.OUTPUT_SK
          ${finalParts.length ? `WHERE ${finalParts.join(" AND ")}` : ""}
          ORDER BY CITATION_CHANGE DESC LIMIT ${limitOf(filters, 20)}`,
    bindings,
  };
}

export function outputCitationRank(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const snapshot = stringFilter(filters, "snapshot_date");
  const parts = ["CATEGORY_KEY <> 'unclassified'"];
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  if (snapshot) {
    parts.push("SNAPSHOT_DATE = ?");
    bindings.push(dateBinding(snapshot));
  }
  return {
    templateId: "M23_OUTPUT_CITATION_RANK_V1",
    sql: `SELECT OUTPUT_SK, CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR,
                 PRIMARY_SOURCE_NAME, SNAPSHOT_DATE, CITED_BY_COUNT
          FROM PAPERSONAR.PROJECT_REPORTING.VW_CITATION_COHORTS
          WHERE ${parts.join(" AND ")}
          QUALIFY ROW_NUMBER() OVER (PARTITION BY OUTPUT_SK ORDER BY SNAPSHOT_DATE DESC) = 1
          ORDER BY CITED_BY_COUNT DESC LIMIT ${limitOf(filters, 10)}`,
    bindings,
  };
}
