// Chart colour, read from tokens.css. A hex literal in a .tsx is a bug and the
// theme task's verify fails on it, so every value here is a custom-property
// reference. Recharts passes these straight through to SVG fill/stroke, so the
// cascade — including the night theme and the in-app toggle — resolves them
// without the component knowing which theme is active.

/** The categorical palette: six slots, FIXED ORDER, never cycled. */
export const CHART_SERIES = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
] as const;

export const CHART_SERIES_COUNT = CHART_SERIES.length;

/**
 * Colour for series `i`.
 *
 * Past the sixth slot this returns a single neutral rather than wrapping back
 * to slot one. Cycling is worse than it looks: two series share a hue, the
 * legend stops being a key, and nothing on screen says it happened. A chart
 * with more than six series wants a table, and `CHART_SERIES_COUNT` is exported
 * so a caller can check before it renders.
 */
export function seriesColor(i: number): string {
  return CHART_SERIES[i] ?? "var(--chart-axis)";
}

/** Single-series emphasis — the brand accent. */
export const CHART_ACCENT = "var(--accent)";

export const CHART_GRID = "var(--chart-grid)";
export const CHART_AXIS = "var(--chart-axis)";
export const CHART_TOOLTIP_BORDER = "var(--chart-tooltip-border)";
export const CHART_CURSOR = "var(--chart-cursor)";

/** Shared axis tick style, so the two chart families cannot drift apart. */
export const AXIS_TICK = { fill: CHART_AXIS, fontSize: 12 } as const;

export const TOOLTIP_STYLE = {
  borderRadius: 8,
  border: `1px solid ${CHART_TOOLTIP_BORDER}`,
  fontSize: 12,
} as const;
