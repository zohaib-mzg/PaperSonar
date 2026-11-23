import { z } from "zod";

const boolFromString = z
  .enum(["true", "false"])
  .default("false")
  .transform((value) => value === "true");

const schema = z.object({
  PUBLIC_APP_ORIGIN: z.string().min(1).default("https://paper-sonar.vercel.app"),
  PUBLIC_CHAT_ENABLED: boolFromString,
  LLM_MODE: z.enum(["auto", "groq", "gemini", "off"]).default("auto"),
  RATE_LIMIT_PER_HOUR: z.coerce.number().int().positive().default(20),
  RATE_LIMIT_PER_DAY: z.coerce.number().int().positive().default(50),
  SNOWFLAKE_ACCOUNT_URL: z.string().min(1).optional(),
  SNOWFLAKE_ACCOUNT: z.string().min(1).optional(),
  SNOWFLAKE_PUBLIC_USER: z.string().min(1).optional(),
  SNOWFLAKE_PUBLIC_ROLE: z.string().min(1).optional(),
  SNOWFLAKE_PUBLIC_WAREHOUSE: z.string().min(1).optional(),
  SNOWFLAKE_DATABASE: z.string().min(1).default("PAPERSONAR"),
  SNOWFLAKE_SCHEMA: z.string().min(1).default("PROJECT_REPORTING"),
  SNOWFLAKE_PUBLIC_PRIVATE_KEY: z.string().min(1).optional(),
  SNOWFLAKE_PUBLIC_PRIVATE_KEY_PASSPHRASE: z.string().min(1).optional(),
  GROQ_API_KEY: z.string().min(1).optional(),
  GROQ_MODEL: z.string().min(1).optional(),
  GEMINI_API_KEY: z.string().min(1).optional(),
  GEMINI_MODEL: z.string().min(1).optional(),
  UPSTASH_REDIS_REST_URL: z.string().min(1).optional(),
  UPSTASH_REDIS_REST_TOKEN: z.string().min(1).optional(),
  IP_HASH_SALT: z.string().min(16).optional(),
});

const parsed = schema.safeParse(process.env);

export const env = parsed.success ? parsed.data : schema.parse({});

export type Env = typeof env;

export function missingForChat(config: Env = env): string[] {
  const missing: string[] = [];

  if (!config.SNOWFLAKE_ACCOUNT_URL) missing.push("SNOWFLAKE_ACCOUNT_URL");
  if (!config.SNOWFLAKE_PUBLIC_USER) missing.push("SNOWFLAKE_PUBLIC_USER");
  if (!config.SNOWFLAKE_PUBLIC_ROLE) missing.push("SNOWFLAKE_PUBLIC_ROLE");
  if (!config.SNOWFLAKE_PUBLIC_WAREHOUSE) missing.push("SNOWFLAKE_PUBLIC_WAREHOUSE");
  if (!config.SNOWFLAKE_PUBLIC_PRIVATE_KEY) missing.push("SNOWFLAKE_PUBLIC_PRIVATE_KEY");
  if (process.env.NODE_ENV === "production") {
    if (!config.UPSTASH_REDIS_REST_URL) missing.push("UPSTASH_REDIS_REST_URL");
    if (!config.UPSTASH_REDIS_REST_TOKEN) missing.push("UPSTASH_REDIS_REST_TOKEN");
  }
  if (!config.IP_HASH_SALT) missing.push("IP_HASH_SALT");

  if (config.LLM_MODE === "auto" || config.LLM_MODE === "groq") {
    if (!config.GROQ_API_KEY) missing.push("GROQ_API_KEY");
    if (!config.GROQ_MODEL) missing.push("GROQ_MODEL");
  }
  if (config.LLM_MODE === "gemini") {
    if (!config.GEMINI_API_KEY) missing.push("GEMINI_API_KEY");
    if (!config.GEMINI_MODEL) missing.push("GEMINI_MODEL");
  }

  return missing;
}

export function providerStatus(config: Env = env) {
  return {
    groq: Boolean(config.GROQ_API_KEY && config.GROQ_MODEL)
      ? ("configured" as const)
      : ("missing" as const),
    gemini: Boolean(config.GEMINI_API_KEY && config.GEMINI_MODEL)
      ? ("configured" as const)
      : ("missing" as const),
  };
}

export const APP_VERSION = "2026-11-23";
