"use client";

import { useMemo, useState } from "react";
import { format, parseISO } from "date-fns";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { fmtUSD } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { PatientSegmentMember } from "@/lib/types";

type SortKey = "name" | "total_revenue" | "ltv_tier" | "recency_tier" | "last_visit_date";

const LTV_VARIANT: Record<string, "default" | "success" | "secondary" | "outline"> = {
  vip: "default",
  high: "success",
  standard: "secondary",
  low: "outline",
};
const RECENCY_VARIANT: Record<string, "success" | "warning" | "danger" | "secondary"> = {
  active: "success",
  lapsing: "warning",
  lapsed: "danger",
  dormant: "secondary",
};

export function SegmentMembersTable({ rows }: { rows: PatientSegmentMember[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("total_revenue");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      switch (sortKey) {
        case "name":
          return dir * `${a.last_name} ${a.first_name}`.localeCompare(`${b.last_name} ${b.first_name}`);
        case "total_revenue":
          return dir * (Number(a.total_revenue) - Number(b.total_revenue));
        case "ltv_tier":
          return dir * a.ltv_tier.localeCompare(b.ltv_tier);
        case "recency_tier":
          return dir * (a.recency_tier ?? "").localeCompare(b.recency_tier ?? "");
        case "last_visit_date":
          return dir * (a.last_visit_date ?? "").localeCompare(b.last_visit_date ?? "");
        default:
          return 0;
      }
    });
  }, [rows, sortKey, sortDir]);

  function toggle(k: SortKey) {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir(k === "total_revenue" ? "desc" : "asc");
    }
  }

  const head = (label: string, k: SortKey, align: "left" | "right" = "left") => {
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
    <div className="max-h-[60vh] overflow-y-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {head("Patient", "name")}
            {head("LTV", "total_revenue", "right")}
            {head("Tier", "ltv_tier")}
            {head("Recency", "recency_tier")}
            {head("Last visit", "last_visit_date")}
            <TableHead>Provider</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((m) => (
            <TableRow key={m.patient_id}>
              <TableCell className="font-medium">
                {m.first_name} {m.last_name}
              </TableCell>
              <TableCell className="text-right tabular-nums">{fmtUSD(m.total_revenue, { dp: 0 })}</TableCell>
              <TableCell>
                <Badge variant={LTV_VARIANT[m.ltv_tier] ?? "secondary"}>{m.ltv_tier}</Badge>
              </TableCell>
              <TableCell>
                {m.recency_tier ? (
                  <Badge variant={RECENCY_VARIANT[m.recency_tier] ?? "secondary"}>{m.recency_tier}</Badge>
                ) : (
                  "—"
                )}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {m.last_visit_date ? format(parseISO(m.last_visit_date), "MMM d, yyyy") : "—"}
              </TableCell>
              <TableCell className="text-muted-foreground">{m.dominant_provider_name ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
