import { env } from "@/server/env";
import { getSnowflakeJwt } from "@/server/snowflake/jwt";
import type {
  Binding,
  SnowflakeQueryResult,
  SnowflakeRow,
  SqlScalar,
} from "@/server/snowflake/types";

export class SnowflakeError extends Error {
  readonly code: "NOT_CONFIGURED" | "SNOWFLAKE_TIMEOUT" | "SNOWFLAKE_ERROR";

  constructor(code: SnowflakeError["code"], message: string, cause?: unknown) {
    super(message);
    this.name = "SnowflakeError";
    this.code = code;
    if (cause !== undefined) (this as Error & { cause?: unknown }).cause = cause;
  }
}

const MAX_ROWS = 200;
const TIMEOUT_MS = 30_000;

export type SnowflakeBinding = {
  type: "TEXT" | "FIXED" | "REAL" | "BOOLEAN" | "DATE" | "TIMESTAMP_NTZ";
  value: string | null;
};

function isTypedBinding(value: unknown): value is Binding {
  return Boolean(
    value &&
      typeof value === "object" &&
      "type" in value &&
      "value" in value,
  );
}

export function toBinding(value: unknown): SnowflakeBinding {
  if (isTypedBinding(value)) {
    if (value.value === null || value.value === undefined) {
      return { type: "TEXT", value: null };
    }
    const raw = value.value as unknown;
    if (raw instanceof Date) {
      return { type: "TIMESTAMP_NTZ", value: raw.toISOString() };
    }
    return { type: value.type, value: String(raw) };
  }

  if (value === null || value === undefined) return { type: "TEXT", value: null };
  if (value instanceof Date) return { type: "TIMESTAMP_NTZ", value: value.toISOString() };
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? { type: "FIXED", value: String(value) }
      : { type: "REAL", value: String(value) };
  }
  if (typeof value === "boolean") return { type: "BOOLEAN", value: String(value) };
  return { type: "TEXT", value: String(value) };
}

function assertReadOnly(sql: string): void {
  const first = sql.trimStart().slice(0, 12).toUpperCase();
  if (!first.startsWith("SELECT") && !first.startsWith("WITH")) {
    throw new SnowflakeError("SNOWFLAKE_ERROR", "Only read-only queries are allowed");
  }
}

function snowflakeBindings(bindings: Binding[]): Record<string, SnowflakeBinding> {
  return Object.fromEntries(
    bindings.map((binding, index) => [String(index + 1), toBinding(binding)]),
  );
}

function epochDaysToDate(text: string): string | null {
  const days = Number(text);
  if (!Number.isFinite(days) || Math.abs(days) > 100_000) return null;
  const date = new Date(days * 86_400_000);
  return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0, 10);
}

function epochSecondsToIso(text: string): string | null {
  const seconds = Number(text);
  if (!Number.isFinite(seconds) || Math.abs(seconds) > 10_000_000_000) return null;
  const date = new Date(seconds * 1000);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function coerceValue(value: unknown, columnType: string): SqlScalar {
  if (value === null || value === undefined) return null;
  const type = columnType.toUpperCase();
  const text = String(value);

  if (type === "DATE" || type.endsWith("_DATE")) {
    const iso = text.match(/^\d{4}-\d{2}-\d{2}/);
    if (iso) return iso[0];
    return epochDaysToDate(text) ?? text;
  }

  if (type.startsWith("TIMESTAMP") || type === "DATETIME") {
    const iso = text.match(/^\d{4}-\d{2}-\d{2}T/);
    if (iso) {
      const parsed = Date.parse(text);
      return Number.isFinite(parsed) ? new Date(parsed).toISOString() : text;
    }
    const epoch = epochSecondsToIso(text);
    if (epoch) return epoch;
    const parsed = Date.parse(text.includes("T") ? text : `${text.replace(" ", "T")}Z`);
    return Number.isFinite(parsed) ? new Date(parsed).toISOString() : text;
  }

  if (typeof value === "boolean" || typeof value === "number") return value;
  if (/FIXED|REAL|NUMBER|FLOAT|DECIMAL/.test(type) && text.trim() !== "") {
    const number = Number(text);
    return Number.isFinite(number) ? number : text;
  }
  if (/BOOLEAN/.test(type)) return text.toLowerCase() === "true";
  return text;
}

function mapRows(payload: Record<string, unknown>): SnowflakeRow[] {
  const meta = payload.resultSetMetaData as
    | { rowType?: Array<{ name?: string; type?: string }> }
    | undefined;
  const data = Array.isArray(payload.data) ? (payload.data as unknown[][]) : [];
  const columns = meta?.rowType ?? [];
  return data.slice(0, MAX_ROWS).map((values) =>
    Object.fromEntries(
      columns.map((column, index) => [
        column.name ?? String(index + 1),
        coerceValue(values[index], column.type ?? ""),
      ]),
    ),
  );
}

function authHeaders(): HeadersInit {
  return {
    Authorization: `Bearer ${getSnowflakeJwt()}`,
    "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
    "Content-Type": "application/json",
    Accept: "application/json",
    "User-Agent": "PaperSonar-Public/1.0",
  };
}

function endpoint(): string {
  if (!env.SNOWFLAKE_ACCOUNT_URL) {
    throw new SnowflakeError("NOT_CONFIGURED", "Snowflake is not configured");
  }
  return env.SNOWFLAKE_ACCOUNT_URL.replace(/\/$/, "");
}

async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (error) {
    if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
      throw new SnowflakeError("SNOWFLAKE_TIMEOUT", "Snowflake query timed out", error);
    }
    throw new SnowflakeError("SNOWFLAKE_ERROR", "Snowflake request failed", error);
  }
}

