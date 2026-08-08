"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { MobileNav } from "./MobileNav";
import { ThemeToggle } from "./ThemeToggle";

export function TopBar() {
  const { data } = useQuery({ queryKey: ["tenant"], queryFn: api.getTenant });

  return (
    <header className="flex h-14 shrink-0 items-center gap-1 border-b border-border bg-card px-4 sm:gap-2 sm:px-6">
      <MobileNav />

      {/* Wordmark lives in the Sidebar on desktop; below `lg` the sidebar is a
          drawer, so the header carries it instead. */}
      <Link
        href="/executive"
        className="wordmark-shimmer shrink-0 rounded text-[18px] font-extrabold tracking-[-0.03em] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background lg:hidden"
      >
        DermIQ
      </Link>

      {/* Tenant name — same gradient-clip shimmer as the wordmark but quieter and
          slower (14s vs 8s), so the two effects rarely align. The gradient sets
          the text color, so no slate text classes here. */}
      <button
        type="button"
        className="tenant-shimmer min-w-0 flex-1 truncate px-2 text-left text-[11px] font-medium uppercase tracking-[0.08em] sm:px-3 sm:text-[13px] sm:tracking-[0.1em] lg:flex-none"
      >
        {data?.tenant_name ?? "Loading…"}
      </button>

      <div className="ml-auto shrink-0">
        <ThemeToggle />
      </div>
    </header>
  );
}
