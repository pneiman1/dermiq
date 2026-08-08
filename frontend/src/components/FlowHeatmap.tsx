"use client";

import { Fragment, useState } from "react";

import { cn } from "@/lib/utils";
import type { FlowByHourRow } from "@/lib/types";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]; // dow 1..7

function hourLabel(h: number): string {
  if (h === 0) return "12a";
  if (h < 12) return `${h}a`;
  if (h === 12) return "12p";
  return `${h - 12}p`;
}

export function FlowHeatmap({ rows }: { rows: FlowByHourRow[] }) {
  // `title` tooltips never fire on touch, so a tapped cell publishes its label here.
  const [tapped, setTapped] = useState<string | null>(null);

  if (rows.length === 0) return null;

  const hoursPresent = [...new Set(rows.map((r) => r.hour))].sort((a, b) => a - b);
  const minH = hoursPresent[0];
  const maxH = hoursPresent[hoursPresent.length - 1];
  const hours = Array.from({ length: maxH - minH + 1 }, (_, i) => minH + i);

  const counts = new Map<string, number>();
  let max = 0;
  for (const r of rows) {
    counts.set(`${r.dow}-${r.hour}`, r.appointment_count);
    if (r.appointment_count > max) max = r.appointment_count;
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <div
          className="inline-grid gap-1"
          style={{ gridTemplateColumns: `auto repeat(${hours.length}, minmax(26px, 1fr))` }}
        >
          <div />
          {hours.map((h) => (
            <div key={h} className="text-center text-[10px] text-muted-foreground">
              {hourLabel(h)}
            </div>
          ))}
          {DAY_LABELS.map((day, i) => {
            const dow = i + 1;
            return (
              <Fragment key={dow}>
                <div className="self-center pr-2 text-right text-xs text-muted-foreground">{day}</div>
                {hours.map((h) => {
                  const c = counts.get(`${dow}-${h}`) ?? 0;
                  const title = `${day} ${hourLabel(h)} · ${c} appt${c === 1 ? "" : "s"}`;
                  const intensity = 0.2 + 0.8 * (c / max);
                  return (
                    <button
                      key={h}
                      type="button"
                      title={title}
                      aria-label={title}
                      onClick={() => setTapped((t) => (t === title ? null : title))}
                      className={cn(
                        "h-7 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        c === 0 && "bg-muted/40",
                        tapped === title && "ring-2 ring-ring",
                      )}
                      style={c === 0 ? undefined : { backgroundColor: `rgba(14, 116, 144, ${intensity})` }}
                    />
                  );
                })}
              </Fragment>
            );
          })}
        </div>
      </div>
      {/* Tap read-out — the touch equivalent of the hover title. */}
      <p className="min-h-[1.25rem] text-xs text-muted-foreground lg:hidden">{tapped ?? ""}</p>

      <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
        Fewer
        <span className="h-3 w-3 rounded-sm bg-muted/40" />
        <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: "rgba(14,116,144,0.4)" }} />
        <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: "rgba(14,116,144,0.7)" }} />
        <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: "rgba(14,116,144,1)" }} />
        More
      </div>
    </div>
  );
}
