"use client";

import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useIsDesktop } from "@/lib/useMediaQuery";
import { AXIS_TICK, CHART_GRID, TOOLTIP_STYLE } from "@/lib/chartTokens";

export interface WastePoint {
  name: string;
  wasteRate: number; // percent, e.g. 4.6
  wasteCost: number; // USD
}

// Accent (low waste) -> critical (high waste), interpolated over the observed
// range so the worst offenders read hot without a hardcoded threshold.
//
// The ramp is unchanged; only its endpoints moved. They used to be two
// hardcoded RGB triplets mixed in JS, which meant the chart kept its teal
// through a theme change and the values never reached the token file. color-mix
// does the same interpolation in CSS, so both ends follow the cascade — night
// theme included — and no hex survives in the bundle.
function colorFor(rate: number, max: number): string {
  const t = max > 0 ? Math.min(rate / max, 1) : 0;
  return `color-mix(in srgb, var(--status-critical) ${Math.round(t * 100)}%, var(--accent))`;
}

export function WasteByServiceBar({ data }: { data: WastePoint[] }) {
  const max = data.reduce((m, d) => Math.max(m, d.wasteRate), 0);
  const isDesktop = useIsDesktop();
  // Category labels are a fixed pixel gutter in Recharts, so on a 375px screen the
  // desktop 150px would eat 44% of the chart. 104px still fits most service names.
  const labelWidth = isDesktop ? 150 : 104;
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 34)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 24, bottom: 4, left: 8 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} horizontal={false} />
        <XAxis
          type="number"
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          tickFormatter={(n: number) => `${n.toFixed(1)}%`}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={labelWidth}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          formatter={(value: number, _name: string, item: { payload?: WastePoint }) => {
            const cost = item.payload?.wasteCost ?? 0;
            return [
              `${value.toFixed(1)}%  ($${cost.toLocaleString(undefined, { maximumFractionDigits: 0 })} wasted)`,
              "Waste rate",
            ];
          }}
          contentStyle={TOOLTIP_STYLE}
        />
        <Bar dataKey="wasteRate" radius={[0, 4, 4, 0]}>
          {data.map((d) => (
            <Cell key={d.name} fill={colorFor(d.wasteRate, max)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
