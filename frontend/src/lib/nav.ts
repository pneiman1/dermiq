import {
  LayoutDashboard,
  Users,
  Megaphone,
  GitBranch,
  PhoneCall,
  Package,
  MessageSquare,
  Sparkles,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  iconClass?: string;
}

// Single source of truth for the 8 tabs — rendered by the desktop Sidebar and the
// mobile drawer, so the two can never drift apart.
export const NAV: NavItem[] = [
  { href: "/executive", label: "Executive", icon: LayoutDashboard },
  { href: "/providers", label: "Providers", icon: Users },
  { href: "/marketing", label: "Marketing", icon: Megaphone },
  { href: "/flow", label: "Flow", icon: GitBranch },
  { href: "/recall", label: "Recall", icon: PhoneCall },
  { href: "/inventory", label: "Inventory", icon: Package },
  { href: "/ai-studio", label: "AI Studio", icon: MessageSquare },
  // AI-powered: teal-tinted Sparkles to signal the LLM-composed canvas.
  { href: "/canvas", label: "Canvas", icon: Sparkles, iconClass: "text-primary" },
];
