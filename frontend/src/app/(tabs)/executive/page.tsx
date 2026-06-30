"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useQueries, useQuery } from "@tanstack/react-query";
import { format, getDay, parseISO, subDays } from "date-fns";
import { ChevronRight, PhoneCall } from "lucide-react";

import { api } from "@/lib/api";
import { fmtInt, fmtPct, fmtUSD, pctChange, sumDecimals } from "@/lib/money";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { KPICard } from "@/components/KPICard";
import { ErrorCard } from "@/components/ErrorCard";
import { PageHeader } from "@/components/PageHeader";
import { DataThrough } from "@/components/DataThrough";
import { StoryCallout } from "@/components/StoryCallout";
import { CategoryStackedBar, type CategoryPoint } from "@/components/charts/CategoryStackedBar";
import { RevenueLineChart, type RevenuePoint } from "@/components/charts/RevenueLineChart";

// Comparison is trailing-90d vs the immediately-preceding 90d. Windows are anchored
// on the latest data date (not "today") so each window stays full while the seed
// lags real time.
// TODO: once real tenants have >2 years of history, switch the comparison baseline
// back to true year-over-year (same 90d one year prior) and relabel "vs. prior year".
const DELTA_LABEL = "vs. prior 90 days";

export default function ExecutivePage() {
  // Generous fetch window; comparison windows are sliced from maxDate below.
  const fetchWindow = useMemo(() => {
    const today = new Date();
    const f = (x: Date) => format(x, "yyyy-MM-dd");
    return { today: f(today), wideStart: f(subDays(today, 220)) };
  }, []);

  const revenue = useQuery({
    queryKey: ["revenue-daily", fetchWindow.wideStart, fetchWindow.today],
    queryFn: () => api.getRevenueDaily({ startDate: fetchWindow.wideStart, endDate: fetchWindow.today }),
  });
  const tiers = useQuery({ queryKey: ["patient-tier-summary"], queryFn: api.getPatientTierSummary });
  const scorecard = useQuery({ queryKey: ["provider-scorecard"], queryFn: api.getProviderScorecard });

  const providerIds = scorecard.data?.map((p) => p.provider_id) ?? [];
  const providerQueries = useQueries({
    queries: providerIds.map((id) => ({
      queryKey: ["provider-revenue-daily", id, fetchWindow.wideStart, fetchWindow.today],
      queryFn: () =>
        api.getProviderRevenueDaily(id, { startDate: fetchWindow.wideStart, endDate: fetchWindow.today }),
    })),
  });

  // Window boundaries anchored on the latest data date.
  const win = useMemo(() => {
    const rows = revenue.data;
    if (!rows || rows.length === 0) return null;
    const maxDate = rows.reduce((m, r) => (r.date_day > m ? r.date_day : m), rows[0].date_day);
    const md = parseISO(maxDate);
    const f = (x: Date) => format(x, "yyyy-MM-dd");
    return {
      maxDate,
      curStart: f(subDays(md, 90)), // current = (curStart, maxDate]
      prevStart: f(subDays(md, 180)), // preceding = (prevStart, curStart]
    };
  }, [revenue.data]);

  const kpis = useMemo(() => {
    const rows = revenue.data;
    if (!rows || rows.length === 0 || !win) return null;
    const cur = rows.filter((r) => r.date_day > win.curStart);
    const prev = rows.filter((r) => r.date_day > win.prevStart && r.date_day <= win.curStart);

    const netRev = sumDecimals(cur.map((r) => r.net_revenue));
    const visits = cur.reduce((a, r) => a + r.completed_visits, 0);
    const noShowNum = cur.reduce((a, r) => a + r.no_show_count, 0);
    const noShowDen = cur.reduce((a, r) => a + r.scheduled_appointments, 0);
    const netRevPrev = sumDecimals(prev.map((r) => r.net_revenue));
    const visitsPrev = prev.reduce((a, r) => a + r.completed_visits, 0);

    const sorted = [...cur].sort((a, b) => a.date_day.localeCompare(b.date_day));
    const lineData: RevenuePoint[] = sorted.map((r) => {
      const day = parseISO(r.date_day);
      const start = subDays(day, 27);
      let sum = 0;
      let n = 0;
      for (const x of sorted) {
        const xd = parseISO(x.date_day);
        if (xd >= start && xd <= day) {
          sum += Number(x.net_revenue);
          n += 1;
        }
      }
      return { date: r.date_day, value: Number(r.net_revenue), avg: n ? sum / n : null };
    });

    const categoryData: CategoryPoint[] = rows
      .filter((r) => ![0, 6].includes(getDay(parseISO(r.date_day)))) // weekdays only
      .sort((a, b) => b.date_day.localeCompare(a.date_day)) // newest first
      .slice(0, 30) // last 30 weekday data points
      .sort((a, b) => a.date_day.localeCompare(b.date_day)) // chronological for the chart
      .map((r) => ({
        date: r.date_day,
        injectable: Number(r.rev_injectable),
        device: Number(r.rev_device),
        skincare: Number(r.rev_skincare),
        surgical: Number(r.rev_surgical),
        membership: Number(r.rev_membership),
        consult: Number(r.rev_consult),
      }));

    return {
      netRev,
      visits,
      avgTicket: visits > 0 ? netRev.div(visits) : null,
      noShowRate: noShowDen > 0 ? noShowNum / noShowDen : null,
      revDelta: pctChange(netRev, netRevPrev),
      visitsDelta: visitsPrev > 0 ? ((visits - visitsPrev) / visitsPrev) * 100 : null,
      lineData,
      categoryData,
    };
  }, [revenue.data, win]);

  // Steepest per-provider decline: trailing 90d vs preceding 90d (same basis).
  const providerWatchLoading = scorecard.isLoading || providerQueries.some((q) => q.isLoading);
  let worstProvider: { name: string; pct: number } | null = null;
  let bestProvider: { name: string; pct: number } | null = null;
  if (!providerWatchLoading && scorecard.data && win) {
    const nameById = new Map(scorecard.data.map((p) => [p.provider_id, p.provider_name]));
    for (let i = 0; i < providerIds.length; i++) {
      const id = providerIds[i];
      const rows = providerQueries[i]?.data;
      if (!rows) continue;
      const cur = sumDecimals(rows.filter((r) => r.date_key > win.curStart).map((r) => r.total_revenue));
      const prior = sumDecimals(
        rows.filter((r) => r.date_key > win.prevStart && r.date_key <= win.curStart).map((r) => r.total_revenue),
      );
      const pct = pctChange(cur, prior);
      if (pct === null) continue;
      const name = nameById.get(id) ?? id;
      if (worstProvider === null || pct < worstProvider.pct) worstProvider = { name, pct };
      if (bestProvider === null || pct > bestProvider.pct) bestProvider = { name, pct };
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Executive" right={<DataThrough />} />

      {revenue.isError ? (
        <ErrorCard message="Couldn't load revenue data." onRetry={() => revenue.refetch()} />
      ) : revenue.isLoading ? (
        <KpiSkeletons />
      ) : !kpis ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No revenue in the selected window yet.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <KPICard
              label="Net revenue (90d)"
              value={fmtUSD(kpis.netRev.toString(), { dp: 0 })}
              delta={kpis.revDelta}
              deltaLabel={DELTA_LABEL}
              emphasis
            />
            <KPICard
              label="Visits (90d)"
              value={fmtInt(kpis.visits)}
              delta={kpis.visitsDelta}
              deltaLabel={DELTA_LABEL}
            />
            <KPICard
              label="Avg ticket (90d)"
              value={kpis.avgTicket ? fmtUSD(kpis.avgTicket.toString(), { dp: 2 }) : "—"}
            />
            <KPICard
              label="Active patients"
              value={tiers.data ? fmtInt(tiers.data.active) : "—"}
              loading={tiers.isLoading}
              deltaLabel="seen in last 120 days"
            />
            <KPICard
              label="No-show rate (90d)"
              value={kpis.noShowRate !== null ? fmtPct(String(kpis.noShowRate)) : "—"}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Net revenue — last 90 days</CardTitle>
            </CardHeader>
            <CardContent>
              <RevenueLineChart data={kpis.lineData} />
            </CardContent>
          </Card>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">Revenue by category — last 30 weekdays</CardTitle>
              </CardHeader>
              <CardContent>
                <CategoryStackedBar data={kpis.categoryData} />
              </CardContent>
            </Card>

            <div className="space-y-4">
              {providerWatchLoading ? (
                <Card>
                  <CardContent className="space-y-2 p-5">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-3 w-48" />
                  </CardContent>
                </Card>
              ) : (
                <>
                  {worstProvider && worstProvider.pct < -10 ? (
                    <StoryCallout tone="watch" title="Provider to watch">
                      <span className="font-medium text-foreground">{worstProvider.name}</span> is down{" "}
                      {Math.abs(worstProvider.pct).toFixed(1)}% in revenue vs. the prior 90 days — the
                      steepest decline on the team.
                    </StoryCallout>
                  ) : (
                    <p className="px-1 text-sm text-muted-foreground">
                      All providers within normal range vs. the prior 90 days.
                    </p>
                  )}
                  {bestProvider && bestProvider.pct > 0 && (
                    <StoryCallout tone="ok" title="Top performer">
                      <span className="font-medium text-foreground">{bestProvider.name}</span> is up{" "}
                      {bestProvider.pct.toFixed(1)}% in revenue vs. the prior 90 days — the strongest
                      growth on the team.
                    </StoryCallout>
                  )}
                </>
              )}

              {tiers.data && (
                <Link href="/recall" className="block">
                  <Card className="transition-colors hover:bg-muted/40">
                    <CardContent className="flex items-center justify-between p-4">
                      <div className="flex items-center gap-3">
                        <PhoneCall className="h-4 w-4 text-primary" />
                        <div>
                          <p className="text-sm font-medium">Recall queue</p>
                          <p className="text-xs text-muted-foreground">
                            {fmtInt(tiers.data.lapsing + tiers.data.lapsed)} patients pending outreach
                          </p>
                        </div>
                      </div>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </CardContent>
                  </Card>
                </Link>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function KpiSkeletons() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="space-y-2 p-5">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-28" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Skeleton className="h-[340px] w-full rounded-lg" />
    </div>
  );
}
