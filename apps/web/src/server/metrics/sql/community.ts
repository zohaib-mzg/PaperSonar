import type { Filters } from "@/server/metrics/guards";
import { fixed, limitOf, numberFilter, stringFilter, text, type CompiledQuery } from "@/server/metrics/sql/shared";

type Binding = ReturnType<typeof text>;
const COMMUNITY = "PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_INSTITUTION_TOPIC";

function yearBindings(filters: Filters): Binding[] {
  return [
    fixed(numberFilter(filters, "year_from", 2021)),
    fixed(numberFilter(filters, "year_to", 2025)),
  ];
}

export function institutionActivity(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const institution = stringFilter(filters, "institution_key");
  const parts = ["IS_UNKNOWN_INSTITUTION = FALSE", "PUBLICATION_YEAR BETWEEN ? AND ?"];
  bindings.push(...yearBindings(filters));
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  if (institution) {
    parts.push("INSTITUTION_KEY = ?");
    bindings.push(text(institution));
  }
  return {
    templateId: "M09_INSTITUTION_ACTIVITY_V1",
    sql: `SELECT INSTITUTION_KEY, INSTITUTION_NAME, COUNTRY_CODE, CATEGORY_KEY,
                 CATEGORY_LABEL, PUBLICATION_YEAR, WORKS, FRACTIONAL_CREDIT
          FROM ${COMMUNITY} WHERE ${parts.join(" AND ")}
          ORDER BY FRACTIONAL_CREDIT DESC LIMIT ${limitOf(filters, 20)}`,
    bindings,
  };
}

export function institutionConcentration(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const parts = ["IS_UNKNOWN_INSTITUTION = FALSE", "PUBLICATION_YEAR BETWEEN ? AND ?"];
  bindings.push(...yearBindings(filters));
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  return {
    templateId: "M10_INSTITUTION_CONCENTRATION_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR, INSTITUTION_KEY,
                 INSTITUTION_NAME, WORKS, FRACTIONAL_CREDIT
          FROM ${COMMUNITY} WHERE ${parts.join(" AND ")}
          ORDER BY PUBLICATION_YEAR, FRACTIONAL_CREDIT DESC LIMIT ${limitOf(filters, 50)}`,
    bindings,
  };
}

export function authorActivity(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const author = stringFilter(filters, "author_key") ?? stringFilter(filters, "orcid");
  const parts = ["PUBLICATION_YEAR BETWEEN ? AND ?"];
  bindings.push(...yearBindings(filters));
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  if (author) {
    parts.push("(AUTHOR_KEY = ? OR ORCID = ?)");
    bindings.push(text(author), text(author));
  }
  return {
    templateId: "M11_AUTHOR_ACTIVITY_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR, AUTHOR_KEY, AUTHOR_NAME,
                 ORCID, SOURCE_NAME, WORKS
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_AUTHOR_ACTIVITY
          WHERE ${parts.join(" AND ")}
          ORDER BY WORKS DESC LIMIT ${limitOf(filters, 20)}`,
    bindings,
  };
}

export function venueActivity(filters: Filters): CompiledQuery {
  const bindings: Binding[] = [];
  const category = stringFilter(filters, "category_key");
  const venue = stringFilter(filters, "venue_name");
  const parts = ["PUBLICATION_YEAR BETWEEN ? AND ?"];
  bindings.push(...yearBindings(filters));
  if (category) {
    parts.push("CATEGORY_KEY = ?");
    bindings.push(text(category));
  }
  if (venue) {
    parts.push("VENUE_NAME = ?");
    bindings.push(text(venue));
  }
  return {
    templateId: "M12_VENUE_ACTIVITY_V1",
    sql: `SELECT CATEGORY_KEY, CATEGORY_LABEL, PUBLICATION_YEAR, VENUE_NAME,
                 OUTPUT_TYPE_NAME, PRIMARY_SOURCE_NAME, WORKS
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_VENUE_TOPIC
          WHERE ${parts.join(" AND ")}
          ORDER BY WORKS DESC LIMIT ${limitOf(filters, 20)}`,
    bindings,
  };
}
