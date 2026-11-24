import { NextResponse } from "next/server";
import { cache } from "@/server/cache";
import { missingForChat } from "@/server/env";
import { logError } from "@/server/logger";
import { compileMetric } from "@/server/metrics/compiler";
import { querySnowflake, SnowflakeError } from "@/server/snowflake/client";
import type { SnowflakeRow } from "@/server/snowflake/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CACHE_KEY = "data-status:v1";
const CACHE_TTL_SECONDS = 300;

type DataStatusRow = {
  source_name: string | null;
  entity_name: string | null;
  batch_id: string | null;
  published_at: string | null;
  window_start: string | null;
  window_end: string | null;
  is_capped: boolean | null;
};

function asText(row: SnowflakeRow, key: string): string | null {
  const value = row[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function asBoolean(row: SnowflakeRow, key: string): boolean | null {
  const value = row[key];
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return null;
}

function publicRow(row: SnowflakeRow): DataStatusRow {
  return {
    source_name: asText(row, "SOURCE_NAME"),
    entity_name: asText(row, "ENTITY_NAME"),
    batch_id: asText(row, "BATCH_ID"),
    published_at: asText(row, "PUBLISHED_AT"),
    window_start: asText(row, "WINDOW_START"),
    window_end: asText(row, "WINDOW_END"),
    is_capped: asBoolean(row, "IS_CAPPED"),
  };
}

export async function GET() {
  const missingSnowflakeConfig = missingForChat().filter((key) => key.startsWith("SNOWFLAKE_"));
  if (missingSnowflakeConfig.length > 0) {
    return NextResponse.json(
      { status: "not_ready", rows: [], reason: "DATA_SOURCE_NOT_CONFIGURED" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  let cached: DataStatusRow[] | null = null;
  try {
    cached = await cache.get<DataStatusRow[]>(CACHE_KEY);
  } catch (error) {
    logError("data_status_cache_failed", error, { operation: "get" });
  }
  if (cached) {
    return NextResponse.json(
      { status: "ok", rows: cached, cached: true },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  try {
    const query = compileMetric("M18", {});
    const result = await querySnowflake(query.sql, query.bindings);
    const rows = result.rows.map(publicRow);
    try {
      await cache.set(CACHE_KEY, rows, CACHE_TTL_SECONDS);
    } catch (error) {
      logError("data_status_cache_failed", error, { operation: "set" });
    }
    return NextResponse.json(
      { status: "ok", rows, cached: false },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    logError("data_status_failed", error, { metric_id: "M18" });
    const reason =
      error instanceof SnowflakeError && error.code === "SNOWFLAKE_TIMEOUT"
        ? "DATA_SOURCE_TIMEOUT"
        : "DATA_SOURCE_ERROR";
    return NextResponse.json(
      { status: "error", rows: [], reason },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
