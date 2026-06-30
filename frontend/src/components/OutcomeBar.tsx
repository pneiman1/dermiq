import { fmtInt } from "@/lib/money";
import { cn } from "@/lib/utils";

const SEGMENTS = [
  { key: "completed", label: "Completed", dot: "bg-emerald-500", bar: "bg-emerald-500" },
  { key: "no_show", label: "No-show", dot: "bg-rose-500", bar: "bg-rose-500" },
  { key: "cancelled", label: "Cancelled", dot: "bg-amber-500", bar: "bg-amber-500" },
] as const;

export function OutcomeBar({
  completed,
  noShow,
  cancelled,
}: {
  completed: number;
  noShow: number;
  cancelled: number;
}) {
  const total = completed + noShow + cancelled;
  const counts = { completed, no_show: noShow, cancelled };
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0);

  return (
    <div className="space-y-5">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
        {SEGMENTS.map((s) => (
          <div key={s.key} className={s.bar} style={{ width: `${pct(counts[s.key])}%` }} />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-4">
        {SEGMENTS.map((s) => {
          const n = counts[s.key];
          return (
            <div key={s.key}>
              <div className="flex items-center gap-1.5">
                <span className={cn("h-2 w-2 rounded-full", s.dot)} />
                <span className="text-sm text-muted-foreground">{s.label}</span>
              </div>
              <p className="mt-1 text-xl font-semibold tabular-nums">{fmtInt(n)}</p>
              <p className="text-xs tabular-nums text-muted-foreground">{pct(n).toFixed(1)}%</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
