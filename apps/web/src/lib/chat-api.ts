import type { ChatAnswer, HealthResponse } from "@/lib/chat-types";

const SESSION_KEY = "papersonar.session";

function getSessionId(): string {
  if (typeof window === "undefined") return "server";
  let id = window.sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = window.crypto.randomUUID();
    window.sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function resetSessionId(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(SESSION_KEY);
}

export async function askQuestion(message: string): Promise<ChatAnswer> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: getSessionId() }),
  });
  const data = (await response.json()) as ChatAnswer;
  if (!response.ok && data.status !== "RATE_LIMITED" && data.status !== "MAINTENANCE") {
    throw new Error(data.answer || "The assistant is temporarily unavailable.");
  }
  return data;
}

export async function getHealth(): Promise<HealthResponse | null> {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as HealthResponse;
  } catch {
    return null;
  }
}

export async function sendFeedback(input: {
  request_id: string;
  rating: "helpful" | "not_helpful";
  reason: "wrong_number" | "wrong_topic" | "not_relevant" | "missing_data" | "other";
}): Promise<void> {
  await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}
