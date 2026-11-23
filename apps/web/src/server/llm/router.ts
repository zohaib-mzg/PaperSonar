import { cache } from "@/server/cache";
import { env } from "@/server/env";
import { geminiProvider } from "@/server/llm/gemini";
import { groqProvider } from "@/server/llm/groq";
import type { ComposeInput, LlmProvider, PlannerInput } from "@/server/llm/types";
import { validateComposition, validatePlan } from "@/server/llm/validate";
import { log } from "@/server/logger";
import { collectCategoryAliases, metrics, publicCategoryList } from "@/server/metrics/catalogue";

const FAILURE_THRESHOLD = 3;
const COOLDOWN_MS = 60_000;

type Breaker = { failures: number; openUntil: number };

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

async function withFallback<T>(
  operation: (provider: LlmProvider) => Promise<T>,
  validate: (value: T) => boolean,
): Promise<{ provider: LlmProvider["name"]; value: T } | null> {
  const providers = configuredProviders();
  if (providers.length === 0) return null;

  let attemptedFallback = false;
  for (const provider of providers) {
    if (await breakerOpen(provider.name)) continue;
    try {
      const value = await operation(provider);
      if (!validate(value)) throw new Error("invalid_llm_output");
      await recordSuccess(provider.name);
      log("info", "llm_success", { provider: provider.name, fallback_used: attemptedFallback });
      return { provider: provider.name, value };
    } catch {
      await recordFailure(provider.name);
      log("warn", "llm_failure", {
        provider: provider.name,
        fallback_used: attemptedFallback,
      });
      attemptedFallback = true;
    }
  }
  return null;
}

export async function planWithLlm(
  message: string,
  recent: PlannerInput["recent"],
): Promise<{ provider: "groq" | "gemini"; plan: NonNullable<ReturnType<typeof validatePlan>> } | null> {
  const input: PlannerInput = {
    message,
    recent,
    metrics: metrics.map((metric) => ({
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
    (provider) => provider.plan(input),
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
    (provider) => provider.compose(input),
    (value) => typeof value === "string" && validateComposition(value, input.facts),
  );
  return result ? { provider: result.provider, text: result.value.trim() } : null;
}
