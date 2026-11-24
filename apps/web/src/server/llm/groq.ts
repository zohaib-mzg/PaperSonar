import { env } from "@/server/env";
import { composerPrompt, plannerPrompt, PLANNER_SCHEMA_HINT } from "@/server/llm/prompts";
import type { ComposeInput, LlmProvider, PlannerInput } from "@/server/llm/types";

const ENDPOINT = "https://api.groq.com/openai/v1/chat/completions";

async function call(messages: Array<{ role: string; content: string }>, json: boolean, maxTokens: number) {
  const response = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GROQ_API_KEY ?? ""}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: env.GROQ_MODEL,
      temperature: 0,
      max_tokens: maxTokens,
      messages,
      ...(json ? { response_format: { type: "json_object" } } : {}),
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
      `groq_${response.status}${detail ? `: ${detail}` : ""}`,
    ) as Error & { status?: number; code?: string };
    error.status = response.status;
    error.code = `groq_${response.status}`;
    throw error;
  }
  const payload = (await response.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  return payload.choices?.[0]?.message?.content ?? "";
}

export const groqProvider: LlmProvider = {
  name: "groq",
  async plan(input: PlannerInput) {
    const text = await call(
      [
        { role: "system", content: `${plannerPrompt(input)}\n${PLANNER_SCHEMA_HINT}` },
        { role: "user", content: input.message },
      ],
      true,
      800,
    );
    return JSON.parse(text);
  },
  async compose(input: ComposeInput) {
    return call(
      [
        { role: "system", content: composerPrompt(input) },
        { role: "user", content: "Write the answer." },
      ],
      false,
      350,
    );
  },
};
