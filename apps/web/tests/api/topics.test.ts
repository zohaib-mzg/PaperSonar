import { describe, expect, it } from "vitest";
import { GET } from "@/app/api/topics/route";

describe("public topics endpoint", () => {
  it("returns only public taxonomy and metric metadata", async () => {
    const response = await GET();
    const body = (await response.json()) as {
      status: string;
      taxonomy_version: string;
      metrics_version: number;
      topics: Array<{ key: string; label: string }>;
      metrics: Array<{ id: string; denominator: string }>;
    };

    expect(response.status).toBe(200);
    expect(body.status).toBe("ok");
    expect(body.taxonomy_version).toBeTruthy();
    expect(body.topics.length).toBeGreaterThan(0);
    expect(body.metrics).toHaveLength(24);
    expect(body.metrics.every((metric) => metric.denominator.length > 0)).toBe(true);
    expect(JSON.stringify(body)).not.toMatch(/SNOWFLAKE|GROQ|GEMINI|PRIVATE_KEY|UPSTASH/);
  });
});
