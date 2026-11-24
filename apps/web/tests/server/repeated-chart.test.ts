import { beforeEach, describe, expect, it, vi } from "vitest";

const { queryMock } = vi.hoisted(() => ({ queryMock: vi.fn() }));

vi.mock("@/server/snowflake/client", () => ({
  querySnowflake: queryMock,
  SnowflakeError: class SnowflakeError extends Error { code = "SNOWFLAKE_ERROR"; },
}));

import { answerChat } from "@/server/chat/service";

function summary() {
  return [{ LATEST_SNAPSHOT_DATE: "2026-11-01", LATEST_PUBLISHED_AT: "2026-11-20T00:00:00Z", TOTAL_OUTPUTS: 12000, RETRIEVED_ON: "2026-11-23" }];
}

describe("repeated chart bug", () => {
  beforeEach(() => {
    queryMock.mockReset();
    queryMock.mockImplementation(async (sql: string) => {
      if (sql.includes("VW_PUBLIC_CORPUS_SUMMARY")) return { rows: summary(), queryId: "q1", rowCount: 1, elapsedMs: 1 };
      if (sql.includes("VW_PUBLIC_TOPIC_CITATIONS")) return {
        rows: [2021,2022,2023,2024,2025].map((y) => ({ PUBLICATION_YEAR: y, OBSERVED_WORKS: 100, AVG_CITED_BY: y * 10, TOTAL_CITATIONS: 1000, COHORT_SIZE: 100, SNAPSHOT_DATE: "2026-11-01" })),
        queryId: "q2", rowCount: 5, elapsedMs: 1,
      };
      if (sql.includes("VW_PUBLIC_TOPIC_YEAR")) return {
        rows: [2021,2022,2023,2024,2025].map((y) => ({ CATEGORY_KEY: "rag", CATEGORY_LABEL: "RAG", PUBLICATION_YEAR: y, WORKS: y * 5 })),
        queryId: "q3", rowCount: 5, elapsedMs: 1,
      };
      return { rows: [], queryId: "q0", rowCount: 0, elapsedMs: 1 };
    });
  });

  it("returns different chart data for different questions", async () => {
    const a = await answerChat({ message: "Average citations per year for RAG", session_id: "11111111-1111-4111-8111-111111111111" }, "203.0.113.50", "r1");
    const b = await answerChat({ message: "Give timeline of trending topics in RAG from 2020 to 2025", session_id: "11111111-1111-4111-8111-111111111111" }, "203.0.113.50", "r2");
    expect(a.body.status).toBe("answered");
    expect(b.body.status).toBe("answered");
    expect(a.body.metric_id).not.toBe(b.body.metric_id);
    const aData = JSON.stringify(a.body.chart?.series ?? a.body.facts.rows);
    const bData = JSON.stringify(b.body.chart?.series ?? b.body.facts.rows);
    expect(aData).not.toBe(bData);
  });
});