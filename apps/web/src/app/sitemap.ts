import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: "https://paper-sonar.vercel.app/",
      lastModified: new Date("2026-11-23T00:00:00.000Z"),
      changeFrequency: "weekly",
      priority: 1,
    },
  ];
}
