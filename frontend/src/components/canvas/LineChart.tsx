"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart as RLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { CanvasRow, LineSpec } from "@/lib/types";

const NoData = () => (
  <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
    No data for this view.
  </div>
);

const AXIS_TICK = { fill: "#94a3b8", fontSize: 12 };
const TOOLTIP_STYLE = { borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 } as const;
const PALETTE = ["#0E7490", "#6366F1", "#F59E0B", "#F43F5E", "#8B5CF6", "#64748B"];

function fmtNumber(n: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function LineChart({ spec, data }: { spec: LineSpec; data: CanvasRow[] }) {
  if (!data || data.length === 0) return <NoData />;

  const measures = Array.isArray(spec.y) ? spec.y : [spec.y];
  const parsed = data.map((row) => {
    const next: CanvasRow = { ...row };
    for (const m of measures) next[m] = Number(row[m]);
    return next;
  });

  return (
    <ResponsiveContainer width="100%" height="100%">
      <RLineChart data={parsed} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis
          dataKey={spec.x}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          minTickGap={16}
        />
        <YAxis
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={fmtNumber}
        />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        {measures.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {measures.map((m, i) => (
          <Line
            key={m}
            type="monotone"
            dataKey={m}
            stroke={PALETTE[i % PALETTE.length]}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </RLineChart>
    </ResponsiveContainer>
  );
}
