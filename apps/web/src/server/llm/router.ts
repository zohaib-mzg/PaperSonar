import { cache } from "@/server/cache";
import { env } from "@/server/env";
import { LlmHttpError, isRetryableLlmError } from "@/server/llm/errors";
import { geminiProvider } from "@/server/llm/gemini";
import { groqProvider } from "@/server/llm/groq";
import type { ComposeInput, LlmProvider, PlannerInput } from "@/server/llm/types";
import { validateComposition, validatePlan } from "@/server/llm/validate";
import { log, logError } from "@/server/logger";
import { collectCategoryAliases, metrics, publicCategoryList } from "@/server/metrics/catalogue";

const FAILURE_THRESHOLD = 3;
const COOLDOWN_MS = 60_000;
const LLM_DEADLINE_MS = 20_000;
const ATTEMPT_TIMEOUT_MS = 7_000;
const MAX_RETRY_AFTER_MS = 4_000;
const MAX_RECENT_TURNS = 3;
const MAX_RELEVANT_METRICS = 8;

type Breaker = { failures: number; openUntil: number };

const STOP_WORDS = new Set([
  "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "is", "are",
  "was", "were", "what", "which", "how", "many", "much", "does", "do", "did",
  "with", "by", "from", "at", "as", "that", "this", "these", "those", "be",
  "been", "has", "have", "had", "can", "could", "should", "would", "will",
  "show", "me", "please", "tell", "about", "between", "compare", "vs",
  "versus", "last", "year", "years", "latest", "current", "published", "data",
  "research", "outputs", "output", "top", "most",
]);

function configuredProviders(): LlmProvider[] {
  if (env.LLM_MODE === "off") return [];
  const result: LlmProvider[] = [];
  if (
    (env.LLM_MODE === "auto" || env.LLM_MODE === "groq") &&
    env.GROQ_API_KEY &&
    env.GROQ_MODEL
  ) {
    result.push(groqProvider);
  }
  if (
    (env.LLM_MODE === "auto" || env.LLM_MODE === "gemini") &&
    env.GEMINI_API_KEY &&
    env.GEMINI_MODEL
  ) {
    result.push(geminiProvider);
  }
  return result;
}

async function breakerOpen(name: string): Promise<boolean> {
  const breaker = await cache.get<Breaker>(`llm:breaker:${name}`);
  return Boolean(breaker && breaker.failures >= FAILURE_THRESHOLD && breaker.openUntil > Date.now());
}

async function recordFailure(name: string): Promise<void> {
  const breaker = (await cache.get<Breaker>(`llm:breaker:${name}`)) ?? {
    failures: 0,
    openUntil: 0,
  };
  const failures = breaker.failures + 1;
  await cache.set(
    `llm:breaker:${name}`,
    {
      failures,
      openUntil: failures >= FAILURE_THRESHOLD ? Date.now() + COOLDOWN_MS : 0,
    } satisfies Breaker,
    120,
  );
}

