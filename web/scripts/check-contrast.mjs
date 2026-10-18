#!/usr/bin/env node
/*
 * WCAG contrast check for the Park LU color tokens (Req 17.5, 17.13).
 *
 * Parses the light `:root` color block and the dark `:root` inside
 * `@media (prefers-color-scheme: dark)` from app/globals.css, computes the
 * WCAG 2.x contrast ratio for every pair below in both appearances, prints a
 * table, and exits 1 when any required pair falls below its minimum.
 *
 * Only plain hex values (#RGB or #RRGGBB) are read as colors. Other custom
 * properties, such as the layout metrics, are ignored.
 *
 * Run: node scripts/check-contrast.mjs (part of `npm run check`).
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const CSS_PATH = resolve(dirname(fileURLToPath(import.meta.url)), "../app/globals.css");

// Minimum ratios. `large` covers text that is only ever 18 px or larger, or bold.
const REQUIRED = {
  text: 4.5,
  large: 3,
  "non-text": 3,
  info: 3,
};

/**
 * Every checked pair. `kind` picks the minimum; `info` rows are reported
 * against 3:1 but never fail, because the meaning is carried by icon and text.
 */
const PAIRS = [
  // Primary and secondary text on every surface they sit on.
  ...["--text", "--text-2"].flatMap((fg) =>
    ["--bg", "--surface", "--surface-2", "--alternative"].map((bg) => ({
      fg,
      bg,
      kind: "text",
      use: fg === "--text" ? "primary text" : "secondary text",
    })),
  ),
  { fg: "--on-accent", bg: "--accent", kind: "text", use: "primary button, Selected chip" },
  { fg: "--on-excluded", bg: "--excluded", kind: "text", use: "Excluded, Selected_Excluded" },
  { fg: "--on-gold", bg: "--gold", kind: "text", use: "gold accent text" },
  { fg: "--on-gold-fill", bg: "--gold-fill", kind: "text", use: "gold fill label" },
  { fg: "--gold", bg: "--bg", kind: "text", use: "gold link/eyebrow text" },
  { fg: "--gold", bg: "--surface", kind: "text", use: "gold link/eyebrow text" },
  { fg: "--accent", bg: "--bg", kind: "text", use: "link text" },
  { fg: "--accent", bg: "--surface", kind: "text", use: "link text" },
  // Band colors as text: dial captions and band labels can be 12 px.
  ...["--free", "--tight", "--full"].flatMap((fg) =>
    ["--surface", "--bg"].map((bg) => ({ fg, bg, kind: "text", use: "band label" })),
  ),
  // Dial strokes against the surfaces a dial can sit on.
  ...["--free", "--tight", "--full"].flatMap((fg) =>
    ["--surface", "--surface-2", "--bg"].map((bg) => ({
      fg,
      bg,
      kind: "non-text",
      use: "dial stroke",
    })),
  ),
  // Focus ring (3 px --accent outline, 2 px offset).
  ...["--bg", "--surface", "--surface-2"].map((bg) => ({
    fg: "--accent",
    bg,
    kind: "non-text",
    use: "focus ring",
  })),
  { fg: "--excluded", bg: "--surface", kind: "non-text", use: "Excluded swatch boundary" },
  { fg: "--alternative", bg: "--surface", kind: "info", use: "Alternative fill (decorative)" },
];

// ---------- CSS parsing ----------

/** Returns the top-level rules of a stylesheet as { prelude, body } pairs. */
function topLevelRules(css) {
  const rules = [];
  let depth = 0;
  let preludeStart = 0;
  let bodyStart = -1;
  let prelude = "";
  for (let i = 0; i < css.length; i += 1) {
    const ch = css[i];
    if (ch === "{") {
      if (depth === 0) {
        prelude = css.slice(preludeStart, i).trim();
        bodyStart = i + 1;
      }
      depth += 1;
    } else if (ch === "}") {
      depth -= 1;
      if (depth < 0) throw new Error(`Unbalanced "}" at offset ${i} in globals.css.`);
      if (depth === 0) {
        rules.push({ prelude, body: css.slice(bodyStart, i) });
        preludeStart = i + 1;
      }
    } else if (ch === ";" && depth === 0) {
      // Statement at-rules such as @import.
      preludeStart = i + 1;
    }
  }
  if (depth !== 0) throw new Error("Unbalanced braces in globals.css.");
  return rules;
}

const HEX_RE = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

