"use client";

import { format, parseISO } from "date-fns";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fmtCompactUSD, fmtUSD } from "@/lib/money";

export interface RevenuePoint {
  date: string; // ISO yyyy-MM-dd
  value: number;
  avg?: number | null; // 28-day trailing mean
}

export function RevenueLineChart({ data }: { data: RevenuePoint[] }) {
  const hasAvg = data.some((d) => d.avg != null);
  return (
    // Height moves to the wrapper so it can be a breakpoint: 240px on mobile,
    // the original 300px from `sm` up.
    <div className="h-[240px] w-full sm:h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(d: string) => format(parseISO(d), "MMM d")}
            minTickGap={28}
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
            labelFormatter={(d: string) => format(parseISO(d), "EEE, MMM d, yyyy")}
            contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="linear"
            dataKey="value"
            name="Net revenue"
            stroke="#0E7490"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
          {hasAvg && (
            <Line
              type="monotone"
              dataKey="avg"
              name="28-day avg"
              stroke="#94a3b8"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
