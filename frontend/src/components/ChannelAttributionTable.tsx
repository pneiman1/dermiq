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
import { ChannelHealthBadge } from "@/components/ChannelHealthBadge";
import { channelLabel } from "@/lib/channels";
import { fmtInt, fmtRatio, fmtUSD } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { ChannelAttributionRow } from "@/lib/types";

type SortKey =
  | "channel"
  | "patients_acquired_ttm"
  | "spend_ttm"
  | "cac_ttm"
  | "avg_ltv_run_rate_ttm"
  | "ltv_cac_ratio_ttm"
  | "channel_health";

type NumKey = Exclude<SortKey, "channel" | "channel_health">;

function num(r: ChannelAttributionRow, k: NumKey): number | null {
  const v = r[k];
  return v === null || v === undefined ? null : Number(v);
}

export function ChannelAttributionTable({ rows }: { rows: ChannelAttributionRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("spend_ttm");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      if (sortKey === "channel") {
        const av = channelLabel(a.acquisition_channel);
        const bv = channelLabel(b.acquisition_channel);
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      if (sortKey === "channel_health") {
        return sortDir === "asc"
          ? a.channel_health.localeCompare(b.channel_health)
          : b.channel_health.localeCompare(a.channel_health);
      }
      const av = num(a, sortKey);
      const bv = num(b, sortKey);
      if (av === null && bv === null) return 0;
      if (av === null) return 1; // nulls last
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
      setSortDir(k === "channel" || k === "channel_health" ? "asc" : "desc");
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
          {head("Channel", "channel", "left")}
          {head("Acquired", "patients_acquired_ttm")}
          {head("Spend", "spend_ttm")}
          {head("CAC", "cac_ttm")}
          {head("Avg LTV run-rate", "avg_ltv_run_rate_ttm")}
          {head("LTV:CAC", "ltv_cac_ratio_ttm")}
          {head("Health", "channel_health", "left")}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((r) => (
          <TableRow key={r.acquisition_channel}>
            <TableCell className="font-medium">{channelLabel(r.acquisition_channel)}</TableCell>
            <TableCell className="text-right tabular-nums">{fmtInt(r.patients_acquired_ttm)}</TableCell>
            <TableCell className="text-right tabular-nums">{fmtUSD(r.spend_ttm, { dp: 0 })}</TableCell>
            <TableCell className="text-right tabular-nums">
              {r.cac_ttm !== null ? fmtUSD(r.cac_ttm, { dp: 0 }) : "—"}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {r.avg_ltv_run_rate_ttm !== null ? fmtUSD(r.avg_ltv_run_rate_ttm, { dp: 0 }) : "—"}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {r.ltv_cac_ratio_ttm !== null ? fmtRatio(r.ltv_cac_ratio_ttm) : "—"}
            </TableCell>
            <TableCell>
              <ChannelHealthBadge health={r.channel_health} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
