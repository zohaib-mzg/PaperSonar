import { env } from "@/server/env";
import { LlmHttpError, parseRetryAfterMs } from "@/server/llm/errors";
import { composerPrompt, plannerPrompt, PLANNER_SCHEMA_HINT } from "@/server/llm/prompts";
import type { ComposeInput, LlmCallOptions, LlmProvider, PlannerInput } from "@/server/llm/types";

const ENDPOINT = "https://api.groq.com/openai/v1/chat/completions";

async function call(
  messages: Array<{ role: string; content: string }>,
  json: boolean,
  maxTokens: number,
  signal?: AbortSignal,
) {
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
    signal: signal ?? AbortSignal.timeout(8000),
  });
  if (!response.ok) {
    let detail = "";
    try {
      detail = (await response.text()).slice(0, 500);
    } catch {
      // ignore unreadable error body
    }
    throw new LlmHttpError(
      "groq",
      response.status,
      detail,
      parseRetryAfterMs(response.headers.get("retry-after"), detail),
    );
  }
  const payload = (await response.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  return payload.choices?.[0]?.message?.content ?? "";
}

export const groqProvider: LlmProvider = {
  name: "groq",
  async plan(input: PlannerInput, options?: LlmCallOptions) {
    const text = await call(
      [
        { role: "system", content: `${plannerPrompt(input)}\n${PLANNER_SCHEMA_HINT}` },
        { role: "user", content: input.message },
      ],
      true,
      600,
      options?.signal,
    );
    return JSON.parse(text);
  },
  async compose(input: ComposeInput, options?: LlmCallOptions) {
    return call(
      [
        { role: "system", content: composerPrompt(input) },
        { role: "user", content: "Write the answer." },
      ],
      false,
      350,
      options?.signal,
    );
  },
};
