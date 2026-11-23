import type { Filters } from "@/server/metrics/guards";
import { escapeLikeTerm, limitOf, stringFilter, text, type CompiledQuery } from "@/server/metrics/sql/shared";

export function outputSearch(filters: Filters): CompiledQuery {
  const term = stringFilter(filters, "search_term");
  if (!term) throw new Error("search_term is required for output search");
  return {
    templateId: "M17_OUTPUT_SEARCH_V1",
    sql: `SELECT OUTPUT_SK, OUTPUT_BK, TITLE, PUBLICATION_YEAR, CATEGORY_KEY,
                 CATEGORY_LABEL, PRIMARY_SOURCE_NAME, OUTPUT_TYPE_NAME, VENUE_NAME,
                 ACCESS_STATUS_NAME, CITED_BY_COUNT
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_OUTPUT_SEARCH
          WHERE TITLE ILIKE ?
          ORDER BY PUBLICATION_YEAR DESC, CITED_BY_COUNT DESC
          LIMIT ${limitOf(filters, 20)}`,
    bindings: [text(escapeLikeTerm(term))],
  };
}

export function dataStatus(filters: Filters): CompiledQuery {
  const source = stringFilter(filters, "source_name");
  return {
    templateId: "M18_DATA_STATUS_V1",
    sql: `SELECT SOURCE_NAME, ENTITY_NAME, BATCH_ID, PUBLISHED_AT, WINDOW_START,
                 WINDOW_END, IS_CAPPED
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_DATA_STATUS
          ${source ? "WHERE SOURCE_NAME = ?" : ""}
          ORDER BY SOURCE_NAME LIMIT ${limitOf(filters, 50)}`,
    bindings: source ? [text(source)] : [],
  };
}

export function corpusSummary(): CompiledQuery {
  return {
    templateId: "M19_CORPUS_SUMMARY_V1",
    sql: `SELECT TOTAL_OUTPUTS, CLASSIFIED_OUTPUTS, SOURCE_COUNT,
                 EARLIEST_PUBLICATION_YEAR, LATEST_PUBLICATION_YEAR,
                 LATEST_SNAPSHOT_DATE, LATEST_PUBLISHED_AT, RETRIEVED_ON
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_CORPUS_SUMMARY
          LIMIT 1`,
    bindings: [],
  };
}

export function topicLookup(filters: Filters): CompiledQuery {
  const category = stringFilter(filters, "category_key");
  return {
    templateId: "M20_TOPIC_LOOKUP_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PARENT_KEY AS PARENT_CATEGORY_KEY,
                 TAXONOMY_VERSION, IS_UNKNOWN
          FROM PAPERSONAR.PROJECT_REPORTING.VW_CATEGORY_LABEL
          ${category ? "WHERE CATEGORY_KEY = ?" : ""}
          ORDER BY CATEGORY_KEY LIMIT ${limitOf(filters, 50)}`,
    bindings: category ? [text(category)] : [],
  };
}

export function comparison(filters: Filters): CompiledQuery {
  const left = stringFilter(filters, "category_key") ?? "ai-ml";
  const right = stringFilter(filters, "category_key_b") ?? "physics";
  return {
    templateId: "M21_COMPARISON_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR, WORKS, CORPUS_WORKS
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_YEAR
          WHERE CATEGORY_KEY IN (?, ?) AND CATEGORY_KEY <> 'unclassified'
          ORDER BY CATEGORY_KEY, PUBLICATION_YEAR LIMIT ${limitOf(filters, 50)}`,
    bindings: [text(left), text(right)],
  };
}

export function freshness(): CompiledQuery {
  return {
    templateId: "M22_FRESHNESS_V1",
    sql: `SELECT LATEST_SNAPSHOT_DATE, LATEST_PUBLISHED_AT, TOTAL_OUTPUTS, RETRIEVED_ON
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_CORPUS_SUMMARY
          LIMIT 1`,
    bindings: [],
  };
}
