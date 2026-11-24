import { describe, expect, it } from "vitest";
import { buildAnswer, defaultFreshness } from "@/server/chat/answer";
import { metricById } from "@/server/metrics/catalogue";
import { resolveQuestion } from "@/server/metrics/resolver";
import type { SnowflakeRow } from "@/server/snowflake/types";

function build(metricId: string, question: string, rows: SnowflakeRow[]) {
  const plan = resolveQuestion(question);
  const metric = metricById.get(metricId)!;
  return buildAnswer({ plan, metric, rows, freshness: { ...defaultFreshness, latest_published_at: "2025-12-31" }, fallbackUsed: false });
}

describe("chart type selection", () => {
  it("uses line for time series citations", () => {
    const rows = [2021,2022,2023,2024,2025].map((y) => ({ PUBLICATION_YEAR: y, OBSERVED_WORKS: 100, AVG_CITED_BY: y - 2018, TOTAL_CITATIONS: 1000, COHORT_SIZE: 100 }));
    const a = build("M04", "Average citations per year for RAG", rows);
    expect(a.chart?.kind).toBe("line");
  });

  it("uses horizontal bar for rankings", () => {
    const rows = Array.from({ length: 5 }).map((_, i) => ({ INSTITUTION_NAME: `Inst ${i}`, FRACTIONAL_CREDIT: 100 - i * 10 }));
    const a = build("M09", "Which institutions publish the most on RAG?", rows);
    expect(a.chart?.kind).toBe("horizontal_bar");
  });

  it("uses donut for open access share", () => {
    const a = build("M14", "What share of RAG papers are open access?", [
      { CATEGORY_LABEL: "RAG", WORKS: 100, KNOWN_ACCESS_WORKS: 80, UNKNOWN_ACCESS_WORKS: 20, OPEN_ACCESS_WORKS: 50, OPEN_ACCESS_SHARE_KNOWN: 0.625 },
    ]);
    expect(a.chart?.kind).toBe("donut");
  });

  it("omits chart for 1-3 rows", () => {
    const a = build("M03", "How many RAG works were published in 2025?", [
      { CATEGORY_LABEL: "RAG", PUBLICATION_YEAR: 2025, WORKS: 42 },
    ]);
    expect(a.chart).toBeUndefined();
  });
});