"use client";

import {
  Bar,
  BarChart as RBarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fmtCompactUSD } from "@/lib/money";
import type { BarSpec, CanvasRow } from "@/lib/types";
import { AXIS_TICK, CHART_ACCENT, CHART_CURSOR, CHART_GRID, TOOLTIP_STYLE } from "@/lib/chartTokens";

const NoData = () => (
  <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
    No data for this view.
  </div>
);


function truncate(v: unknown): string {
  const s = String(v ?? "");
  return s.length > 16 ? `${s.slice(0, 15)}…` : s;
}

function fmtNumber(n: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function BarChart({ spec, data }: { spec: BarSpec; data: CanvasRow[] }) {
  if (!data || data.length === 0) return <NoData />;

  const parsed = data.map((row) => ({ ...row, [spec.y]: Number(row[spec.y]) }));
  const horizontal = spec.orientation === "horizontal";

  return (
    <ResponsiveContainer width="100%" height="100%">
      <RBarChart
        data={parsed}
        layout={horizontal ? "vertical" : "horizontal"}
        margin={{ top: 8, right: 16, bottom: horizontal ? 0 : 24, left: 8 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
        {horizontal ? (
          <>
            <XAxis
              type="number"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              tickFormatter={fmtNumber}
            />
            <YAxis
              type="category"
              dataKey={spec.x}
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              width={120}
              tickFormatter={truncate}
            />
          </>
        ) : (
          <>
            <XAxis
              dataKey={spec.x}
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              interval={0}
              angle={-30}
              textAnchor="end"
              height={48}
              tickFormatter={truncate}
            />
            <YAxis
              type="number"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              width={56}
              tickFormatter={fmtNumber}
            />
          </>
        )}
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: CHART_CURSOR }} />
        <Bar dataKey={spec.y} fill={CHART_ACCENT} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} />
      </RBarChart>
    </ResponsiveContainer>
  );
}
