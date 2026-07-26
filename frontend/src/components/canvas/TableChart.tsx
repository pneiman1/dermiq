"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { CanvasRow, TableSpec } from "@/lib/types";

const NoData = () => (
  <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
    No data for this view.
  </div>
);

function prettify(col: string): string {
  return col.replace(/_/g, " ");
}

// A value that parses cleanly as a finite number (and isn't an empty string).
function isNumeric(v: string | number | boolean | null): boolean {
  if (typeof v === "number") return Number.isFinite(v);
  if (typeof v === "string" && v.trim() !== "") return Number.isFinite(Number(v));
  return false;
}

export function TableChart({ spec, data }: { spec: TableSpec; data: CanvasRow[] }) {
  if (!data || data.length === 0) return <NoData />;

  return (
    <div className="h-full w-full overflow-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {spec.columns.map((col) => (
              <TableHead key={col} className={isNumeric(data[0]?.[col] ?? null) ? "text-right" : ""}>
                {prettify(col)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row, i) => (
            <TableRow key={i}>
              {spec.columns.map((col) => {
                const val = row[col] ?? null;
                const numeric = isNumeric(val);
                return (
                  <TableCell
                    key={col}
                    className={numeric ? "text-right tabular-nums" : ""}
                  >
                    {String(val ?? "—")}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
