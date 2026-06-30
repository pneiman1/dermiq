"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtInt, fmtPct, fmtUSD } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { ProviderScorecardRow } from "@/lib/types";

type SortKey =
  | "provider_name"
  | "revenue_per_hour_ttm"
  | "revenue_ttm"
  | "visits_ttm"
  | "avg_ticket_ttm"
  | "cross_sell_rate_ttm"
  | "skincare_attach_rate_ttm";

function num(r: ProviderScorecardRow, k: Exclude<SortKey, "provider_name">): number | null {
  const v = r[k];
  return v === null || v === undefined ? null : Number(v);
}

export function ProvidersTable({
  rows,
  onRowClick,
}: {
  rows: ProviderScorecardRow[];
  onRowClick: (r: ProviderScorecardRow) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("revenue_per_hour_ttm");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const maxRevPerHour = useMemo(
    () => rows.reduce((m, r) => Math.max(m, num(r, "revenue_per_hour_ttm") ?? 0), 0),
    [rows],
  );

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      if (sortKey === "provider_name") {
        return sortDir === "asc"
          ? a.provider_name.localeCompare(b.provider_name)
          : b.provider_name.localeCompare(a.provider_name);
      }
      const av = num(a, sortKey);
      const bv = num(b, sortKey);
      if (av === null && bv === null) return 0;
      if (av === null) return 1; // nulls last regardless of direction
      if (bv === null) return -1;
      return sortDir === "asc" ? av - bv : bv - av;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  function toggle(k: SortKey) {
    if (k === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setSortDir(k === "provider_name" ? "asc" : "desc");
    }
  }

  const head = (label: string, k: SortKey, align: "left" | "right" = "right") => {
    const active = sortKey === k;
    const Icon = !active ? ChevronsUpDown : sortDir === "asc" ? ArrowUp : ArrowDown;
    return (
      <TableHead
        className={cn("cursor-pointer select-none", align === "right" && "text-right")}
        onClick={() => toggle(k)}
      >
        <span className={cn("inline-flex items-center gap-1", align === "right" && "flex-row-reverse")}>
          {label}
          <Icon className={cn("h-3 w-3", active ? "text-foreground" : "text-muted-foreground/40")} />
        </span>
      </TableHead>
    );
  };

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {head("Provider", "provider_name", "left")}
          {head("Rev / hour", "revenue_per_hour_ttm", "left")}
          {head("Revenue", "revenue_ttm")}
          {head("Visits", "visits_ttm")}
          {head("Avg ticket", "avg_ticket_ttm")}
          {head("Cross-sell", "cross_sell_rate_ttm")}
          {head("Skincare attach", "skincare_attach_rate_ttm")}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((r) => {
          const rph = num(r, "revenue_per_hour_ttm");
          const pct = rph !== null && maxRevPerHour > 0 ? (rph / maxRevPerHour) * 100 : 0;
          return (
            <TableRow key={r.provider_id} onClick={() => onRowClick(r)} className="cursor-pointer">
              <TableCell>
                <div className="font-medium">{r.provider_name}</div>
                <div className="text-xs text-muted-foreground">{r.provider_role}</div>
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="tabular-nums text-slate-700 dark:text-slate-300">
                    {rph !== null ? fmtUSD(String(rph), { dp: 0 }) : "—"}
                  </span>
                </div>
              </TableCell>
              <TableCell className="text-right tabular-nums">{fmtUSD(r.revenue_ttm, { dp: 0 })}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtInt(r.visits_ttm)}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtUSD(r.avg_ticket_ttm, { dp: 2 })}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtPct(r.cross_sell_rate_ttm)}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtPct(r.skincare_attach_rate_ttm)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
