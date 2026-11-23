export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().slice(0, 10);
}
