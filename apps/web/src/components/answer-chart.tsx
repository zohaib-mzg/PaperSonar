import type { ChartSpec } from "@/lib/chat-types";

const WIDTH = 640;
const HEIGHT = 190;
const PAD_X = 44;
const PAD_Y = 24;

function short(label: string): string {
  return label.length > 18 ? `${label.slice(0, 17)}…` : label;
}

function nice(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function scale(values: number[]): { min: number; max: number; span: number } {
  const finite = values.filter((value) => Number.isFinite(value));
  const min = Math.min(0, ...finite);
  const max = Math.max(0, ...finite);
  return { min, max, span: max - min || 1 };
}

function ChartTable({ chart }: { chart: ChartSpec }) {
  return (
    <table className="chart-table">
      <thead>
        <tr>
          {chart.fallback.headers.map((header) => (
            <th key={header} scope="col">{header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {chart.fallback.rows.map((row, rowIndex) => (
          <tr key={`${row[0]}-${rowIndex}`}>
            {row.map((cell, cellIndex) => (
              <td key={`${cell}-${cellIndex}`}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AnswerChart({ chart }: { chart: ChartSpec }) {
  const accessibleLabel = `${chart.title}. Inline chart with accessible table fallback.`;

  if (chart.kind === "line") {
    const { min, span } = scale(
      chart.series.flatMap((series) => series.values).filter((value): value is number => value !== null),
    );
    const plotWidth = WIDTH - PAD_X * 2;
    const plotHeight = HEIGHT - PAD_Y * 2;
    const xFor = (index: number) =>
      PAD_X + (chart.labels.length <= 1 ? plotWidth / 2 : (index / (chart.labels.length - 1)) * plotWidth);
    const pointsFor = (values: Array<number | null>) =>
      values
        .map((value, index) => {
          if (value === null) return null;
          const y = HEIGHT - PAD_Y - ((value - min) / span) * plotHeight;
          return `${xFor(index).toFixed(1)},${y.toFixed(1)}`;
        })
        .filter((point): point is string => point !== null)
        .join(" ");

    return (
      <section className="chart-block" aria-label={chart.title}>
        <div className="chart-title">{chart.title}</div>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={accessibleLabel} preserveAspectRatio="xMidYMid meet">
          <line x1={PAD_X} y1={HEIGHT - PAD_Y} x2={WIDTH - PAD_X} y2={HEIGHT - PAD_Y} className="chart-axis" />
          {chart.series.map((series, seriesIndex) => (
            <polyline
              key={series.label}
              points={pointsFor(series.values)}
              fill="none"
              className={seriesIndex === 0 ? "chart-line primary" : "chart-line secondary"}
            />
          ))}
          {chart.labels.map((label, index) => (
            <text key={`${label}-${index}`} x={xFor(index)} y={HEIGHT - 6} textAnchor="middle" className="chart-label">
              {short(label)}
            </text>
          ))}
        </svg>
        {chart.note ? <p className="chart-note">{chart.note}</p> : null}
        <details className="chart-details">
          <summary>View data table</summary>
          <ChartTable chart={chart} />
        </details>
      </section>
    );
  }

  const values = chart.series[0]?.values ?? [];
  const { min, span } = scale(values.filter((value): value is number => value !== null));
  const usable = WIDTH - PAD_X * 2;
  const slot = usable / Math.max(1, chart.labels.length);
  const barWidth = Math.max(8, Math.min(42, slot * 0.62));
  const plotHeight = HEIGHT - PAD_Y * 2;
  const zeroY = HEIGHT - PAD_Y - ((0 - min) / span) * plotHeight;

  return (
    <section className="chart-block" aria-label={chart.title}>
      <div className="chart-title">{chart.title}</div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={accessibleLabel} preserveAspectRatio="xMidYMid meet">
        <line x1={PAD_X} y1={zeroY} x2={WIDTH - PAD_X} y2={zeroY} className="chart-axis" />
        {values.map((value, index) => {
          if (value === null) return null;
          const x = PAD_X + slot * index + (slot - barWidth) / 2;
          const height = Math.max(1, (Math.abs(value) / span) * plotHeight);
          const y = value >= 0 ? zeroY - height : zeroY;
          return (
            <rect
              key={`${chart.labels[index]}-${index}`}
              x={x}
              y={y}
              width={barWidth}
              height={height}
              rx={2}
              className="chart-bar"
            />
          );
        })}
        {chart.labels.map((label, index) => (
          <text key={`${label}-${index}`} x={PAD_X + slot * index + slot / 2} y={HEIGHT - 6} textAnchor="middle" className="chart-label">
            {short(label)}
          </text>
        ))}
        {values.map((value, index) =>
          value === null ? null : (
            <text
              key={`value-${index}`}
              x={PAD_X + slot * index + slot / 2}
              y={
                value >= 0
                  ? Math.max(14, zeroY - (Math.abs(value) / span) * plotHeight - 5)
                  : Math.min(HEIGHT - 22, zeroY + (Math.abs(value) / span) * plotHeight + 13)
              }
              textAnchor="middle"
              className="chart-value"
            >
              {nice(value)}
            </text>
          ),
        )}
      </svg>
      {chart.unit ? <p className="chart-note">Unit: {chart.unit}</p> : null}
      {chart.note ? <p className="chart-note">{chart.note}</p> : null}
      <details className="chart-details">
        <summary>View data table</summary>
        <ChartTable chart={chart} />
      </details>
    </section>
  );
}
