"use client";

import {
  Cell,
  Legend,
  Pie,
  PieChart as RPieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type { CanvasRow, PieSpec } from "@/lib/types";
import { TOOLTIP_STYLE, seriesColor } from "@/lib/chartTokens";

const NoData = () => (
  <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
    No data for this view.
  </div>
);

// A pie with more slices than the palette has slots used to wrap and repeat a
// hue, which makes two wedges look like the same category. seriesColor returns
// a neutral past the sixth instead.

export function PieChart({ spec, data }: { spec: PieSpec; data: CanvasRow[] }) {
  if (!data || data.length === 0) return <NoData />;

  const parsed = data.map((row) => ({
    ...row,
    [spec.category]: String(row[spec.category] ?? ""),
    [spec.value]: Number(row[spec.value]),
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <RPieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <Pie
          data={parsed}
          dataKey={spec.value}
          nameKey={spec.category}
          cx="50%"
          cy="50%"
          outerRadius="75%"
          innerRadius="0%"
        >
          {parsed.map((_, i) => (
            <Cell key={i} fill={seriesColor(i)} />
          ))}
        </Pie>
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </RPieChart>
    </ResponsiveContainer>
  );
}
