import type { PlannerOutput } from "@/server/llm/types";
import { categories, categoryByKey } from "@/server/metrics/catalogue";
import { allCategoryAliases } from "@/server/metrics/catalogue";
import { latestCompleteYear, type Filters } from "@/server/metrics/guards";

export type CompareSide = { label: string; filters: Filters };

export type ResolvedPlan = {
  intent: "metric" | "compare" | "search" | "clarify" | "refuse";
  metric_ids: string[];
  filters: Filters;
  comparison?: {
    metric_id: string;
    dimension: "category" | "source" | "year" | "institution" | "venue" | "type";
    sides: [CompareSide, CompareSide];
  };
  interpretation: string;
  confidence: number;
  clarification?: string;
  refusal_reason?: string;
  closest_match_disclosure?: string;
  follow_up?: boolean;
  plan_source: "deterministic" | "llm";
  provider?: "groq" | "gemini";
};

export type RecentTurn = {
  metric_id: string;
  filters: Filters;
  interpretation: string;
};

type Match = { key: string; start: number; end: number; matched: string; alias: string };

const SOURCE_NAMES = ["OPENALEX", "CROSSREF", "ARXIV", "DATACITE", "ZENODO"];

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function bounded(alias: string): RegExp {
  const body = escapeRegex(alias);
  return new RegExp(`(?<![a-z0-9\\-])${body}(?![a-z0-9\\-])`, "i");
}

function boundedGlobal(alias: string): RegExp {
  const body = escapeRegex(alias);
  return new RegExp(`(?<![a-z0-9\\-])${body}(?![a-z0-9\\-])`, "gi");
}

const aliasEntries = allCategoryAliases()
  .flatMap(({ key, aliases }) =>
    aliases
      .filter((alias) => alias && alias !== "unclassified")
      .map((alias) => ({ key, alias: alias.toLowerCase() })),
  )
  .sort((a, b) => b.alias.length - a.alias.length);

const keyEntries = categories
  .filter((category) => category.key !== "unclassified")
  .map((category) => ({ key: category.key, alias: category.key }))
  .sort((a, b) => b.alias.length - a.alias.length);

export function matchCategories(text: string): Match[] {
  const hits = new Map<string, Match>();
  for (const entry of [...keyEntries, ...aliasEntries]) {
    const regex = boundedGlobal(entry.alias);
    for (const found of text.matchAll(regex)) {
      const start = found.index ?? 0;
      const end = start + found[0].length;
      const existing = hits.get(entry.key);
      if (!existing || start < existing.start || (start === existing.start && end > existing.end)) {
        hits.set(entry.key, {
          key: entry.key,
          start,
          end,
          matched: found[0],
          alias: entry.alias,
        });
      }
    }
  }
  return [...hits.values()].sort((a, b) => a.start - b.start);
}

function matchSources(text: string): Array<{ name: string; start: number; matched: string }> {
  const names = new Map<string, { name: string; start: number; matched: string }>();
  for (const source of SOURCE_NAMES) {
    const patterns = source === "ARXIV" ? ["arxiv", "arxiv"] : [source.toLowerCase()];
    for (const pattern of patterns) {
      for (const found of text.matchAll(boundedGlobal(pattern))) {
        const start = found.index ?? 0;
        const existing = names.get(source);
        if (!existing || start < existing.start) {
          names.set(source, { name: source, start, matched: found[0] });
        }
      }
    }
  }
  return [...names.values()].sort((a, b) => a.start - b.start);
}

function matchedYears(text: string): number[] {
  const years = [...text.matchAll(/\b(?:19|20)\d{2}\b/g)].map((match) => Number(match[0]));
  return [...new Set(years)].sort((a, b) => a - b);
}

