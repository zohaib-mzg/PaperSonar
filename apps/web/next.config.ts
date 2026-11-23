import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const projectDir = path.dirname(fileURLToPath(import.meta.url));
const posthogHost = process.env.NEXT_PUBLIC_POSTHOG_HOST?.replace(/\/$/, "") ?? "";
const connectSources = ["'self'", posthogHost].filter(Boolean).join(" ");
const scriptSources = ["'self'", "'unsafe-inline'"]
  .concat(process.env.NODE_ENV === "production" ? [] : ["'unsafe-eval'"])
  .join(" ");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  outputFileTracingRoot: path.join(projectDir, "../../"),
  outputFileTracingIncludes: {
    "/*": ["config/public_metrics.yml", "config/taxonomy.yml"],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Content-Security-Policy",
            value:
              `default-src 'self'; script-src ${scriptSources}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src ${connectSources}; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`,
          },
        ],
      },
      {
        source: "/api/:path*",
        headers: [{ key: "Cache-Control", value: "no-store" }],
      },
    ];
  },
};

export default nextConfig;
