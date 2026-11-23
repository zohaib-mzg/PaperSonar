import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/"] }],
    sitemap: "https://paper-sonar.vercel.app/sitemap.xml",
    host: "https://paper-sonar.vercel.app",
  };
}
