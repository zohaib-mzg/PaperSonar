import type { Filters } from "@/server/metrics/guards";
import { limitOf, stringFilter, text, type CompiledQuery } from "@/server/metrics/sql/shared";

export function topicIntersections(filters: Filters): CompiledQuery {
  const bindings = [];
  const category = stringFilter(filters, "category_key");
  const other = stringFilter(filters, "category_key_b");
  if (category) bindings.push(text(category));
  if (other) bindings.push(text(other));
  const parts = [];
  if (category) parts.push("CATEGORY_KEY_A = ?");
  if (other) parts.push("CATEGORY_KEY_B = ?");
  return {
    templateId: "M06_TOPIC_INTERSECTIONS_V1",
    sql: `SELECT CATEGORY_KEY_A, CATEGORY_LABEL_A, CATEGORY_KEY_B, CATEGORY_LABEL_B,
                 JOINT_WORKS, PARENT_WORKS_A, PARENT_WORKS_B,
                 JOINT_TO_SMALLER_PARENT_RATIO, IS_REPORTABLE, MIN_PARENT_WORKS, MIN_JOINT_WORKS
          FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_TOPIC_INTERSECTIONS
          ${parts.length ? `WHERE ${parts.join(" AND ")}` : ""}
          ORDER BY JOINT_WORKS DESC LIMIT ${limitOf(filters, 20)}`,
    bindings,
  };
}
