import type { Filters } from "@/server/metrics/guards";
import { fixed, limitOf, numberFilter, stringFilter, text, type CompiledQuery } from "@/server/metrics/sql/shared";

const VIEW = "PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_YEAR";

function yearRange(filters: Filters, bindings: Binding[]) {
  const from = numberFilter(filters, "year_from", 2024);
  const to = numberFilter(filters, "year_to", 2025);
  bindings.push(fixed(from), fixed(to));
  return "PUBLICATION_YEAR BETWEEN ? AND ?";
}

type Binding = ReturnType<typeof fixed>;

export function topicGrowth(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const parts = [yearRange(filters, bindings), "CATEGORY_KEY <> 'unclassified'"];
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  return {
    templateId: "M01_TOPIC_GROWTH_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR, WORKS, CORPUS_WORKS, CLASSIFIED_WORKS, SHARE_OF_CORPUS
          FROM ${VIEW} WHERE ${parts.join(" AND ")}
          ORDER BY CATEGORY_KEY, PUBLICATION_YEAR LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}

export function topicShare(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const parts = [yearRange(filters, bindings), "CATEGORY_KEY <> 'unclassified'"];
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  return {
    templateId: "M02_TOPIC_SHARE_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR, WORKS, CORPUS_WORKS,
                 CLASSIFIED_WORKS, SHARE_OF_CORPUS, SHARE_OF_CLASSIFIED_CORPUS
          FROM ${VIEW} WHERE ${parts.join(" AND ")}
          ORDER BY PUBLICATION_YEAR DESC, SHARE_OF_CORPUS DESC LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}

export function topicVolume(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const parts = [yearRange(filters, bindings), "CATEGORY_KEY <> 'unclassified'"];
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  return {
    templateId: "M03_TOPIC_VOLUME_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR, WORKS, CORPUS_WORKS, CLASSIFIED_WORKS
          FROM ${VIEW} WHERE ${parts.join(" AND ")}
          ORDER BY WORKS DESC LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}

export function yearDistribution(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const parts = [yearRange(filters, bindings)];
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  } else {
    parts.push("CATEGORY_KEY <> 'unclassified'");
  }
  return {
    templateId: "M15_YEAR_DISTRIBUTION_V1",
    sql: `SELECT PUBLICATION_YEAR, SUM(WORKS) AS WORKS, MAX(CORPUS_WORKS) AS CORPUS_WORKS
          FROM ${VIEW} WHERE ${parts.join(" AND ")}
          GROUP BY PUBLICATION_YEAR ORDER BY PUBLICATION_YEAR LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}