/** Reads `--name: #hex;` declarations from a rule body, skipping non-hex values. */
function hexDeclarations(body) {
  const tokens = {};
  for (const match of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    const value = match[2].trim();
    if (HEX_RE.test(value)) tokens[match[1]] = value.toUpperCase();
  }
  return tokens;
}

function parseTokens(css) {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const light = {};
  const darkOverrides = {};
  let darkBlocks = 0;

  for (const rule of topLevelRules(stripped)) {
    if (rule.prelude === ":root") {
      Object.assign(light, hexDeclarations(rule.body));
    } else if (/^@media\b[^{]*prefers-color-scheme\s*:\s*dark/i.test(rule.prelude)) {
      for (const inner of topLevelRules(rule.body)) {
        if (inner.prelude === ":root") {
          Object.assign(darkOverrides, hexDeclarations(inner.body));
          darkBlocks += 1;
        }
      }
    }
  }

  if (Object.keys(light).length === 0) {
    throw new Error("No light `:root` color tokens found in globals.css.");
  }
  if (darkBlocks === 0) {
    throw new Error(
      "No dark `:root` block found inside `@media (prefers-color-scheme: dark)` in globals.css.",
    );
  }
  // Dark inherits any light token it doesn't override, as the cascade does.
  return { light, dark: { ...light, ...darkOverrides } };
}

// ---------- WCAG 2.x contrast ----------

function hexToRgb(hex) {
  let h = hex.slice(1);
  if (h.length === 3) h = [...h].map((c) => c + c).join("");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}

function relativeLuminance(hex) {
  const [r, g, b] = hexToRgb(hex).map((channel) => {
    const c = channel / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(a, b) {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

// Truncate rather than round so a 4.496 ratio never prints as a passing 4.50.
const formatRatio = (ratio) => `${(Math.floor(ratio * 100) / 100).toFixed(2)}:1`;

// ---------- Report ----------

function main() {
  const { light, dark } = parseTokens(readFileSync(CSS_PATH, "utf8"));
  const appearances = [
    ["light", light],
    ["dark", dark],
  ];

  const missing = [];
  for (const [name, tokens] of appearances) {
    for (const { fg, bg } of PAIRS) {
      for (const token of [fg, bg]) {
        if (!tokens[token]) missing.push(`${name} ${token}`);
      }
    }
  }
  if (missing.length > 0) {
    console.error(
      `Missing hex color tokens in globals.css: ${[...new Set(missing)].join(", ")}.\n` +
        "Define each one as a plain hex value in the light and dark :root blocks.",
    );
    process.exit(1);
  }

  const rows = [];
  for (const [name, tokens] of appearances) {
    for (const { fg, bg, kind, use } of PAIRS) {
      const ratio = contrastRatio(tokens[fg], tokens[bg]);
      const required = REQUIRED[kind];
      const result = kind === "info" ? "INFO" : ratio >= required ? "PASS" : "FAIL";
      rows.push({
        appearance: name,
        foreground: `${fg} ${tokens[fg]}`,
        background: `${bg} ${tokens[bg]}`,
        ratio: formatRatio(ratio),
        required: `${required}:1 ${kind}`,
        result,
        use,
      });
    }
  }

  const columns = [
    ["appearance", "Appearance"],
    ["foreground", "Foreground"],
    ["background", "Background"],
    ["ratio", "Ratio"],
    ["required", "Required"],
    ["result", "Result"],
    ["use", "Use"],
  ];
  const widths = columns.map(([key, label]) =>
    Math.max(label.length, ...rows.map((row) => row[key].length)),
  );
  const line = (cells) => cells.map((cell, i) => cell.padEnd(widths[i])).join("  ").trimEnd();

  console.log(`Contrast check: ${CSS_PATH}\n`);
  console.log(line(columns.map(([, label]) => label)));
  console.log(line(widths.map((w) => "-".repeat(w))));
  for (const row of rows) console.log(line(columns.map(([key]) => row[key])));

  const failures = rows.filter((row) => row.result === "FAIL");
  const passes = rows.filter((row) => row.result === "PASS").length;
  const infos = rows.length - passes - failures.length;
  console.log(`\n${passes} passed, ${failures.length} failed, ${infos} informational.`);

  if (failures.length > 0) {
    console.error("\nRaise the contrast of these tokens in app/globals.css:");
    for (const f of failures) {
      console.error(`  ${f.appearance}: ${f.foreground} on ${f.background} is ${f.ratio}, needs ${f.required}`);
    }
    process.exit(1);
  }
}

try {
  main();
} catch (error) {
  console.error(`Contrast check could not run: ${error.message}`);
  process.exit(1);
}
