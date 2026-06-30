"use client";

import { format, parseISO } from "date-fns";

import { useMaxDataDate } from "@/lib/hooks";

/** "Data through <freshest warehouse date>" — same date on every tab. */
export function DataThrough() {
  const { data } = useMaxDataDate();
  if (!data) return null;
  return (
    <span className="text-xs text-muted-foreground">
      Data through {format(parseISO(data), "MMM d, yyyy")}
    </span>
  );
}
