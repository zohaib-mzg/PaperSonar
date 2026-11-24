export class LlmHttpError extends Error {
  readonly provider: "groq" | "gemini";
  readonly status: number;
  readonly code: string;
  readonly retryAfterMs?: number;

  constructor(
    provider: "groq" | "gemini",
    status: number,
    detail: string,
    retryAfterMs?: number,
  ) {
    super(`${provider}_${status}${detail ? `: ${detail}` : ""}`);
    this.name = "LlmHttpError";
    this.provider = provider;
    this.status = status;
    this.code = `${provider}_${status}`;
    if (retryAfterMs !== undefined) this.retryAfterMs = retryAfterMs;
  }
}

export function parseRetryAfterMs(header: string | null, body: string): number | undefined {
  if (header?.trim()) {
    const seconds = Number(header);
    if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
    const date = Date.parse(header);
    if (Number.isFinite(date)) return Math.max(0, date - Date.now());
  }

  const match = body.match(/try again in\s+([\d.]+)\s*(ms|s)?/i);
  if (match) {
    const amount = Number(match[1]);
    if (Number.isFinite(amount)) {
      return match[2]?.toLowerCase() === "ms" ? amount : amount * 1000;
    }
  }
  return undefined;
}

export function isRetryableLlmError(error: unknown): boolean {
  if (error instanceof LlmHttpError) {
    return [429, 500, 502, 503, 504].includes(error.status);
  }
  return (
    error instanceof Error &&
    (error.name === "TimeoutError" || error.name === "AbortError")
  );
}
