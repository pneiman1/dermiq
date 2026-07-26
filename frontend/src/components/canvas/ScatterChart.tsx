"use client";

import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart as RScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import type { CanvasRow, ScatterSpec } from "@/lib/types";

const NoData = () => (
  <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
    No data for this view.
  </div>
);

const AXIS_TICK = { fill: "#94a3b8", fontSize: 12 };
const TOOLTIP_STYLE = { borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 } as const;

function fmtNumber(n: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function ScatterChart({ spec, data }: { spec: ScatterSpec; data: CanvasRow[] }) {
  if (!data || data.length === 0) return <NoData />;

  const parsed = data.map((row) => {
    const next: CanvasRow = { ...row };
    next[spec.x] = Number(row[spec.x]);
    next[spec.y] = Number(row[spec.y]);
    if (spec.size) next[spec.size] = Number(row[spec.size]);
    return next;
  });

  return (
    <ResponsiveContainer width="100%" height="100%">
      <RScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          type="number"
          dataKey={spec.x}
          name={spec.x}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          tickFormatter={fmtNumber}
        />
        <YAxis
          type="number"
          dataKey={spec.y}
          name={spec.y}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={fmtNumber}
        />
        {spec.size && <ZAxis type="number" dataKey={spec.size} name={spec.size} range={[40, 400]} />}
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          contentStyle={TOOLTIP_STYLE}
          formatter={(v: number | string, name: string) => [
            typeof v === "number" ? fmtNumber(v) : v,
            name,
          ]}
          labelFormatter={(_, payload) => {
            const p = payload?.[0]?.payload as CanvasRow | undefined;
            return p ? String(p[spec.point_label] ?? "") : "";
          }}
        />
        <Scatter data={parsed} fill="#0E7490" />
      </RScatterChart>
    </ResponsiveContainer>
  );
}
