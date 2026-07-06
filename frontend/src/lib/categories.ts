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

export const CATEGORY_COLORS: Record<string, string> = {
  injectable: "#0E7490", // teal
  energy_device: "#6366F1", // indigo
  skincare_retail: "#F59E0B", // amber
  surgical: "#F43F5E", // rose
  membership: "#8B5CF6", // violet
  consult: "#64748B", // slate
};

export function categoryLabel(key: string): string {
  return CATEGORY_LABELS[key] ?? key;
}

export function categoryColor(key: string): string {
  return CATEGORY_COLORS[key] ?? "#64748B";
}
