export type ChartSpec = {
  kind: "bar" | "line";
  title: string;
  labels: string[];
  series: Array<{ label: string; values: Array<number | null> }>;
  unit?: string;
  note?: string;
  fallback: { headers: string[]; rows: string[][] };
};

export type ChatFacts = {
  values: Record<string, string | number | boolean | null>;
  rows: Array<Record<string, string | number | boolean | null>>;
  denominators: string[];
  caveats: string[];
  source_scope: string;
  as_of: string | null;
  snapshot_date: string | null;
  coverage_note: string | null;
};

export type ChatAnswer = {
  request_id?: string;
  status:
    | "answered"
    | "clarify"
    | "unsupported"
    | "refused"
    | "DATA_UNAVAILABLE"
    | "RATE_LIMITED"
    | "MAINTENANCE"
    | "INTERNAL"
    | "INVALID";
  answer: string;
  mode?: "deterministic" | "composed";
  intent?: "metric" | "compare" | "search" | "clarify" | "refuse";
  interpretation?: string;
  metric_id?: string | null;
  metric_label?: string | null;
  facts: ChatFacts;
  chart?: ChartSpec;
  citations?: Array<{ label: string; view: string }>;
  closest_match_disclosure?: string;
  degraded?: string;
  provider?: "groq" | "gemini";
  fallback_used?: boolean;
  cached?: boolean;
  freshness: {
    latest_snapshot_date: string | null;
    latest_published_at: string | null;
    total_outputs: number | null;
    retrieved_on: string | null;
  };
};

export type HealthResponse = {
  status: "ok" | "degraded" | "not_ready";
  version: string;
  checks: {
    env: "ok" | "not_ready";
    snowflake: "ok" | "error" | "missing";
    redis: "ok" | "missing" | "error";
    groq: "configured" | "missing";
    gemini: "configured" | "missing";
    chat_enabled: boolean;
  };
  latency_ms: number;
};
