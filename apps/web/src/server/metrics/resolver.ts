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
    /^(please\s+)?(find|search|look\s+up)\b|\b(find|search|look\s+up)\b.{0,60}\b(papers?|outputs?|works?|titles?|datasets?|research)\b|\b(latest|recent|new)\b.{0,20}\b(papers?|outputs?|works?|articles?)\b.{0,10}\b(on|about|for|related to)\b/i,
  ],
  ["M22", /\b(how fresh|freshness|latest snapshot|last updated|up to date)\b/i],
  [
    "M18",
    /\b(latest|most recent|fresh|status|failed|published)\b.{0,30}\b(batch|data|ingest|pipeline)\b|\bwhich batch\b|\bsources are currently included\b|\bnot reportable\b|\bmissing from an answer\b|\bdata status\b/i,
  ],
  ["M19", /\b(corpus size|total outputs|overall totals|how many outputs (in|across) (the )?corpus)\b/i],
  ["M20", /\b(define|definition|meaning of|what does .{1,40} mean)\b|\bwhat is [a-z0-9/-]{2,40}\?$/i],
  ["M23", /\b(most cited|top cited|highest cited)\b.{0,40}\b(papers?|outputs?|works?|research)\b|\btop\s+\d+\b.{0,60}\b(papers?|outputs?|works?|research)\b.{0,30}\b(citations?|cited)\b/i],
  ["M05", /\b(citation gain|gained citations|citation growth|citation change|citations gained)\b/i],
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
  ["M12", /\b(venue|venues|journal|journals|conference|conferences|where\b.{0,50}\bpublished most)\b/i],
  ["M14", /\b(open access|oa\b|access status|gold oa|green oa)\b/i],
  ["M08", /\b(missing metadata|completeness|without doi|without a? venue|without access status|missing author)\b/i],
  ["M07", /\b(coverage|coverage ratio|by source|per source|source coverage|underrepresented)\b/i],
  ["M13", /\b(output type|output types|article type|type mix|publication types)\b/i],
  ["M24", /\b(source contribution|which source contributes|contribution by source)\b/i],
  ["M02", /\b(share|percent|percentage|proportion|what fraction|of the corpus)\b/i],
  [
    "M15",
    /\b(by year|per year|publication years|publication[- ]year|year distribution|each year|partial[- ]year|year effect|under-?represented years?|years are under-represented|sparse years?|(?<!trending topics? )timeline|over time|annual trend|yearly trend|publication trend|trend over|trend of|trend in|trends? by|publication trend)\b/i,
  ],
  [
    "M01",
    /\b(grew|growth|declined|decline|increased|decreased|fastest|rising|falling|change in|relative increase|emerging|trending topics?|fastest growing)\b/i,
  ],
  [
    "M03",
    /\b(how many|count|number of|volume|published|works?|papers?|outputs?|classified vs unclassified|what'?s new|new in|recent papers?|recent publications?)\b/i,
  ],
];

