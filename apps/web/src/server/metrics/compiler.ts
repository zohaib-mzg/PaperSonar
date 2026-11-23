import { metricById } from "@/server/metrics/catalogue";
import type { Filters } from "@/server/metrics/guards";
import { compileTemplate } from "@/server/metrics/sql";

export function compileMetric(metricId: string, filters: Filters) {
  if (!metricById.has(metricId)) throw new Error(`Unknown metric: ${metricId}`);
  return compileTemplate(metricId, filters);
}
