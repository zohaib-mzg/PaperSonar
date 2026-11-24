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

  constructor(code: SnowflakeError["code"], message: string) {
    super(message);
    this.name = "SnowflakeError";
    this.code = code;
  }
}

const MAX_ROWS = 200;
const TIMEOUT_MS = 30_000;

function assertReadOnly(sql: string): void {
  const first = sql.trimStart().slice(0, 12).toUpperCase();
  if (!first.startsWith("SELECT") && !first.startsWith("WITH")) {
    throw new SnowflakeError("SNOWFLAKE_ERROR", "Only read-only queries are allowed");
  }
}

function snowflakeBindings(bindings: Binding[]): Record<string, { type: string; value: SqlScalar }> {
  return Object.fromEntries(
    bindings.map((binding, index) => [String(index + 1), binding]),
  );
}

function coerceValue(value: unknown, columnType: string): SqlScalar {
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean" || typeof value === "number") return value;
  const type = columnType.toUpperCase();
  const text = String(value);
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
      throw new SnowflakeError("SNOWFLAKE_TIMEOUT", "Snowflake query timed out");
    }
    throw new SnowflakeError("SNOWFLAKE_ERROR", "Snowflake request failed");
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
    try {
      const body = (await response.json()) as { message?: string; code?: string };
      if (body?.code) detail += ` code=${body.code}`;
      if (body?.message) detail += ` message=${String(body.message).slice(0, 200)}`;
    } catch {
      // ignore unreadable body
    }
    throw new SnowflakeError(
      response.status === 408 || response.status === 429
        ? "SNOWFLAKE_TIMEOUT"
        : "SNOWFLAKE_ERROR",
      `Snowflake request was rejected (${response.status})${detail}`.slice(0, 500),
    );
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
        try {
          const body = (await poll.json()) as { message?: string; code?: string };
          if (body?.code) detail += ` code=${body.code}`;
          if (body?.message) detail += ` message=${String(body.message).slice(0, 200)}`;
        } catch {
          // ignore unreadable body
        }
        throw new SnowflakeError(
          "SNOWFLAKE_ERROR",
          `Snowflake poll failed (${poll.status})${detail}`.slice(0, 500),
        );
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
