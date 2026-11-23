"use client";

export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="error-page">
      <h1>Terminal interrupted</h1>
      <p>Something went wrong. Published reporting pages remain available.</p>
      <button type="button" onClick={reset}>Try again</button>
    </main>
  );
}
