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

function errorFields(error: unknown, depth = 0): Record<string, unknown> {
  if (error === null || error === undefined) return { error_message: String(error) };
  if (typeof error === "string") return { error_message: error };
  if (typeof error !== "object") return { error_message: String(error) };

  const err = error as Record<string, unknown>;
  const fields: Record<string, unknown> = {};

  if (typeof err.name === "string") fields.error_name = err.name;
  if (typeof err.message === "string") fields.error_message = err.message;
  if (typeof err.code === "string" || typeof err.code === "number") fields.error_code = err.code;
  if (typeof err.status === "number") fields.error_status = err.status;
  if (typeof err.sqlState === "string") fields.error_sql_state = err.sqlState;
  if (typeof err.stack === "string") fields.error_stack = err.stack.slice(0, 6000);

  if (err.cause !== undefined && depth < 3) {
    const cause = errorFields(err.cause, depth + 1);
    fields.error_cause_name = cause.error_name;
    fields.error_cause_message = cause.error_message;
    fields.error_cause_code = cause.error_code;
    fields.error_cause_status = cause.error_status;
    fields.error_cause_sql_state = cause.error_sql_state;
  }

  return Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined));
}

export function logError(event: string, error: unknown, fields: Record<string, unknown> = {}): void {
  log("error", event, { ...fields, ...errorFields(error) });
}

export function requestId(prefix = "req"): string {
  const random = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
  return `${prefix}_${random}`;
}
