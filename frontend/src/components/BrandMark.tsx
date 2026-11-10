/**
 * Three ascending dots — a course of treatment over time — the wordmark's corner mark.
 *
 * Left to right they rise and grow: 2.0, 2.2 and 2.4 radius at falling
 * baselines. The growth is what stops it reading as a generic ellipsis — a
 * course of treatment is a sequence that builds, not three equal marks.
 *
 * One <path>, no fill colour of its own: it paints with `currentColor`, so the
 * caller sets the hue with a text utility and the token cascade handles both
 * themes. It cannot live *inside* the wordmark link's text span — that span is
 * `wordmark-shimmer`, which sets `color: transparent` to clip a gradient to the
 * glyphs, and a currentColor mark inside it would vanish.
 *
 * Sized in the caller. The -1px nudge is optical, not geometric: the mark's
 * visual mass sits slightly below the cap height of an extrabold wordmark, and
 * flex centring alone leaves it reading a touch low.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className={className}
      fill="currentColor"
    >
      <path d="M5 19a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm7-3a2.2 2.2 0 1 1 0-4.4 2.2 2.2 0 0 1 0 4.4zm7-3.6a2.4 2.4 0 1 1 0-4.8 2.4 2.4 0 0 1 0 4.8z" />
    </svg>
  );
}
