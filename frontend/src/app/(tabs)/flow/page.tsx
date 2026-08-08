"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { format, subDays } from "date-fns";

import { api } from "@/lib/api";
import { fmtInt, fmtPct } from "@/lib/money";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";
import { DataThrough } from "@/components/DataThrough";
import { KPICard } from "@/components/KPICard";
import { ErrorCard } from "@/components/ErrorCard";
import { OutcomeBar } from "@/components/OutcomeBar";
import { FlowHeatmap } from "@/components/FlowHeatmap";
import { NoShowByProviderTable } from "@/components/NoShowByProviderTable";

export default function FlowPage() {
  const win = useMemo(() => {
    const today = new Date();
    const f = (x: Date) => format(x, "yyyy-MM-dd");
    return { today: f(today), start: f(subDays(today, 90)) };
  }, []);

  const disp = useQuery({
    queryKey: ["flow-dispositions", win.start, win.today],
    queryFn: () => api.getFlowDispositions({ startDate: win.start, endDate: win.today }),
  });
  const byHour = useQuery({ queryKey: ["flow-by-hour"], queryFn: () => api.getFlowByHour() });
  const noShow = useQuery({ queryKey: ["no-show-by-provider"], queryFn: api.getNoShowByProvider });

  const agg = useMemo(() => {
    const rows = disp.data;
    if (!rows || rows.length === 0) return null;
    const completed = rows.reduce((a, r) => a + r.completed, 0);
    const no_show = rows.reduce((a, r) => a + r.no_show, 0);
    const cancelled = rows.reduce((a, r) => a + r.cancelled, 0);
    const total = rows.reduce((a, r) => a + r.total, 0);
    return { completed, no_show, cancelled, total };
  }, [disp.data]);

  const rate = (n: number) => (agg && agg.total > 0 ? String(n / agg.total) : null);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Flow"
        subtitle="Appointment funnel & scheduling"
        right={<DataThrough />}
      />

      {disp.isError ? (
        <ErrorCard message="Couldn't load appointment flow." onRetry={() => disp.refetch()} />
      ) : disp.isLoading ? (
        <FlowSkeleton />
      ) : !agg ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No appointments in the selected window.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KPICard label="Scheduled (90d)" value={fmtInt(agg.total)} />
            <KPICard label="Completion rate" value={fmtPct(rate(agg.completed))} />
            <KPICard label="No-show rate" value={fmtPct(rate(agg.no_show))} emphasis />
            <KPICard label="Cancel rate" value={fmtPct(rate(agg.cancelled))} />
          </div>

          <Card>
            <CardHeader className="p-4 sm:p-5">
              <CardTitle className="text-base">Outcomes</CardTitle>
              <p className="text-sm text-muted-foreground">Appointment outcomes — last 90 days</p>
            </CardHeader>
            <CardContent className="p-4 pt-0 sm:p-5 sm:pt-0">
              <OutcomeBar completed={agg.completed} noShow={agg.no_show} cancelled={agg.cancelled} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="p-4 sm:p-5">
              <CardTitle className="text-base">Appointments by day &amp; hour</CardTitle>
              <p className="text-sm text-muted-foreground">Trailing 12 weeks · clinic-local time</p>
            </CardHeader>
            <CardContent className="p-4 pt-0 sm:p-5 sm:pt-0">
              {byHour.isError ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  Couldn&apos;t load the heatmap.
                </p>
              ) : byHour.isLoading ? (
                <Skeleton className="h-[240px] w-full" />
              ) : (
                <FlowHeatmap rows={byHour.data ?? []} />
              )}
            </CardContent>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader className="p-4 sm:p-5">
              <CardTitle className="text-base">No-show rate by provider</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {noShow.isError ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  Couldn&apos;t load provider no-show rates.
                </p>
              ) : noShow.isLoading ? (
                <div className="space-y-2 p-4">
                  {Array.from({ length: 7 }).map((_, i) => (
                    <Skeleton key={i} className="h-9 w-full" />
                  ))}
                </div>
              ) : (
                <NoShowByProviderTable rows={noShow.data ?? []} />
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function FlowSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="space-y-2 p-4 sm:p-5">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-28" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Skeleton className="h-[260px] w-full rounded-xl" />
    </div>
  );
}
