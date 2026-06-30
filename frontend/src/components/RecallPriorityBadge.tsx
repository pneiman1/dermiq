import { Badge } from "@/components/ui/badge";
import type { Priority } from "@/lib/types";

const MAP: Record<Priority, { label: string; variant: "danger" | "warning" | "secondary" | "outline" }> = {
  urgent: { label: "Urgent", variant: "danger" },
  high: { label: "High", variant: "warning" },
  medium: { label: "Medium", variant: "secondary" },
  low: { label: "Low", variant: "outline" },
};

export function RecallPriorityBadge({ priority }: { priority: Priority }) {
  const c = MAP[priority];
  return <Badge variant={c.variant}>{c.label}</Badge>;
}
