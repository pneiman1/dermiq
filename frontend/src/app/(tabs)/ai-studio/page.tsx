"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";
import { SectionHeader } from "@/components/SectionHeader";
import { ErrorCard } from "@/components/ErrorCard";
import { SegmentCard } from "@/components/SegmentCard";

const SAMPLES = [
  {
    q: "Why is Q1 revenue down?",
    a: "Driven mainly by Dr. Marcus Halloway's medical leave (Apr–May), which cut his visit volume ~60% and dropped his trailing revenue 10.7% vs. the prior 90 days. The January seasonal slump compounded it. The rest of the team is up 35–70%, so this is provider-specific, not practice-wide.",
  },
  {
    q: "Which marketing channel should I cut first?",
    a: "Instagram / Meta — it's your lowest-ROI paid channel at ~22× LTV:CAC vs. RealSelf's ~46×. Meta-acquired patients carry lower lifetime value. It's still profitable, but it's the first place to trim or re-target spend.",
  },
  {
    q: "Who should we prioritize for recall this week?",
    a: "Start with the 235 'urgent' patients — high-value and newly lapsing. The full recall queue holds 1,099 patients representing ~$2.45M of annual revenue at risk if they churn.",
  },
];

function TypewriterAnswer({ text }: { text: string }) {
  const [shown, setShown] = useState("");
  useEffect(() => {
    setShown("");
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, 30);
    return () => clearInterval(id);
  }, [text]);
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2 text-sm duration-200 animate-in fade-in slide-in-from-right-4">
        {shown}
        {shown.length < text.length && (
          <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-primary align-text-bottom" />
        )}
      </div>
    </div>
  );
}

export default function AiStudioPage() {
  const segments = useQuery({ queryKey: ["segments"], queryFn: api.getSegments });
  const [active, setActive] = useState<{ i: number; nonce: number } | null>(null);

  return (
    <div className="space-y-8">
      <PageHeader title="AI Studio" subtitle="Segments and answers from your practice data" />

      {/* Section A — real ML */}
      <div className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <SectionHeader title="Patient segments discovered from your data" />
          <p className="text-sm text-muted-foreground">
            Unsupervised k-means across 12 behavior features.{" "}
            <Badge
              variant="secondary"
              title="The k-means model is re-fit every Monday at 3am by an Airflow DAG, so segments always reflect the latest patient behavior."
              className="cursor-help align-middle"
            >
              Retrained weekly
            </Badge>{" "}
            via Airflow.
          </p>
        </div>

        {segments.isError ? (
          <ErrorCard message="Couldn't load segments." onRetry={() => segments.refetch()} />
        ) : segments.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Card key={i}>
                <CardContent className="space-y-3 p-5">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-8 w-20" />
                  <Skeleton className="h-4 w-full" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {(segments.data ?? []).map((s) => (
              <SegmentCard key={s.cluster_id} segment={s} />
            ))}
          </div>
        )}
      </div>

      {/* Section B — sample Q&A (interactive preview) */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <SectionHeader title="Sample questions" />
          <Badge variant="warning">Demo preview — not live</Badge>
        </div>

        <Card>
          <CardContent className="space-y-4 p-5">
            {SAMPLES.map((s, i) => (
              <div key={i} className="space-y-2">
                <button
                  type="button"
                  onClick={() =>
                    setActive((prev) => ({ i, nonce: prev?.i === i ? prev.nonce + 1 : 0 }))
                  }
                  className="ml-auto block max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-left text-sm text-primary-foreground transition hover:bg-primary/90"
                >
                  {s.q}
                </button>
                {active?.i === i && <TypewriterAnswer key={`${i}-${active.nonce}`} text={s.a} />}
              </div>
            ))}

            <div className="pt-2">
              <input
                disabled
                placeholder="Live AI Q&A available Q4 2026 — retrained clustering above is live."
                className="w-full cursor-not-allowed rounded-lg border border-border bg-muted/40 px-4 py-2 text-sm text-muted-foreground"
              />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
