"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { fmtInt, fmtPct, fmtUSD } from "@/lib/money";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/PageHeader";
import { DataThrough } from "@/components/DataThrough";
import { KPICard } from "@/components/KPICard";
import { ErrorCard } from "@/components/ErrorCard";
import { SectionHeader } from "@/components/SectionHeader";
import { WasteByServiceBar } from "@/components/charts/WasteByServiceBar";
import { cn } from "@/lib/utils";
import type { ExpiringItem, InventoryStatusRow } from "@/lib/types";

const STATUS_BADGE: Record<InventoryStatusRow["stock_status"], { variant: "danger" | "warning" | "success" | "secondary"; label: string }> = {
  out: { variant: "danger", label: "Out" },
  low: { variant: "warning", label: "Low" },
  adequate: { variant: "success", label: "Adequate" },
  overstock: { variant: "secondary", label: "Overstock" },
};

const URGENCY: Record<string, { variant: "danger" | "warning" | "secondary"; ring: string; label: string }> = {
  critical: { variant: "danger", ring: "border-l-4 border-l-destructive", label: "Critical" },
  warning: { variant: "warning", ring: "border-l-4 border-l-amber-500", label: "Warning" },
  watch: { variant: "secondary", ring: "border-l-4 border-l-muted-foreground/40", label: "Watch" },
};

function fmtDays(v: string | null): string {
  if (v === null) return "—";
  return `${Math.round(Number(v))} days`;
}

