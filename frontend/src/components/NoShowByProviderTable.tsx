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
import { fmtInt, fmtPct } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { NoShowByProviderRow } from "@/lib/types";

type SortKey = "provider_name" | "scheduled" | "no_show" | "no_show_rate" | "cancel_rate";

function num(r: NoShowByProviderRow, k: Exclude<SortKey, "provider_name">): number {
  const v = r[k];
  return v === null || v === undefined ? 0 : Number(v);
}

export function NoShowByProviderTable({ rows }: { rows: NoShowByProviderRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("no_show_rate");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const maxRate = useMemo(
    () => rows.reduce((m, r) => Math.max(m, num(r, "no_show_rate")), 0),
    [rows],
  );

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) =>
      sortKey === "provider_name"
        ? dir * a.provider_name.localeCompare(b.provider_name)
        : dir * (num(a, sortKey) - num(b, sortKey)),
    );
  }, [rows, sortKey, sortDir]);

  function toggle(k: SortKey) {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
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
          {head("Scheduled", "scheduled")}
          {head("No-shows", "no_show")}
          {head("No-show rate", "no_show_rate", "left")}
          {head("Cancel rate", "cancel_rate")}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((r) => {
          const rate = num(r, "no_show_rate");
          const pct = maxRate > 0 ? (rate / maxRate) * 100 : 0;
          return (
            <TableRow key={r.provider_id}>
              <TableCell>
                <div className="font-medium">{r.provider_name}</div>
              </TableCell>
              <TableCell className="text-right tabular-nums">{fmtInt(r.scheduled)}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtInt(r.no_show)}</TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-rose-500" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="tabular-nums text-slate-700 dark:text-slate-300">
                    {fmtPct(r.no_show_rate)}
                  </span>
                </div>
              </TableCell>
              <TableCell className="text-right tabular-nums">{fmtPct(r.cancel_rate)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
