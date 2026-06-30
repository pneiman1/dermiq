import { FileText, Sparkles } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CAPABILITIES = [
  {
    icon: Sparkles,
    title: "Natural-language Q&A",
    body: "Ask about revenue, providers, marketing, or patients in plain English — answered from the live warehouse.",
  },
  {
    icon: FileText,
    title: "Weekly performance brief",
    body: "An auto-generated narrative of the week's wins, risks, and recommended actions, ready for Monday.",
  },
];

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

export default function AiStudioPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Studio"
        subtitle="Ask the practice data in plain English"
        right={<Badge variant="secondary">Roadmap · ML chunk</Badge>}
      />

      <div className="grid gap-4 sm:grid-cols-2">
        {CAPABILITIES.map((c) => (
          <Card key={c.title}>
            <CardContent className="flex gap-3 p-5">
              <c.icon className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
              <div>
                <p className="text-sm font-medium">{c.title}</p>
                <p className="mt-1 text-sm text-muted-foreground">{c.body}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Sample answers</CardTitle>
          <Badge variant="warning">Demo preview — not live</Badge>
        </CardHeader>
        <CardContent className="space-y-6">
          {SAMPLES.map((s, i) => (
            <div key={i} className="space-y-2">
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-sm text-primary-foreground">
                  {s.q}
                </div>
              </div>
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2 text-sm">
                  {s.a}
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