export default function InventoryPage() {
  const summary = useQuery({ queryKey: ["inv-summary"], queryFn: api.getInventorySummary });
  const status = useQuery({ queryKey: ["inv-status"], queryFn: api.getInventoryStatus });
  const waste = useQuery({ queryKey: ["inv-waste"], queryFn: () => api.getInventoryWaste(50) });
  const trueMargin = useQuery({ queryKey: ["inv-true-margin"], queryFn: api.getInventoryTrueMargin });
  const expiring = useQuery({ queryKey: ["inv-expiring", 60], queryFn: () => api.getInventoryExpiring(60) });

  const wastePoints = useMemo(() => {
    return (waste.data ?? [])
      .filter((r) => r.waste_rate !== null)
      .slice(0, 10)
      .map((r) => ({
        name: r.service_name.replace(/ consumable$/, ""),
        wasteRate: Number(r.waste_rate) * 100,
        wasteCost: Number(r.waste_cost_ttm),
      }));
  }, [waste.data]);

  const expiringByUrgency = useMemo(() => {
    const rows = (expiring.data ?? []).filter((r) => r.urgency_level !== "future");
    const groups: Record<string, ExpiringItem[]> = { critical: [], warning: [], watch: [] };
    for (const r of rows) groups[r.urgency_level]?.push(r);
    return groups;
  }, [expiring.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Inventory"
        subtitle="Consumables, true margin, waste, and expiry"
        right={<DataThrough />}
      />

      {summary.isError ? (
        <ErrorCard message="Couldn't load inventory." onRetry={() => summary.refetch()} />
      ) : (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <KPICard
              label="Total inventory value"
              value={summary.data ? fmtUSD(summary.data.total_inventory_value, { dp: 0 }) : "—"}
              loading={summary.isLoading}
            />
            <KPICard
              label="Waste rate (TTM)"
              value={summary.data ? fmtPct(summary.data.waste_rate_ttm) : "—"}
              loading={summary.isLoading}
              emphasis
            />
            <KPICard
              label="Waste value (TTM)"
              value={summary.data ? fmtUSD(summary.data.waste_value_ttm, { dp: 0 }) : "—"}
              loading={summary.isLoading}
              deltaLabel="overage + expiry write-offs"
            />
            <KPICard
              label="Items below par"
              value={summary.data ? fmtInt(summary.data.items_below_par) : "—"}
              loading={summary.isLoading}
            />
            <KPICard
              label="Expiring in 30 days"
              value={summary.data ? fmtInt(summary.data.expiring_30d_count) : "—"}
              loading={summary.isLoading}
              deltaLabel={summary.data ? `${fmtUSD(summary.data.expiring_30d_value, { dp: 0 })} at risk` : undefined}
            />
          </div>

          {/* Section 1: Waste by SKU */}
          <div className="space-y-3">
            <SectionHeader title="Waste by SKU" subtitle="Overage as a share of consumption (TTM), worst offenders first" />
            <Card>
              <CardContent className="p-4">
                {waste.isLoading ? (
                  <Skeleton className="h-64 w-full" />
                ) : wastePoints.length === 0 ? (
                  <p className="py-12 text-center text-sm text-muted-foreground">No waste recorded.</p>
                ) : (
                  <WasteByServiceBar data={wastePoints} />
                )}
              </CardContent>
            </Card>
          </div>

          {/* Section 3: True margin surprises (the headline) */}
          <div className="space-y-3">
            <SectionHeader
              title="True margin surprises"
              subtitle="Real cost-of-goods vs list price — biggest gaps between catalog and true margin first"
            />
            <Card className="overflow-hidden">
              <CardContent className="p-0">
                {trueMargin.isLoading ? (
                  <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Service</TableHead>
                        <TableHead className="text-right">Revenue TTM</TableHead>
                        <TableHead className="text-right">Consumables cost</TableHead>
                        <TableHead className="text-right">True margin</TableHead>
                        <TableHead className="text-right">Catalog margin</TableHead>
                        <TableHead className="text-right">Δ (pts)</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(trueMargin.data ?? []).map((r) => {
                        const delta =
                          r.catalog_margin_pct !== null && r.true_margin_pct !== null
                            ? (Number(r.catalog_margin_pct) - Number(r.true_margin_pct)) * 100
                            : null;
                        return (
                          <TableRow key={r.service_code}>
                            <TableCell className="font-medium">{r.service_name}</TableCell>
                            <TableCell className="text-right tabular-nums">{fmtUSD(r.revenue_ttm, { dp: 0 })}</TableCell>
                            <TableCell className="text-right tabular-nums text-muted-foreground">{fmtUSD(r.consumables_cost_ttm, { dp: 0 })}</TableCell>
                            <TableCell className="text-right tabular-nums font-medium">{fmtPct(r.true_margin_pct)}</TableCell>
                            <TableCell className="text-right tabular-nums text-muted-foreground">{fmtPct(r.catalog_margin_pct)}</TableCell>
                            <TableCell className={cn("text-right tabular-nums font-semibold", delta !== null && delta >= 5 ? "text-destructive" : "text-muted-foreground")}>
                              {delta !== null ? `-${delta.toFixed(1)}` : "—"}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Section 2: Stock status */}
          <div className="space-y-3">
            <SectionHeader title="Stock status" subtitle="On-hand vs par level — out and low first" />
            <Card className="overflow-hidden">
              <CardContent className="p-0">
                {status.isLoading ? (
                  <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>SKU</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead className="text-right">On hand</TableHead>
                        <TableHead className="text-right">Par</TableHead>
                        <TableHead className="text-right">Days of supply</TableHead>
                        <TableHead className="text-right">Value</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(status.data ?? []).map((r) => {
                        const b = STATUS_BADGE[r.stock_status];
                        const alert = r.stock_status === "out" || r.stock_status === "low";
                        return (
                          <TableRow key={r.sku} className={cn(alert && "bg-destructive/5")}>
                            <TableCell className="font-medium">{r.sku_name.replace(/ consumable$/, "")}</TableCell>
                            <TableCell className="text-muted-foreground">{r.category.replace(/_/g, " ")}</TableCell>
                            <TableCell className="text-right tabular-nums">{fmtInt(Math.round(Number(r.on_hand_quantity)))}</TableCell>
                            <TableCell className="text-right tabular-nums text-muted-foreground">{fmtInt(Math.round(Number(r.par_level)))}</TableCell>
                            <TableCell className="text-right tabular-nums">{fmtDays(r.days_of_supply)}</TableCell>
                            <TableCell className="text-right tabular-nums">{fmtUSD(r.on_hand_value, { dp: 0 })}</TableCell>
                            <TableCell><Badge variant={b.variant}>{b.label}</Badge></TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Section 4: Expiring soon */}
          <div className="space-y-3">
            <SectionHeader title="Expiring soon" subtitle="On-hand lots within 60 days of expiry, by urgency" />
            {expiring.isLoading ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-28 w-full" />)}</div>
            ) : (["critical", "warning", "watch"] as const).every((k) => expiringByUrgency[k].length === 0) ? (
              <Card><CardContent className="p-6"><p className="text-sm text-muted-foreground">Nothing expiring in the next 60 days.</p></CardContent></Card>
            ) : (
              <div className="space-y-4">
                {(["critical", "warning", "watch"] as const).map((level) =>
                  expiringByUrgency[level].length === 0 ? null : (
                    <div key={level} className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant={URGENCY[level].variant}>{URGENCY[level].label}</Badge>
                        <span className="text-xs text-muted-foreground">{expiringByUrgency[level].length} lot{expiringByUrgency[level].length === 1 ? "" : "s"}</span>
                      </div>
                      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {expiringByUrgency[level].map((r) => (
                          <Card key={r.lot_id} className={URGENCY[level].ring}>
                            <CardContent className="p-4">
                              <div className="flex items-baseline justify-between gap-2">
                                <p className="truncate text-sm font-medium">{r.sku_name.replace(/ consumable$/, "")}</p>
                                <span className="shrink-0 text-sm font-semibold tabular-nums">{fmtUSD(r.estimated_value_at_risk, { dp: 0 })}</span>
                              </div>
                              <p className="mt-1 font-mono text-xs text-muted-foreground">{r.lot_number}</p>
                              <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                                <span>{Math.round(Number(r.quantity_remaining))} {r.category === "injectable" ? "units" : "on hand"}</span>
                                <span className="font-medium text-foreground">{r.days_to_expiry} days left</span>
                              </div>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    </div>
                  ),
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
