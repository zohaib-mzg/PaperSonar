import { NextResponse } from "next/server";
import { APP_VERSION, env, missingForChat, providerStatus } from "@/server/env";
import { cache } from "@/server/cache";
import { logError } from "@/server/logger";
import { querySnowflake, SnowflakeError } from "@/server/snowflake/client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type HealthCheck = {
  status: "ok" | "degraded" | "not_ready";
  version: string;
  checks: {
    env: "ok" | "not_ready";
    snowflake: "ok" | "error" | "missing";
    redis: "ok" | "missing" | "error";
    groq: "configured" | "missing";
    gemini: "configured" | "missing";
    chat_enabled: boolean;
  };
  latency_ms: number;
};

export async function GET() {
  const startedAt = Date.now();
  const missing = missingForChat();
  const providers = providerStatus();
  const redis = await cache.ping();

  const snowflakeRequired = [
    "SNOWFLAKE_ACCOUNT_URL",
    "SNOWFLAKE_PUBLIC_USER",
    "SNOWFLAKE_PUBLIC_ROLE",
    "SNOWFLAKE_PUBLIC_WAREHOUSE",
    "SNOWFLAKE_PUBLIC_PRIVATE_KEY",
  ].some((key) => missing.includes(key));

  let snowflake: HealthCheck["checks"]["snowflake"] = "missing";
  if (!snowflakeRequired) {
    let cached: HealthCheck["checks"]["snowflake"] | null = null;
    try {
      cached = await cache.get<HealthCheck["checks"]["snowflake"]>("health:snowflake");
    } catch (error) {
      logError("health.cache_failed", error, { operation: "get" });
    }
    if (cached) {
      snowflake = cached;
    } else {
      try {
        await querySnowflake("SELECT 1 AS OK");
        snowflake = "ok";
      } catch (error) {
        logError("health.snowflake_failed", error, { check: "SELECT 1 AS OK" });
        snowflake = error instanceof SnowflakeError && error.code === "NOT_CONFIGURED"
          ? "missing"
          : "error";
      }
      try {
        await cache.set("health:snowflake", snowflake, 60);
      } catch (error) {
        logError("health.cache_failed", error, { operation: "set" });
      }
    }
  }

  const hardFailure =
    missing.length > 0 || snowflake !== "ok" || redis === "missing" || redis === "error";
  const optionalProviderMissing =
    (env.LLM_MODE === "auto" && providers.gemini === "missing") ||
    (env.LLM_MODE === "groq" && providers.gemini === "missing");

  const status: HealthCheck["status"] = hardFailure
    ? "not_ready"
    : optionalProviderMissing || !env.PUBLIC_CHAT_ENABLED
      ? "degraded"
      : "ok";

  const body: HealthCheck = {
    status,
    version: APP_VERSION,
    checks: {
      env: missing.length === 0 ? "ok" : "not_ready",
      snowflake,
      redis,
      groq: providers.groq,
      gemini: providers.gemini,
      chat_enabled: env.PUBLIC_CHAT_ENABLED,
    },
    latency_ms: Date.now() - startedAt,
  };

  return NextResponse.json(body, {
    status: status === "not_ready" ? 503 : 200,
    headers: { "Cache-Control": "no-store" },
  });
}
