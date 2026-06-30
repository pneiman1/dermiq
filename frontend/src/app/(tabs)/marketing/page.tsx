"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { channelLabel } from "@/lib/channels";
import { fmtInt, fmtRatio, fmtUSD, sumDecimals, weightedAvg } from "@/lib/money";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";
import { DataThrough } from "@/components/DataThrough";
import { SectionHeader } from "@/components/SectionHeader";
import { KPICard } from "@/components/KPICard";
import { ErrorCard } from "@/components/ErrorCard";
import { StoryCallout } from "@/components/StoryCallout";
import { AcquisitionStackedBar } from "@/components/charts/AcquisitionStackedBar";
import { ChannelAttributionTable } from "@/components/ChannelAttributionTable";

export default function MarketingPage() {
  const acq = useQuery({
    queryKey: ["acquisition-by-month", 18],
    queryFn: () => api.getAcquisitionByMonth(18),
  });
  const attr = useQuery({ queryKey: ["channel-attribution"], queryFn: api.getChannelAttribution });

  const kpis = useMemo(() => {
    const rows = attr.data;
    if (!rows || rows.length === 0) return null;

    const totalAcquired = rows.reduce((a, r) => a + r.patients_acquired_ttm, 0);
    const totalSpend = sumDecimals(rows.map((r) => r.spend_ttm));

    const ltvWeighted = (set: typeof rows) =>
      weightedAvg(set.map((r) => ({ value: r.avg_ltv_run_rate_ttm, weight: r.patients_acquired_ttm })));

    // Blended = all channels (organic dilutes CAC down).
    const blendedLTV = ltvWeighted(rows);
    const blendedCAC = totalAcquired > 0 ? totalSpend.div(totalAcquired) : null;
    const blendedRatio =
      blendedLTV && blendedCAC && !blendedCAC.isZero() ? blendedLTV.div(blendedCAC) : null;

    // Paid-only = channels with spend (is ad spend actually working?).
    const paid = rows.filter((r) => Number(r.spend_ttm) > 0);
    const paidAcquired = paid.reduce((a, r) => a + r.patients_acquired_ttm, 0);
    const paidSpend = sumDecimals(paid.map((r) => r.spend_ttm));
    const paidLTV = ltvWeighted(paid);
    const paidCAC = paidAcquired > 0 ? paidSpend.div(paidAcquired) : null;
    const paidRatio = paidLTV && paidCAC && !paidCAC.isZero() ? paidLTV.div(paidCAC) : null;

    const ratable = paid.filter((r) => r.ltv_cac_ratio_ttm !== null);
    const bestPaid = ratable.length
      ? ratable.reduce((m, r) => (Number(r.ltv_cac_ratio_ttm) > Number(m.ltv_cac_ratio_ttm) ? r : m), ratable[0])
      : null;
    const worstPaid = ratable.length
      ? ratable.reduce((m, r) => (Number(r.ltv_cac_ratio_ttm) < Number(m.ltv_cac_ratio_ttm) ? r : m), ratable[0])
      : null;

    return { totalAcquired, totalSpend, blendedRatio, paidRatio, bestPaid, worstPaid };
  }, [attr.data]);

  return (
    <div className="space-y-6">
      <PageHeader title="Marketing" right={<DataThrough />} />

      {attr.isError ? (
        <ErrorCard message="Couldn't load channel attribution." onRetry={() => attr.refetch()} />
      ) : attr.isLoading ? (
        <MarketingSkeleton />
      ) : !kpis || !attr.data ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No channel data yet.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="space-y-4">
            <SectionHeader title="Channel performance" subtitle="Trailing 12 months" />
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
              <KPICard label="Total acquired" value={fmtInt(kpis.totalAcquired)} />
              <KPICard label="Spend" value={fmtUSD(kpis.totalSpend.toString(), { dp: 0 })} />
              <KPICard
                label="Blended LTV:CAC"
                value={kpis.blendedRatio ? fmtRatio(kpis.blendedRatio.toString()) : "—"}
              />
              <KPICard
                label="Paid LTV:CAC"
                value={kpis.paidRatio ? fmtRatio(kpis.paidRatio.toString()) : "—"}
                emphasis
              />
              <KPICard
                label="Best paid channel"
                value={kpis.bestPaid ? channelLabel(kpis.bestPaid.acquisition_channel) : "—"}
                valueSize="lg"
                deltaLabel={
                  kpis.bestPaid ? `${fmtRatio(kpis.bestPaid.ltv_cac_ratio_ttm)} LTV:CAC` : undefined
                }
              />
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">
                  Patients acquired by channel — last 18 months
                </CardTitle>
              </CardHeader>
              <CardContent>
                {acq.isError ? (
                  <p className="py-12 text-center text-sm text-muted-foreground">
                    Couldn&apos;t load acquisition data.
                  </p>
                ) : acq.isLoading ? (
                  <Skeleton className="h-[320px] w-full" />
                ) : !acq.data || acq.data.length === 0 ? (
                  <p className="py-12 text-center text-sm text-muted-foreground">
                    No acquisition data.
                  </p>
                ) : (
                  <AcquisitionStackedBar rows={acq.data} />
                )}
              </CardContent>
            </Card>

            <div>
              {kpis.worstPaid && (
                <StoryCallout tone="watch" title="Lowest-ROI paid channel">
                  <span className="font-medium text-foreground">
                    {channelLabel(kpis.worstPaid.acquisition_channel)}
                  </span>{" "}
                  returns {fmtRatio(kpis.worstPaid.ltv_cac_ratio_ttm)} LTV:CAC — your weakest paid
                  channel. These patients carry lower lifetime value than other channels; still
                  profitable, but the first place to scrutinize spend.
                </StoryCallout>
              )}
            </div>
          </div>

          <Card className="overflow-hidden">
            <CardContent className="p-0">
              <ChannelAttributionTable rows={attr.data} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function MarketingSkeleton() {
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
      <Skeleton className="h-[360px] w-full rounded-xl" />
    </div>
  );
}
