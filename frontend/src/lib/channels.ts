// Display labels + chart colors for acquisition channels, shared by the chart,
// table, KPIs, and callout so they stay consistent.

export const CHANNEL_LABELS: Record<string, string> = {
  google_ads: "Google Ads",
  instagram_meta: "Instagram / Meta",
  referral: "Referral",
  realself: "RealSelf",
  alle_directory: "Allē Directory", // Allergan's actual trademark uses the diacritic
  walkin: "Walk-in",
  other: "Other",
};

export function channelLabel(key: string): string {
  return CHANNEL_LABELS[key] ?? key;
}

// Stable stacking order + distinct muted hues.
export const CHANNEL_ORDER = [
  "google_ads",
  "instagram_meta",
  "referral",
  "realself",
  "alle_directory",
  "walkin",
  "other",
];

export const CHANNEL_COLORS: Record<string, string> = {
  google_ads: "#0E7490", // teal
  instagram_meta: "#6366F1", // indigo
  referral: "#10B981", // emerald
  realself: "#F59E0B", // amber
  alle_directory: "#8B5CF6", // violet
  walkin: "#F43F5E", // rose
  other: "#64748B", // slate
};
