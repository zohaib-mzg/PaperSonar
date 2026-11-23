import { Redis } from "@upstash/redis";
import { env } from "@/server/env";

type CacheValue = { value: unknown; expiresAt: number | null };

const memory = new Map<string, CacheValue>();

const redis =
  env.UPSTASH_REDIS_REST_URL && env.UPSTASH_REDIS_REST_TOKEN
    ? new Redis({
        url: env.UPSTASH_REDIS_REST_URL,
        token: env.UPSTASH_REDIS_REST_TOKEN,
      })
    : null;

function canUseMemory(): boolean {
  return process.env.NODE_ENV !== "production";
}

export const cache = {
  async get<T>(key: string): Promise<T | null> {
    if (redis) {
      const value = await redis.get<T>(key);
      return value ?? null;
    }
    if (!canUseMemory()) return null;
    const entry = memory.get(key);
    if (!entry) return null;
    if (entry.expiresAt !== null && entry.expiresAt < Date.now()) {
      memory.delete(key);
      return null;
    }
    return entry.value as T;
  },

  async set(key: string, value: unknown, ttlSeconds: number): Promise<void> {
    if (redis) {
      await redis.set(key, value, { ex: ttlSeconds });
      return;
    }
    if (!canUseMemory()) return;
    memory.set(key, {
      value,
      expiresAt: ttlSeconds > 0 ? Date.now() + ttlSeconds * 1000 : null,
    });
  },

  async delete(key: string): Promise<void> {
    if (redis) {
      await redis.del(key);
      return;
    }
    memory.delete(key);
  },

  async ping(): Promise<"ok" | "missing" | "error"> {
    if (!redis) return canUseMemory() ? "ok" : "missing";
    try {
      const result = await redis.ping();
      return result === "PONG" ? "ok" : "error";
    } catch {
      return "error";
    }
  },
};

export function canonicalHash(value: unknown): string {
  const sorted = JSON.stringify(value, (_key, item) => {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      return Object.fromEntries(
        Object.entries(item as Record<string, unknown>).sort(([a], [b]) =>
          a.localeCompare(b),
        ),
      );
    }
    return item;
  });
  let hash = 2166136261;
  for (let index = 0; index < sorted.length; index += 1) {
    hash ^= sorted.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}
