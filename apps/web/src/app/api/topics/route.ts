import { NextResponse } from "next/server";
import {
  METRIC_VERSION,
  TAXONOMY_VERSION,
  publicCategoryList,
  publicMetricList,
} from "@/server/metrics/catalogue";

export const runtime = "nodejs";
export const dynamic = "force-static";

export function GET() {
  return NextResponse.json(
    {
      status: "ok",
      taxonomy_version: TAXONOMY_VERSION,
      metrics_version: METRIC_VERSION,
      topics: publicCategoryList(),
      metrics: publicMetricList(),
    },
    { headers: { "Cache-Control": "public, max-age=3600" } },
  );
}
