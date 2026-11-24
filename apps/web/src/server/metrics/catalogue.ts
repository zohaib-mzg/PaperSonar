import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { parse } from "yaml";

export type PublicMetric = {
  id: string;
  label: string;
  description: string;
  template: string;
  primary_view: string;
  dimensions: string[];
  denominator: string;
  caveats: string[];
};

export type TaxonomyCategory = {
  key: string;
  label: string;
  parent_key: string | null;
};

export type TaxonomyRule = {
  category: string;
  pattern: string;
  field: string;
  weight: number;
};

function resolveConfigFile(name: string): string {
  const candidates = [
    path.join(process.cwd(), "config", name),
    path.join(process.cwd(), "..", "config", name),
    path.join(process.cwd(), "..", "..", "config", name),
  ];
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) throw new Error(`Missing config file: ${name}`);
  return found;
}

function readYaml<T>(name: string): T {
  return parse(readFileSync(resolveConfigFile(name), "utf8")) as T;
}

const metricFile = readYaml<{ version: number; metrics: PublicMetric[] }>("public_metrics.yml");
const taxonomyFile = readYaml<{
  taxonomy_version: string;
  categories: Array<{ key: string; label: string; parent: string | null }>;
  rules?: TaxonomyRule[];
}>("taxonomy.yml");

export const METRIC_VERSION = metricFile.version;
export const metrics: PublicMetric[] = metricFile.metrics;
export const metricById = new Map(metrics.map((metric) => [metric.id, metric]));

export const TAXONOMY_VERSION = taxonomyFile.taxonomy_version;
export const categories: TaxonomyCategory[] = taxonomyFile.categories.map((category) => ({
  key: category.key,
  label: category.label,
  parent_key: category.parent,
}));
export const categoryByKey = new Map(categories.map((category) => [category.key, category]));
export const taxonomyRules: TaxonomyRule[] = taxonomyFile.rules ?? [];

export function publicMetricList() {
  return metrics.map((metric) => ({
    id: metric.id,
    label: metric.label,
    description: metric.description,
    dimensions: metric.dimensions,
    denominator: metric.denominator,
    caveats: metric.caveats,
  }));
}

export function publicCategoryList() {
  return categories.map((category) => ({
    key: category.key,
    label: category.label,
    parent_key: category.parent_key,
  }));
}

const aliasMap = new Map<string, string[]>();
for (const category of categories) {
  aliasMap.set(category.key, [category.key, category.label.toLowerCase()]);
}
for (const rule of taxonomyRules) {
  if (!aliasMap.has(rule.category)) continue;
  const aliases = aliasMap.get(rule.category) ?? [];
  if (!aliases.includes(rule.pattern.toLowerCase())) aliases.push(rule.pattern.toLowerCase());
  aliasMap.set(rule.category, aliases);
}

const manualAliases: Record<string, string[]> = {
  "ai-ml": ["ai/ml", "artificial intelligence", "machine learning", "ai"],
  llm: ["large language model", "large language models", "llms"],
  rag: ["retrieval augmented generation", "retrieval-augmented generation", "rag"],
  "ai-agents": ["ai agent", "ai agents", "agentic ai"],
  "software-engineering": ["software engineering"],
  "health-sciences": ["health sciences", "healthcare", "medicine"],
  "clinical-medicine": ["clinical medicine", "medical"],
};
for (const [key, aliases] of Object.entries(manualAliases)) {
  if (!aliasMap.has(key)) continue;
  const existing = aliasMap.get(key) ?? [];
  for (const alias of aliases) if (!existing.includes(alias)) existing.push(alias);
  aliasMap.set(key, existing);
}

export function collectCategoryAliases(key: string): string[] {
  return aliasMap.get(key) ?? [];
}

export function allCategoryAliases(): Array<{ key: string; aliases: string[] }> {
  return categories.map((category) => ({
    key: category.key,
    aliases: collectCategoryAliases(category.key),
  }));
}
