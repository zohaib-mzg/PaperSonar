import {
  buildAnswer,
  buildComparisonAnswer,
  citationsFor,
  dateOnly,
  defaultFreshness,
  emptyFacts,
  type AnswerEnvelope,
  type FreshnessContext,
} from "@/server/chat/answer";
import type { ChatRequest } from "@/server/chat/schema";
import { getRecentTurns, recordTurn } from "@/server/chat/session";
import { cache, canonicalHash } from "@/server/cache";
import { env, missingForChat } from "@/server/env";
import { composeWithLlm, planWithLlm } from "@/server/llm/router";
import { log, logError, requestId } from "@/server/logger";
import { metricById } from "@/server/metrics/catalogue";
import { compileMetric } from "@/server/metrics/compiler";
import { validateFilters, type Filters } from "@/server/metrics/guards";
import { planFromLlm, resolveQuestion, type ResolvedPlan } from "@/server/metrics/resolver";
import { enforceLimit } from "@/server/rate-limit";
import { querySnowflake, SnowflakeError } from "@/server/snowflake/client";
import type { SnowflakeRow } from "@/server/snowflake/types";

export type ChatResult = {
  status: number;
  body: AnswerEnvelope & { request_id: string };
};

type SideResult = {
  side: { label: string; filters: Record<string, unknown> };
  rows: SnowflakeRow[];
};

const CACHE_TTL_SECONDS = 10 * 60;

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

async function getFreshness(): Promise<FreshnessContext> {
  const cached = await cache.get<FreshnessContext>("freshness:v2");
  if (cached) return cached;
  try {
    const result = await querySnowflake(
      `SELECT LATEST_SNAPSHOT_DATE, LATEST_PUBLISHED_AT, TOTAL_OUTPUTS, RETRIEVED_ON
       FROM PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_CORPUS_SUMMARY LIMIT 1`,
    );
    const row = result.rows[0] ?? {};
    const freshness: FreshnessContext = {
      latest_snapshot_date:
        typeof row.LATEST_SNAPSHOT_DATE === "string" ? dateOnly(row.LATEST_SNAPSHOT_DATE) : null,
      latest_published_at:
        typeof row.LATEST_PUBLISHED_AT === "string" ? dateOnly(row.LATEST_PUBLISHED_AT) : null,
      total_outputs: asNumber(row.TOTAL_OUTPUTS),
      retrieved_on: typeof row.RETRIEVED_ON === "string" ? dateOnly(row.RETRIEVED_ON) : null,
    };
    await cache.set("freshness:v2", freshness, 300);
    return freshness;
  } catch (error) {
    logError("chat_freshness_failed", error, {
      source: "PAPERSONAR.PROJECT_REPORTING.VW_PUBLIC_CORPUS_SUMMARY",
    });
    return defaultFreshness;
  }
}

function envelopeBase(
  requestIdValue: string,
  status: AnswerEnvelope["status"],
  answer: string,
  freshness: FreshnessContext,
  plan?: ResolvedPlan,
): AnswerEnvelope & { request_id: string } {
  return {
    request_id: requestIdValue,
    status,
    answer,
    mode: "deterministic",
    intent: plan?.intent ?? "metric",
    interpretation: plan?.interpretation ?? "",
    metric_id: plan?.metric_ids[0] ?? null,
    metric_label: plan ? (metricById.get(plan.metric_ids[0])?.label ?? null) : null,
    facts: emptyFacts(freshness),
    citations: plan?.metric_ids[0] && metricById.has(plan.metric_ids[0])
      ? citationsFor(metricById.get(plan.metric_ids[0])!)
      : [],
    closest_match_disclosure: plan?.closest_match_disclosure,
    fallback_used: false,
    freshness,
  };
}

function mergeYearFilters(base: Filters, side: Filters): Filters {
  const merged: Filters = { ...base, ...side };
  if (merged.year_from === undefined && base.year_from !== undefined) merged.year_from = base.year_from;
  if (merged.year_to === undefined && base.year_to !== undefined) merged.year_to = base.year_to;
  return merged;
}

