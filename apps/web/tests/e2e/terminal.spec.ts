import { expect, test } from "@playwright/test";

const mockAnswer = {
  request_id: "req_e2e",
  status: "answered",
  answer: "Between 2024 and 2025 the largest reportable change was RAG.",
  mode: "deterministic",
  intent: "metric",
  interpretation: "M01 · RAG · 2024–2025",
  metric_id: "M01",
  metric_label: "Topic growth",
  facts: {
    values: { change_1: 15 },
    rows: [{ category: "RAG", start: 30, end: 45, change: 15 }],
    denominators: ["distinct published outputs"],
    caveats: ["Growth describes the retained published corpus."],
    source_scope: "PUBLISHED PROJECT_REPORTING · VW_PUBLIC_TOPIC_YEAR",
    as_of: "2026-11-20T00:00:00Z",
    snapshot_date: "2026-11-01",
    coverage_note: null,
  },
  chart: {
    kind: "bar",
    title: "Works change 2024–2025",
    labels: ["RAG"],
    series: [{ label: "Change in works", values: [15] }],
    unit: "works",
    fallback: { headers: ["Category", "Change in works"], rows: [["RAG", "15"]] },
  },
  citations: [{ label: "Published reporting view", view: "VW_PUBLIC_TOPIC_YEAR" }],
  fallback_used: false,
  freshness: {
    latest_snapshot_date: "2026-11-01",
    latest_published_at: "2026-11-20T00:00:00Z",
    total_outputs: 12000,
    retrieved_on: "2026-11-23",
  },
};

test("matches the research terminal at desktop width", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.locator(".logo")).toContainText("PaperSonar");
  await expect(page.locator(".sub")).toHaveText("RESEARCH INTELLIGENCE");
  await expect(page.locator(".path")).toContainText("~/papersonar/terminal");
  await expect(page.locator(".stats")).toContainText("MODE");
  await expect(page.locator(".chips button")).toHaveCount(3);
  await expect(page.locator("textarea")).toHaveAttribute("placeholder", "Ask about published research...");
});

test("hides rails at the documented breakpoints", async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 900 });
  await page.goto("/");
  await expect(page.locator(".right")).toBeHidden();

  await page.setViewportSize({ width: 700, height: 900 });
  await expect(page.locator(".left")).toBeHidden();
});

test("renders a grounded answer with an inline chart and table fallback", async ({ page }) => {
  await page.route("**/api/chat", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockAnswer) });
  });
  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        version: "test",
        checks: {
          env: "ok",
          snowflake: "ok",
          redis: "ok",
          groq: "configured",
          gemini: "missing",
          chat_enabled: true,
        },
        latency_ms: 1,
      }),
    });
  });
  const healthResponse = page.waitForResponse("**/api/health");
  await page.goto("/");
  await healthResponse;
  await page.locator(".chips button").first().click();
  await expect(page.locator(".m.bot").last()).toContainText("largest reportable change");
  await expect(page.locator(".evidence")).toBeVisible();
  await expect(page.locator(".chart-block svg")).toBeVisible();
  await expect(page.locator(".chart-details summary")).toHaveText("View data table");
});
