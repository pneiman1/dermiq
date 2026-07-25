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

export interface WastePoint {
  name: string;
  wasteRate: number; // percent, e.g. 4.6
  wasteCost: number; // USD
}

// Teal (low waste) -> rose (high waste). Interpolated over the observed range so
// the worst offenders read hot without a hardcoded threshold.
function colorFor(rate: number, max: number): string {
  const t = max > 0 ? Math.min(rate / max, 1) : 0;
  const teal = [14, 116, 144]; // #0E7490
  const rose = [244, 63, 94]; // #F43F5E
  const mix = teal.map((c, i) => Math.round(c + (rose[i] - c) * t));
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
}

export function WasteByServiceBar({ data }: { data: WastePoint[] }) {
  const max = data.reduce((m, d) => Math.max(m, d.wasteRate), 0);
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 34)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 24, bottom: 4, left: 8 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
        <XAxis
          type="number"
          tick={{ fill: "#94a3b8", fontSize: 12 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(n: number) => `${n.toFixed(1)}%`}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={150}
          tick={{ fill: "#94a3b8", fontSize: 12 }}
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
          contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
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
