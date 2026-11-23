import { describe, expect, it } from "vitest";
import { compileMetric } from "@/server/metrics/compiler";
import { metrics } from "@/server/metrics/catalogue";
import type { Filters } from "@/server/metrics/guards";

const fullFilters: Filters = {
  category_key: "rag",
  category_key_b: "llm",
  year_from: 2021,
  year_to: 2025,
  source_name: "OPENALEX",
  search_term: "transformer",
  snapshot_date: "2025-01-01",
  institution_key: "inst-1",
  author_key: "author-1",
  venue_name: "Nature",
  output_type: "article",
  limit: 10,
};

function countPlaceholders(sql: string): number {
  return (sql.match(/\?/g) ?? []).length;
}

describe("validated SQL templates", () => {
  it("compiles every metric to a read-only, bound query", () => {
    for (const metric of metrics) {
      const compiled = compileMetric(metric.id, fullFilters);
      expect(compiled.sql.trimStart()).toMatch(/^(SELECT|WITH)/i);
      expect(compiled.sql).not.toMatch(/;\s*$/);
      expect(compiled.sql).not.toMatch(/DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|EXEC|IDENTIFIER\s*\(/i);
      expect(compiled.sql).not.toMatch(/BRONZE|SILVER|PROJECT_DW|PROJECT_AUDIT/);
      expect(countPlaceholders(compiled.sql)).toBe(compiled.bindings.length);
      const limit = Number(compiled.sql.match(/LIMIT\s+(\d+)/i)?.[1] ?? 0);
      expect(limit).toBeGreaterThan(0);
      expect(limit).toBeLessThanOrEqual(50);
    }
  });

  it("binds growth filters in placeholder order", () => {
    const compiled = compileMetric("M01", {
      category_key: "rag",
      year_from: 2024,
      year_to: 2025,
    });
    expect(compiled.bindings).toEqual([
      { type: "FIXED", value: 2024 },
      { type: "FIXED", value: 2025 },
      { type: "TEXT", value: "rag" },
    ]);
  });

  it("requires a search term for title search", () => {
    expect(() => compileMetric("M17", {})).toThrow(/search_term/);
  });

  it("escapes LIKE wildcards in search terms", () => {
    const compiled = compileMetric("M17", { search_term: "100%_rag" });
    expect(compiled.bindings[0].value).toBe("%100\\%\\_rag%");
  });
});
