import type { Filters } from "@/server/metrics/guards";
import { fixed, limitOf, numberFilter, stringFilter, text, type CompiledQuery } from "@/server/metrics/sql/shared";

export function openAccess(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const parts = ["PUBLICATION_YEAR BETWEEN ? AND ?"];
  bindings.push(
    fixed(numberFilter(filters, "year_from", 2021)),
    fixed(numberFilter(filters, "year_to", 2025)),
  );
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  return {
    templateId: "M14_OPEN_ACCESS_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR, OUTPUT_TYPE_NAME,
                 WORKS, KNOWN_ACCESS_WORKS, UNKNOWN_ACCESS_WORKS, OPEN_ACCESS_WORKS,
                 OPEN_ACCESS_SHARE_KNOWN
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_ACCESS_TOPIC
          WHERE ${parts.join(" AND ")}
          ORDER BY PUBLICATION_YEAR DESC, WORKS DESC LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}

type Binding = ReturnType<typeof text>;
