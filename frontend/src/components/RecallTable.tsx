"use client";

import { useEffect, useMemo, useState } from "react";
import { format, parseISO } from "date-fns";
import { ArrowDown, ArrowUp, ChevronsUpDown, Mail, MessageSquare, Phone } from "lucide-react";
import { toast } from "sonner";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { RecallPriorityBadge } from "@/components/RecallPriorityBadge";
import { fmtInt, fmtUSD } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { Priority, RecallQueueRow } from "@/lib/types";

const PRIORITY_RANK: Record<Priority, number> = { urgent: 4, high: 3, medium: 2, low: 1 };
const PAGE_SIZE = 25;

type SortKey =
  | "patient"
  | "recall_priority"
  | "last_visit_date"
  | "recency_days"
  | "total_revenue"
  | "ltv_tier"
  | "last_provider";

function patientName(r: RecallQueueRow) {
  return `${r.first_name} ${r.last_name}`;
}

export function RecallTable({ rows }: { rows: RecallQueueRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("recall_priority");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);

  // Reset to the first page whenever the (filtered) row set changes.
  useEffect(() => setPage(0), [rows]);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    const copy = [...rows];
    copy.sort((a, b) => {
      switch (sortKey) {
        case "patient":
          return dir * `${a.last_name} ${a.first_name}`.localeCompare(`${b.last_name} ${b.first_name}`);
        case "recall_priority": {
          const d = PRIORITY_RANK[a.recall_priority] - PRIORITY_RANK[b.recall_priority];
          return d !== 0 ? dir * d : a.recency_days - b.recency_days; // tiebreak: most recent first
        }
        case "last_visit_date":
          return dir * a.last_visit_date.localeCompare(b.last_visit_date);
        case "recency_days":
          return dir * (a.recency_days - b.recency_days);
        case "total_revenue":
          return dir * (Number(a.total_revenue) - Number(b.total_revenue));
        case "ltv_tier":
          return dir * a.ltv_tier.localeCompare(b.ltv_tier);
        case "last_provider":
          return dir * (a.last_provider_name ?? "").localeCompare(b.last_provider_name ?? "");
        default:
          return 0;
      }
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const current = Math.min(page, pageCount - 1);
  const slice = sorted.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE);
  const from = sorted.length === 0 ? 0 : current * PAGE_SIZE + 1;
  const to = Math.min(sorted.length, (current + 1) * PAGE_SIZE);

  function toggle(k: SortKey) {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir(k === "patient" || k === "ltv_tier" || k === "last_provider" ? "asc" : "desc");
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
    <div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Actions</TableHead>
            {head("Patient", "patient")}
            {head("Priority", "recall_priority")}
            {head("Last visit", "last_visit_date")}
            {head("Recency", "recency_days", "right")}
            {head("Total revenue", "total_revenue", "right")}
            {head("LTV tier", "ltv_tier")}
            {head("Last provider", "last_provider")}
          </TableRow>
        </TableHeader>
        <TableBody>
          {slice.map((r) => {
            const name = patientName(r);
            return (
              <TableRow key={r.patient_id}>
                <TableCell>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 active:bg-slate-200 dark:active:bg-slate-700"
                      title="SMS"
                      aria-label={`Send SMS to ${name}`}
                      onClick={() => toast.success(`SMS queued to ${name}`)}
                    >
                      <MessageSquare className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 active:bg-slate-200 dark:active:bg-slate-700"
                      title="Call"
                      aria-label={`Call ${name}`}
                      onClick={() => toast(`Calling ${name}…`)}
                    >
                      <Phone className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 active:bg-slate-200 dark:active:bg-slate-700"
                      title="Email"
                      aria-label={`Email ${name}`}
                      onClick={() => toast.success(`Email drafted to ${name}`)}
                    >
                      <Mail className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </TableCell>
                <TableCell className="font-medium">{name}</TableCell>
                <TableCell>
                  <RecallPriorityBadge priority={r.recall_priority} />
                </TableCell>
                <TableCell>{format(parseISO(r.last_visit_date), "MMM d, yyyy")}</TableCell>
                <TableCell className="text-right tabular-nums">{fmtInt(r.recency_days)}d</TableCell>
                <TableCell className="text-right tabular-nums">{fmtUSD(r.total_revenue, { dp: 0 })}</TableCell>
                <TableCell className="capitalize text-muted-foreground">{r.ltv_tier}</TableCell>
                <TableCell className="text-muted-foreground">{r.last_provider_name ?? "—"}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm text-muted-foreground">
        <span>
          {from}–{to} of {fmtInt(sorted.length)}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={current >= pageCount - 1}
            onClick={() => setPage(current + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
