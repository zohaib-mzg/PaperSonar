import Link from "next/link";

export default function NotFound() {
  return (
    <main className="error-page">
      <h1>404 · Path not found</h1>
      <p>This terminal has one route.</p>
      <Link href="/">Return to terminal</Link>
    </main>
  );
}
