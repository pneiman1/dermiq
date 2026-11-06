"use client";

import { format, parseISO } from "date-fns";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fmtCompactUSD, fmtUSD } from "@/lib/money";
import { AXIS_TICK, CHART_GRID, TOOLTIP_STYLE, seriesColor } from "@/lib/chartTokens";

export interface CategoryPoint {
  date: string;
  injectable: number;
  device: number;
  skincare: number;
  surgical: number;
  membership: number;
  consult: number;
}

// Ordered largest → smallest so the stack hierarchy is stable (injectable bottom).
// Distinct (muted) hues so six segments are actually distinguishable.
const SERIES: { key: keyof Omit<CategoryPoint, "date">; label: string; color: string }[] = [
  // The six categorical slots, in their fixed order. Not shades of the brand,
  // and never cycled — there are exactly six categories and exactly six slots.
  { key: "injectable", label: "Injectable", color: seriesColor(0) },
  { key: "device", label: "Energy device", color: seriesColor(1) },
  { key: "skincare", label: "Skincare", color: seriesColor(2) },
  { key: "surgical", label: "Surgical", color: seriesColor(3) },
  { key: "membership", label: "Membership", color: seriesColor(4) },
  { key: "consult", label: "Consult", color: seriesColor(5) },
];

export function CategoryStackedBar({ data }: { data: CategoryPoint[] }) {
  return (
    <div className="h-[260px] w-full sm:h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
          <XAxis
            dataKey="date"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            tickFormatter={(d: string) => format(parseISO(d), "MMM d")}
            minTickGap={16}
          />
          <YAxis
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={64}
            tickFormatter={(n: number) => fmtCompactUSD(n)}
          />
          <Tooltip
            formatter={(value: number, name: string) => [fmtUSD(String(value), { dp: 0 }), name]}
            labelFormatter={(d: string) => format(parseISO(d), "EEE, MMM d")}
            contentStyle={TOOLTIP_STYLE}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {SERIES.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.label} stackId="a" fill={s.color} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
