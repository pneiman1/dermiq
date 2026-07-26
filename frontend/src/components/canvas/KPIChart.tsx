"use client";

import { fmtInt, fmtPct, fmtUSD } from "@/lib/money";
import type { CanvasRow, KpiSpec } from "@/lib/types";

const NoData = () => (
  <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
    No data for this view.
  </div>
);

// A value "looks like money" when the measure name hints at revenue/cost/price/ltv/etc.
function looksLikeMoney(measure: string): boolean {
  return /revenue|rev_|amount|cost|price|ltv|ticket|value|spend|cac|margin/i.test(measure);
}

export function KPIChart({ spec, data }: { spec: KpiSpec; data: CanvasRow[] }) {
  const row = data[0];
  const value = row?.value;
  if (!row || value === null || value === undefined) return <NoData />;

  const isMoney = looksLikeMoney(spec.measure);
  const num = Number(value);
  const display = isMoney
    ? fmtUSD(String(value), { dp: 0 })
    : Number.isFinite(num)
      ? fmtInt(num)
      : String(value);

  const deltaRaw = row.delta_pct;
  const showDelta =
    spec.comparison_period != null && deltaRaw !== null && deltaRaw !== undefined;
  const deltaNum = Number(deltaRaw);
  const isUp = deltaNum >= 0;

  const prior = row.prior_value;
  const priorDisplay =
    prior === null || prior === undefined
      ? null
      : isMoney
        ? fmtUSD(String(prior), { dp: 0 })
        : fmtInt(Number(prior));

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-4 text-center">
      <div className="text-4xl font-semibold tracking-tight text-foreground">{display}</div>
      {showDelta && (
        <div className="flex flex-col items-center gap-1">
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
              isUp
                ? "bg-emerald-50 text-emerald-700"
                : "bg-rose-50 text-rose-700"
            }`}
          >
            {isUp ? "▲" : "▼"} {fmtPct(String(deltaRaw))}
          </span>
          {priorDisplay && (
            <span className="text-xs text-muted-foreground">vs. {priorDisplay} prior</span>
          )}
        </div>
      )}
    </div>
  );
}
