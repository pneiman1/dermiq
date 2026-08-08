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
  { key: "injectable", label: "Injectable", color: "#0E7490" }, // clinical teal (primary)
  { key: "device", label: "Energy device", color: "#6366F1" }, // indigo-500
  { key: "skincare", label: "Skincare", color: "#F59E0B" }, // amber-500
  { key: "surgical", label: "Surgical", color: "#F43F5E" }, // rose-500
  { key: "membership", label: "Membership", color: "#8B5CF6" }, // violet-500
  { key: "consult", label: "Consult", color: "#64748B" }, // slate-500
];

export function CategoryStackedBar({ data }: { data: CategoryPoint[] }) {
  return (
    <div className="h-[260px] w-full sm:h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(d: string) => format(parseISO(d), "MMM d")}
            minTickGap={16}
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            width={64}
            tickFormatter={(n: number) => fmtCompactUSD(n)}
          />
          <Tooltip
            formatter={(value: number, name: string) => [fmtUSD(String(value), { dp: 0 }), name]}
            labelFormatter={(d: string) => format(parseISO(d), "EEE, MMM d")}
            contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
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
