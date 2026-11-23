import { NextResponse } from "next/server";
import { METRIC_VERSION, publicCategoryList, publicMetricList, TAXONOMY_VERSION } from "@/server/metrics/catalogue";

export const runtime = "nodejs";
export const dynamic = "force-static";

export async function GET() {
  return NextResponse.json({
    metric_version: METRIC_VERSION,
    taxonomy_version: TAXONOMY_VERSION,
    metrics: publicMetricList(),
    categories: publicCategoryList(),
  });
}
