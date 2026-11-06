#!/usr/bin/env node
// check-contrast.mjs — assert the theme's text/surface pairs clear WCAG AA.
// No test runner, no dependencies. Reads the token file, computes, exits 1 on fail.
//
//   node scripts/check-contrast.mjs [path/to/tokens.css]

import { readFileSync } from "node:fs";

const file = process.argv[2] ?? "src/styles/tokens.css";
let css;
try {
  css = readFileSync(file, "utf8");
} catch {
  console.error(`FAIL: cannot read ${file}`);
  process.exit(1);
}

// Strip comments before parsing. The selector capture below is brace-delimited,
// so a comment above a block becomes part of that block's "selector" — and a
// comment mentioning dark mode then makes the LIGHT block parse as dark.
css = css.replace(/\/\*[\s\S]*?\*\//g, "");

const lin = (c) => {
  c /= 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
};
const lum = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
};
const ratio = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const blocks = [...css.matchAll(/([^{}]*)\{([^{}]*)\}/g)];
const themes = { light: {}, dark: {} };
for (const m of blocks) {
  const [, selector, body] = m;
  const sel = selector.replace(/:not\([^)]*\)/g, "");
  const before = css.slice(Math.max(0, m.index - 160), m.index);
  const isDark =
    /data-theme\s*=\s*["']?dark/i.test(sel) ||
    /\bdark\b/i.test(sel) ||
    /prefers-color-scheme\s*:\s*dark/i.test(before);
  const theme = isDark ? "dark" : "light";
  for (const [, name, hex] of body.matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})/g)) {
    themes[theme][name] = hex;
  }
}
themes.dark = { ...themes.light, ...themes.dark };

const required = ["--surface-1", "--text-primary", "--text-secondary", "--accent"];
const pairs = [
  ["--text-primary", "--surface-1", 4.5, "body text"],
  ["--text-secondary", "--surface-1", 4.5, "secondary text"],
  ["--accent", "--surface-1", 3.0, "accent vs surface"],
];

let failed = 0;
for (const theme of ["light", "dark"]) {
  const t = themes[theme];
  const missing = required.filter((k) => !t[k]);
  if (missing.length) {
    console.error(`FAIL [${theme}] missing tokens: ${missing.join(", ")}`);
    failed++;
    continue;
  }
  console.log(`[${theme}] surface ${t["--surface-1"]}`);
  for (const [fg, bg, floor, label] of pairs) {
    const r = ratio(t[fg], t[bg]);
    const ok = r >= floor;
    if (!ok) failed++;
    console.log(
      `  ${ok ? "PASS" : "FAIL"}  ${r.toFixed(2).padStart(6)}:1  (needs ${floor})  ${label}  ${t[fg]} on ${t[bg]}`
    );
  }
}

if (themes.light["--accent"] && themes.dark["--accent"]) {
  if (themes.light["--accent"].toLowerCase() === themes.dark["--accent"].toLowerCase()) {
    console.log(`  FAIL  --accent is identical in both themes; dark mode must define its own, lighter step`);
    failed++;
  }
}

if (failed) {
  console.error(`\n${failed} contrast failure(s) in ${file}`);
  process.exit(1);
}
console.log("\nall contrast gates pass");
