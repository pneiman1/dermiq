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

import { CHANNEL_COLORS, CHANNEL_ORDER, channelLabel } from "@/lib/channels";
import { fmtInt } from "@/lib/money";
import type { AcquisitionByMonthRow } from "@/lib/types";

export function AcquisitionStackedBar({ rows }: { rows: AcquisitionByMonthRow[] }) {
  // Pivot the long (month × channel) rows to wide (one row per month).
  const byMonth = new Map<string, Record<string, number>>();
  for (const r of rows) {
    const m = byMonth.get(r.month_start) ?? {};
    m[r.channel] = (m[r.channel] ?? 0) + r.patient_count;
    byMonth.set(r.month_start, m);
  }
  const data = Array.from(byMonth.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([month_start, counts]) => ({ month_start, ...counts }));

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis
          dataKey="month_start"
          tick={{ fill: "#94a3b8", fontSize: 12 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(d: string) => format(parseISO(d), "MMM ''yy")}
          minTickGap={12}
        />
        <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} tickLine={false} axisLine={false} width={36} />
        <Tooltip
          formatter={(value: number, name: string) => [fmtInt(value), channelLabel(name)]}
          labelFormatter={(d: string) => format(parseISO(d), "MMMM yyyy")}
          contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} formatter={(value: string) => channelLabel(value)} />
        {CHANNEL_ORDER.map((ch) => (
          <Bar key={ch} dataKey={ch} name={ch} stackId="a" fill={CHANNEL_COLORS[ch]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
