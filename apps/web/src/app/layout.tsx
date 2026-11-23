import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://paper-sonar.vercel.app"),
  title: "PaperSonar — Research Intelligence",
  description: "A research terminal for published PaperSonar evidence.",
  robots: { index: true, follow: true },
  openGraph: {
    title: "PaperSonar — Research Intelligence",
    description: "A research terminal for published PaperSonar evidence.",
    url: "https://paper-sonar.vercel.app/",
    siteName: "PaperSonar",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "PaperSonar — Research Intelligence",
    description: "A research terminal for published PaperSonar evidence.",
  },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover" as const,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
