import { Bell, DollarSign, Package, TriangleAlert } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const FEATURES = [
  {
    icon: Package,
    title: "Consumable tracking",
    body: "Injectable units (Botox, fillers) and device consumables drawn down per transaction, tied to the service that used them.",
  },
  {
    icon: Bell,
    title: "Par levels & reorder alerts",
    body: "Set par levels per SKU and get alerted before high-velocity products run out.",
  },
  {
    icon: TriangleAlert,
    title: "Waste & overage",
    body: "Surface Botox vial overage and expired-product waste, valued against the revenue it should have produced.",
  },
  {
    icon: DollarSign,
    title: "True margin",
    body: "Service-level margin from real cost-of-goods, not list price — so you know which treatments actually pay.",
  },
];

export default function InventoryPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Inventory"
        subtitle="Consumables, par levels, and waste"
        right={<Badge variant="secondary">Roadmap · Q3 2026</Badge>}
      />
      <Card>
        <CardContent className="p-6">
          <p className="max-w-2xl text-sm text-muted-foreground">
            Inventory will tie product consumption to revenue so you can see margin, waste, and
            reorder timing at a glance. What&apos;s coming:
          </p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex gap-3 rounded-lg border border-border p-4">
                <f.icon className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-medium">{f.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{f.body}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
