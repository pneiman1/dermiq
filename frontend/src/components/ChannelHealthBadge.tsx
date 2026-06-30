import { Badge } from "@/components/ui/badge";
import type { ChannelHealth } from "@/lib/types";

const MAP: Record<ChannelHealth, { label: string; variant: "secondary" | "success" | "warning" | "danger" }> = {
  organic: { label: "Organic", variant: "secondary" },
  excellent: { label: "Excellent", variant: "success" },
  healthy: { label: "Healthy", variant: "success" },
  marginal: { label: "Marginal", variant: "warning" },
  unprofitable: { label: "Unprofitable", variant: "danger" },
};

export function ChannelHealthBadge({ health }: { health: ChannelHealth }) {
  const c = MAP[health] ?? { label: health, variant: "secondary" as const };
  return <Badge variant={c.variant}>{c.label}</Badge>;
}
