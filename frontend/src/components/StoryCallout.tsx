import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StoryCalloutProps {
  tone: "watch" | "ok";
  title: string;
  children?: React.ReactNode;
}

export function StoryCallout({ tone, title, children }: StoryCalloutProps) {
  const Icon = tone === "watch" ? AlertTriangle : CheckCircle2;
  const iconColor =
    tone === "watch" ? "text-amber-500" : "text-emerald-600 dark:text-emerald-400";
  return (
    <Card>
      <CardContent className="flex gap-3 p-5">
        <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", iconColor)} />
        <div>
          <p className="text-base font-semibold">{title}</p>
          {children && <div className="mt-1 text-sm text-muted-foreground">{children}</div>}
        </div>
      </CardContent>
    </Card>
  );
}
