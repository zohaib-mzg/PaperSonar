import { categoryByKey } from "@/server/metrics/catalogue";
import type { PublicMetric } from "@/server/metrics/catalogue";
import { growthSuppressionNote, intersectionReportable } from "@/server/metrics/guards";
import type { ResolvedPlan } from "@/server/metrics/resolver";
import type { SnowflakeRow } from "@/server/snowflake/types";

export type ChartSpec = {
  kind: "bar" | "line" | "horizontal_bar" | "donut" | "multi_line" | "grouped_bar" | "metric";
  title: string;
  labels: string[];
  series: Array<{ label: string; values: Array<number | null> }>;
  unit?: string;
  note?: string;
  xLabel?: string;
  yLabel?: string;
  fallback: { headers: string[]; rows: string[][] };
};

export type AnswerFacts = {
  values: Record<string, string | number | boolean | null>;
  rows: Array<Record<string, string | number | boolean | null>>;
  denominators: string[];
  caveats: string[];
  source_scope: string;
  as_of: string | null;
  snapshot_date: string | null;
  coverage_note: string | null;
};

export type FreshnessContext = {
  latest_snapshot_date: string | null;
  latest_published_at: string | null;
  total_outputs: number | null;
  retrieved_on: string | null;
};

export type AnswerEnvelope = {
  status:
    | "answered"
    | "clarify"
    | "unsupported"
    | "refused"
    | "DATA_UNAVAILABLE"
    | "RATE_LIMITED"
    | "MAINTENANCE"
    | "INTERNAL";
  answer: string;
  mode: "deterministic" | "composed";
  intent: ResolvedPlan["intent"];
  interpretation: string;
  metric_id: string | null;
  metric_label: string | null;
  facts: AnswerFacts;
  chart?: ChartSpec;
  citations: Array<{ label: string; view: string }>;
  closest_match_disclosure?: string;
  degraded?: string;
  provider?: "groq" | "gemini";
  fallback_used: boolean;
  freshness: FreshnessContext;
};

type BuildInput = {
  plan: ResolvedPlan;
  metric: PublicMetric;
  rows: SnowflakeRow[];
  freshness: FreshnessContext;
  provider?: "groq" | "gemini";
  fallbackUsed: boolean;
};

type SideResult = {
  side: { label: string; filters: Record<string, unknown> };
  rows: SnowflakeRow[];
};

const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export function fmt(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "not reported";
  return nf.format(value);
}

export function pct(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "not reported";
  return `${nf.format(value)}%`;
}