const METRIC_RULES: Array<[string, RegExp]> = [
  [
    "M17",
    /^(please\s+)?(find|search|look\s+up)\b|\b(find|search|look\s+up)\b.{0,60}\b(papers?|outputs?|works?|titles?|datasets?|research)\b/i,
  ],
  [
    "M18",
    /\b(latest|most recent|fresh|status|failed|published)\b.{0,30}\b(batch|data|ingest|pipeline)\b|\bwhich batch\b|\bsources are currently included\b|\bnot reportable\b|\bmissing from an answer\b/i,
  ],
  ["M22", /\b(how fresh|freshness|latest snapshot|last updated|up to date)\b/i],
  ["M19", /\b(corpus size|total outputs|overall totals|how many outputs (in|across) (the )?corpus)\b/i],
  ["M20", /\b(define|definition|meaning of|what does .{1,40} mean)\b|\bwhat is [a-z0-9/-]{2,40}\?$/i],
  ["M23", /\b(most cited|top cited|highest cited)\b.{0,40}\b(papers?|outputs?|works?|research)\b/i],
  ["M05", /\b(citation gain|gained citations|citation growth|citation change|citations gained|citation trend)\b/i],
  [
    "M16",
    /\b(cross[- ]source|duplicate|overlap between sources|same output in multiple sources|appear in only one source)\b/i,
  ],
  [
    "M04",
    /\b(citations?|cited by|how often cited|average citations|median citations|citation distribution|citation impact|citations per output)\b/i,
  ],
  [
    "M06",
    /\b(overlap|co[- ]?occur|cooccurrence|intersection|topic pairs|bridge the most domains|both .{1,40} and .{1,40})\b/i,
  ],
  ["M10", /\b(concentrated|concentration|top institutions share|share held by institutions)\b/i],
  ["M09", /\b(institution|institutions|university|universities|affiliation|affiliations|country|countries)\b/i],
  ["M11", /\b(author|authors|researcher|researchers|who publishes)\b/i],
  ["M12", /\b(venue|venues|journal|journals|conference|conferences)\b/i],
  ["M14", /\b(open access|oa\b|access status|gold oa|green oa)\b/i],
  ["M08", /\b(missing metadata|completeness|without doi|without a? venue|without access status|missing author)\b/i],
  ["M07", /\b(coverage|coverage ratio|by source|per source|source coverage|underrepresented)\b/i],
  ["M13", /\b(output type|output types|article type|type mix|publication types)\b/i],
  ["M24", /\b(source contribution|which source contributes|contribution by source)\b/i],
  ["M02", /\b(share|percent|percentage|proportion|what fraction|of the corpus)\b/i],
  [
    "M01",
    /\b(grew|growth|declined|decline|increased|decreased|fastest|rising|falling|change in|relative increase|emerging)\b/i,
  ],
  [
    "M15",
    /\b(by year|per year|publication years|publication[- ]year|year distribution|each year|partial[- ]year|year effect|under-?represented years?|years are under-represented|sparse years?)\b/i,
  ],
  [
    "M03",
    /\b(how many|count|number of|volume|published|works?|papers?|outputs?|classified vs unclassified)\b/i,
  ],
];

function detectMetric(text: string): string | null {
  for (const [metricId, pattern] of METRIC_RULES) {
    if (pattern.test(text)) return metricId;
  }
  return null;
}

const CATEGORY_REQUIRED = new Set(["M20", "M23"]);

function labelFor(key: string | undefined): string {
  if (!key) return "the selected corpus";
  return categoryByKey.get(key)?.label ?? key;
}

function disclosureFor(match: Match | undefined): string | undefined {
  if (!match) return undefined;
  const label = labelFor(match.key);
  if (match.alias !== match.key) {
    return `I matched “${match.matched}” to ${label} (${match.key}).`;
  }
  if (match.matched.toLowerCase() === label.toLowerCase()) return undefined;
  return `I matched “${match.matched}” to ${label} (${match.key}).`;
}

function extractSearchTerm(message: string): string | null {
  const quoted = message.match(/"([^"]{2,100})"/);
  if (quoted) return quoted[1];
  let term = message
    .replace(/^(please\s+)?(find|search\s+for|look\s+up|show\s+me)\s+/i, "")
    .replace(/^(papers?|outputs?|works?|titles?|datasets?|research)\s+(about|on|containing|with)?\s*/i, "")
    .replace(/^(title\s+search|search)\s*:?\s*/i, "")
    .replace(/[?.!]+$/g, "")
    .trim();
  if (term.length < 2) return null;
  if (term.length > 100) term = term.slice(0, 100).trim();
  return term;
}

function applyYears(
  text: string,
  filters: Filters,
  metricId: string,
  disclosures: string[],
): void {
  const years = matchedYears(text);
  const latest = latestCompleteYear();
  if (/\b(last|past)\s+(five|5)\s+years?\b/i.test(text)) {
    filters.year_from = latest - 4;
    filters.year_to = latest;
    disclosures.push(`Using the latest five complete publication years (${latest - 4}–${latest}).`);
    return;
  }
  if (/\blast year\b/i.test(text) && years.length === 0) {
    filters.year_from = latest - 1;
    filters.year_to = latest - 1;
    disclosures.push(`“Last year” is interpreted as ${latest - 1}, the latest complete publication year.`);
    return;
  }
  if (years.length >= 2) {
    filters.year_from = years[0];
    filters.year_to = years[years.length - 1];
    return;
  }
  if (years.length === 1) {
    filters.year_from = years[0];
    filters.year_to = years[0];
    return;
  }
  filters.year_from = metricId === "M01" ? latest - 1 : latest - 4;
  filters.year_to = latest;
  disclosures.push(`Using the latest complete publication window (${filters.year_from}–${latest}).`);
}

