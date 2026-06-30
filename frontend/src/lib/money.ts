// Helpers for the Decimal-as-string API contract. Always parse through decimal.js
// before formatting so we never lose precision client-side.
import Decimal from "decimal.js";

export function toDecimal(v: string | null | undefined): Decimal | null {
  if (v === null || v === undefined || v === "") return null;
  try {
    return new Decimal(v);
  } catch {
    return null;
  }
}

const usd0 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const usd2 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Format a money string as USD. `dp: 0` for totals/KPIs, `dp: 2` for ticket values. */
export function fmtUSD(v: string | null | undefined, opts?: { dp?: 0 | 2 }): string {
  const d = toDecimal(v);
  if (d === null) return "—";
  return (opts?.dp === 2 ? usd2 : usd0).format(d.toNumber());
}

/** Format a fractional rate string (e.g. "0.0357") as a percentage ("3.6%"). */
export function fmtPct(v: string | null | undefined, dp = 1): string {
  const d = toDecimal(v);
  if (d === null) return "—";
  return `${d.times(100).toFixed(dp)}%`;
}

/** Format a ratio string (e.g. "31.857") as "31.9x". */
export function fmtRatio(v: string | null | undefined, dp = 1): string {
  const d = toDecimal(v);
  if (d === null) return "—";
  return `${d.toFixed(dp)}x`;
}

/** Format an integer count with thousands separators. */
export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("en-US").format(v);
}

const usdCompact = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Compact currency for chart axes, e.g. "$1.2M". Takes a number. */
export function fmtCompactUSD(n: number): string {
  return usdCompact.format(n);
}

/** Sum an array of Decimal-as-string values without precision loss. */
export function sumDecimals(values: (string | null | undefined)[]): Decimal {
  return values.reduce<Decimal>((acc, v) => {
    const d = toDecimal(v);
    return d ? acc.plus(d) : acc;
  }, new Decimal(0));
}

/** Percentage change from prior to current; null when prior is zero. */
export function pctChange(current: Decimal, prior: Decimal): number | null {
  if (prior.isZero()) return null;
  return current.minus(prior).div(prior).times(100).toNumber();
}

/** Weight a set of Decimal-as-string values; null when there's no weight. */
export function weightedAvg(items: { value: string | null; weight: number }[]): Decimal | null {
  let num = new Decimal(0);
  let den = 0;
  for (const it of items) {
    const v = toDecimal(it.value);
    if (v && it.weight > 0) {
      num = num.plus(v.times(it.weight));
      den += it.weight;
    }
  }
  return den > 0 ? num.div(den) : null;
}
