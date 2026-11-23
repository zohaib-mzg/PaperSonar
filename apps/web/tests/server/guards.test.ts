import { describe, expect, it } from "vitest";
import {
  growthSuppressed,
  intersectionReportable,
  latestCompleteYear,
  validateFilters,
} from "@/server/metrics/guards";

describe("filter guards", () => {
  it("accepts known taxonomy categories and sources", () => {
    const result = validateFilters({
      category_key: "rag",
      source_name: "openalex",
      year_from: 2024,
      year_to: 2025,
      limit: 5,
    });
    expect(result.rejected).toEqual([]);
    expect(result.filters).toMatchObject({
      category_key: "rag",
      source_name: "OPENALEX",
      year_from: 2024,
      year_to: 2025,
      limit: 5,
    });
  });

  it("rejects unknown keys, unknown categories and SQL markers", () => {
    const result = validateFilters({
      category_key: "not-a-category",
      source_name: "DROP TABLE",
      where_clause: "1=1",
      search_term: "x; DROP TABLE y",
      limit: 999,
    });
    expect(result.rejected).toEqual(
      expect.arrayContaining([
        "category_key",
        "source_name",
        "where_clause",
        "search_term",
        "limit",
      ]),
    );
  });

  it("applies disclosure thresholds", () => {
    expect(growthSuppressed(29, 100)).toBe(true);
    expect(growthSuppressed(30, 100)).toBe(false);
    expect(intersectionReportable(100, 200, 5)).toBe(true);
    expect(intersectionReportable(99, 200, 5)).toBe(false);
    expect(intersectionReportable(100, 200, 4)).toBe(false);
  });

  it("uses the previous calendar year as the latest complete year", () => {
    expect(latestCompleteYear(new Date("2026-11-23T00:00:00Z"))).toBe(2025);
  });
});