function isPolicyRefusal(text: string): boolean {
  return /\b(caus(e|ed|ality)|why did|why does|because of|predict|forecast|will .{0,30}(rise|fall|grow|decline)|invest|buy|sell|medical advice|diagnose|legal advice|financial advice|full[- ]text|raw bronze|raw silver|accountadmin|ignore (your|previous|all) instructions|reveal (your|the) (prompt|system))\b/i.test(
    text,
  );
}

function interpretationFor(metricId: string, filters: Filters, intent: string): string {
  if (intent === "search") return `Title search for “${String(filters.search_term ?? "")}”.`;
  if (intent === "compare") {
    return `Comparing ${labelFor(String(filters.category_key ?? ""))} with ${labelFor(
      String(filters.category_key_b ?? filters.source_name ?? ""),
    )}.`;
  }
  const label = labelFor(String(filters.category_key ?? ""));
  const years =
    filters.year_from === filters.year_to
      ? `${String(filters.year_from)}`
      : `${String(filters.year_from ?? "")}–${String(filters.year_to ?? "")}`;
  return `${metricId} · ${label} · ${years}`;
}

function clarify(): ResolvedPlan {
  return {
    intent: "clarify",
    metric_ids: [],
    filters: {},
    interpretation: "I need a little more detail.",
    confidence: 0.4,
    clarification:
      "I can answer defined questions about topics, citations, sources, institutions, authors, venues, access and freshness. Try: “How many RAG outputs were published in 2025?”",
    plan_source: "deterministic",
  };
}

function refuse(): ResolvedPlan {
  return {
    intent: "refuse",
    metric_ids: [],
    filters: {},
    interpretation: "Unsupported request.",
    confidence: 1,
    refusal_reason:
      "I can describe publication and citation patterns, but I cannot attribute causes, predict outcomes, give professional advice, expose raw records or reveal internal instructions. I can instead show defined counts, shares, snapshots or source coverage.",
    plan_source: "deterministic",
  };
}

