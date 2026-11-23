const REDACTED_KEYS = new Set([
  "authorization",
  "cookie",
  "ip",
  "session_id",
  "message",
  "question",
  "answer",
  "query",
  "sql",
  "token",
  "api_key",
  "private_key",
  "password",
  "prompt",
  "completion",
]);

function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        REDACTED_KEYS.has(key.toLowerCase()) ? "[REDACTED]" : redact(item),
      ]),
    );
  }
  return value;
}

export function log(level: "info" | "warn" | "error", event: string, fields: Record<string, unknown> = {}) {
  const line = {
    level,
    event,
    timestamp: new Date().toISOString(),
    ...(redact(fields) as Record<string, unknown>),
  };
  const output = JSON.stringify(line);
  if (level === "error") console.error(output);
  else if (level === "warn") console.warn(output);
  else console.log(output);
}

export function requestId(prefix = "req"): string {
  const random = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
  return `${prefix}_${random}`;
}
