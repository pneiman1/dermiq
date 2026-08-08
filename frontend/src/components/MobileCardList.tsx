"use client";

import { useId } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Shared "table becomes a card list" primitives for <lg viewports.
 *
 * Every data table in the app renders two siblings: the real <table> wrapped in
 * `hidden lg:block`, and a <MobileCardList> wrapped in `lg:hidden`. Both read from
 * the same sorted array, so sort state stays in sync across a resize.
 */

export interface CardField {
  label: string;
  value: React.ReactNode;
  /** Span both columns — for wide values like a provider name. */
  wide?: boolean;
}

export function MobileCardList({ children }: { children: React.ReactNode }) {
  return <div className="divide-y divide-border lg:hidden">{children}</div>;
}

export function MobileCard({
  title,
  subtitle,
  right,
  fields,
  onClick,
  className,
  children,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  right?: React.ReactNode;
  fields?: CardField[];
  onClick?: () => void;
  className?: string;
  children?: React.ReactNode;
}) {
  const interactive = typeof onClick === "function";
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{title}</div>
          {subtitle && (
            <div className="truncate text-xs text-muted-foreground">{subtitle}</div>
          )}
        </div>
        {right && <div className="shrink-0">{right}</div>}
      </div>
      {fields && fields.length > 0 && (
        <dl className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5">
          {fields.map((f) => (
            <div
              key={f.label}
              className={cn("flex items-baseline justify-between gap-2", f.wide && "col-span-2")}
            >
              <dt className="shrink-0 text-xs text-muted-foreground">{f.label}</dt>
              <dd className="min-w-0 truncate text-right text-sm tabular-nums">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {children}
    </>
  );

  if (interactive) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "block w-full px-4 py-3 text-left transition-colors active:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
          className,
        )}
      >
        {body}
      </button>
    );
  }

  return <div className={cn("px-4 py-3", className)}>{body}</div>;
}

/**
 * Native <select> + direction toggle. A native picker is the most reliable sort
 * affordance on touch, and it keeps the mobile list at parity with the sortable
 * column headers shown on desktop.
 */
export function MobileSortBar<K extends string>({
  options,
  sortKey,
  sortDir,
  onKeyChange,
  onDirToggle,
}: {
  options: { key: K; label: string }[];
  sortKey: K;
  sortDir: "asc" | "desc";
  onKeyChange: (k: K) => void;
  onDirToggle: () => void;
}) {
  // Two sort bars can be mounted at once (a page-level list plus one inside a
  // dialog), so the label/select pairing needs a per-instance id.
  const id = useId();
  return (
    <div className="flex items-center gap-2 border-b border-border px-4 py-2 lg:hidden">
      <label htmlFor={id} className="shrink-0 text-xs text-muted-foreground">
        Sort
      </label>
      <select
        id={id}
        value={sortKey}
        onChange={(e) => onKeyChange(e.target.value as K)}
        // text-base (16px) keeps iOS Safari from zooming the viewport on focus.
        className="h-11 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-base outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-sm"
      >
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={onDirToggle}
        aria-label={sortDir === "asc" ? "Sort descending" : "Sort ascending"}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors active:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {sortDir === "asc" ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
      </button>
    </div>
  );
}

/** Wrapper that hides the real table below `lg`. */
export function DesktopTable({ children }: { children: React.ReactNode }) {
  return <div className="hidden lg:block">{children}</div>;
}
