"use client";

import { useEffect, useState } from "react";

/**
 * Subscribe to a CSS media query from JS. Returns `false` on the server and on the
 * first client render so SSR markup matches; the real value lands in an effect.
 * Only use this for behaviour that can't be expressed in CSS (e.g. props passed to
 * a JS-driven grid) — prefer Tailwind breakpoints for pure styling.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** Tailwind's `lg` breakpoint (1024px) — the desktop/mobile split used across the app. */
export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 1024px)");
}
