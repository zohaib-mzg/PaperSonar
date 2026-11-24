import { describe, expect, it } from "vitest";
import { resolveQuestion } from "@/server/metrics/resolver";

const CASES: Array<{ q: string; intent: string; metric?: string; category?: string }> = [
  { q: "Give timeline of trending topics in RAG from 2020 to 2025", intent: "metric", metric: "M01", category: "rag" },
  { q: "How many RAG papers were published in 2025?", intent: "metric", metric: "M03", category: "rag" },
  { q: "Top 10 most cited RAG papers", intent: "metric", metric: "M23", category: "rag" },
  { q: "Which institutions publish the most on RAG?", intent: "metric", metric: "M09", category: "rag" },
  { q: "Compare RAG and fine-tuning publications since 2021", intent: "compare", metric: "M03" },
  { q: "Average citations per year for RAG", intent: "metric", metric: "M04", category: "rag" },
  { q: "What share of RAG papers are open access?", intent: "metric", metric: "M14", category: "rag" },
  { q: "Which venues publish the most RAG research?", intent: "metric", metric: "M12", category: "rag" },
  { q: "Who are the top authors in retrieval augmented generation?", intent: "metric", metric: "M11", category: "rag" },
  { q: "What's new in RAG this year?", intent: "metric", metric: "M03", category: "rag" },
  { q: "how many papers on rag in 2023 vs 2024", intent: "compare", metric: "M03" },
  { q: "how many pubications on LLM in 2024?", intent: "metric", metric: "M03", category: "llm" },
  { q: "trend of AI/ML papers since 2021", intent: "metric", metric: "M15", category: "ai-ml" },
  { q: "top 5 venues for machine learning", intent: "metric", metric: "M12", category: "ai-ml" },
  { q: "which countries publish most on NLP", intent: "metric", metric: "M09" },
  { q: "open access share for computer vision last 3 years", intent: "metric", metric: "M14" },
  { q: "rag vs llm citation impact", intent: "compare", metric: "M04" },
  { q: "most cited papers in software engineering 2024", intent: "metric", metric: "M23" },
  { q: "how fresh is the data?", intent: "metric", metric: "M22" },
  { q: "latest papers on retrieval augmented generation", intent: "search", metric: "M17" },
  { q: "find papers titled attention is all you need", intent: "search", metric: "M17" },
  { q: "which source has more rag outputs openalex or crossref", intent: "compare" },
  { q: "total citations for rag in 2024", intent: "metric", metric: "M04", category: "rag" },
  { q: "show me rag output types", intent: "metric", metric: "M13", category: "rag" },
  { q: "what percentage of ai papers are open access", intent: "metric", metric: "M14", category: "ai-ml" },
  { q: "top authors in llms", intent: "metric", metric: "M11", category: "llm" },
  { q: "compare 2023 and 2024 rag publications", intent: "compare", metric: "M03" },
  { q: "institution concentration in clinical medicine", intent: "metric", metric: "M10" },
  { q: "where are rag papers published most", intent: "metric", metric: "M12", category: "rag" },
  { q: "how many ai agent papers in last 5 years", intent: "metric", metric: "M03" },
  { q: "citation trend for llm over time", intent: "metric", metric: "M04", category: "llm" },
  { q: "show publication timeline for cybersecurity 2019-2024", intent: "metric", metric: "M15" },
  { q: "rag papers by country", intent: "metric", metric: "M09", category: "rag" },
  { q: "what are the top 10 rag papers by citations", intent: "metric", metric: "M23", category: "rag" },
  { q: "open access vs closed in rag", intent: "metric", metric: "M14", category: "rag" },
  { q: "crossref vs arxiv for ai-ml", intent: "compare" },
  { q: "whats the corpus size", intent: "metric", metric: "M19" },
  { q: "which topics are growing fastest", intent: "metric", metric: "M01" },
  { q: "emerging topics in 2025", intent: "metric", metric: "M01" },
  { q: "data status", intent: "metric", metric: "M18" },
  { q: "find papers about diffusion models", intent: "search", metric: "M17" },
  { q: "How many outputs were published in 2024?", intent: "metric", metric: "M03" },
];

describe("resolver intent mapping", () => {
  it("maps 40+ varied phrasings to supported intents", () => {
    expect(CASES.length).toBeGreaterThanOrEqual(40);
    for (const c of CASES) {
      const plan = resolveQuestion(c.q);
      expect(plan.intent, c.q).toBe(c.intent);
      if (c.metric) expect(plan.metric_ids[0], c.q).toBe(c.metric);
      if (c.category) expect(plan.filters.category_key, c.q).toBe(c.category);
    }
  });

  it("handles follow-up by country", () => {
    const first = resolveQuestion("Which institutions publish the most on RAG?");
    const follow = resolveQuestion("now show it by country", [{
      metric_id: first.metric_ids[0],
      filters: first.filters,
      interpretation: first.interpretation,
    }]);
    expect(follow.intent).toBe("metric");
    expect(follow.metric_ids[0]).toBe("M09");
    expect(follow.filters.category_key).toBe("rag");
  });
});