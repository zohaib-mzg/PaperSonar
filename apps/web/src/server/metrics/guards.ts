import { categoryByKey, categories } from "@/server/metrics/catalogue";

export type FilterValue = string | number | boolean | null | undefined;
export type Filters = Record<string, FilterValue>;

const ALLOWED_KEYS = new Set([
  "category_key",
  "category_key_b",
  "parent_category_key",
  "year_from",
  "year_to",
  "source_name",
  "output_type",
  "venue_name",
  "institution_key",
  "country_code",
  "author_key",
  "orcid",
  "access_status",
  "snapshot_date",
  "search_term",
  "limit",
  "order",
  "min_works",
]);

const SOURCES = new Set(["OPENALEX", "CROSSREF", "ARXIV", "DATACITE", "ZENODO"]);
const SQL_MARKERS = /[;]|--|\/\*|\b(DROP|DELETE|UPDATE|INSERT|CREATE|ALTER|EXEC|UNION)\b/i;

function cleanString(value: unknown, maxLength = 200): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text || text.length > maxLength || SQL_MARKERS.test(text)) return null;
  return text;
}

export function validateFilters(input: Filters): { filters: Filters; rejected: string[] } {
  const filters: Filters = {};
  const rejected: string[] = [];

  for (const [key, raw] of Object.entries(input)) {
    if (!ALLOWED_KEYS.has(key) || raw === undefined || raw === null) {
      if (raw !== undefined && raw !== null) rejected.push(key);
      continue;
    }

    if (key === "category_key" || key === "category_key_b" || key === "parent_category_key") {
      const value = cleanString(raw, 100);
      if (value && categoryByKey.has(value)) filters[key] = value;
      else rejected.push(key);
      continue;
    }

    if (key === "year_from" || key === "year_to" || key === "limit" || key === "min_works") {
      const number = typeof raw === "number" ? raw : Number(raw);
      if (!Number.isInteger(number)) {
        rejected.push(key);
        continue;
      }
      if (key === "limit" && (number < 1 || number > 50)) {
        rejected.push(key);
        continue;
      }
      if ((key === "year_from" || key === "year_to") && (number < 1900 || number > 2100)) {
        rejected.push(key);
        continue;
      }
      if (key === "min_works" && (number < 1 || number > 1000)) {
        rejected.push(key);
        continue;
      }
      filters[key] = number;
      continue;
    }

    if (key === "source_name") {
      const value = cleanString(raw, 40)?.toUpperCase() ?? null;
      if (value && SOURCES.has(value)) filters.source_name = value;
      else rejected.push(key);
      continue;
    }

    if (key === "snapshot_date") {
      const value = cleanString(raw, 20) ?? null;
      if (value && /^\d{4}-\d{2}-\d{2}$/.test(value)) filters.snapshot_date = value;
      else rejected.push(key);
      continue;
    }

    if (key === "order") {
      const value = cleanString(raw, 20)?.toLowerCase() ?? null;
      if (value === "asc" || value === "desc" || value === "a_vs_b") filters.order = value;
      else rejected.push(key);
      continue;
    }

    if (key === "search_term") {
      const value = cleanString(raw, 100) ?? null;
      if (value && value.length >= 2 && !/^[%_\\]+$/.test(value)) filters.search_term = value;
      else rejected.push(key);
      continue;
    }

    if (key === "country_code") {
      const value = cleanString(raw, 8)?.toUpperCase() ?? null;
      if (value && /^[A-Z]{2,3}$/.test(value)) filters.country_code = value;
      else rejected.push(key);
      continue;
    }

    const value = cleanString(raw, key === "venue_name" ? 200 : 100);
    if (value) filters[key] = value;
    else rejected.push(key);
  }

  return { filters, rejected };
}

export const MIN_GROWTH_WORKS = 30;
export const MIN_INTERSECTION_PARENT_WORKS = 100;
export const MIN_INTERSECTION_JOINT_WORKS = 5;

export function growthSuppressed(
  startWorks: number | null | undefined,
  endWorks: number | null | undefined,
  minWorks = MIN_GROWTH_WORKS,
): boolean {
  return (
    typeof startWorks !== "number" ||
    typeof endWorks !== "number" ||
    startWorks < minWorks ||
    endWorks < minWorks
  );
}

export function growthSuppressionNote(
  startWorks: number | null | undefined,
  endWorks: number | null | undefined,
  minWorks = MIN_GROWTH_WORKS,
): string | null {
  return growthSuppressed(startWorks, endWorks, minWorks)
    ? `One side has fewer than ${minWorks} works.`
    : null;
}

export function intersectionReportable(
  parentA: number | null | undefined,
  parentB: number | null | undefined,
  joint: number | null | undefined,
  isReportable?: boolean | null,
): boolean {
  if (typeof parentA !== "number" || typeof parentB !== "number" || typeof joint !== "number") {
    return false;
  }
  const thresholdPass =
    parentA >= MIN_INTERSECTION_PARENT_WORKS &&
    parentB >= MIN_INTERSECTION_PARENT_WORKS &&
    joint >= MIN_INTERSECTION_JOINT_WORKS;
  return isReportable === undefined || isReportable === null
    ? thresholdPass
    : Boolean(isReportable) && thresholdPass;
}

export function intersectionReportabilityNote(
  parentA: number | null | undefined,
  parentB: number | null | undefined,
  joint: number | null | undefined,
  isReportable?: boolean | null,
): string | null {
  return intersectionReportable(parentA, parentB, joint, isReportable)
    ? null
    : "Parent or joint-work thresholds are not met.";
}

export function isRankableCategory(categoryKey: string | null | undefined): boolean {
  return Boolean(categoryKey && categoryKey !== "unclassified" && categoryByKey.has(categoryKey));
}

export function latestCompleteYear(now = new Date()): number {
  return now.getUTCFullYear() - 1;
}

export function allCategoryKeys(): string[] {
  return categories.map((category) => category.key);
}
