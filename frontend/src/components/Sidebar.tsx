"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Megaphone,
  GitBranch,
  PhoneCall,
  Package,
  Sparkles,
} from "lucide-react";

import { cn } from "@/lib/utils";

const NAV = [
  { href: "/executive", label: "Executive", icon: LayoutDashboard },
  { href: "/providers", label: "Providers", icon: Users },
  { href: "/marketing", label: "Marketing", icon: Megaphone },
  { href: "/flow", label: "Flow", icon: GitBranch },
  { href: "/recall", label: "Recall", icon: PhoneCall },
  { href: "/inventory", label: "Inventory", icon: Package },
  { href: "/ai-studio", label: "AI Studio", icon: Sparkles },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-card">
      <div className="flex h-14 items-center px-5">
        <Link href="/executive" className="text-lg font-semibold tracking-tight">
          <span className="text-primary">Derm</span>IQ
        </Link>
      </div>
      <nav className="flex flex-col gap-1 p-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
