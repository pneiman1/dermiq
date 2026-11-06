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
import { AXIS_TICK, CHART_GRID, TOOLTIP_STYLE, seriesColor } from "@/lib/chartTokens";

const NoData = () => (
  <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
    No data for this view.
  </div>
);

// seriesColor does not wrap past the sixth slot; it returns a neutral instead,
// because two series sharing a hue makes the legend stop being a key.

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
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
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
            stroke={seriesColor(i)}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </RLineChart>
    </ResponsiveContainer>
  );
}
