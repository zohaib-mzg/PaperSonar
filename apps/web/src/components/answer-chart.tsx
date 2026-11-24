"use client";

import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpec } from "@/lib/chat-types";

const COLORS = ["#5eead4", "#60a5fa", "#f59e0b", "#f472b6", "#a78bfa", "#94a3b8"];

function compactNum(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function exactNum(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function formatLabel(label: string): string {
  const year = label.match(/^(19|20)\d{2}$/);
  if (year) return label;
  const yearPrefix = label.match(/^((?:19|20)\d{2})(?:[-/].*)?$/);
  if (yearPrefix) return yearPrefix[1];
  return label.length > 16 ? `${label.slice(0, 15)}…` : label;
}



function spansOrders(values: number[]): boolean {
  const positives = values.filter((v) => Number.isFinite(v) && Math.abs(v) > 0).map(Math.abs);
  if (positives.length < 2) return false;
  return Math.max(...positives) / Math.min(...positives) >= 1000;
}

type Row = Record<string, string | number | null>;

function toRows(chart: ChartSpec): Row[] {
  return chart.labels.map((label, i) => {
    const row: Row = { name: formatLabel(label), __raw: label };
    chart.series.forEach((s) => { row[s.label] = s.values[i] ?? null; });
    return row;
  });
}

function ChartTable({ chart }: { chart: ChartSpec }) {
  return (
    <table className="chart-table">
      <thead>
        <tr>{chart.fallback.headers.map((h) => <th key={h} scope="col">{h}</th>)}</tr>
      </thead>
      <tbody>
        {chart.fallback.rows.map((row, i) => (
          <tr key={`r-${i}`}>{row.map((cell, j) => <td key={`c-${i}-${j}`}>{cell}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

type TooltipPayload = { dataKey?: string; name?: string; value?: unknown; color?: string };
function DarkTooltip({ active, payload, label, unit }: { active?: boolean; payload?: TooltipPayload[]; label?: string; unit?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#111827", border: "1px solid #334155", padding: "8px 10px", borderRadius: 6, color: "#e5e7eb", fontSize: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      {payload.map((p) => (
        <div key={String(p.dataKey)} style={{ color: p.color || "#e5e7eb" }}>
          {p.name}: {typeof p.value === "number" ? exactNum(p.value) : "not reported"}{unit ? ` ${unit}` : ""}
        </div>
      ))}
    </div>
  );
}

function SingleMetric({ chart }: { chart: ChartSpec }) {
  const value = chart.series[0]?.values.find((v): v is number => typeof v === "number");
  return (
    <div className="chart-metric-card" aria-label={chart.title}>
      <div className="chart-title">{chart.title}</div>
      <div style={{ fontSize: 32, fontWeight: 700, color: "#5eead4", margin: "12px 0" }}>
        {typeof value === "number" ? exactNum(value) : "not reported"}{chart.unit ? <span style={{ fontSize: 14, color: "#94a3b8", marginLeft: 6 }}>{chart.unit}</span> : null}
      </div>
      {chart.note ? <p className="chart-note">{chart.note}</p> : null}
      <details className="chart-details"><summary>View data table</summary><ChartTable chart={chart} /></details>
    </div>
  );
}

export function AnswerChart({ chart }: { chart: ChartSpec }) {
  const [logScale, setLogScale] = useState(false);
  const rows = useMemo(() => toRows(chart), [chart]);
  const allValues = useMemo(
    () => chart.series.flatMap((s) => s.values).filter((v): v is number => typeof v === "number" && Number.isFinite(v)),
    [chart],
  );
  const showLogToggle = useMemo(() => spansOrders(allValues) && allValues.every((v) => v >= 0), [allValues]);
  const maxBySeries = useMemo(() => chart.series.map((s) => {
    let maxI = -1; let maxV = -Infinity;
    s.values.forEach((v, i) => { if (typeof v === "number" && v > maxV) { maxV = v; maxI = i; } });
    return maxI;
  }), [chart]);

  if (chart.kind === "metric") return <section className="chart-block"><SingleMetric chart={chart} /></section>;

  const commonAxisProps = {
    tick: { fill: "#94a3b8", fontSize: 11 },
    axisLine: { stroke: "#334155" },
    tickLine: { stroke: "#334155" },
  };

  const xTickInterval = chart.labels.length > 12 ? Math.ceil(chart.labels.length / 8) - 1 : 0;

  const wrap = (children: React.ReactNode) => (
    <section className="chart-block" aria-label={chart.title}>
      <div className="chart-title-row" style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <div className="chart-title">{chart.title}</div>
        {showLogToggle ? (
          <button type="button" className="chart-toggle" onClick={() => setLogScale((v) => !v)} style={{ fontSize: 11, color: "#94a3b8", background: "transparent", border: "1px solid #334155", borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>
            {logScale ? "Linear" : "Log"} scale
          </button>
        ) : null}
      </div>
      {chart.yLabel || chart.unit ? <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 4 }}>{chart.yLabel ?? chart.unit}</div> : null}
      {children}
      {chart.xLabel ? <div style={{ fontSize: 11, color: "#94a3b8", textAlign: "center", marginTop: 2 }}>{chart.xLabel}</div> : null}
      {chart.note ? <p className="chart-note">{chart.note}</p> : null}
      <details className="chart-details"><summary>View data table</summary><ChartTable chart={chart} /></details>
    </section>
  );

  if (chart.kind === "donut") {
    const s = chart.series[0];
    const data = chart.labels.map((label, i) => ({ name: formatLabel(label), value: typeof s?.values[i] === "number" ? (s.values[i] as number) : 0 })).filter((d) => d.value > 0);
    const total = data.reduce((sum, d) => sum + d.value, 0);
    return wrap(
      <div style={{ height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={2}>
              {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip content={<DarkTooltip unit={chart.unit ?? "%"} />} />
            <Legend formatter={(v) => <span style={{ color: "#cbd5e1", fontSize: 11 }}>{v}</span>} />
          </PieChart>
        </ResponsiveContainer>
        <div style={{ textAlign: "center", fontSize: 11, color: "#94a3b8", marginTop: -8 }}>Total: {exactNum(total)}{chart.unit ? ` ${chart.unit}` : ""}</div>
      </div>
    );
  }

  if (chart.kind === "horizontal_bar") {
    return wrap(
      <div style={{ height: Math.max(220, chart.labels.length * 34) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 10, right: 24, top: 8, bottom: 8 }}>
            <CartesianGrid stroke="#1f2937" horizontal={false} />
            <XAxis type="number" {...commonAxisProps} tickFormatter={compactNum} scale={logScale ? "log" : "auto"} domain={logScale ? ["auto", "auto"] : [0, "auto"]} allowDataOverflow />
            <YAxis type="category" dataKey="name" {...commonAxisProps} width={130} />
            <Tooltip content={<DarkTooltip unit={chart.unit} />} />
            {chart.series.map((s, si) => <Bar key={s.label} dataKey={s.label} fill={COLORS[si % COLORS.length]} radius={[0, 3, 3, 0]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (chart.kind === "grouped_bar") {
    return wrap(
      <div style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ left: 8, right: 16, top: 8, bottom: 24 }}>
            <CartesianGrid stroke="#1f2937" vertical={false} />
            <XAxis dataKey="name" {...commonAxisProps} interval={xTickInterval} />
            <YAxis {...commonAxisProps} tickFormatter={compactNum} scale={logScale ? "log" : "auto"} domain={logScale ? ["auto", "auto"] : [0, "auto"]} allowDataOverflow />
            <Tooltip content={<DarkTooltip unit={chart.unit} />} />
            {chart.series.length > 1 ? <Legend formatter={(v) => <span style={{ color: "#cbd5e1", fontSize: 11 }}>{v}</span>} /> : null}
            {chart.series.map((s, si) => <Bar key={s.label} dataKey={s.label} fill={COLORS[si % COLORS.length]} radius={[3, 3, 0, 0]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (chart.kind === "line" || chart.kind === "multi_line") {
    return wrap(
      <div style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ left: 8, right: 16, top: 8, bottom: 24 }}>
            <CartesianGrid stroke="#1f2937" vertical={false} />
            <XAxis dataKey="name" {...commonAxisProps} interval={xTickInterval} />
            <YAxis {...commonAxisProps} tickFormatter={compactNum} scale={logScale ? "log" : "auto"} domain={logScale ? ["auto", "auto"] : ["auto", "auto"]} allowDataOverflow />
            <Tooltip content={<DarkTooltip unit={chart.unit} />} />
            {chart.series.length > 1 ? <Legend formatter={(v) => <span style={{ color: "#cbd5e1", fontSize: 11 }}>{v}</span>} /> : null}
            {chart.series.map((s, si) => (
              <Line
                key={s.label}
                type="monotone"
                dataKey={s.label}
                stroke={COLORS[si % COLORS.length]}
                strokeWidth={2}
                dot={(props: { index?: number; cx?: number; cy?: number }) => {
                  const idx = props.index ?? -1;
                  if (idx !== maxBySeries[si]) return <g key={`d-${si}-${idx}`} />;
                  return <circle key={`d-${si}-${idx}`} cx={props.cx} cy={props.cy} r={4} fill={COLORS[si % COLORS.length]} stroke="#0f172a" />;
                }}
                activeDot={{ r: 5 }}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // default bar
  return wrap(
    <div style={{ height: 300 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ left: 8, right: 16, top: 8, bottom: 24 }}>
          <CartesianGrid stroke="#1f2937" vertical={false} />
          <XAxis dataKey="name" {...commonAxisProps} interval={xTickInterval} />
          <YAxis {...commonAxisProps} tickFormatter={compactNum} scale={logScale ? "log" : "auto"} domain={logScale ? ["auto", "auto"] : [0, "auto"]} allowDataOverflow />
          <Tooltip content={<DarkTooltip unit={chart.unit} />} />
          {chart.series.length > 1 ? <Legend formatter={(v) => <span style={{ color: "#cbd5e1", fontSize: 11 }}>{v}</span>} /> : null}
          {chart.series.map((s, si) => <Bar key={s.label} dataKey={s.label} fill={COLORS[si % COLORS.length]} radius={[3, 3, 0, 0]} />)}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}