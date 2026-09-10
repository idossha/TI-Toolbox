/**
 * Computed-contrast check on the *token values themselves* (ra_12 #3), not on rendered DOM: reads
 * `ui/tokens.css` as text, extracts the hex value of each `--token` in the light `:root` block and
 * in both dark blocks (`prefers-color-scheme` + `[data-theme="dark"]`), and asserts every
 * text-on-filled-background pair a component actually uses (`.btn-primary`, `.btn-destructive`,
 * `.badge` — see `components.css`) meets the DESIGN.md §8 floor of 4.5:1 (WCAG AA normal text).
 *
 * This intentionally does not touch `--on-accent`'s previous hard-coded value ("#fff" inline in
 * components.css) — the whole point of the token is that dark mode's light, low-contrast accent
 * (#7fa6ff) and danger (#f28b7d) fills need a *dark* foreground, which "#fff" never was.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const CSS_PATH = resolve(__dirname, "../../src/renderer/ui/tokens.css");

function extractBlock(css: string, startMarker: string): string {
  const start = css.indexOf(startMarker);
  if (start === -1) throw new Error(`marker not found: ${startMarker}`);
  const braceOpen = css.indexOf("{", start);
  let depth = 0;
  let i = braceOpen;
  for (; i < css.length; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}") {
      depth--;
      if (depth === 0) break;
    }
  }
  return css.slice(braceOpen + 1, i);
}

function extractVars(block: string): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const m of block.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)) {
    vars[m[1]!] = m[2]!.trim();
  }
  return vars;
}

function srgbToLinear(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function relativeLuminance(hex: string): number {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

const HEX = /^#[0-9a-f]{6}$/i;
const AA_NORMAL_TEXT = 4.5;

const css = readFileSync(CSS_PATH, "utf8");
// Markers include the trailing " {" so they only match the actual rule, not this file's own
// header comment describing these three blocks (which quotes the same selector text in
// backticks, with no "{" after it — `indexOf` would otherwise land inside the comment and then
// grab the *next* brace it finds, silently reading the wrong block).
const lightBlock = extractBlock(css, ":root {");
const darkSystemBlock = extractBlock(css, "@media (prefers-color-scheme: dark) {");
const darkExplicitBlock = extractBlock(css, ':root[data-theme="dark"] {');
const light = extractVars(lightBlock);
const darkSystem = extractVars(darkSystemBlock);
const darkExplicit = extractVars(darkExplicitBlock);

// Module scope so every describe block below (filled buttons, soft chips) asserts against the
// same three theme reads rather than three redundant `extractVars` passes.
const themes: Array<[string, Record<string, string>]> = [
  ["light", light],
  ["dark (prefers-color-scheme)", darkSystem],
  ["dark (data-theme explicit)", darkExplicit],
];

describe("token contrast — filled buttons/chips (ra_12 #3)", () => {
  it("every theme defines --on-accent and --on-danger as real hex colours", () => {
    for (const theme of [light, darkSystem, darkExplicit]) {
      expect(theme["on-accent"]).toMatch(HEX);
      expect(theme["on-danger"]).toMatch(HEX);
      expect(theme["accent"]).toMatch(HEX);
      expect(theme["danger"]).toMatch(HEX);
    }
  });

  it.each(themes)("%s: --on-accent on --accent >= 4.5:1", (_name, theme) => {
    const ratio = contrastRatio(theme["accent"]!, theme["on-accent"]!);
    expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it.each(themes)("%s: --on-danger on --danger >= 4.5:1", (_name, theme) => {
    const ratio = contrastRatio(theme["danger"]!, theme["on-danger"]!);
    expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it("the two dark blocks (system-preference and explicit data-theme) agree exactly", () => {
    // DESIGN.md §7: the toggle must win in both directions, which only holds if both dark
    // definitions carry the same values — a drift here would mean "system dark" and "explicit
    // dark" render different button text colours.
    expect(darkSystem["on-accent"]).toBe(darkExplicit["on-accent"]);
    expect(darkSystem["on-danger"]).toBe(darkExplicit["on-danger"]);
    expect(darkSystem["accent"]).toBe(darkExplicit["accent"]);
    expect(darkSystem["danger"]).toBe(darkExplicit["danger"]);
  });

  it("dark mode's fix is real: white text on dark --accent/--danger would have failed", () => {
    // Documents *why* the token exists rather than reusing "#fff" — regression guard against
    // someone reverting components.css back to a literal "#fff".
    expect(contrastRatio(darkExplicit["accent"]!, "#ffffff")).toBeLessThan(AA_NORMAL_TEXT);
    expect(contrastRatio(darkExplicit["danger"]!, "#ffffff")).toBeLessThan(AA_NORMAL_TEXT);
  });
});

describe("token contrast — soft-chip text (critic round 1, findings 2 & 3)", () => {
  // The pair `tests/unit/tokenContrast.test.ts` above never covered: `.chip-<kind>` and
  // `.status-dot-<kind>`'s label text (`ui/components.css`) render `--<kind>` on `--<kind>-soft`,
  // not on a solid fill — `.chip-field` (Results' "TI"/"mTI" badges, Analyzer's field badge) and
  // `.chip-warning` (Subjects' readiness chips, the Plan grid's `overwrite` cell, DESIGN.md §4.5)
  // are real, shipping UI, not a hypothetical pairing. Chip text is 12px (`.chip`) — normal text,
  // so 4.5:1 is the applicable floor, not the 3:1 large-text one.
  const SOFT_KINDS = ["accent", "success", "warning", "danger", "field", "lost"] as const;

  for (const kind of SOFT_KINDS) {
    it.each(themes)(`%s: --${kind} on --${kind}-soft >= 4.5:1`, (_name, theme) => {
      const fg = theme[kind];
      const bg = theme[`${kind}-soft`];
      expect(fg, `--${kind} missing`).toMatch(HEX);
      expect(bg, `--${kind}-soft missing`).toMatch(HEX);
      expect(contrastRatio(fg!, bg!)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });
  }
});

describe("color-scheme narrowing (ra_12 #16)", () => {
  // `color-scheme: light dark` on bare :root lets the browser pick either native-chrome
  // rendering regardless of which palette the page is actually painting (native scrollbars,
  // checkbox/radio chrome can end up dark while Settings = Light, or vice versa). Each block must
  // declare the one scheme it actually paints.
  function colorScheme(block: string): string | undefined {
    const m = block.match(/(?<!-)\bcolor-scheme:\s*([^;]+);/);
    return m?.[1]?.trim();
  }

  it("bare :root declares only light", () => {
    expect(colorScheme(lightBlock)).toBe("light");
  });

  it("both dark blocks declare only dark", () => {
    expect(colorScheme(darkSystemBlock)).toBe("dark");
    expect(colorScheme(darkExplicitBlock)).toBe("dark");
  });
});
