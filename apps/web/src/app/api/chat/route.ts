import { NextRequest, NextResponse } from "next/server";
import { chatRequestSchema } from "@/server/chat/schema";
import { answerChat } from "@/server/chat/service";
import { logError } from "@/server/logger";

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
    return NextResponse.json(
      { status: "INVALID", answer: "The request body must be JSON." },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  const parsed = chatRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      {
        status: "INVALID",
        answer: "Please send a question of 1–500 characters with optional session details.",
      },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  try {
    const result = await answerChat(parsed.data, clientIp(request.headers));
    return NextResponse.json(result.body, {
      status: result.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    logError("chat_route_failure", error, { route: "/api/chat" });
    return NextResponse.json(
      {
        status: "INTERNAL",
        answer: "Something went wrong. Please try again.",
      },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
