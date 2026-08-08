"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { fmtInt, fmtPct, fmtUSD, sumDecimals } from "@/lib/money";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";
import { DataThrough } from "@/components/DataThrough";
import { SectionHeader } from "@/components/SectionHeader";
import { KPICard } from "@/components/KPICard";
import { ErrorCard } from "@/components/ErrorCard";
import { ProvidersTable } from "@/components/ProvidersTable";
import { ProviderDrillInDialog } from "@/components/ProviderDrillInDialog";
import type { ProviderScorecardRow } from "@/lib/types";

const rph = (r: ProviderScorecardRow) => Number(r.revenue_per_hour_ttm ?? 0);

export default function ProvidersPage() {
  const scorecard = useQuery({ queryKey: ["provider-scorecard"], queryFn: api.getProviderScorecard });
  const [selected, setSelected] = useState<ProviderScorecardRow | null>(null);

  const summary = useMemo(() => {
    const rows = scorecard.data;
    if (!rows || rows.length === 0) return null;
    const totalRevenue = sumDecimals(rows.map((r) => r.revenue_ttm));
    const totalHours = sumDecimals(rows.map((r) => r.productive_hours_ttm));
    const totalVisits = rows.reduce((a, r) => a + r.visits_ttm, 0);

    const busiest = rows.reduce((b, r) => (r.visits_ttm > b.visits_ttm ? r : b), rows[0]);
    const top = rows.reduce((t, r) => (rph(r) > rph(t) ? r : t), rows[0]);
    const withRph = rows.filter((r) => r.revenue_per_hour_ttm !== null);
    const low = withRph.length
      ? withRph.reduce((m, r) => (rph(r) < rph(m) ? r : m), withRph[0])
      : null;
    const withCross = rows.filter((r) => r.cross_sell_rate_ttm !== null);
    const lowestCross = withCross.length
      ? withCross.reduce(
          (m, r) => (Number(r.cross_sell_rate_ttm) < Number(m.cross_sell_rate_ttm) ? r : m),
          withCross[0],
        )
      : null;
    const dataThrough = rows.reduce<string | null>(
      (m, r) => (r.last_visit_date && (m === null || r.last_visit_date > m) ? r.last_visit_date : m),
      null,
    );

    return {
      teamRevPerHour: totalHours.isZero() ? null : totalRevenue.div(totalHours),
      totalRevenue,
      totalVisits,
      busiest,
      lowestCross,
      top,
      low,
      dataThrough,
    };
  }, [scorecard.data]);

  return (
    <div className="space-y-6">
      <PageHeader title="Providers" right={<DataThrough />} />

      {scorecard.isError ? (
        <ErrorCard message="Couldn't load provider scorecard." onRetry={() => scorecard.refetch()} />
      ) : scorecard.isLoading ? (
        <ProvidersSkeleton />
      ) : !summary || !scorecard.data ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No providers yet.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="space-y-4">
            <SectionHeader title="Team performance" subtitle="Trailing 12 months" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <KPICard
                label="Team avg revenue/hour"
                value={summary.teamRevPerHour ? fmtUSD(summary.teamRevPerHour.toString(), { dp: 0 }) : "—"}
                emphasis
              />
              <KPICard label="Total revenue" value={fmtUSD(summary.totalRevenue.toString(), { dp: 0 })} />
              <KPICard label="Total visits" value={fmtInt(summary.totalVisits)} />
              <KPICard
                label="Busiest provider"
                value={summary.busiest.provider_name}
                valueSize="lg"
                deltaLabel={`${fmtInt(summary.busiest.visits_ttm)} visits`}
              />
              <KPICard
                label="Lowest cross-sell"
                value={summary.lowestCross ? summary.lowestCross.provider_name : "—"}
                valueSize="lg"
                deltaLabel={
                  summary.lowestCross
                    ? `${fmtPct(summary.lowestCross.cross_sell_rate_ttm)} cross-sell`
                    : undefined
                }
              />
            </div>
          </div>

          <Card>
            <CardContent className="p-4 sm:p-5">
              {/* Stacks with a horizontal rule on mobile; side-by-side with a
                  vertical divider from `sm` up. */}
              <div className="grid grid-cols-1 divide-y divide-slate-200 dark:divide-slate-800 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
                <div className="pb-4 sm:pb-0 sm:pr-5">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Top performer
                  </p>
                  <p className="mt-1 font-semibold">{summary.top.provider_name}</p>
                  <p className="text-sm text-muted-foreground">
                    {fmtUSD(summary.top.revenue_per_hour_ttm, { dp: 0 })} / productive hour
                  </p>
                </div>
                <div className="pt-4 sm:pl-5 sm:pt-0">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Lowest performer
                  </p>
                  <p className="mt-1 font-semibold">{summary.low ? summary.low.provider_name : "—"}</p>
                  <p className="text-sm text-muted-foreground">
                    {summary.low ? `${fmtUSD(summary.low.revenue_per_hour_ttm, { dp: 0 })} / productive hour` : ""}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="overflow-hidden">
            <CardContent className="p-0">
              <ProvidersTable rows={scorecard.data} onRowClick={setSelected} />
            </CardContent>
          </Card>
        </>
      )}

      <ProviderDrillInDialog provider={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function ProvidersSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="space-y-2 p-4 sm:p-5">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-28" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}
