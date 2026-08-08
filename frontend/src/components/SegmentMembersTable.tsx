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
import {
  DesktopTable,
  MobileCard,
  MobileCardList,
  MobileSortBar,
} from "@/components/MobileCardList";
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

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "total_revenue", label: "LTV" },
  { key: "name", label: "Patient" },
  { key: "ltv_tier", label: "Tier" },
  { key: "recency_tier", label: "Recency" },
  { key: "last_visit_date", label: "Last visit" },
];

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
    // -mx-4 lets the card list run edge-to-edge inside the full-screen mobile
    // dialog; the desktop dialog keeps its own padding.
    <div className="-mx-4 max-h-none overflow-y-auto sm:mx-0 sm:max-h-[60vh]">
      <MobileSortBar
        options={SORT_OPTIONS}
        sortKey={sortKey}
        sortDir={sortDir}
        onKeyChange={(k) => {
          setSortKey(k);
          setSortDir(k === "total_revenue" ? "desc" : "asc");
        }}
        onDirToggle={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
      />
      <MobileCardList>
        {sorted.map((m) => (
          <MobileCard
            key={m.patient_id}
            title={`${m.first_name} ${m.last_name}`}
            subtitle={m.dominant_provider_name ?? undefined}
            right={<Badge variant={LTV_VARIANT[m.ltv_tier] ?? "secondary"}>{m.ltv_tier}</Badge>}
            fields={[
              { label: "LTV", value: fmtUSD(m.total_revenue, { dp: 0 }) },
              {
                label: "Recency",
                value: m.recency_tier ? (
                  <Badge variant={RECENCY_VARIANT[m.recency_tier] ?? "secondary"}>
                    {m.recency_tier}
                  </Badge>
                ) : (
                  "—"
                ),
              },
              {
                label: "Last visit",
                value: m.last_visit_date
                  ? format(parseISO(m.last_visit_date), "MMM d, yyyy")
                  : "—",
                wide: true,
              },
            ]}
          />
        ))}
      </MobileCardList>

      <DesktopTable>
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
      </DesktopTable>
    </div>
  );
}
