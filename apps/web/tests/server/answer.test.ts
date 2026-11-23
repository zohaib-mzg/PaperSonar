import { describe, expect, it } from "vitest";
import { buildAnswer, defaultFreshness } from "@/server/chat/answer";
import { metricById } from "@/server/metrics/catalogue";
import { resolveQuestion } from "@/server/metrics/resolver";
import type { SnowflakeRow } from "@/server/snowflake/types";

function build(metricId: string, question: string, rows: SnowflakeRow[]) {
  const plan = resolveQuestion(question);
  const metric = metricById.get(metricId);
  if (!metric) throw new Error(`missing metric ${metricId}`);
  return buildAnswer({
    plan,
    metric,
    rows,
    freshness: defaultFreshness,
    fallbackUsed: false,
  });
}

describe("answer construction", () => {
  it("suppresses growth below 30 works and omits a chart", () => {
    const answer = build("M01", "Which topics grew fastest in 2024 vs 2025?", [
      { CATEGORY_KEY: "rag", CATEGORY_LABEL: "Retrieval-Augmented Generation", PUBLICATION_YEAR: 2024, WORKS: 29 },
      { CATEGORY_KEY: "rag", CATEGORY_LABEL: "Retrieval-Augmented Generation", PUBLICATION_YEAR: 2025, WORKS: 100 },
    ]);
    expect(answer.answer).toMatch(/fewer than 30 works/i);
    expect(answer.chart).toBeUndefined();
    expect(answer.facts.caveats.join(" ")).toMatch(/suppression rule/i);
  });

  it("omits a chart for a single-value answer", () => {
    const answer = build("M03", "How many RAG works were published in 2025?", [
      { CATEGORY_KEY: "rag", CATEGORY_LABEL: "Retrieval-Augmented Generation", PUBLICATION_YEAR: 2025, WORKS: 42 },
    ]);
    expect(answer.status).toBe("answered");
    expect(answer.chart).toBeUndefined();
    expect(answer.answer).toContain("42");
  });

  it("suppresses non-reportable intersections", () => {
    const answer = build("M06", "Do AI/ML and physics intersect?", [
      {
        CATEGORY_KEY_A: "ai-ml",
        CATEGORY_LABEL_A: "Artificial Intelligence and Machine Learning",
        CATEGORY_KEY_B: "physics",
        CATEGORY_LABEL_B: "Physics",
        JOINT_WORKS: 2,
        PARENT_WORKS_A: 50,
        PARENT_WORKS_B: 200,
        IS_REPORTABLE: false,
      },
    ]);
    expect(answer.answer).toMatch(/below the disclosure thresholds/i);
    expect(answer.chart).toBeUndefined();
  });

  it("includes denominator, scope and as-of context", () => {
    const answer = build("M03", "How many RAG works were published in 2025?", [
      { CATEGORY_KEY: "rag", CATEGORY_LABEL: "Retrieval-Augmented Generation", PUBLICATION_YEAR: 2025, WORKS: 42 },
    ]);
    expect(answer.facts.denominators.length).toBeGreaterThan(0);
    expect(answer.facts.source_scope).toContain("VW_PUBLIC_TOPIC_YEAR");
    expect(answer.citations.length).toBeGreaterThan(0);
  });
});
