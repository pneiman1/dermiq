"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { format, parseISO, subDays } from "date-fns";

import { api } from "@/lib/api";
import { fmtInt, fmtUSD } from "@/lib/money";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { RevenueLineChart, type RevenuePoint } from "@/components/charts/RevenueLineChart";
import type { ProviderScorecardRow } from "@/lib/types";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/50 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-lg font-semibold">{value}</p>
    </div>
  );
}

export function ProviderDrillInDialog({
  provider,
  onClose,
}: {
  provider: ProviderScorecardRow | null;
  onClose: () => void;
}) {
  const win = useMemo(() => {
    const today = new Date();
    const f = (x: Date) => format(x, "yyyy-MM-dd");
    return { today: f(today), wideStart: f(subDays(today, 220)) };
  }, []);

  // Shares the key shape with the Executive tab, so an already-fetched provider hits cache.
  const q = useQuery({
    queryKey: ["provider-revenue-daily", provider?.provider_id, win.wideStart, win.today],
    queryFn: () =>
      api.getProviderRevenueDaily(provider!.provider_id, {
        startDate: win.wideStart,
        endDate: win.today,
      }),
    enabled: !!provider,
  });

  const chartData: RevenuePoint[] = useMemo(() => {
    const rows = q.data;
    if (!rows || rows.length === 0) return [];
    const maxDate = rows.reduce((m, r) => (r.date_key > m ? r.date_key : m), rows[0].date_key);
    const cut = format(subDays(parseISO(maxDate), 90), "yyyy-MM-dd");
    return rows
      .filter((r) => r.date_key > cut)
      .sort((a, b) => a.date_key.localeCompare(b.date_key))
      .map((r) => ({ date: r.date_key, value: Number(r.total_revenue) }));
  }, [q.data]);

  return (
    <Dialog
      open={!!provider}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-w-3xl">
        {provider && (
          <>
            <DialogHeader>
              <DialogTitle>{provider.provider_name}</DialogTitle>
              <DialogDescription>
                {provider.provider_role}
                {provider.specialties ? ` · ${provider.specialties}` : ""}
              </DialogDescription>
            </DialogHeader>

            <div className="grid grid-cols-3 gap-4">
              <Stat label="Visits (TTM)" value={fmtInt(provider.visits_ttm)} />
              <Stat label="Avg ticket" value={fmtUSD(provider.avg_ticket_ttm, { dp: 2 })} />
              <Stat label="Rev / hour" value={fmtUSD(provider.revenue_per_hour_ttm, { dp: 0 })} />
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">Net revenue — last 90 days</p>
              {q.isLoading ? (
                <Skeleton className="h-[300px] w-full" />
              ) : q.isError ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  Couldn&apos;t load this provider&apos;s trend.
                </p>
              ) : chartData.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  No recent visits to chart.
                </p>
              ) : (
                <RevenueLineChart data={chartData} />
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
