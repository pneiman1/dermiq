"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";

import { api } from "@/lib/api";
import { categoryColor, categoryLabel } from "@/lib/categories";
import { fmtInt, fmtUSD } from "@/lib/money";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { SegmentMembersTable } from "@/components/SegmentMembersTable";
import type { PatientSegment } from "@/lib/types";

export function SegmentCard({ segment }: { segment: PatientSegment }) {
  const [open, setOpen] = useState(false);
  const color = categoryColor(segment.dominant_category);

  const members = useQuery({
    queryKey: ["segment-members", segment.cluster_id],
    queryFn: () => api.getSegmentMembers(segment.cluster_id, 100),
    enabled: open,
  });

  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-1 flex-col gap-4 p-4 sm:p-5">
        <div>
          <p className="font-semibold text-primary">{segment.cluster_name}</p>
          <span
            className="mt-2 inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium"
            style={{ color, backgroundColor: `${color}1A` }}
          >
            {categoryLabel(segment.dominant_category)}
          </span>
        </div>

        <div>
          <p className="text-3xl font-semibold tabular-nums">{fmtInt(segment.patient_count)}</p>
          <p className="text-xs text-muted-foreground">patients</p>
        </div>

        <div className="space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Avg annual value</span>
            <span className="tabular-nums font-medium">{fmtUSD(segment.avg_annual_run_rate, { dp: 0 })}</span>
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{fmtInt(segment.active_patient_count)} active</span>
            <span>{fmtInt(segment.urgent_recall_count)} urgent recalls</span>
          </div>
        </div>

        {segment.top_provider_name && (
          <p className="text-xs text-muted-foreground">Most common: {segment.top_provider_name}</p>
        )}

        <Button variant="outline" size="sm" className="mt-auto" onClick={() => setOpen(true)}>
          <Users className="h-3.5 w-3.5" />
          See sample patients
        </Button>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{segment.cluster_name}</DialogTitle>
            <DialogDescription>
              {fmtInt(segment.patient_count)} patients · top by lifetime value
            </DialogDescription>
          </DialogHeader>
          {members.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : members.isError ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Couldn&apos;t load members.</p>
          ) : (
            <SegmentMembersTable rows={members.data ?? []} />
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
