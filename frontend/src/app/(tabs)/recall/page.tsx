"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { fmtInt, fmtUSD, sumDecimals } from "@/lib/money";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";
import { DataThrough } from "@/components/DataThrough";
import { KPICard } from "@/components/KPICard";
import { ErrorCard } from "@/components/ErrorCard";
import { RecallTable } from "@/components/RecallTable";
import { cn } from "@/lib/utils";
import type { Priority } from "@/lib/types";

type Filter = "all" | Priority;

export default function RecallPage() {
  const summary = useQuery({ queryKey: ["recall-summary"], queryFn: api.getRecallSummary });
  const queue = useQuery({
    queryKey: ["recall-queue", 2000, "low"],
    queryFn: () => api.getRecallQueue({ limit: 2000, minPriority: "low" }),
  });

  const [filter, setFilter] = useState<Filter>("all");

  const filtered = useMemo(() => {
    const rows = queue.data ?? [];
    return filter === "all" ? rows : rows.filter((r) => r.recall_priority === filter);
  }, [queue.data, filter]);

  // Annualized LTV that lapses if no recall succeeds — the operational stakes number.
  const revenueAtRisk = useMemo(
    () => (queue.data ? sumDecimals(queue.data.map((r) => r.annual_revenue_run_rate)) : null),
    [queue.data],
  );

  const FILTERS: { key: Filter; label: string; count?: number }[] = [
    { key: "all", label: "All", count: summary.data?.total },
    { key: "urgent", label: "Urgent", count: summary.data?.urgent },
    { key: "high", label: "High", count: summary.data?.high },
    { key: "medium", label: "Medium", count: summary.data?.medium },
    { key: "low", label: "Low", count: summary.data?.low },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Recall" subtitle="Patients due for outreach" right={<DataThrough />} />

      {summary.isError ? (
        <ErrorCard message="Couldn't load the recall queue." onRetry={() => summary.refetch()} />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <KPICard
              label="Total in queue"
              value={summary.data ? fmtInt(summary.data.total) : "—"}
              loading={summary.isLoading}
              emphasis
            />
            <KPICard
              label="Urgent"
              value={summary.data ? fmtInt(summary.data.urgent) : "—"}
              loading={summary.isLoading}
            />
            <KPICard
              label="High"
              value={summary.data ? fmtInt(summary.data.high) : "—"}
              loading={summary.isLoading}
            />
            <KPICard
              label="Avg recency"
              value={summary.data?.avg_recency_days != null ? `${summary.data.avg_recency_days} days` : "—"}
              loading={summary.isLoading}
            />
            <KPICard
              label="Revenue at risk"
              value={revenueAtRisk ? fmtUSD(revenueAtRisk.toString(), { dp: 0 }) : "—"}
              loading={queue.isLoading}
              deltaLabel="annual LTV if not re-engaged"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            {FILTERS.map((f) => (
              <Button
                key={f.key}
                variant={filter === f.key ? "default" : "outline"}
                size="sm"
                onClick={() => setFilter(f.key)}
                className={cn(filter !== f.key && "text-muted-foreground")}
              >
                {f.label}
                {f.count != null && (
                  <span className="ml-1.5 tabular-nums opacity-70">{fmtInt(f.count)}</span>
                )}
              </Button>
            ))}
          </div>

          <Card className="overflow-hidden">
            <CardContent className="p-0">
              {queue.isError ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  Couldn&apos;t load patients.
                </p>
              ) : queue.isLoading ? (
                <div className="space-y-2 p-4">
                  {Array.from({ length: 10 }).map((_, i) => (
                    <Skeleton key={i} className="h-9 w-full" />
                  ))}
                </div>
              ) : filtered.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  No patients at this priority.
                </p>
              ) : (
                <RecallTable rows={filtered} />
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
