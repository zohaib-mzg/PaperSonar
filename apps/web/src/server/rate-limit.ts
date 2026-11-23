import { createHmac } from "node:crypto";
import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";
import { env } from "@/server/env";

export type LimitResult = {
  success: boolean;
  limit: number;
  remaining: number;
  reset: number;
};

export type LimitKind = "chat-hour" | "chat-day" | "feedback";

const redis =
  env.UPSTASH_REDIS_REST_URL && env.UPSTASH_REDIS_REST_TOKEN
    ? new Redis({
        url: env.UPSTASH_REDIS_REST_URL,
        token: env.UPSTASH_REDIS_REST_TOKEN,
      })
    : null;

const limiters = redis
  ? {
      "chat-hour": new Ratelimit({
        redis,
        limiter: Ratelimit.slidingWindow(env.RATE_LIMIT_PER_HOUR, "1 h"),
        prefix: "ratelimit:chat-hour",
      }),
      "chat-day": new Ratelimit({
        redis,
        limiter: Ratelimit.slidingWindow(env.RATE_LIMIT_PER_DAY, "1 d"),
        prefix: "ratelimit:chat-day",
      }),
      feedback: new Ratelimit({
        redis,
        limiter: Ratelimit.slidingWindow(5, "1 m"),
        prefix: "ratelimit:feedback",
      }),
    }
  : null;

const memoryBuckets = new Map<string, number[]>();

function memoryLimit(identifier: string, kind: LimitKind, limit: number, windowMs: number): LimitResult {
  const now = Date.now();
  const key = `${kind}:${identifier}`;
  const timestamps = (memoryBuckets.get(key) ?? []).filter((time) => now - time < windowMs);
  const success = timestamps.length < limit;
  if (success) timestamps.push(now);
  memoryBuckets.set(key, timestamps);
  const reset = timestamps.length > 0 ? timestamps[0] + windowMs : now + windowMs;
  return { success, limit, remaining: Math.max(0, limit - timestamps.length), reset };
}

export function hashIdentifier(raw: string, salt = env.IP_HASH_SALT): string {
  if (!salt) return "dev-no-salt";
  return createHmac("sha256", salt).update(raw).digest("hex").slice(0, 32);
}

export async function enforceLimit(
  rawIdentifier: string,
  kind: LimitKind,
): Promise<LimitResult> {
  const identifier = hashIdentifier(rawIdentifier);

  if (!limiters) {
    if (process.env.NODE_ENV === "production") {
      return { success: false, limit: 0, remaining: 0, reset: Date.now() };
    }
    if (kind === "chat-hour") return memoryLimit(identifier, kind, env.RATE_LIMIT_PER_HOUR, 3_600_000);
    if (kind === "chat-day") return memoryLimit(identifier, kind, env.RATE_LIMIT_PER_DAY, 86_400_000);
    return memoryLimit(identifier, kind, 5, 60_000);
  }

  const result = await limiters[kind].limit(identifier);
  return {
    success: result.success,
    limit: result.limit,
    remaining: result.remaining,
    reset: result.reset,
  };
}
