import { describe, expect, it } from "vitest";
import { buildAnswer, defaultFreshness } from "@/server/chat/answer";
import { metricById } from "@/server/metrics/catalogue";
import { resolveQuestion } from "@/server/metrics/resolver";

function numbers(text: string): string[] {
  const cleaned = text.replace(/,/g, "").replace(/\b(19|20)\d{2}-\d{2}-\d{2}\b/g, " ");
  return cleaned.match(/-?\d+(?:\.\d+)?/g) ?? [];
}

describe("answer grounding", () => {
  it("does not include numbers absent from query result/facts", () => {
    const plan = resolveQuestion("How many RAG papers were published in 2025?");
    const metric = metricById.get("M03")!;
    const rows = [{ CATEGORY_KEY: "rag", CATEGORY_LABEL: "RAG", PUBLICATION_YEAR: 2025, WORKS: 42 }];
    const a = buildAnswer({ plan, metric, rows, freshness: { ...defaultFreshness, latest_published_at: "2025-12-31" }, fallbackUsed: false });
    const allowed = new Set<string>(["0","1","2","5","30","100","2024","2025","2026"]);
    const collect = (v: unknown): void => { if (typeof v === "number") { allowed.add(String(v)); allowed.add(String(Math.round(v*10)/10)); } if (Array.isArray(v)) v.forEach(collect); else if (v && typeof v === "object") Object.values(v as Record<string, unknown>).forEach(collect); };
    collect(a.facts);
    for (const n of numbers(a.answer)) {
      if (/^(19|20)\d{2}$/.test(n)) continue;
      expect([...allowed].some((x) => Number(x) === Number(n)) || allowed.has(n), `unexpected number ${n} in: ${a.answer}`).toBe(true);
    }
  });
});