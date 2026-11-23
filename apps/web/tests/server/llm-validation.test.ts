import { describe, expect, it } from "vitest";
import { validateComposition, validatePlan } from "@/server/llm/validate";

describe("LLM output validation", () => {
  it("accepts a plan with an approved metric and rejects unknown metrics", () => {
    expect(
      validatePlan({
        intent: "metric",
        metric_ids: ["M01"],
        filters: { year_from: 2025, year_to: 2025 },
        interpretation: "Growth in 2025",
        confidence: 0.9,
      }),
    ).not.toBeNull();
    expect(
      validatePlan({
        intent: "metric",
        metric_ids: ["M99"],
        filters: {},
        interpretation: "Nope",
        confidence: 0.9,
      }),
    ).toBeNull();
  });

  it("rejects numbers not present in the deterministic facts", () => {
    const facts = { values: { works: 42, observed: 100 } };
    expect(validateComposition("There were 42 works out of 100.", facts)).toBe(true);
    expect(validateComposition("There were 999 works.", facts)).toBe(false);
    expect(validateComposition("That is 42% of the corpus.", facts)).toBe(true);
  });
});
