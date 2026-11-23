import { describe, expect, it } from "vitest";
import {
  categories,
  collectCategoryAliases,
  metrics,
  publicCategoryList,
  publicMetricList,
} from "@/server/metrics/catalogue";
import { TEMPLATE_IDS } from "@/server/metrics/sql";

describe("public metric catalogue", () => {
  it("defines exactly 24 unique public metrics", () => {
    expect(metrics).toHaveLength(24);
    expect(new Set(metrics.map((metric) => metric.id)).size).toBe(24);
  });

  it("has a compiled template for every metric", () => {
    expect(new Set(TEMPLATE_IDS)).toEqual(new Set(metrics.map((metric) => metric.id)));
  });

  it("only points at published reporting views", () => {
    for (const metric of metrics) {
      expect(metric.primary_view === "composed" || metric.primary_view.startsWith("VW_")).toBe(true);
      expect(metric.primary_view).not.toMatch(/BRONZE|SILVER|PROJECT_DW|PROJECT_AUDIT/);
    }
  });

  it("keeps RAG as a distinct category", () => {
    const rag = categories.find((category) => category.key === "rag");
    expect(rag?.label).toBe("Retrieval-Augmented Generation");
    expect(collectCategoryAliases("rag")).toContain("rag");
    expect(collectCategoryAliases("rag")).not.toContain("ai-ml");
  });

  it("exposes public metadata without internal fields", () => {
    for (const metric of publicMetricList()) {
      expect(metric).not.toHaveProperty("sql");
      expect(metric).toHaveProperty("denominator");
      expect(metric).toHaveProperty("caveats");
    }
    expect(publicCategoryList().length).toBeGreaterThan(50);
  });
});
