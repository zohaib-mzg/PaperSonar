import { plannerOutputSchema, type PlannerOutput } from "@/server/llm/types";
import { metrics } from "@/server/metrics/catalogue";

export function validatePlan(value: unknown): PlannerOutput | null {
  const parsed = plannerOutputSchema.safeParse(value);
  if (!parsed.success) return null;
  const plan = parsed.data;
  const allowed = new Set(metrics.map((metric) => metric.id));
  if (!plan.metric_ids.every((id) => allowed.has(id))) return null;
  if (plan.intent === "metric" && plan.metric_ids.length !== 1) return null;
  if (plan.intent === "search" && (!plan.filters.search_term || plan.filters.search_term.length < 2)) {
    return null;
  }
  if (plan.intent === "clarify" && !plan.clarification) return null;
  if (plan.intent === "refuse" && !plan.refusal_reason) return null;
  return plan;
}

function numericTokens(text: string): string[] {
  return text
    .replace(/,/g, "")
    .match(/-?\d+(?:\.\d+)?/g) ?? [];
}

function formatNumber(value: number): string[] {
  const plain = Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  return [plain, value.toLocaleString("en-US"), value.toFixed(1), value.toFixed(2)];
}

function collectNumbers(value: unknown, output: number[] = []): number[] {
  if (typeof value === "number" && Number.isFinite(value)) {
    output.push(value);
  } else if (Array.isArray(value)) {
    for (const item of value) collectNumbers(item, output);
  } else if (value && typeof value === "object") {
    for (const item of Object.values(value)) collectNumbers(item, output);
  }
  return output;
}

export function validateComposition(prose: string, facts: Record<string, unknown>): boolean {
  const numbers = collectNumbers(facts);
  const allowed = new Set<string>(["0", "1", "2", "5", "30", "100"]);
  for (const number of numbers) {
    for (const variant of formatNumber(number)) allowed.add(variant);
  }
  const currentYear = new Date().getUTCFullYear();
  for (let year = currentYear - 10; year <= currentYear; year += 1) allowed.add(String(year));
  for (const key of ["as_of", "snapshot_date"]) {
    const value = facts[key];
    if (typeof value !== "string") continue;
    for (const token of value.match(/\d+/g) ?? []) {
      allowed.add(token);
      allowed.add(`-${token}`);
    }
  }
  for (const a of numbers) {
    for (const b of numbers) {
      if (b === 0) continue;
      const percent = Math.round((a / b) * 1000) / 10;
      allowed.add(String(percent));
      allowed.add(`${percent}%`);
    }
  }
  for (const token of numericTokens(prose)) {
    if (!allowed.has(token)) return false;
  }
  return true;
}
