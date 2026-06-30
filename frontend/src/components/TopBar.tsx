"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";

import { api } from "@/lib/api";
import { ThemeToggle } from "./ThemeToggle";

export function TopBar() {
  const { data } = useQuery({ queryKey: ["tenant"], queryFn: api.getTenant });

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-6">
      <button
        type="button"
        className="flex items-center gap-2 rounded-md px-2 py-1 text-sm font-medium hover:bg-muted"
      >
        {data?.tenant_name ?? "Loading…"}
        <ChevronDown className="h-4 w-4 text-muted-foreground" />
      </button>
      <ThemeToggle />
    </header>
  );
}
