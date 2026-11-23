import { beforeEach, describe, expect, it, vi } from "vitest";

const { queryMock } = vi.hoisted(() => ({ queryMock: vi.fn() }));

vi.mock("@/server/snowflake/client", () => ({
  querySnowflake: queryMock,
  SnowflakeError: class SnowflakeError extends Error {
    code = "SNOWFLAKE_ERROR";
    constructor(code = "SNOWFLAKE_ERROR", message = "error") {
      super(message);
      this.code = code;
    }
  },
}));

import { answerChat } from "@/server/chat/service";
import type { SnowflakeRow } from "@/server/snowflake/types";

const summaryRows: SnowflakeRow[] = [
  {
    LATEST_SNAPSHOT_DATE: "2026-11-01",
    LATEST_PUBLISHED_AT: "2026-11-20T00:00:00Z",
    TOTAL_OUTPUTS: 12000,
    RETRIEVED_ON: "2026-11-23",
  },
];

const citationRows: SnowflakeRow[] = [
  {
    CATEGORY_KEY: "rag",
    CATEGORY_LABEL: "Retrieval-Augmented Generation",
    PUBLICATION_YEAR: 2025,
    SNAPSHOT_DATE: "2026-11-01",
    COHORT_SIZE: 120,
    OBSERVED_WORKS: 110,
    TOTAL_CITATIONS: 440,
    AVG_CITED_BY: 4,
    MEDIAN_CITED_BY: 2,
  },
];

function routeQuery(sql: string): SnowflakeRow[] {
  if (sql.includes("VW_PUBLIC_CORPUS_SUMMARY")) return summaryRows;
  if (sql.includes("VW_PUBLIC_TOPIC_CITATIONS")) return citationRows;
  return [];
}

describe("chat orchestration", () => {
  beforeEach(() => {
    queryMock.mockReset();
    queryMock.mockImplementation(async (sql: string) => ({
      rows: routeQuery(sql),
      queryId: "query-test",
      rowCount: routeQuery(sql).length,
      elapsedMs: 1,
    }));
  });

  it("answers with grounded facts and scope", async () => {
    const result = await answerChat(
      { message: "How many citations does RAG have?", session_id: "11111111-1111-4111-8111-111111111111" },
      "203.0.113.10",
      "req-test-1",
    );
    expect(result.status).toBe(200);
    expect(result.body.status).toBe("answered");
    expect(result.body.metric_id).toBe("M04");
    expect(result.body.answer).toContain("published reporting data");
    expect(result.body.facts.source_scope).toContain("VW_PUBLIC_TOPIC_CITATIONS");
    expect(result.body.closest_match_disclosure).toContain("Retrieval-Augmented Generation");
    expect(result.body.freshness.latest_snapshot_date).toBe("2026-11-01");
  });

  it("clarifies unsupported questions without querying a metric", async () => {
    queryMock.mockImplementation(async (sql: string) => ({
      rows: sql.includes("VW_PUBLIC_CORPUS_SUMMARY") ? summaryRows : [],
      queryId: null,
      rowCount: sql.includes("VW_PUBLIC_CORPUS_SUMMARY") ? 1 : 0,
      elapsedMs: 1,
    }));
    const result = await answerChat(
      { message: "Tell me a joke", session_id: "22222222-2222-4222-8222-222222222222" },
      "203.0.113.11",
      "req-test-2",
    );
    expect(result.status).toBe(200);
    expect(result.body.status).toBe("clarify");
    expect(result.body.metric_id).toBeNull();
  });

  it("degrades gracefully when Snowflake fails", async () => {
    queryMock.mockImplementation(async (sql: string) => {
      if (sql.includes("VW_PUBLIC_CORPUS_SUMMARY")) {
        return { rows: summaryRows, queryId: null, rowCount: 1, elapsedMs: 1 };
      }
      throw new Error("snowflake down");
    });
    const result = await answerChat(
      { message: "How many RAG works were published in 2025?", session_id: "33333333-3333-4333-8333-333333333333" },
      "203.0.113.12",
      "req-test-3",
    );
    expect(result.status).toBe(200);
    expect(result.body.status).toBe("DATA_UNAVAILABLE");
    expect(result.body.answer).toContain("temporarily unavailable");
  });

  it("enforces hourly rate limits", async () => {
    for (let index = 0; index < 20; index += 1) {
      await answerChat(
        {
          message: `Count RAG works ${index}`,
          session_id: "44444444-4444-4444-8444-444444444444",
        },
        "198.51.100.77",
        `req-limit-${index}`,
      );
    }
    const blocked = await answerChat(
      { message: "Count RAG works again", session_id: "44444444-4444-4444-8444-444444444444" },
      "198.51.100.77",
      "req-limit-21",
    );
    expect(blocked.status).toBe(429);
    expect(blocked.body.status).toBe("RATE_LIMITED");
  }, 30_000);
});
