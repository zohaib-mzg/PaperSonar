import type { Filters } from "@/server/metrics/guards";
import { openAccess } from "@/server/metrics/sql/access";
import { citationGains, outputCitationRank, topicCitations } from "@/server/metrics/sql/citations";
import {
  authorActivity,
  institutionActivity,
  institutionConcentration,
  venueActivity,
} from "@/server/metrics/sql/community";
import {
  crossSourceOverlap,
  metadataCompleteness,
  outputTypeMix,
  sourceContribution,
  sourceCoverage,
} from "@/server/metrics/sql/coverage";
import {
  topicGrowth,
  topicShare,
  topicVolume,
  yearDistribution,
} from "@/server/metrics/sql/growth";
import { topicIntersections } from "@/server/metrics/sql/intersections";
import {
  comparison,
  corpusSummary,
  dataStatus,
  freshness,
  outputSearch,
  topicLookup,
} from "@/server/metrics/sql/meta";
import type { CompiledQuery } from "@/server/metrics/sql/shared";

type Template = (filters: Filters) => CompiledQuery;

const registry: Record<string, Template> = {
  M01: topicGrowth,
  M02: topicShare,
  M03: topicVolume,
  M04: topicCitations,
  M05: citationGains,
  M06: topicIntersections,
  M07: sourceCoverage,
  M08: metadataCompleteness,
  M09: institutionActivity,
  M10: institutionConcentration,
  M11: authorActivity,
  M12: venueActivity,
  M13: outputTypeMix,
  M14: openAccess,
  M15: yearDistribution,
  M16: crossSourceOverlap,
  M17: outputSearch,
  M18: dataStatus,
  M19: corpusSummary,
  M20: topicLookup,
  M21: comparison,
  M22: freshness,
  M23: outputCitationRank,
  M24: sourceContribution,
};

export const TEMPLATE_IDS = Object.keys(registry);

export function compileTemplate(metricId: string, filters: Filters): CompiledQuery {
  const template = registry[metricId];
  if (!template) throw new Error(`Unknown metric: ${metricId}`);
  const compiled = template(filters);
  const first = compiled.sql.trimStart().slice(0, 12).toUpperCase();
  if (!first.startsWith("SELECT") && !first.startsWith("WITH")) {
    throw new Error(`Template for ${metricId} is not read-only`);
  }
  return compiled;
}
