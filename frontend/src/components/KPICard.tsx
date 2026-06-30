import { ArrowDown, ArrowUp, Minus } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function DeltaBadge({ delta }: { delta: number }) {
  const material = Math.abs(delta) >= 2; // within ±2% is not material
  const positive = delta > 0;
  const Icon = !material ? Minus : positive ? ArrowUp : ArrowDown;
  const color = !material
    ? "text-muted-foreground"
    : positive
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-destructive";
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-xs font-medium", color)}>
      <Icon className="h-3 w-3" />
      {Math.abs(delta).toFixed(1)}%
    </span>
  );
}

interface KPICardProps {
  label: string;
  value: string;
  delta?: number | null;
  deltaLabel?: string;
  loading?: boolean;
  emphasis?: boolean;
  valueSize?: "2xl" | "lg"; // "lg" for text values (e.g. a provider name)
}

export function KPICard({
  label,
  value,
  delta,
  deltaLabel,
  loading,
  emphasis,
  valueSize = "2xl",
}: KPICardProps) {
  return (
    <Card className={emphasis ? "border-l-4 border-l-primary" : undefined}>
      <CardContent className="p-5">
        <p className="text-sm text-muted-foreground">{label}</p>
        {loading ? (
          <Skeleton className="mt-2 h-8 w-28" />
        ) : (
          <div className="mt-1 flex min-w-0 items-baseline gap-2">
            <span
              className={cn(
                "truncate font-semibold tracking-tight",
                valueSize === "lg" ? "text-lg" : "text-2xl",
              )}
              title={value}
            >
              {value}
            </span>
            {delta !== undefined && delta !== null && <DeltaBadge delta={delta} />}
          </div>
        )}
        {deltaLabel && !loading && (
          <p className="mt-1 text-xs text-muted-foreground">{deltaLabel}</p>
        )}
      </CardContent>
    </Card>
  );
}