function detectMetric(text: string): string | null {
  for (const [metricId, pattern] of METRIC_RULES) {
    if (pattern.test(text)) {
      if (metricId === "M15" && /\btrending topics?\b/i.test(text)) return "M01";
      return metricId;
    }
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
    .replace(/^(latest|recent|new)\s+(papers?|outputs?|works?|articles?|research)\s+(on|about|for|related to)\s+/i, "")
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
  const lastN = text.match(/\b(?:last|past)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+years?\b/i);
  if (lastN) {
    const wordMap: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
    const n = wordMap[lastN[1].toLowerCase()] ?? Number(lastN[1]);
    if (Number.isFinite(n) && n > 0 && n <= 20) {
      filters.year_from = latest - (n - 1);
      filters.year_to = latest;
      disclosures.push(`Using the latest ${n} complete publication year${n === 1 ? "" : "s"} (${filters.year_from}–${latest}).`);
      return;
    }
  }
  if (/\b(this year|current year)\b/i.test(text) && years.length === 0) {
    filters.year_from = latest;
    filters.year_to = latest;
    disclosures.push(`“This year” is interpreted as ${latest}, the latest complete publication year.`);
    return;
  }
  if (/\bsince\s+((?:19|20)\d{2})\b/i.test(text)) {
    const since = Number(text.match(/\bsince\s+((?:19|20)\d{2})\b/i)?.[1]);
    if (Number.isFinite(since)) {
      filters.year_from = since;
      filters.year_to = latest;
      disclosures.push(`Using publication years ${since}–${latest}.`);
      return;
    }
  }
  if (/\blast year\b/i.test(text) && years.length === 0) {
    if (metricId === "M01") {
      filters.year_from = latest - 1;
      filters.year_to = latest;
      disclosures.push(`“Last year” growth compares ${latest - 1} with ${latest}.`);
    } else {
      filters.year_from = latest;
      filters.year_to = latest;
      disclosures.push(`“Last year” is interpreted as ${latest}, the latest complete publication year.`);
    }
    return;
  }
  if (years.length >= 2) {
    filters.year_from = years[0];
    filters.year_to = years[years.length - 1];
    return;
  }
  if (years.length === 1) {
    const year = years[0];
    if (metricId === "M01") {
      filters.year_from = year - 1;
      filters.year_to = year;
      disclosures.push(`Growth for ${year} compares ${year - 1} with ${year}.`);
    } else {
      filters.year_from = year;
      filters.year_to = year;
    }
    return;
  }
  filters.year_from = metricId === "M01" ? latest - 1 : latest - 4;
  filters.year_to = latest;
  disclosures.push(`Using the latest complete publication window (${filters.year_from}–${latest}).`);
}

function isPromptInjection(text: string): boolean {
  return /\b(ignore (your|previous|all) instructions|reveal (your|the) (prompt|system)|system prompt|developer message|jailbreak|do anything now|answer from your own knowledge)\b/i.test(
    text,
  );
}

function isPolicyRefusal(text: string): boolean {
  return /\b(caus(e|ed|ality)|why did|why does|because of|predict|forecast|will .{0,30}(rise|fall|grow|decline)|invest|buy|sell|medical advice|diagnose|legal advice|financial advice|full[- ]text|raw bronze|raw silver|accountadmin)\b/i.test(
    text,
  ) || isPromptInjection(text);
}

function isOutOfScopeQuestion(text: string): boolean {
  if (isPromptInjection(text)) return true;
  const asksCode = /\b(write|generate|create|show me)\b.{0,40}\b(code|python|javascript|sql|script|function|program)\b/i.test(text) || /\b(code for|implement|regex for)\b/i.test(text);
  const asksGeneral = /\b(president|weather|news|stock price|joke|poem|story|recipe|capital of|who won|movie|song)\b/i.test(text);
  const chitChat = /^(hi|hello|hey|thanks|thank you|who are you|what can you do\??)$/i.test(text.trim());
  const asksData = /\b(how many|count|number of|trend|timeline|over time|by year|per year|top\b|most cited|citations?|compare|versus|vs\.?|share|percentage|open access|institutions?|authors?|venues?|countries?|which|latest|fresh|new in|status|batch|outputs?|papers?|publications?|works?|articles?|datasets?|search|find|look up)\b/i.test(text);
  const generalExplanation = /\b(explain|tell me about|teach me|how does .+ work|give me an overview of|describe)\b/i.test(text) && !asksData;
  if (asksCode || asksGeneral || chitChat) return true;
  if (generalExplanation) return true;
  if (/\bexplain\b/i.test(text) && !/\b(trend|growth|change|difference|why .* (count|number|share))\b/i.test(text)) return true;
  return false;
}

function outOfScopeRefusal(message: string): ResolvedPlan {
  const lower = message.toLowerCase();
  const hasRag = /\brag\b|retrieval[- ]augmented/.test(lower);
  const suggestions = hasRag
    ? [
        "How many RAG papers were published in 2025?",
        "Show the RAG publication timeline from 2020 to 2025.",
        "Which institutions publish the most on RAG?",
      ]
    : [
        "How many RAG outputs were published in 2025?",
        "Which topics grew fastest in the latest complete year?",
        "Compare OpenAlex and Crossref coverage.",
      ];
  return {
    intent: "refuse",
    metric_ids: [],
    filters: {},
    interpretation: "Out-of-scope question.",
    confidence: 1,
    refusal_reason: `I only answer questions about the published research data in this warehouse. Try: ${suggestions.map((s) => `“${s}”`).join(" ")}`,
    plan_source: "deterministic",
  };
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

function clarify(message = ""): ResolvedPlan {
  const lower = message.toLowerCase();
  const hasCategory = matchCategories(lower).length > 0;
  const suggestions = hasCategory
    ? ["How many outputs were published in the latest year?", "Show the publication timeline by year.", "Which institutions publish the most?"]
    : ["How many RAG outputs were published in 2025?", "Which topics grew fastest in the latest complete year?", "Compare OpenAlex and Crossref coverage."];
  return {
    intent: "clarify",
    metric_ids: [],
    filters: {},
    interpretation: "Clarification needed.",
    confidence: 0.4,
    clarification: `Which research-data question do you want answered? Options: ${suggestions.map((s) => `“${s}”`).join(" ")}`,
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

  if (isOutOfScopeQuestion(text)) return outOfScopeRefusal(clean);
  if (isPolicyRefusal(text)) return refuse();

  const matches = matchCategories(text);
  const sources = matchSources(text);
  const firstCategory = matches[0];
  const secondCategory = matches[1];

  const followUp = /^(what about|how about|same for|and for|and what about|now\b|instead\b|also\b|break(?:ing)? down|split by|show it|by country|by institution|by author|by venue)\b/i.test(text);
  if (followUp && recent.length > 0) {
    const previous = recent[0];
    const filters: Filters = { ...previous.filters };
    let followMetricId = previous.metric_id;
    if (/\b(by country|countries|geography)\b/i.test(text)) followMetricId = "M09";
    if (/\b(by institution|institutions|universit)\b/i.test(text)) followMetricId = "M09";
    if (/\b(by author|authors|researchers)\b/i.test(text)) followMetricId = "M11";
    if (/\b(by venue|venues|journals?|conferences?)\b/i.test(text)) followMetricId = "M12";
    if (/\b(by year|per year|timeline|over time)\b/i.test(text)) followMetricId = "M15";
    if (firstCategory) filters.category_key = firstCategory.key;
    if (secondCategory) filters.category_key_b = secondCategory.key;
    if (sources[0]) filters.source_name = sources[0].name;
    const years = matchedYears(text);
    if (years.length >= 2) {
      filters.year_from = years[0];
      filters.year_to = years[years.length - 1];
    } else if (years.length === 1) {
      const year = years[0];
      filters.year_from = followMetricId === "M01" ? year - 1 : year;
      filters.year_to = year;
      if (followMetricId === "M01") {
        disclosures.push(`Growth for ${year} compares ${year - 1} with ${year}.`);
      }
    } else if (followMetricId === "M01") {
      const from = Number(filters.year_from);
      const to = Number(filters.year_to);
      if (Number.isInteger(from) && Number.isInteger(to) && from === to) {
        filters.year_from = to - 1;
        disclosures.push(`Growth compares ${to - 1} with ${to}.`);
      }
    }
    const disclosure = disclosureFor(firstCategory);
    if (disclosure) disclosures.push(disclosure);
    const topN = text.match(/\btop\s+(\d{1,2})\b/i);
    if (topN) filters.limit = Math.min(50, Math.max(1, Number(topN[1])));
    return {
      intent: "metric",
      metric_ids: [followMetricId],
      filters,
      interpretation: `Following up: ${previous.interpretation}`,
      confidence: firstCategory || followMetricId !== previous.metric_id ? 0.9 : 0.7,
      closest_match_disclosure: disclosures.join(" ") || undefined,
      follow_up: true,
      plan_source: "deterministic",
    };
  }

  const wantsCompare =
    /\b(compare|comparison|versus|vs\.?|difference between|side by side|more than|fewer than|higher than|lower than)\b/i.test(text) ||
    (sources.length >= 2 && /\b(and|or|versus|vs\.?|more|fewer|higher|lower)\b/i.test(text)) ||
    (matches.length >= 2 && /\b(and|or|versus|vs\.?|more|fewer|higher|lower)\b/i.test(text));

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
      if (firstCategory && dimension !== "category") {
        sides[0].filters.category_key = firstCategory.key;
        sides[1].filters.category_key = firstCategory.key;
        const disclosure = disclosureFor(firstCategory);
        if (disclosure) disclosures.push(disclosure);
      }
      if (sources[0] && dimension !== "source") {
        sides[0].filters.source_name = sources[0].name;
        sides[1].filters.source_name = sources[0].name;
      }
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
  const topN = text.match(/\btop\s+(\d{1,2})\b/i);
  if (topN) filters.limit = Math.min(50, Math.max(1, Number(topN[1])));

  if (metricId === "M17") {
    const term = extractSearchTerm(clean);
    if (!term) {
      return {
        ...clarify(),
        clarification: "Which title should I search for? Options: “attention is all you need”, “retrieval augmented generation”, or “BERT”.",
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
        clarification: `Which second category should I intersect with ${labelFor(firstCategory.key)}? Options: “LLM”, “AI/ML”, or “software testing”.`,
      };
    }
  }

  if (CATEGORY_REQUIRED.has(metricId) && !filters.category_key) {
    return {
      ...clarify(),
      clarification: "Which category should I use? Options: “RAG”, “LLM”, or “AI/ML”.",
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
  const filters = { ...plan.filters } as Filters;
  if (plan.metric_ids[0] === "M01") {
    const from = Number(filters.year_from);
    const to = Number(filters.year_to);
    if (Number.isInteger(from) && Number.isInteger(to) && from === to) {
      filters.year_from = to - 1;
    }
  }
  return {
    intent: plan.intent,
    metric_ids: plan.metric_ids,
    filters,
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
