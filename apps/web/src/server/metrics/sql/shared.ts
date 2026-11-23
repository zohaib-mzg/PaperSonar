import type { Binding } from "@/server/snowflake/types";
import type { Filters } from "@/server/metrics/guards";

export type CompiledQuery = {
  sql: string;
  bindings: Binding[];
  templateId: string;
};

export const text = (value: string): Binding => ({ type: "TEXT", value });
export const fixed = (value: number): Binding => ({ type: "FIXED", value });
export const dateBinding = (value: string): Binding => ({ type: "DATE", value });

export function numberFilter(filters: Filters, key: string, fallback: number): number {
  const value = filters[key];
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function stringFilter(filters: Filters, key: string): string | null {
  const value = filters[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function limitOf(filters: Filters, fallback = 10): number {
  return Math.min(50, Math.max(1, numberFilter(filters, "limit", fallback)));
}

export function escapeLikeTerm(term: string): string {
  return `%${term.replace(/[\\%_]/g, "\\$&")}%`;
}
