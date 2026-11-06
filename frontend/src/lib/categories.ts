import { seriesColor } from "@/lib/chartTokens";

// Service-category labels + colors — matches the Executive stacked-bar palette so
// a category reads the same everywhere.

export const CATEGORY_LABELS: Record<string, string> = {
  injectable: "Injectable",
  energy_device: "Energy device",
  skincare_retail: "Skincare",
  membership: "Membership",
  surgical: "Surgical",
  consult: "Consult",
};

// Same six slots, same order, as the Executive stacked bar — so a category
// reads identically wherever it appears.
export const CATEGORY_COLORS: Record<string, string> = {
  injectable: seriesColor(0),
  energy_device: seriesColor(1),
  skincare_retail: seriesColor(2),
  surgical: seriesColor(3),
  membership: seriesColor(4),
  consult: seriesColor(5),
};

export function categoryLabel(key: string): string {
  return CATEGORY_LABELS[key] ?? key;
}

export function categoryColor(key: string): string {
  // Unknown category falls back to the same neutral seriesColor uses past the
  // last slot, so an unmapped key never borrows a category hue.
  return CATEGORY_COLORS[key] ?? seriesColor(99);
}
