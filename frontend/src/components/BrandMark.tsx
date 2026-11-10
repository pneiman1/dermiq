/**
 * Regimen — three ascending dots, a course of treatment over time.
 *
 * Left to right they rise and grow: 2.0, 2.3 and 2.6 radius on a falling
 * baseline. Both the rise and the growth are load-bearing — at equal size the
 * same three dots read as an ellipsis rather than as a course that builds.
 *
 * Filled, because dots are dots. The nav icons beside it are stroked lucide,
 * but three stroked rings read as bubbles rather than as a progression.
 *
 * `currentColor` throughout, so the caller sets the hue with a text utility
 * and the token cascade handles both themes. It cannot live *inside* the
 * wordmark's text span — that span is `wordmark-shimmer`, which sets
 * `color: transparent` to clip a gradient to the glyphs, and a currentColor
 * mark inside it would vanish.
 *
 * Sized by the caller. The -1px nudge is optical, not geometric: the mark's
 * visual mass sits slightly below the cap height of an extrabold wordmark, so
 * flex centring alone leaves it reading low.
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
      <path d="M4.6 20.4a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm7.4-3.6a2.3 2.3 0 1 1 0-4.6 2.3 2.3 0 0 1 0 4.6zm7.4-4a2.6 2.6 0 1 1 0-5.2 2.6 2.6 0 0 1 0 5.2z" />
    </svg>
  );
}