async function resolveWithFallback(
  message: string,
  recent: Awaited<ReturnType<typeof getRecentTurns>>,
): Promise<{ plan: ResolvedPlan; providerFallbackUsed: boolean; compositionProvider?: "groq" | "gemini" }> {
  const deterministic = resolveQuestion(message, recent);
  if (deterministic.intent === "refuse" || deterministic.confidence >= 0.82) {
    return { plan: deterministic, providerFallbackUsed: false };
  }
  const llm = await planWithLlm(
    message,
    recent.map((turn) => ({
      metric_id: turn.metric_id,
      filters: turn.filters as Record<string, unknown>,
      interpretation: turn.interpretation,
    })),
  );
  if (!llm) return { plan: deterministic, providerFallbackUsed: false };

  const candidate = planFromLlm(llm.plan, llm.provider);
  const checked = validateFilters(candidate.filters);
  if (checked.rejected.length > 0 || !candidate.metric_ids.every((id) => metricById.has(id))) {
    return { plan: deterministic, providerFallbackUsed: false };
  }
  if (candidate.comparison) {
    const sidesValid = candidate.comparison.sides.every(
      (side) => validateFilters(side.filters as Filters).rejected.length === 0,
    );
    if (!sidesValid) return { plan: deterministic, providerFallbackUsed: false };
  }
  return {
    plan: candidate,
    providerFallbackUsed: llm.provider === "gemini" && env.LLM_MODE !== "gemini",
  };
}

