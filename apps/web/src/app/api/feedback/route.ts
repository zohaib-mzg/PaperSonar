import { NextRequest, NextResponse } from "next/server";
import { cache } from "@/server/cache";
import { feedbackRequestSchema } from "@/server/chat/schema";
import { enforceLimit, type LimitResult } from "@/server/rate-limit";
import { log, logError } from "@/server/logger";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function clientIp(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0]?.trim() || "unknown";
  return headers.get("x-real-ip")?.trim() || "local";
}

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ status: "INVALID" }, { status: 400 });
  }

  const parsed = feedbackRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ status: "INVALID" }, { status: 400 });
  }

  let limit: LimitResult;
  try {
    limit = await enforceLimit(clientIp(request.headers), "feedback");
  } catch (error) {
    logError("feedback_rate_limit_failed", error, { route: "/api/feedback" });
    return NextResponse.json({ status: "INTERNAL" }, { status: 500 });
  }
  if (!limit.success) {
    return NextResponse.json({ status: "RATE_LIMITED" }, { status: 429 });
  }

  const key = `feedback:aggregate:${parsed.data.rating}:${parsed.data.reason}`;
  try {
    const current = (await cache.get<number>(key)) ?? 0;
    await cache.set(key, current + 1, 60 * 60 * 24 * 30);
  } catch (error) {
    logError("feedback_store_failed", error, { route: "/api/feedback" });
    return NextResponse.json({ status: "INTERNAL" }, { status: 500 });
  }

  log("info", "feedback_recorded", {
    route: "/api/feedback",
    rating: parsed.data.rating,
    reason: parsed.data.reason,
    request_id: parsed.data.request_id,
  });

  return NextResponse.json({ status: "OK" });
}
