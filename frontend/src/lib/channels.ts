import { seriesColor } from "@/lib/chartTokens";

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

// The categorical slots, in CHANNEL_ORDER. There are seven channels and six
// slots: "other" deliberately takes seriesColor(6), which is the neutral rather
// than a wrap back to slot one — a repeated hue would make two channels read as
// the same series, and "other" is the one that should recede.
export const CHANNEL_COLORS: Record<string, string> = {
  google_ads: seriesColor(0),
  instagram_meta: seriesColor(1),
  referral: seriesColor(2),
  realself: seriesColor(3),
  alle_directory: seriesColor(4),
  walkin: seriesColor(5),
  other: seriesColor(6),
};