export async function answerChat(
  input: ChatRequest,
  clientIp: string,
  requestIdValue = requestId(),
): Promise<ChatResult> {
  const startedAt = Date.now();
  let finalStatus: AnswerEnvelope["status"] = "INTERNAL";
  let finalMetricId: string | null = null;
  let finalProvider: string | undefined;
  let finalFallback = false;
  let finalCached = false;
  let finalRowCount = 0;
  let finalQueryId: string | null = null;
  let finalErrorCode: string | null = null;

  const freshness = await getFreshness();

  if (!env.PUBLIC_CHAT_ENABLED) {
    const body = envelopeBase(
      requestIdValue,
      "MAINTENANCE",
      "The assistant is temporarily unavailable while the public index is being refreshed. Published reporting pages remain available.",
      freshness,
    );
    log("warn", "chat_blocked", { request_id: requestIdValue, reason: "kill_switch", status: "MAINTENANCE" });
    return { status: 503, body };
  }

  const missing = missingForChat();
  if (missing.length > 0) {
    const body = envelopeBase(
      requestIdValue,
      "DATA_UNAVAILABLE",
      "The assistant is not connected to the published reporting layer yet. Published reporting pages remain available.",
      freshness,
    );
    body.degraded = `Missing configuration: ${missing.join(", ")}`;
    body.answer = "Live data is not connected yet. Published reporting pages remain available.";
    log("warn", "chat_unconfigured", {
      request_id: requestIdValue,
      status: "DATA_UNAVAILABLE",
      missing_count: missing.length,
    });
    return { status: 200, body };
  }

  const [hour, day] = await Promise.all([
    enforceLimit(clientIp, "chat-hour"),
    enforceLimit(clientIp, "chat-day"),
  ]);
  if (!hour.success || !day.success) {
    const body = envelopeBase(
      requestIdValue,
      "RATE_LIMITED",
      "You’ve reached the public assistant’s hourly or daily limit. Please try again later; published reporting pages remain available.",
      freshness,
    );
    body.degraded = !hour.success ? "hourly_limit" : "daily_limit";
    log("info", "chat_rate_limited", {
      request_id: requestIdValue,
      status: "RATE_LIMITED",
      scope: body.degraded,
    });
    return { status: 429, body };
  }

  const sessionId = input.session_id ?? requestIdValue;
  const recent = await getRecentTurns(sessionId);
  const cacheKey = `chat:v2:${canonicalHash({
    message: input.message.toLowerCase(),
    recent: recent.map((turn) => turn.metric_id),
  })}`;
  const cached = await cache.get<AnswerEnvelope>(cacheKey);
  finalCached = Boolean(cached);
  if (cached) {
    const body = { ...cached, request_id: requestIdValue, cached: true } as AnswerEnvelope & {
      request_id: string;
      cached: boolean;
    };
    finalStatus = cached.status;
    finalMetricId = cached.metric_id;
    finalProvider = cached.provider;
    log("info", "chat_complete", {
      request_id: requestIdValue,
      route: "/api/chat",
      status: finalStatus,
      metric_id: finalMetricId,
      provider: finalProvider,
      fallback_used: false,
      cached: true,
      row_count: cached.facts.rows.length,
      latency_ms: Date.now() - startedAt,
      snowflake_query_id: null,
      error_code: null,
    });
    return { status: 200, body };
  }

  const { plan, providerFallbackUsed } = await resolveWithFallback(input.message, recent);
  finalMetricId = plan.metric_ids[0] ?? null;
  finalFallback = providerFallbackUsed;

  if (plan.intent === "refuse") {
    finalStatus = "refused";
    const body = envelopeBase(requestIdValue, "refused", plan.refusal_reason ?? "", freshness, plan);
    log("info", "chat_complete", {
      request_id: requestIdValue,
      route: "/api/chat",
      status: finalStatus,
      metric_id: null,
      provider: plan.provider,
      fallback_used: providerFallbackUsed,
      cached: false,
      row_count: 0,
      latency_ms: Date.now() - startedAt,
      snowflake_query_id: null,
      error_code: null,
    });
    return { status: 200, body };
  }

  if (plan.intent === "clarify") {
    finalStatus = "clarify";
    const body = envelopeBase(
      requestIdValue,
      "clarify",
      plan.clarification ?? "I need a little more detail to answer that question.",
      freshness,
      plan,
    );
    log("info", "chat_complete", {
      request_id: requestIdValue,
      route: "/api/chat",
      status: finalStatus,
      metric_id: null,
      provider: plan.provider,
      fallback_used: providerFallbackUsed,
      cached: false,
      row_count: 0,
      latency_ms: Date.now() - startedAt,
      snowflake_query_id: null,
      error_code: null,
    });
    return { status: 200, body };
  }

  const metricId = plan.metric_ids[0];
  const metric = metricId ? metricById.get(metricId) : undefined;
  if (!metric || !metricId) {
    finalStatus = "unsupported";
    const body = envelopeBase(
      requestIdValue,
      "unsupported",
      "I don’t have a defined metric for that yet. I can answer questions about topics, citations, sources, institutions, authors, venues, access and freshness.",
      freshness,
      plan,
    );
    log("info", "chat_complete", {
      request_id: requestIdValue,
      route: "/api/chat",
      status: finalStatus,
      metric_id: null,
      provider: plan.provider,
      fallback_used: providerFallbackUsed,
      cached: false,
      row_count: 0,
      latency_ms: Date.now() - startedAt,
      snowflake_query_id: null,
      error_code: null,
    });
    return { status: 200, body };
  }

  const checked = validateFilters(plan.filters);
  if (checked.rejected.length > 0) {
    finalStatus = "unsupported";
    const body = envelopeBase(
      requestIdValue,
      "unsupported",
      `I can’t use the filters “${checked.rejected.join(", ")}” for this metric. Try a supported category, source or year.`,
      freshness,
      plan,
    );
    return { status: 200, body };
  }

  if (metricId === "M17" && typeof checked.filters.search_term !== "string") {
    finalStatus = "clarify";
    const body = envelopeBase(
      requestIdValue,
      "clarify",
      "Please tell me which title words to search for.",
      freshness,
      plan,
    );
    return { status: 200, body };
  }

  try {
    let envelope: AnswerEnvelope;

    if (plan.intent === "compare" && plan.comparison) {
      const sideMetric = metricById.get(plan.comparison.metric_id) ?? metric;
      const sides: SideResult[] = [];
      for (const side of plan.comparison.sides) {
        try {
          const sideChecked = validateFilters(mergeYearFilters(checked.filters, side.filters as Filters));
          const compiled = compileMetric(sideMetric.id, sideChecked.filters);
          const result = await querySnowflake(compiled.sql, compiled.bindings);
          finalRowCount += result.rowCount;
          if (result.queryId) finalQueryId = result.queryId;
          sides.push({ side, rows: result.rows });
        } catch (error) {
          logError("metric_query_failed", error, {
            request_id: requestIdValue,
            metric_id: sideMetric.id,
            phase: "comparison_side",
            side: side.label,
          });
          throw error;
        }
      }
      envelope = buildComparisonAnswer(
        plan,
        sideMetric,
        sides,
        freshness,
        plan.provider,
        providerFallbackUsed,
      );
    } else {
      try {
        const compiled = compileMetric(metricId, checked.filters);
        const result = await querySnowflake(compiled.sql, compiled.bindings);
        finalRowCount = result.rowCount;
        finalQueryId = result.queryId;
        envelope = buildAnswer({
          plan,
          metric,
          rows: result.rows,
          freshness,
          provider: plan.provider,
          fallbackUsed: providerFallbackUsed,
        });
      } catch (error) {
        logError("metric_query_failed", error, {
          request_id: requestIdValue,
          metric_id: metricId,
          phase: "single",
        });
        throw error;
      }
    }

    if (envelope.status === "answered" && env.LLM_MODE !== "off") {
      const composed = await composeWithLlm({
        metricLabel: envelope.metric_label ?? metric.label,
        intent: envelope.intent,
        facts: {
          values: envelope.facts.values,
          rows: envelope.facts.rows.slice(0, 5),
          denominator: envelope.facts.denominators.join("; "),
          as_of: envelope.facts.as_of,
          snapshot_date: envelope.facts.snapshot_date,
        },
        caveats: envelope.facts.caveats,
      });
      if (composed) {
        envelope.answer = composed.text;
        envelope.mode = "composed";
        envelope.provider = composed.provider;
        finalProvider = composed.provider;
        finalFallback =
          providerFallbackUsed ||
          (composed.provider === "gemini" && env.LLM_MODE !== "gemini");
      } else if (plan.provider) {
        envelope.degraded = "Answer composition unavailable; showing deterministic facts.";
        finalFallback = true;
      }
    }

    finalStatus = envelope.status;
    finalProvider = envelope.provider ?? finalProvider;
    await recordTurn(sessionId, {
      metric_id: envelope.metric_id ?? metricId,
      filters: checked.filters,
      interpretation: envelope.interpretation,
    });

    const body = { ...envelope, request_id: requestIdValue } as AnswerEnvelope & {
      request_id: string;
    };
    if (!envelope.degraded) await cache.set(cacheKey, envelope, CACHE_TTL_SECONDS);

    log("info", "chat_complete", {
      request_id: requestIdValue,
      route: "/api/chat",
      status: finalStatus,
      metric_id: finalMetricId,
      provider: finalProvider,
      fallback_used: finalFallback,
      cached: finalCached,
      row_count: finalRowCount,
      latency_ms: Date.now() - startedAt,
      snowflake_query_id: finalQueryId,
      error_code: finalErrorCode,
    });
    return { status: 200, body };
  } catch (error) {
    const isSnowflake = error instanceof SnowflakeError;
    finalErrorCode = isSnowflake ? error.code : "INTERNAL";
    finalStatus = "DATA_UNAVAILABLE";
    const body = envelopeBase(
      requestIdValue,
      "DATA_UNAVAILABLE",
      "Live reporting data is temporarily unavailable. Published reporting pages remain available; please try again shortly.",
      freshness,
      plan,
    );
    body.degraded = finalErrorCode === "SNOWFLAKE_TIMEOUT" ? "snowflake_timeout" : "snowflake_error";
    logError("chat_complete", error, {
      request_id: requestIdValue,
      route: "/api/chat",
      status: finalStatus,
      metric_id: finalMetricId,
      provider: finalProvider,
      fallback_used: finalFallback,
      cached: finalCached,
      row_count: finalRowCount,
      latency_ms: Date.now() - startedAt,
      snowflake_query_id: finalQueryId,
      error_code: finalErrorCode,
    });
    return { status: 200, body };
  }
}
