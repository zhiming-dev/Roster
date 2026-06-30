// WCAG AA contrast audit for the design tokens (spec 002, T026 / SC-003).
// Parses the real token values from app.css so the themes can't silently drift below AA.
// AA: normal text >= 4.5:1. We check each text/background pair against the worst-case
// (lightest) surface it renders on in each theme.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Vitest stubs `*.css` imports to empty, so read the stylesheet from disk (cwd = frontend root).
const css = readFileSync(resolve("src/styles/app.css"), "utf8");

/** Extract the `--name: #hex;` custom properties from a selector's block. */
function tokens(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  const out: Record<string, string> = {};
  for (const line of css.slice(open + 1, close).split("\n")) {
    const m = line.match(/^\s*(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;/);
    if (m) out[m[1]] = m[2];
  }
  return out;
}

function rgb(hex: string): [number, number, number] {
  let h = hex.slice(1);
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

function luminance(hex: string): number {
  const lin = rgb(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [foreground token, background token] — every pair must clear AA normal text (4.5:1).
const PAIRS: Record<"light" | "dark", [string, string][]> = {
  light: [
    ["--text", "--surface"],
    ["--text-2", "--surface"],
    ["--text-3", "--surface"],
    ["--text-3", "--surface-2"],
    ["--accent", "--surface"], // accent used as text (links, labels)
    ["--err", "--surface"], // error text
    ["--on-accent", "--accent"], // text on primary buttons / user bubbles
  ],
  dark: [
    // Dark text is light-on-dark; the lightest panel (surface-2) is the worst case.
    ["--text", "--surface-2"],
    ["--text-2", "--surface-2"],
    ["--text-3", "--surface-2"],
    ["--accent", "--surface-2"],
    ["--err", "--surface-2"],
    ["--on-accent", "--accent"],
  ],
};

const AA_NORMAL = 4.5;

describe.each(["light", "dark"] as const)("WCAG AA contrast — %s theme", (theme) => {
  const t = tokens(theme === "light" ? '[data-theme="light"]' : '[data-theme="dark"]');

  it.each(PAIRS[theme])("%s on %s ≥ 4.5:1", (fg, bg) => {
    const ratio = contrast(t[fg], t[bg]);
    expect(
      ratio,
      `${fg} (${t[fg]}) on ${bg} (${t[bg]}) = ${ratio.toFixed(2)}:1 (need ${AA_NORMAL}:1)`,
    ).toBeGreaterThanOrEqual(AA_NORMAL);
  });
});
