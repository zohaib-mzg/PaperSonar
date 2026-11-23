type AnalyticsProps = Record<string, string | number | boolean | null | undefined>;

const host = process.env.NEXT_PUBLIC_POSTHOG_HOST?.replace(/\/$/, "");
const apiKey = process.env.NEXT_PUBLIC_POSTHOG_KEY;

export function track(event: string, props: AnalyticsProps = {}): void {
  if (!host || !apiKey || typeof window === "undefined") return;
  const body = JSON.stringify({
    api_key: apiKey,
    event,
    properties: {
      ...props,
      $lib: "papersonar-web",
      $current_url: window.location.pathname,
    },
  });
  try {
    void fetch(`${host}/capture/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    });
  } catch {
    // Analytics is best-effort and never blocks an answer.
  }
}