export async function querySnowflake(
  sql: string,
  bindings: Binding[] = [],
): Promise<SnowflakeQueryResult> {
  assertReadOnly(sql);
  const startedAt = Date.now();
  const base = endpoint();

  const response = await fetchWithTimeout(`${base}/api/v2/statements`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      statement: sql,
      timeout: 30,
      database: env.SNOWFLAKE_DATABASE,
      schema: env.SNOWFLAKE_SCHEMA,
      warehouse: env.SNOWFLAKE_PUBLIC_WAREHOUSE,
      role: env.SNOWFLAKE_PUBLIC_ROLE,
      bindings: snowflakeBindings(bindings),
      parameters: { QUERY_TAG: "public-chatbot" },
    }),
  });

  if (!response.ok && response.status !== 202) {
    let detail = "";
    let sqlState: string | undefined;
    try {
      const body = (await response.json()) as { message?: string; code?: string; sqlState?: string };
      if (body?.code) detail += ` code=${body.code}`;
      if (body?.sqlState) {
        sqlState = body.sqlState;
        detail += ` sqlState=${body.sqlState}`;
      }
      if (body?.message) detail += ` message=${String(body.message).slice(0, 200)}`;
    } catch {
      // ignore unreadable body
    }
    const error = new SnowflakeError(
      response.status === 408 || response.status === 429
        ? "SNOWFLAKE_TIMEOUT"
        : "SNOWFLAKE_ERROR",
      `Snowflake request was rejected (${response.status})${detail}`.slice(0, 500),
    );
    if (sqlState) (error as Error & { sqlState?: string }).sqlState = sqlState;
    throw error;
  }

  let payload = (await response.json()) as Record<string, unknown>;
  let queryId = typeof payload.queryId === "string" ? payload.queryId : null;

  if (response.status === 202 || payload.status === "RUNNING") {
    const handle =
      response.headers.get("x-snowflake-statement-handle") ??
      (typeof payload.statementHandle === "string" ? payload.statementHandle : null);
    if (!handle) {
      throw new SnowflakeError("SNOWFLAKE_ERROR", "Snowflake statement handle missing");
    }
    while (Date.now() - startedAt < TIMEOUT_MS) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      const poll = await fetchWithTimeout(`${base}/api/v2/statements/${encodeURIComponent(handle)}`, {
        method: "GET",
        headers: authHeaders(),
      });
      if (!poll.ok) {
        let detail = "";
        let sqlState: string | undefined;
        try {
          const body = (await poll.json()) as { message?: string; code?: string; sqlState?: string };
          if (body?.code) detail += ` code=${body.code}`;
          if (body?.sqlState) {
            sqlState = body.sqlState;
            detail += ` sqlState=${body.sqlState}`;
          }
          if (body?.message) detail += ` message=${String(body.message).slice(0, 200)}`;
        } catch {
          // ignore unreadable body
        }
        const error = new SnowflakeError(
          "SNOWFLAKE_ERROR",
          `Snowflake poll failed (${poll.status})${detail}`.slice(0, 500),
        );
        if (sqlState) (error as Error & { sqlState?: string }).sqlState = sqlState;
        throw error;
      }
      payload = (await poll.json()) as Record<string, unknown>;
      queryId = typeof payload.queryId === "string" ? payload.queryId : queryId;
      const status = String(payload.status ?? "").toUpperCase();
      if (status === "SUCCESS" || status === "SUCCEEDED" || payload.data !== undefined) break;
      if (status === "FAILED" || status === "ABORTED") {
        throw new SnowflakeError("SNOWFLAKE_ERROR", "Snowflake statement failed");
      }
    }
    if (Date.now() - startedAt >= TIMEOUT_MS) {
      throw new SnowflakeError("SNOWFLAKE_TIMEOUT", "Snowflake query timed out");
    }
  }

  const rows = mapRows(payload);
  return {
    rows,
    queryId,
    rowCount: rows.length,
    elapsedMs: Date.now() - startedAt,
  };
}