function num(row: SnowflakeRow, key: string): number | null {
  const value = row[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function str(row: SnowflakeRow, key: string): string | null {
  const value = row[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function dateOnly(value: string | null | undefined): string | null {
  if (!value) return null;
  const match = value.match(/^\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : value;
}

function labelForCategory(key: string | null | undefined): string {
  if (!key) return "all categories";
  return categoryByKey.get(key)?.label ?? key;
}

function ratioToPercent(value: number | null): number | null {
  if (value === null) return null;
  const scaled = value > 0 && value <= 1 ? value * 100 : value;
  return Math.round(scaled * 10) / 10;
}

type ChartOptions = {
  preferred?: ChartSpec["kind"];
  xLabel?: string;
  yLabel?: string;
  asOfYear?: number | null;
};

function trimTrailingEmptyYears(
  labels: string[],
  series: Array<{ label: string; values: Array<number | null> }>,
  asOfYear?: number | null,
): { labels: string[]; series: Array<{ label: string; values: Array<number | null> }> } {
  const yearIdxs = labels.map((l, i) => ({ l, i, y: Number(l.match(/^(19|20)\d{2}$/)?.[0]) }));
  const isYearSeries = yearIdxs.every((x) => Number.isFinite(x.y));
  if (!isYearSeries) return { labels, series };
  let end = labels.length - 1;
  while (end >= 0) {
    const y = yearIdxs[end].y;
    if (asOfYear != null && y > asOfYear) { end -= 1; continue; }
    const allEmpty = series.every((s) => s.values[end] == null || s.values[end] === 0);
    if (allEmpty) { end -= 1; continue; }
    break;
  }
  if (end === labels.length - 1) return { labels, series };
  if (end < 0) return { labels: [], series: series.map((s) => ({ ...s, values: [] })) };
  return { labels: labels.slice(0, end + 1), series: series.map((s) => ({ ...s, values: s.values.slice(0, end + 1) })) };
}

function pickKind(labels: string[], series: Array<{ label: string; values: Array<number | null> }>, opts?: ChartOptions): ChartSpec["kind"] {
  if (opts?.preferred) return opts.preferred;
  const isYears = labels.length > 1 && labels.every((l) => /^(19|20)\d{2}$/.test(l));
  if (series.length > 1) return isYears ? "multi_line" : "grouped_bar";
  if (isYears) return "line";
  return labels.length > 6 ? "horizontal_bar" : "bar";
}

function chartFromSeries(
  title: string,
  labelsIn: string[],
  seriesIn: Array<{ label: string; values: Array<number | null> }>,
  unit?: string,
  note?: string,
  opts?: ChartOptions,
): ChartSpec | undefined {
  const trimmed = trimTrailingEmptyYears(labelsIn, seriesIn, opts?.asOfYear);
  const labels = trimmed.labels;
  const series = trimmed.series;
  if (labels.length === 0 || series.length === 0) return undefined;
  if (labels.length <= 3 && (opts?.preferred === undefined || opts.preferred === "bar" || opts.preferred === "horizontal_bar")) return undefined;
  const flat = series.flatMap((item) => item.values).filter((value): value is number => value !== null);
  if (flat.length < 2 || new Set(flat).size < 2) return undefined;
  const kind = pickKind(labels, series, opts);
  const headers = ["Label", ...series.map((item) => item.label)];
  const fallbackRows = labels.map((label, index) => [
    label,
    ...series.map((item) => (item.values[index] === null ? "not reported" : fmt(item.values[index]))),
  ]);
  return { kind, title, labels, series, unit, note, xLabel: opts?.xLabel, yLabel: opts?.yLabel ?? unit, fallback: { headers, rows: fallbackRows } };
}

function donutChart(title: string, labels: string[], values: number[], unit?: string, note?: string): ChartSpec | undefined {
  const pairs = labels.map((l, i) => ({ l, v: values[i] ?? 0 })).filter((p) => p.v > 0);
  if (pairs.length < 2) return undefined;
  pairs.sort((a, b) => b.v - a.v);
  const top = pairs.slice(0, 6);
  const rest = pairs.slice(6).reduce((s, p) => s + p.v, 0);
  if (rest > 0) top.push({ l: "Other", v: rest });
  const finalLabels = top.map((p) => p.l);
  const finalValues = top.map((p) => p.v);
  return {
    kind: "donut",
    title,
    labels: finalLabels,
    series: [{ label: title, values: finalValues }],
    unit: unit ?? "%",
    note,
    fallback: { headers: ["Category", "Value"], rows: finalLabels.map((l, i) => [l, fmt(finalValues[i])]) },
  };
}

function baseFacts(metric: PublicMetric, freshness: FreshnessContext): AnswerFacts {
  return {
    values: {},
    rows: [],
    denominators: [metric.denominator],
    caveats: [...metric.caveats],
    source_scope: `PUBLISHED PROJECT_REPORTING · ${metric.primary_view}`,
    as_of: dateOnly(freshness.latest_published_at) ?? dateOnly(freshness.retrieved_on),
    snapshot_date: dateOnly(freshness.latest_snapshot_date),
    coverage_note: null,
  };
}

function headerAnswer(metric: PublicMetric, facts: AnswerFacts): string {
  const asOf = facts.as_of ? ` As of ${facts.as_of}.` : " As of latest snapshot.";
  return `Based on the published reporting data.${asOf} ${facts.denominators.join("; ")}. ${
    facts.caveats[0] ?? ""
  }`.trim();
}

function valuesFromRows(rows: SnowflakeRow[], keys: string[]): Record<string, number> {
  const result: Record<string, number> = {};
  for (const key of keys) {
    const values = rows.map((row) => num(row, key)).filter((value): value is number => value !== null);
    if (values.length > 0) result[key] = values.reduce((sum, value) => sum + value, 0);
  }
  return result;
}

function growthAnswer(input: BuildInput): AnswerEnvelope {
  const { plan, metric, rows, freshness, provider, fallbackUsed } = input;
  const facts = baseFacts(metric, freshness);
  const byCategory = new Map<
    string,
    { label: string; start: number | null; end: number | null }
  >();
  const years = [...new Set(rows.map((row) => num(row, "PUBLICATION_YEAR")).filter(Boolean))]
    .map(Number)
    .sort((a, b) => a - b);
  const startYear = Number(plan.filters.year_from ?? years[0] ?? 2024);
  const endYear = Number(plan.filters.year_to ?? years[years.length - 1] ?? 2025);

  for (const row of rows) {
    const key = str(row, "CATEGORY_KEY") ?? "unclassified";
    const entry = byCategory.get(key) ?? {
      label: str(row, "CATEGORY_LABEL") ?? labelForCategory(key),
      start: null,
      end: null,
    };
    const year = num(row, "PUBLICATION_YEAR");
    if (year === startYear) entry.start = num(row, "WORKS");
    if (year === endYear) entry.end = num(row, "WORKS");
    byCategory.set(key, entry);
  }

  const ranked = [...byCategory.entries()]
    .map(([key, value]) => ({ key, ...value }))
    .filter((entry) => !(growthSuppressionNote(entry.start, entry.end) !== null))
    .map((entry) => ({ ...entry, delta: (entry.end ?? 0) - (entry.start ?? 0) }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  if (ranked.length === 0) {
    facts.values = { start_year: startYear, end_year: endYear, reportable_categories: 0 };
    facts.caveats.push(
      "Suppression rule: this comparison is withheld because one side has fewer than 30 works; this is not zero growth.",
    );
    return {
      status: "answered",
      answer: `I can’t report this growth comparison because at least one side has fewer than 30 works. This is a suppression rule, not a finding of no growth. I can still show annual volume for ${labelForCategory(
        String(plan.filters.category_key ?? null),
      )}.`,
      mode: "deterministic",
      intent: plan.intent,
      interpretation: plan.interpretation,
      metric_id: metric.id,
      metric_label: metric.label,
      facts,
      citations: citationsFor(metric),
      closest_match_disclosure: plan.closest_match_disclosure,
      provider,
      fallback_used: fallbackUsed,
      freshness,
    };
  }

  const asOfYear = Number(String(freshness.latest_published_at ?? "").slice(0, 4)) || null;
  const allYears = [...new Set(rows.map((r) => num(r, "PUBLICATION_YEAR")).filter((y): y is number => y !== null))].sort((a, b) => a - b);
  const timelineYears = allYears.filter((y) => (asOfYear ? y <= asOfYear : true));
  const isTimeline = timelineYears.length > 2;
  const categoryYear = new Map<string, { label: string; byYear: Map<number, number> }>();
  for (const row of rows) {
    const key = str(row, "CATEGORY_KEY") ?? "unclassified";
    const year = num(row, "PUBLICATION_YEAR");
    const works = num(row, "WORKS");
    if (year === null || works === null) continue;
    const entry = categoryYear.get(key) ?? { label: str(row, "CATEGORY_LABEL") ?? labelForCategory(key), byYear: new Map<number, number>() };
    entry.byYear.set(year, (entry.byYear.get(year) ?? 0) + works);
    categoryYear.set(key, entry);
  }
  const topCats = [...categoryYear.entries()]
    .map(([key, v]) => ({ key, ...v, total: [...v.byYear.values()].reduce((s, n) => s + n, 0) }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 5);

  let chart: ChartSpec | undefined;
  if (isTimeline && topCats.length > 0) {
    const labels = timelineYears.map(String);
    const series = topCats.map((cat) => ({
      label: cat.label,
      values: timelineYears.map((y) => cat.byYear.get(y) ?? 0),
    }));
    const topByYear = timelineYears.map((y) => {
      let best: { label: string; works: number } | null = null;
      for (const cat of categoryYear.values()) {
        const w = cat.byYear.get(y) ?? 0;
        if (!best || w > best.works) best = { label: cat.label, works: w };
      }
      return { year: y, label: best?.label ?? "n/a", works: best?.works ?? 0 };
    });
    chart = chartFromSeries(
      "Trending topics timeline",
      labels,
      series,
      "works",
      "Top 5 categories by published works in the selected window.",
      { preferred: series.length > 1 ? "multi_line" : "line", xLabel: "Year", yLabel: "Works", asOfYear },
    );
    facts.rows = topByYear.map((r) => ({ year: r.year, top_category: r.label, works: r.works }));
    facts.values = { start_year: timelineYears[0], end_year: timelineYears[timelineYears.length - 1], categories_shown: topCats.length };
    const emerging = topByYear[topByYear.length - 1];
    const answer = `The timeline shows the top ${topCats.length} categories by published works from ${timelineYears[0]} to ${timelineYears[timelineYears.length - 1]}. In ${emerging.year}, the leading category was ${emerging.label} (${fmt(emerging.works)} works). ${headerAnswer(metric, facts)}`;
    return {
      status: "answered",
      answer,
      mode: "deterministic",
      intent: plan.intent,
      interpretation: plan.interpretation,
      metric_id: metric.id,
      metric_label: metric.label,
      facts,
      chart,
      citations: citationsFor(metric),
      closest_match_disclosure: plan.closest_match_disclosure,
      provider,
      fallback_used: fallbackUsed,
      freshness,
    };
  }

  const top = ranked.slice(0, 5);
  facts.values = {
    start_year: startYear,
    end_year: endYear,
    reportable_categories: ranked.length,
    ...Object.fromEntries(top.map((entry, index) => [`change_${index + 1}`, entry.delta])),
  };
  facts.rows = top.map((entry) => ({
    category: entry.label,
    start: entry.start,
    end: entry.end,
    change: entry.delta,
  }));
  facts.denominators.push("change = works in end year minus works in start year");
  chart = chartFromSeries(
    `Works change ${startYear}–${endYear}`,
    top.map((entry) => entry.label),
    [{ label: "Change in works", values: top.map((entry) => entry.delta) }],
    "works",
    undefined,
    { preferred: "bar", xLabel: "Category", yLabel: "Change in works", asOfYear },
  );
  const answer = `Between ${startYear} and ${endYear}, the largest change among reportable categories was ${top[0].label} (${fmt(top[0].delta)} works). ${headerAnswer(metric, facts)}`;
  return {
    status: "answered",
    answer,
    mode: "deterministic",
    intent: plan.intent,
    interpretation: plan.interpretation,
    metric_id: metric.id,
    metric_label: metric.label,
    facts,
    chart,
    citations: citationsFor(metric),
    closest_match_disclosure: plan.closest_match_disclosure,
    provider,
    fallback_used: fallbackUsed,
    freshness,
  };
}

function genericAnswer(input: BuildInput): AnswerEnvelope {
  const { plan, metric, rows, freshness, provider, fallbackUsed } = input;
  const facts = baseFacts(metric, freshness);
  let chart: ChartSpec | undefined;
  let answer = "";

  if (metric.id === "M02" || metric.id === "M15" || metric.id === "M24") {
    const valueKey =
      metric.id === "M02" ? "SHARE_OF_CORPUS" : metric.id === "M15" ? "WORKS" : "CANONICAL_OUTPUTS";
    const grouped = new Map<string, number>();
    for (const row of rows) {
      const key = metric.id === "M15" ? String(num(row, "PUBLICATION_YEAR") ?? "unknown") : (metric.id === "M24" ? (str(row, "PRIMARY_SOURCE_NAME") ?? str(row, "SOURCE_NAME") ?? "unknown") : labelForCategory(str(row, "CATEGORY_KEY")));
      const value = num(row, valueKey);
      if (value !== null) grouped.set(key, (grouped.get(key) ?? 0) + value);
    }
    const entries = [...grouped.entries()];
    const sorted = metric.id === "M15" ? entries.sort((a, b) => Number(a[0]) - Number(b[0])) : entries.sort((a, b) => b[1] - a[1]);
    const top = sorted.slice(0, metric.id === "M15" ? 20 : 8);
    const values = top.map(([, value]) => (metric.id === "M02" ? ratioToPercent(value) : value));
    facts.values = Object.fromEntries(top.map(([, value], index) => [`value_${index + 1}`, value]));
    facts.rows = top.map(([label, value]) => ({ label, value }));
    const asOfYear = Number(String(freshness.latest_published_at ?? "").slice(0, 4)) || null;
    if (metric.id === "M02") {
      chart = donutChart(metric.label, top.map(([l]) => l), top.map(([, v]) => ratioToPercent(v) ?? 0), "%");
    } else {
      chart = chartFromSeries(
        metric.label,
        top.map(([label]) => label),
        [{ label: metric.label, values }],
        "works",
        undefined,
        metric.id === "M15"
          ? { preferred: "line", xLabel: "Year", yLabel: "Works", asOfYear }
          : { preferred: top.length > 3 ? "horizontal_bar" : "bar", xLabel: "Works" },
      );
    }
    const lead = metric.id === "M15" ? top[top.length - 1] : top[0];
    const leadVal = metric.id === "M02" ? pct(values[top.indexOf(lead!)] ?? null) : fmt(lead?.[1] ?? null);
    answer = `The largest reported ${metric.label.toLowerCase()} is ${lead?.[0] ?? "n/a"} (${leadVal}). ${headerAnswer(metric, facts)}`;
  } else if (metric.id === "M03" || metric.id === "M07" || metric.id === "M13") {
    const valueKey = metric.id === "M03" ? "WORKS" : metric.id === "M07" ? "OUTPUTS" : "OUTPUTS";
    const labelKey = metric.id === "M03" ? "CATEGORY_LABEL" : metric.id === "M07" ? "PRIMARY_SOURCE_NAME" : "OUTPUT_TYPE_NAME";
    const grouped = new Map<string, number>();
    for (const row of rows) {
      const label = str(row, labelKey) ?? labelForCategory(str(row, "CATEGORY_KEY"));
      const value = num(row, valueKey);
      if (value !== null) grouped.set(label, (grouped.get(label) ?? 0) + value);
    }
    const top = [...grouped.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
    facts.values = Object.fromEntries(top.map(([, value], index) => [`value_${index + 1}`, value]));
    facts.rows = top.map(([label, value]) => ({ label, value }));
    if (metric.id === "M13") {
      chart = top.length > 3 ? donutChart(metric.label, top.map(([l]) => l), top.map(([, v]) => v), "works") : undefined;
    } else {
      chart = top.length > 3 ? chartFromSeries(
        metric.label,
        top.map(([label]) => label),
        [{ label: "Works", values: top.map(([, value]) => value) }],
        "works",
        undefined,
        { preferred: top.length > 5 ? "horizontal_bar" : "bar", xLabel: "Works" },
      ) : undefined;
    }
    answer = `The reported ${metric.label.toLowerCase()} is ${fmt(top[0]?.[1] ?? null)} for ${
      top[0]?.[0] ?? "the selected scope"
    }. ${headerAnswer(metric, facts)}`;
  } else if (metric.id === "M04") {
    const asOfYear = Number(String(freshness.latest_published_at ?? "").slice(0, 4)) || null;
    const sorted = [...rows]
      .filter((row) => num(row, "PUBLICATION_YEAR") !== null)
      .sort((a, b) => (num(a, "PUBLICATION_YEAR") ?? 0) - (num(b, "PUBLICATION_YEAR") ?? 0))
      .filter((row) => {
        const y = num(row, "PUBLICATION_YEAR");
        return y !== null && (asOfYear ? y <= asOfYear : true);
      });
    while (sorted.length > 0) {
      const last = sorted[sorted.length - 1];
      const observed = num(last, "OBSERVED_WORKS") ?? 0;
      const avg = num(last, "AVG_CITED_BY") ?? 0;
      if (observed === 0 && avg === 0) { sorted.pop(); continue; }
      break;
    }
    const labels = sorted.map((row) => String(num(row, "PUBLICATION_YEAR")));
    const averages = sorted.map((row) => num(row, "AVG_CITED_BY"));
    facts.values = valuesFromRows(sorted, ["TOTAL_CITATIONS", "OBSERVED_WORKS", "COHORT_SIZE", "AVG_CITED_BY"]);
    facts.rows = sorted.slice(0, 12).map((row) => ({
      year: num(row, "PUBLICATION_YEAR"),
      observed: num(row, "OBSERVED_WORKS"),
      average_citations: num(row, "AVG_CITED_BY"),
      median_citations: num(row, "MEDIAN_CITED_BY"),
    }));
    facts.snapshot_date = str(sorted[0] ?? rows[0] ?? {}, "SNAPSHOT_DATE") ?? facts.snapshot_date;
    chart = chartFromSeries("Average citations by year", labels, [{ label: "Average cited-by", values: averages }], "citations", undefined, { preferred: "line", xLabel: "Year", yLabel: "Average citations", asOfYear });
    answer = `The reported citation snapshot covers ${fmt(facts.values.OBSERVED_WORKS as number)} observed works with ${fmt(
      facts.values.TOTAL_CITATIONS as number,
    )} total citations. ${headerAnswer(metric, facts)}`;
  } else if (metric.id === "M05" || metric.id === "M23") {
    const valueKey = metric.id === "M05" ? "CITATION_CHANGE" : "CITED_BY_COUNT";
    const limit = Math.min(10, Math.max(1, Number(plan.filters.limit ?? 10)));
    const top = [...rows].sort((a, b) => (num(b, valueKey) ?? -Infinity) - (num(a, valueKey) ?? -Infinity)).slice(0, limit);
    const labels = top.map((row) => String(str(row, "TITLE") ?? str(row, "OUTPUT_SK") ?? num(row, "OUTPUT_SK") ?? "output"));
    facts.values = Object.fromEntries(top.map((row, index) => [`output_${index + 1}`, num(row, valueKey) ?? 0]));
    facts.rows = top.map((row) => ({ output: str(row, "OUTPUT_SK") ?? num(row, "OUTPUT_SK"), title: str(row, "TITLE"), value: num(row, valueKey) }));
    chart = top.length > 3 ? chartFromSeries(metric.label, labels, [{ label: metric.id === "M05" ? "Citation change" : "Citations", values: top.map((row) => num(row, valueKey)) }], "citations", undefined, { preferred: "horizontal_bar", yLabel: "Output", xLabel: "Citations" }) : undefined;
    answer = `The largest reported ${metric.label.toLowerCase()} is ${fmt(num(top[0] ?? {}, valueKey))}. ${headerAnswer(
      metric,
      facts,
    )}`;
  } else if (metric.id === "M06") {
    const rowsWithFlags = rows.map((row) => ({
      row,
      reportable: intersectionReportable(
        num(row, "PARENT_WORKS_A"),
        num(row, "PARENT_WORKS_B"),
        num(row, "JOINT_WORKS"),
        row.IS_REPORTABLE === true || row.IS_REPORTABLE === "true" ? true : null,
      ),
    }));
    const reportable = rowsWithFlags.filter((item) => item.reportable);
    if (reportable.length === 0) {
      facts.values = { reportable_pairs: 0 };
      facts.caveats.push("The joint-work and parent-work thresholds were not met.");
      return {
        status: "answered",
        answer: "I can’t report this intersection because the parent categories or joint works fall below the disclosure thresholds. This is a suppression rule, not evidence of no overlap.",
        mode: "deterministic",
        intent: plan.intent,
        interpretation: plan.interpretation,
        metric_id: metric.id,
        metric_label: metric.label,
        facts,
        citations: citationsFor(metric),
        closest_match_disclosure: plan.closest_match_disclosure,
        provider,
        fallback_used: fallbackUsed,
        freshness,
      };
    }
    const top = reportable.slice(0, 8).map((item) => item.row);
    const labels = top.map(
      (row) => `${labelForCategory(str(row, "CATEGORY_LABEL_A"))} × ${labelForCategory(str(row, "CATEGORY_LABEL_B"))}`,
    );
    facts.values = Object.fromEntries(top.map((row, index) => [`joint_${index + 1}`, num(row, "JOINT_WORKS") ?? 0]));
    facts.rows = top.map((row) => ({
      pair: `${str(row, "CATEGORY_KEY_A")} × ${str(row, "CATEGORY_KEY_B")}`,
      joint_works: num(row, "JOINT_WORKS"),
      ratio: num(row, "JOINT_TO_SMALLER_PARENT_RATIO"),
    }));
    chart = chartFromSeries(
      "Reportable topic intersections",
      labels,
      [{ label: "Joint works", values: top.map((row) => num(row, "JOINT_WORKS")) }],
      "works",
      "Discovery signal only; not proof of novelty or causality.",
    );
    answer = `The largest reportable intersection is ${labels[0]} with ${fmt(num(top[0] ?? {}, "JOINT_WORKS"))} joint works. ${headerAnswer(
      metric,
      facts,
    )}`;
  } else if (metric.id === "M08" || metric.id === "M14") {
    const labelKey = metric.id === "M08" ? "PRIMARY_SOURCE_NAME" : "CATEGORY_LABEL";
    if (metric.id === "M14") {
      const totalKnown = rows.reduce((s, r) => s + (num(r, "KNOWN_ACCESS_WORKS") ?? 0), 0);
      const open = rows.reduce((s, r) => s + (num(r, "OPEN_ACCESS_WORKS") ?? 0), 0);
      const unknown = rows.reduce((s, r) => s + (num(r, "UNKNOWN_ACCESS_WORKS") ?? 0), 0);
      const closed = Math.max(0, totalKnown - open);
      facts.values = { ...valuesFromRows(rows, ["WORKS", "KNOWN_ACCESS_WORKS", "UNKNOWN_ACCESS_WORKS", "OPEN_ACCESS_WORKS"]), open_access_works: open, closed_known_works: closed };
      facts.rows = rows.slice(0, 8).map((row) => ({ label: str(row, labelKey), open_access_share_known: ratioToPercent(num(row, "OPEN_ACCESS_SHARE_KNOWN")) }));
      const share = totalKnown > 0 ? Math.round((open / totalKnown) * 1000) / 10 : null;
      chart = totalKnown > 0 ? donutChart("Open access share", ["Open access", "Closed (known)", ...(unknown > 0 ? ["Unknown access"] : [])], [open, closed, ...(unknown > 0 ? [unknown] : [])], "works", "Share based on published winner-source access fields.") : undefined;
      answer = share === null ? `Open-access share is not reported for this scope. ${headerAnswer(metric, facts)}` : `Open access accounts for ${pct(share)} of known-access works in this scope. ${headerAnswer(metric, facts)}`;
    } else {
      const valueKey = "OUTPUTS_WITHOUT_DOI";
      const labels = rows.slice(0, 8).map((row) => str(row, labelKey) ?? "unknown");
      const values = rows.slice(0, 8).map((row) => num(row, valueKey));
      facts.values = valuesFromRows(rows, ["OUTPUTS", "OUTPUTS_WITHOUT_DOI", "OUTPUTS_WITHOUT_VENUE", "OUTPUTS_WITHOUT_ACCESS_STATUS"]);
      facts.rows = rows.slice(0, 8).map((row) => ({ label: str(row, labelKey), value: num(row, valueKey) }));
      chart = labels.length > 3 ? chartFromSeries(metric.label, labels, [{ label: metric.label, values }], "outputs", undefined, { preferred: "horizontal_bar", xLabel: "Outputs" }) : undefined;
      answer = `${metric.label} is reported for ${labels.length} scope rows. ${headerAnswer(metric, facts)}`;
    }
  } else if (metric.id === "M09" || metric.id === "M10" || metric.id === "M11" || metric.id === "M12") {
    const labelKey =
      metric.id === "M09"
        ? "INSTITUTION_NAME"
        : metric.id === "M10"
          ? "INSTITUTION_NAME"
          : metric.id === "M11"
            ? "AUTHOR_NAME"
            : "VENUE_NAME";
    const valueKey = metric.id === "M09" || metric.id === "M10" ? "FRACTIONAL_CREDIT" : "WORKS";
    const grouped = new Map<string, number>();
    for (const row of rows) {
      const label = str(row, labelKey) ?? "unknown";
      const value = num(row, valueKey);
      if (value !== null) grouped.set(label, (grouped.get(label) ?? 0) + value);
    }
    const limit = Math.min(15, Math.max(1, Number(plan.filters.limit ?? 10)));
    const top = [...grouped.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit);
    facts.values = Object.fromEntries(top.map(([, value], index) => [`value_${index + 1}`, value]));
    facts.rows = top.map(([label, value]) => ({ label, value }));
    chart = top.length > 3 ? chartFromSeries(
      metric.label,
      top.map(([label]) => label),
      [{ label: metric.id === "M09" || metric.id === "M10" ? "Fractional credit" : "Works", values: top.map(([, value]) => value) }],
      metric.id === "M09" || metric.id === "M10" ? "fractional credit" : "works",
      undefined,
      { preferred: "horizontal_bar", xLabel: metric.id === "M09" || metric.id === "M10" ? "Fractional credit" : "Works", yLabel: labelKey.toLowerCase().replace("_name", "").replace("_", " ") },
    ) : undefined;
    answer = `The leading reported ${labelKey.toLowerCase().replace("_name", "")} is ${top[0]?.[0] ?? "n/a"} with ${fmt(
      top[0]?.[1] ?? null,
    )}. ${headerAnswer(metric, facts)}`;
  } else if (metric.id === "M16") {
    const grouped = new Map<number, number>();
    for (const row of rows) {
      const sourceCount = num(row, "SOURCE_COUNT");
      if (sourceCount !== null) grouped.set(sourceCount, (grouped.get(sourceCount) ?? 0) + 1);
    }
    const top = [...grouped.entries()].sort((a, b) => a[0] - b[0]).slice(0, 8);
    facts.values = Object.fromEntries(top.map(([count, outputs]) => [`source_count_${count}`, outputs]));
    facts.rows = top.map(([count, outputs]) => ({ source_count: count, outputs }));
    chart = chartFromSeries(
      "Outputs by number of source observations",
      top.map(([count]) => `${count} sources`),
      [{ label: "Outputs", values: top.map(([, outputs]) => outputs) }],
      "outputs",
    );
    answer = `${fmt(top.reduce((sum, [, count]) => sum + count, 0))} canonical outputs have observations from more than one source. ${headerAnswer(
      metric,
      facts,
    )}`;
  } else if (metric.id === "M17") {
    facts.rows = rows.slice(0, 8).map((row) => ({
      title: str(row, "TITLE"),
      year: num(row, "PUBLICATION_YEAR"),
      category: str(row, "CATEGORY_LABEL"),
      source: str(row, "PRIMARY_SOURCE_NAME"),
    }));
    facts.values = { matches: rows.length, shown: Math.min(rows.length, 8) };
    facts.caveats.push("Title search is lexical and does not search full text.");
    answer = rows.length === 0
      ? "No published output titles matched that search. Try a shorter or more exact title phrase."
      : `Found ${fmt(rows.length)} published title match${rows.length === 1 ? "" : "es"}. The first ${Math.min(
          rows.length,
          8,
        )} are listed as evidence. ${headerAnswer(metric, facts)}`;
  } else if (metric.id === "M18") {
    facts.rows = rows.slice(0, 8).map((row) => ({
      source: str(row, "SOURCE_NAME"),
      batch: str(row, "BATCH_ID"),
      published_at: str(row, "PUBLISHED_AT"),
      capped: row.IS_CAPPED,
    }));
    facts.values = { sources: rows.length };
    facts.caveats.push("A published batch is not a promise that every source is complete.");
    answer = `The latest published batch is listed for ${fmt(rows.length)} source${rows.length === 1 ? "" : "s"}. ${headerAnswer(
      metric,
      facts,
    )}`;
  } else if (metric.id === "M19" || metric.id === "M22") {
    facts.values = valuesFromRows(rows, [
      "TOTAL_OUTPUTS",
      "CLASSIFIED_OUTPUTS",
      "SOURCE_COUNT",
      "TOTAL_OUTPUTS",
    ]);
    facts.rows = rows.slice(0, 1).map((row) => ({ ...row }));
    facts.as_of = facts.snapshot_date ?? facts.as_of;
    answer = `The published corpus contains ${fmt(facts.values.TOTAL_OUTPUTS as number)} outputs from ${fmt(
      facts.values.SOURCE_COUNT as number,
    )} source${facts.values.SOURCE_COUNT === 1 ? "" : "s"}. ${headerAnswer(metric, facts)}`;
  } else if (metric.id === "M20" || metric.id === "M21") {
    facts.rows = rows.slice(0, 8).map((row) => ({ ...row }));
    facts.values = { rows: rows.length };
    answer = `${metric.description} ${headerAnswer(metric, facts)}`;
  } else {
    facts.values = valuesFromRows(rows, ["WORKS", "OUTPUTS", "CITED_BY_COUNT"]);
    facts.rows = rows.slice(0, 8).map((row) => ({ ...row }));
    answer = `${metric.description} ${headerAnswer(metric, facts)}`;
  }

  if (chart && chart.kind !== "metric" && chart.kind !== "donut" && facts.rows.length > 0 && facts.rows.length <= 3 && metric.id !== "M04" && metric.id !== "M15") {
    chart = undefined;
  }
  const numericValues = Object.values(facts.values).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!chart && numericValues.length === 1 && (metric.id === "M19" || metric.id === "M22") && facts.rows.length === 0) {
    chart = {
      kind: "metric",
      title: metric.label,
      labels: [metric.label],
      series: [{ label: metric.label, values: [numericValues[0]] }],
      unit: metric.id === "M19" ? "outputs" : undefined,
      fallback: { headers: ["Metric", "Value"], rows: [[metric.label, fmt(numericValues[0])]] },
    };
  }

  return {
    status: "answered",
    answer,
    mode: "deterministic",
    intent: plan.intent,
    interpretation: plan.interpretation,
    metric_id: metric.id,
    metric_label: metric.label,
    facts,
    chart,
    citations: citationsFor(metric),
    closest_match_disclosure: plan.closest_match_disclosure,
    provider,
    fallback_used: fallbackUsed,
    freshness,
  };
}

export function buildAnswer(input: BuildInput): AnswerEnvelope {
  if (input.metric.id === "M01") return growthAnswer(input);
  return genericAnswer(input);
}

export function buildComparisonAnswer(
  plan: ResolvedPlan,
  metric: PublicMetric,
  sides: SideResult[],
  freshness: FreshnessContext,
  provider?: "groq" | "gemini",
  fallbackUsed = false,
): AnswerEnvelope {
  const facts = baseFacts(metric, freshness);
  const valueKey =
    metric.id === "M02"
      ? "SHARE_OF_CORPUS"
      : metric.id === "M04"
        ? "AVG_CITED_BY"
        : metric.id === "M14"
          ? "OPEN_ACCESS_SHARE_KNOWN"
          : metric.id === "M09" || metric.id === "M10"
            ? "FRACTIONAL_CREDIT"
            : metric.id === "M23"
              ? "CITED_BY_COUNT"
              : "WORKS";

  const sums = sides.map((side) => ({
    label: side.side.label,
    value: side.rows.reduce((total, row) => total + (num(row, valueKey) ?? 0), 0),
  }));
  const display = sums.map((item) =>
    metric.id === "M02" || metric.id === "M14" ? ratioToPercent(item.value) : item.value,
  );
  facts.values = Object.fromEntries(sums.map((item, index) => [`side_${index + 1}`, item.value]));
  facts.rows = sums.map((item, index) => ({ label: item.label, value: display[index] }));
  facts.denominators.push(`each side uses ${metric.denominator.toLowerCase()}`);
  const preferred: ChartSpec["kind"] = plan.comparison?.dimension === "year" ? "grouped_bar" : "grouped_bar";
  const chart = chartFromSeries(
    `${metric.label} comparison`,
    sums.map((item) => item.label),
    [{ label: metric.label, values: display }],
    metric.id === "M02" || metric.id === "M14" ? "%" : undefined,
    undefined,
    { preferred, xLabel: "Comparison", yLabel: metric.label },
  );
  const answer = `Comparison: ${sums[0]?.label ?? "left side"} ${fmt(display[0])} versus ${
    sums[1]?.label ?? "right side"
  } ${fmt(display[1])}. ${headerAnswer(metric, facts)}`;
  return {
    status: "answered",
    answer,
    mode: "deterministic",
    intent: "compare",
    interpretation: plan.interpretation,
    metric_id: metric.id,
    metric_label: metric.label,
    facts,
    chart,
    citations: citationsFor(metric),
    closest_match_disclosure: plan.closest_match_disclosure,
    provider,
    fallback_used: fallbackUsed,
    freshness,
  };
}

export function citationsFor(metric: PublicMetric) {
  return [
    { label: "Published reporting view", view: metric.primary_view },
    { label: "Freshness", view: "VW_PUBLIC_CORPUS_SUMMARY" },
  ];
}

export function emptyFacts(freshness: FreshnessContext): AnswerFacts {
  return {
    values: {},
    rows: [],
    denominators: [],
    caveats: [],
    source_scope: "PUBLISHED PROJECT_REPORTING",
    as_of: dateOnly(freshness.latest_published_at) ?? dateOnly(freshness.retrieved_on),
    snapshot_date: dateOnly(freshness.latest_snapshot_date),
    coverage_note: null,
  };
}

export const defaultFreshness: FreshnessContext = {
  latest_snapshot_date: null,
  latest_published_at: null,
  total_outputs: null,
  retrieved_on: null,
};
