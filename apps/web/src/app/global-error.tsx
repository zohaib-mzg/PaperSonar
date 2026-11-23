"use client";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <main className="error-page">
          <h1>Terminal interrupted</h1>
          <p>Something went wrong. Published reporting pages remain available.</p>
          <button type="button" onClick={reset}>Try again</button>
        </main>
      </body>
    </html>
  );
}
