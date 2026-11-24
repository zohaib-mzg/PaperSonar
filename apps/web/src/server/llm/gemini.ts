import { env } from "@/server/env";
import { composerPrompt, plannerPrompt } from "@/server/llm/prompts";
import type { ComposeInput, LlmProvider, PlannerInput } from "@/server/llm/types";

function endpoint(): string {
  return `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(
    env.GEMINI_MODEL ?? "",
  )}:generateContent`;
}

async function call(prompt: string, json: boolean, maxTokens: number): Promise<string> {
  const response = await fetch(endpoint(), {
    method: "POST",
    headers: {
      "x-goog-api-key": env.GEMINI_API_KEY ?? "",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      generationConfig: {
        temperature: 0,
        maxOutputTokens: maxTokens,
        ...(json ? { responseMimeType: "application/json" } : {}),
      },
    }),
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) {
    let detail = "";
    try {
      detail = (await response.text()).slice(0, 500);
    } catch {
      // ignore unreadable error body
    }
    const error = new Error(
      `gemini_${response.status}${detail ? `: ${detail}` : ""}`,
    ) as Error & { status?: number; code?: string };
    error.status = response.status;
    error.code = `gemini_${response.status}`;
    throw error;
  }
  const payload = (await response.json()) as {
    candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
  };
  return payload.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
}

export const geminiProvider: LlmProvider = {
  name: "gemini",
  async plan(input: PlannerInput) {
    const text = await call(plannerPrompt(input), true, 800);
    return JSON.parse(text);
  },
  async compose(input: ComposeInput) {
    return call(composerPrompt(input), false, 350);
  },
};
