#!/usr/bin/env node
/**
 * Theme gate, asserted against the BUILT output.
 *
 * The task-025 verify checked that src/styles/tokens.css exists, that it
 * contains the accent hex, and that no .tsx holds a `#rrggbb`. Every one of
 * those passed while the live site served a blue theme, because:
 *
 *   - globals.css carried a second palette (--primary #0E7490, slate surfaces)
 *     and tailwind.config resolved every utility against it, so the tokens
 *     reached only the charts;
 *   - `bg-slate-900` and `text-slate-900` are not hex literals, so the .tsx
 *     grep was satisfied by them;
 *   - the hardcoded teal gradients lived in .css, which the grep never read.
 *
 * A source check cannot catch any of that. This reads the compiled CSS and HTML
 * that Next.js emits and asserts on what a browser would actually receive:
 *
 *   1. the light and dark accent hexes are both present in the compiled CSS;
 *   2. every UI role token is defined, so no Tailwind utility resolves to
 *      nothing;
 *   3. no Tailwind blue/indigo/sky/cyan/teal/slate utility survives in the
 *      built CSS or HTML;
 *   4. no off-palette hex appears in the compiled CSS at all — the allowed set
 *      is exactly what tokens.css declares;
 *   5. the two themes do not share an accent, which is what inverting produces.
 *
 * Usage: node scripts/check-theme.mjs [--dir .next]
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const argDir = process.argv.indexOf("--dir");
const BUILD = argDir > -1 ? process.argv[argDir + 1] : ".next";
const TOKENS = "src/styles/tokens.css";

// ---------------------------------------------------------------- helpers
function walk(dir, exts, out = []) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const e of entries) {
    const p = join(dir, e);
    let st;
    try {
      st = statSync(p);
    } catch {
      continue;
    }
    if (st.isDirectory()) walk(p, exts, out);
    else if (exts.includes(extname(p))) out.push(p);
  }
  return out;
}

const fail = [];
const note = (m) => console.log(`  ${m}`);

// ---------------------------------------------------------------- the palette
// tokens.css is the declaration of intent; everything below is checked against
// it rather than against hardcoded expectations, so adding a token to the file
// is all it takes to allow it in the bundle.
const tokensSrc = readFileSync(TOKENS, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const declaredHex = new Set(
  [...tokensSrc.matchAll(/#[0-9a-fA-F]{6}\b/g)].map((m) => m[0].toLowerCase()),
);
const accentHexes = [
  ...tokensSrc.matchAll(/--accent:\s*(#[0-9a-fA-F]{6})/g),
].map((m) => m[1].toLowerCase());

const uiRoles = new Set(
  [...tokensSrc.matchAll(/--ui-[a-z-]+/g)].map((m) => m[0]),
);

if (accentHexes.length < 2) {
  fail.push(
    `tokens.css declares ${accentHexes.length} --accent value(s); both a light and a dark one are required`,
  );
}
if (new Set(accentHexes).size < 2) {
  fail.push(
    `both themes share the accent ${accentHexes[0]} — a dark accent must be defined, not inverted`,
  );
}
if (uiRoles.size === 0) {
  fail.push(
    "tokens.css declares no --ui-* role tokens, so Tailwind utilities cannot resolve to the palette",
  );
}

// ---------------------------------------------------------------- the bundle
const cssFiles = walk(BUILD, [".css"]);
const htmlFiles = walk(BUILD, [".html"]);
if (cssFiles.length === 0) {
  fail.push(`no compiled CSS under ${BUILD}/ — run \`next build\` first`);
}
const css = cssFiles.map((f) => readFileSync(f, "utf8")).join("\n");
const html = htmlFiles.map((f) => readFileSync(f, "utf8")).join("\n");

note(`compiled CSS: ${cssFiles.length} file(s), ${css.length} bytes`);
note(`compiled HTML: ${htmlFiles.length} file(s), ${html.length} bytes`);

// 1. both accents present in what ships
for (const hex of new Set(accentHexes)) {
  const present = css.toLowerCase().includes(hex);
  note(`accent ${hex} in compiled CSS: ${present ? "yes" : "NO"}`);
  if (!present) {
    fail.push(`accent ${hex} does not appear in the compiled CSS`);
  }
}

// 2. every UI role token actually reaches the bundle
const missingRoles = [...uiRoles].filter((r) => !css.includes(`${r}:`));
if (missingRoles.length) {
  fail.push(
    `${missingRoles.length} UI role token(s) never defined in the compiled CSS: ${missingRoles.join(", ")}`,
  );
}

// 3. no Tailwind blue-family utility survives anywhere in the output
const BANNED_FAMILIES = "blue|indigo|sky|cyan|teal|slate|violet|purple";
const UTIL = new RegExp(
  String.raw`(?<![\w-])(?:bg|text|border|ring|from|to|via|fill|stroke|divide|outline|shadow|decoration|accent|caret|placeholder)-(?:${BANNED_FAMILIES})-\d{2,3}(?![\w-])`,
  "g",
);
for (const [label, body] of [
  ["CSS", css],
  ["HTML", html],
]) {
  const hits = [...new Set([...body.matchAll(UTIL)].map((m) => m[0]))];
  note(`Tailwind ${BANNED_FAMILIES.split("|").join("/")} utilities in compiled ${label}: ${hits.length}`);
  if (hits.length) {
    fail.push(
      `${hits.length} Tailwind blue-family utility class(es) survive in the compiled ${label}: ${hits.slice(0, 12).join(", ")}`,
    );
  }
}

// 4. no hex in the compiled CSS that tokens.css did not declare
//    (Next inlines its own dev/error styling, so only colour-ish declarations
//    are considered — anything matching a #rrggbb in a custom property or a
//    colour property.)
const bundleHex = new Set(
  [...css.matchAll(/#[0-9a-fA-F]{6}\b/g)].map((m) => m[0].toLowerCase()),
);
const strayHex = [...bundleHex].filter((h) => !declaredHex.has(h));
note(`distinct hex in compiled CSS: ${bundleHex.size}, undeclared: ${strayHex.length}`);
if (strayHex.length) {
  fail.push(
    `${strayHex.length} hex colour(s) in the compiled CSS are not declared in ${TOKENS}: ${strayHex.slice(0, 16).join(", ")}`,
  );
}

// ---------------------------------------------------------------- verdict
console.log("");
if (fail.length) {
  console.error("THEME GATE FAILED");
  for (const f of fail) console.error(`  - ${f}`);
  process.exit(1);
}
console.log("theme gate passes: the bundle serves the token palette and nothing else");
