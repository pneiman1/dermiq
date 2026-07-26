"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { ThemeToggle } from "./ThemeToggle";

export function TopBar() {
  const { data } = useQuery({ queryKey: ["tenant"], queryFn: api.getTenant });

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-6">
      {/* Tenant name — same gradient-clip shimmer as the wordmark but quieter and
          slower (14s vs 8s), so the two effects rarely align. The gradient sets
          the text color, so no slate text classes here. */}
      <button
        type="button"
        className="tenant-shimmer px-3 py-1 text-[13px] font-medium uppercase tracking-[0.1em]"
      >
        {data?.tenant_name ?? "Loading…"}
      </button>
      <ThemeToggle />
    </header>
  );
}