async function recordSuccess(name: string): Promise<void> {
  await cache.set(`llm:breaker:${name}`, { failures: 0, openUntil: 0 } satisfies Breaker, 120);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function queryTokens(message: string): string[] {
  return Array.from(
    new Set(
      (message.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter(
        (token) => token.length > 2 && !STOP_WORDS.has(token),
      ),
    ),
  );
}

function selectRelevantMetrics(message: string) {
  const tokens = queryTokens(message);
  if (tokens.length === 0) return metrics;

  const scored = metrics
    .map((metric) => {
      const id = metric.id.toLowerCase();
      const label = metric.label.toLowerCase();
      const description = metric.description.toLowerCase();
      const dimensions = metric.dimensions.join(" ").toLowerCase();
      let score = 0;
      for (const token of tokens) {
        if (id.includes(token)) score += 5;
        if (label.includes(token)) score += 3;
        if (description.includes(token)) score += 1;
        if (dimensions.includes(token)) score += 1;
      }
      return { metric, score };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score);

  return scored.length > 0
    ? scored.slice(0, MAX_RELEVANT_METRICS).map((item) => item.metric)
    : metrics;
}

function retryDelayMs(error: unknown): number {
  if (
    error instanceof LlmHttpError &&
    error.status === 429 &&
    error.retryAfterMs !== undefined
  ) {
    return Math.min(MAX_RETRY_AFTER_MS, Math.max(0, error.retryAfterMs));
  }
  return 500 + Math.floor(Math.random() * 1001);
}

function timeoutError(): Error {
  const error = new Error("llm_attempt_timeout");
  error.name = "TimeoutError";
  return error;
}

async function withAttemptTimeout<T>(
  operation: (signal: AbortSignal) => Promise<T>,
  deadline: number,
): Promise<T> {
  const remaining = deadline - Date.now();
  if (remaining <= 0) throw timeoutError();

  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    Math.min(ATTEMPT_TIMEOUT_MS, remaining),
  );
  try {
    return await operation(controller.signal);
  } finally {
    clearTimeout(timer);
  }
}

async function withFallback<T>(
  operation: (provider: LlmProvider, signal: AbortSignal) => Promise<T>,
  validate: (value: T) => boolean,
): Promise<{ provider: LlmProvider["name"]; value: T } | null> {
  const providers = configuredProviders();
  if (providers.length === 0) return null;

  const deadline = Date.now() + LLM_DEADLINE_MS;
  let attemptedFallback = false;

  for (const provider of providers) {
    if (Date.now() >= deadline) break;
    if (await breakerOpen(provider.name)) {
      attemptedFallback = true;
      continue;
    }

    let attempted = false;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      if (Date.now() >= deadline) break;
      attempted = true;
      const startedAt = Date.now();
      try {
        const value = await withAttemptTimeout(
          (signal) => operation(provider, signal),
          deadline,
        );
        if (!validate(value)) throw new Error("invalid_llm_output");
        await recordSuccess(provider.name);
        log("info", "llm_success", {
          provider: provider.name,
          fallback_used: attemptedFallback,
          attempt: attempt + 1,
          latency_ms: Date.now() - startedAt,
        });
        return { provider: provider.name, value };
      } catch (error) {
        const retryable = isRetryableLlmError(error);
        const canRetry = retryable && attempt === 0 && Date.now() < deadline;
        logError("llm_failure", error, {
          provider: provider.name,
          fallback_used: attemptedFallback,
          attempt: attempt + 1,
          will_retry: canRetry,
          latency_ms: Date.now() - startedAt,
        });
        if (canRetry) {
          const delay = retryDelayMs(error);
          if (Date.now() + delay < deadline) {
            await sleep(delay);
            continue;
          }
        }
        break;
      }
    }

    if (attempted) await recordFailure(provider.name);
    attemptedFallback = true;
  }

  return null;
}

export async function planWithLlm(
  message: string,
  recent: PlannerInput["recent"],
): Promise<{ provider: "groq" | "gemini"; plan: NonNullable<ReturnType<typeof validatePlan>> } | null> {
  const input: PlannerInput = {
    message,
    recent: recent.slice(0, MAX_RECENT_TURNS),
    metrics: selectRelevantMetrics(message).map((metric) => ({
      id: metric.id,
      label: metric.label,
      description: metric.description,
      dimensions: metric.dimensions,
    })),
    categories: publicCategoryList().map((category) => ({
      ...category,
      aliases: collectCategoryAliases(category.key),
    })),
  };
  const result = await withFallback(
    (provider, signal) => provider.plan(input, { signal }),
    (value) => validatePlan(value) !== null,
  );
  if (!result) return null;
  const plan = validatePlan(result.value);
  return plan ? { provider: result.provider, plan } : null;
}

export async function composeWithLlm(
  input: ComposeInput,
): Promise<{ provider: "groq" | "gemini"; text: string } | null> {
  const result = await withFallback(
    (provider, signal) => provider.compose(input, { signal }),
    (value) => typeof value === "string" && validateComposition(value, input.facts),
  );
  return result ? { provider: result.provider, text: result.value.trim() } : null;
}