export function resolveQuestion(message: string, recent: RecentTurn[] = []): ResolvedPlan {
  const clean = message.trim();
  const text = clean.toLowerCase();
  const disclosures: string[] = [];

  if (isPolicyRefusal(text)) return refuse();

  const matches = matchCategories(text);
  const sources = matchSources(text);
  const firstCategory = matches[0];
  const secondCategory = matches[1];

  const followUp = /^(what about|how about|same for|and for|and what about)\b/i.test(text);
  if (followUp && recent.length > 0) {
    const previous = recent[0];
    const filters: Filters = { ...previous.filters };
    if (firstCategory) filters.category_key = firstCategory.key;
    if (secondCategory) filters.category_key_b = secondCategory.key;
    if (sources[0]) filters.source_name = sources[0].name;
    const years = matchedYears(text);
    if (years.length === 1) {
      filters.year_from = years[0];
      filters.year_to = years[0];
    }
    const disclosure = disclosureFor(firstCategory);
    if (disclosure) disclosures.push(disclosure);
    return {
      intent: "metric",
      metric_ids: [previous.metric_id],
      filters,
      interpretation: `Following up: ${previous.interpretation}`,
      confidence: firstCategory ? 0.92 : 0.7,
      closest_match_disclosure: disclosures.join(" ") || undefined,
      follow_up: true,
      plan_source: "deterministic",
    };
  }

  const wantsCompare =
    /\b(compare|comparison|versus|vs\.?|difference between|side by side)\b/i.test(text) ||
    (sources.length >= 2 && /\b(and|versus|vs\.?)\b/i.test(text)) ||
    (matches.length >= 2 && /\b(and|versus|vs\.?)\b/i.test(text));

  let impliedMetricId: string | null = null;

  if (wantsCompare) {
    const detectedCompareMetric = detectMetric(text);
    const typeCompareMetric = /\b(preprints?|articles?|datasets?|output types?)\b/i.test(text)
      ? "M13"
      : null;
    const compareMetricId = detectedCompareMetric ?? typeCompareMetric ?? "M03";
    let dimension: "category" | "source" | "year" = "category";
    let sides: [CompareSide, CompareSide] | null = null;

    if (sources.length >= 2) {
      dimension = "source";
      sides = [
        { label: sources[0].name, filters: { source_name: sources[0].name } },
        { label: sources[1].name, filters: { source_name: sources[1].name } },
      ];
    } else {
      const years = matchedYears(text);
      if (years.length >= 2) {
        dimension = "year";
        sides = [
          { label: String(years[0]), filters: { year_from: years[0], year_to: years[0] } },
          {
            label: String(years[1]),
            filters: { year_from: years[1], year_to: years[1] },
          },
        ];
      } else if (matches.length >= 2) {
        sides = [
          { label: labelFor(matches[0].key), filters: { category_key: matches[0].key } },
          { label: labelFor(matches[1].key), filters: { category_key: matches[1].key } },
        ];
      }
    }

    if (sides) {
      for (const side of sides) {
        if (dimension === "category") {
          const category = matches.find((match) => labelFor(match.key) === side.label);
          const disclosure = disclosureFor(category);
          if (disclosure) disclosures.push(disclosure);
        }
      }

      applyYears(text, sides[0].filters, compareMetricId, disclosures);
      if (dimension !== "year") {
        sides[1].filters.year_from = sides[0].filters.year_from;
        sides[1].filters.year_to = sides[0].filters.year_to;
      }
      if (sources[0] && dimension === "category") sides[0].filters.source_name = sources[0].name;

      return {
        intent: "compare",
        metric_ids: [compareMetricId],
        filters: { ...sides[0].filters, category_key_b: sides[1].filters.category_key },
        comparison: { metric_id: compareMetricId, dimension, sides },
        interpretation: `Comparing ${sides[0].label} with ${sides[1].label}.`,
        confidence: 0.93,
        closest_match_disclosure: disclosures.join(" ") || undefined,
        plan_source: "deterministic",
      };
    }

    impliedMetricId = compareMetricId;
    disclosures.push(
      "I treated this as one published-data measure because no two comparable categories, sources or years were named.",
    );
  }

  const metricId = detectMetric(text) ?? impliedMetricId;
  if (!metricId) return clarify();

  const filters: Filters = {};
  const disclosure = disclosureFor(firstCategory);
  if (disclosure) disclosures.push(disclosure);
  if (firstCategory) filters.category_key = firstCategory.key;
  if (sources[0]) filters.source_name = sources[0].name;

  const quote = clean.match(/"([^"]{2,100})"/)?.[1];
  if (quote) filters.venue_name = quote;

  applyYears(text, filters, metricId, disclosures);

  if (metricId === "M17") {
    const term = extractSearchTerm(clean);
    if (!term) {
      return {
        ...clarify(),
        clarification: "Please tell me which title words to search for.",
      };
    }
    filters.search_term = term;
  }

  if (metricId === "M06") {
    if (secondCategory) {
      filters.category_key_b = secondCategory.key;
      const secondDisclosure = disclosureFor(secondCategory);
      if (secondDisclosure) disclosures.push(secondDisclosure);
    } else if (firstCategory) {
      return {
        ...clarify(),
        clarification: `Which second category should I intersect with ${labelFor(
          firstCategory.key,
        )}?`,
      };
    }
  }

  if (CATEGORY_REQUIRED.has(metricId) && !filters.category_key) {
    return {
      ...clarify(),
      clarification: `Which category should I use for this question? For example: RAG, AI/ML, physics or economics.`,
    };
  }

  return {
    intent: metricId === "M17" ? "search" : "metric",
    metric_ids: [metricId],
    filters,
    interpretation: interpretationFor(metricId, filters, metricId === "M17" ? "search" : "metric"),
    confidence: firstCategory ? (disclosure ? 0.78 : 0.95) : 0.88,
    closest_match_disclosure: disclosures.join(" ") || undefined,
    plan_source: "deterministic",
  };
}

export function planFromLlm(
  plan: PlannerOutput,
  provider: "groq" | "gemini",
): ResolvedPlan {
  return {
    intent: plan.intent,
    metric_ids: plan.metric_ids,
    filters: { ...plan.filters } as Filters,
    comparison: plan.comparison
      ? {
          metric_id: plan.comparison.metric_id,
          dimension: plan.comparison.dimension,
          sides: plan.comparison.sides.map((side) => ({
            label: side.label,
            filters: { ...side.filters } as Filters,
          })) as [CompareSide, CompareSide],
        }
      : undefined,
    interpretation: plan.interpretation,
    confidence: plan.confidence,
    clarification: plan.clarification,
    refusal_reason: plan.refusal_reason,
    plan_source: "llm",
    provider,
  };
}

export function hasCategoryAlias(key: string, alias: string): boolean {
  return allCategoryAliases()
    .find((entry) => entry.key === key)
    ?.aliases.includes(alias.toLowerCase()) ?? false;
}

export function topicAliasBounded(alias: string): RegExp {
  return bounded(alias);
}
