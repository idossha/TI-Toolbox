/**
 * Static checks on `ui/components.css` for fixes that are pure CSS (no React branch to exercise
 * directly): ra_12 #2 (stacked-panel overflow) and #13 (disabled Select has no disabled style).
 * These read the stylesheet as text rather than computing layout, matching
 * `tokenContrast.test.ts`'s approach for the same file family.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "../../src/renderer/ui/components.css"), "utf8");

function extractBlock(text: string, startMarker: string): string {
  const start = text.indexOf(startMarker);
  if (start === -1) throw new Error(`marker not found: ${startMarker}`);
  const braceOpen = text.indexOf("{", start);
  let depth = 0;
  let i = braceOpen;
  for (; i < text.length; i++) {
    if (text[i] === "{") depth++;
    else if (text[i] === "}") {
      depth--;
      if (depth === 0) break;
    }
  }
  return text.slice(braceOpen + 1, i);
}

describe("ra_12 #2 — stacked-panel overflow below 1100px", () => {
  const stacked = extractBlock(css, "@media (max-width: 1099px) {");

  it("the page itself stops forcing a fixed height once the panel stacks under the form", () => {
    // Extract just the nested `.page-layout { ... }` rule inside the media query (not
    // `.page-layout-body`/`-main`/`-panel`, which share the `.page-layout` prefix).
    const rule = extractBlock(stacked, ".page-layout {");
    expect(rule).toMatch(/height:\s*auto/);
  });

  it(".page-layout-main is no longer its own scroller and no longer capped to 960px", () => {
    const rule = extractBlock(stacked, ".page-layout-main {");
    expect(rule).toMatch(/overflow:\s*visible/);
    expect(rule).toMatch(/max-width:\s*none/);
  });

  it(".shell-content remains the only scroller (app/shell.css) — spot-check it still sets overflow: auto", () => {
    const shellCss = readFileSync(resolve(__dirname, "../../src/renderer/app/shell.css"), "utf8");
    const rule = extractBlock(shellCss, ".shell-content {");
    expect(rule).toMatch(/overflow:\s*auto/);
  });
});

describe("ra_12 #6 / U7 — the icon rail shows the mark, not a wrapped wordmark", () => {
  const shellCss = readFileSync(resolve(__dirname, "../../src/renderer/app/shell.css"), "utf8");

  it("the .nav-rail-icons overrides set the expected display values", () => {
    expect(extractBlock(shellCss, ".nav-rail-icons .nav-brand-mark {")).toMatch(/display:\s*flex/);
    expect(extractBlock(shellCss, ".nav-rail-icons .nav-brand-text {")).toMatch(/display:\s*none/);
    expect(extractBlock(shellCss, ".nav-rail-icons {")).toMatch(/width:\s*var\(--nav-w-icons\)/);
  });

  it("the overrides beat the base rules on specificity, not on source order", () => {
    // The bug this shipped with once already was positional: an unconditional
    // `.nav-brand-mark { display: none }` with the SAME specificity as a media-query override,
    // declared later in the file, silently won at every width. v3 moves the rail mode onto a
    // class (`NavRail.tsx` sets it), so the override is two classes to the base rule's one and
    // wins wherever it sits. Assert the shape that makes that true: every icon-rail rule is
    // descended from `.nav-rail-icons`, and no bare `@media` decides the rail's width any more.
    for (const sel of [".nav-brand-mark", ".nav-brand-text", ".nav-label", ".nav-item", ".nav-divider"]) {
      expect(shellCss).toContain(`.nav-rail-icons ${sel} {`);
    }
    expect(shellCss).not.toContain("@media (max-width: 1280px) {");
  });
});

describe("ra_12 #13 — disabled Select/Combobox has a visible disabled style", () => {
  it(".select-trigger:disabled and .combobox-trigger:disabled match .control:disabled's treatment", () => {
    const controlDisabled = extractBlock(css, ".control:disabled {");
    expect(controlDisabled).toMatch(/opacity:\s*0\.5/);
    expect(controlDisabled).toMatch(/cursor:\s*not-allowed/);

    expect(css).toMatch(/\.select-trigger:disabled,\s*\n\s*\.combobox-trigger:disabled\s*\{/);
    const triggerDisabled = extractBlock(css, ".select-trigger:disabled,");
    expect(triggerDisabled).toMatch(/opacity:\s*0\.5/);
    expect(triggerDisabled).toMatch(/cursor:\s*not-allowed/);
  });
});

/**
 * v2 density (DESIGN.md §3). These are the numbers the whole redesign is measured against, and
 * every one of them lives in CSS rather than in a component, so a text assertion on the stylesheet
 * is the honest place to pin them. The Gallery's density ruler measures the same three heights in
 * a real browser (`pages/dev/DensityGallery.tsx`); this is the guard that runs on every commit.
 */
describe("v2 density — tokens", () => {
  const tokens = readFileSync(resolve(__dirname, "../../src/renderer/ui/tokens.css"), "utf8");
  const root = extractBlock(tokens, ":root {");

  it("defines the canonical density tokens at their specified values", () => {
    expect(root).toMatch(/--control-h:\s*28px/);
    expect(root).toMatch(/--row-h:\s*28px/);
    expect(root).toMatch(/--section-header-h:\s*28px/);
    expect(root).toMatch(/--field-label-w:\s*160px/);
    expect(root).toMatch(/--pane-pad:\s*12px/);
  });

  it("keeps the v1 token names working as aliases, so no page needs an edit", () => {
    expect(root).toMatch(/--control-height:\s*var\(--control-h\)/);
    expect(root).toMatch(/--row-height:\s*var\(--row-h\)/);
    expect(root).toMatch(/--control-height-sm:\s*var\(--control-h-sm\)/);
    expect(root).toMatch(/--control-height-lg:\s*var\(--control-h-lg\)/);
  });

  it("defines the shell chrome geometry", () => {
    expect(root).toMatch(/--context-bar-h:\s*40px/);
    expect(root).toMatch(/--action-bar-h:\s*44px/);
    expect(root).toMatch(/--status-bar-h:\s*24px/);
    expect(root).toMatch(/--nav-w:\s*216px/);
    expect(root).toMatch(/--nav-w-icons:\s*56px/);
    expect(root).toMatch(/--inspector-w:\s*300px/);
  });

  it("--canvas is #0b0d10 in BOTH themes: it is defined once on bare :root and never overridden", () => {
    // Imaging convention (Tetravox docs/ARCHITECTURE.md §13): a light viewport changes what a
    // greyscale T1 and a heat overlay look like. A theme block redefining this would silently
    // break every screenshot of the viewer in light mode.
    expect(root).toMatch(/--canvas:\s*#0b0d10/i);
    const darkSystem = extractBlock(tokens, "@media (prefers-color-scheme: dark) {");
    const darkExplicit = extractBlock(tokens, ':root[data-theme="dark"] {');
    expect(darkSystem).not.toMatch(/--canvas:/);
    expect(darkExplicit).not.toMatch(/--canvas:/);
  });

  it("ground inversion is exposed as tokens rather than hard-coded per stylesheet", () => {
    expect(root).toMatch(/--app-ground:\s*var\(--surface\)/);
    expect(root).toMatch(/--gutter:\s*var\(--bg\)/);
    const base = readFileSync(resolve(__dirname, "../../src/renderer/ui/base.css"), "utf8");
    expect(extractBlock(base, "body {")).toMatch(/background:\s*var\(--app-ground\)/);
  });
});

describe("v2 density — geometry", () => {
  it("Field is a label-left grid row at --row-h", () => {
    const field = extractBlock(css, "\n.field {");
    expect(field).toMatch(/display:\s*grid/);
    expect(field).toMatch(/grid-template-columns:\s*var\(--field-label-w\)\s+minmax\(0,\s*1fr\)/);
    expect(field).toMatch(/min-height:\s*var\(--row-h\)/);
  });

  // L4 ("nothing overlaps", plan `dev/notes/v3-scene-ia-plan.md` §4): the section header is a
  // 28px band on --surface-2 — the same object §4.3 defines for a table header — and it is NOT
  // sticky any more. A sticky header inside the pane's own scroller paints over its own body:
  // measured on the Optimizer at 1280x800, five controls (the Target radios, the atlas combobox
  // and the region multi-select) hit-tested to `.form-section-header-trigger "Target"` instead of
  // to themselves at scrollTop 120-200, which is exactly where `scrollIntoViewIfNeeded` parks
  // them. `tests/e2e/layout.spec.ts` is the end-to-end assertion; this pins the rule that fixed it.
  it("FormSection's header is a --section-header-h band and is NOT sticky", () => {
    const header = extractBlock(css, ".form-section-header {");
    expect(header).toMatch(/height:\s*var\(--section-header-h\)/);
    expect(header).toMatch(/background:\s*var\(--surface-2\)/);
    expect(header).not.toMatch(/position:\s*sticky/);
  });

  // L4, the other half: the work pane is not its own scroller — its scroll child is — so the
  // action bar is a `flex: none` sibling OUTSIDE the scrollport and reserves its own 44px.
  // Before this, `.page-layout-main` was `overflow: auto` AND the sticky bar's flex parent, so
  // the bar rendered inside the overflowing content and no scroll offset ever cleared it (lane
  // UC scanned scrollTop 0->161 in 10px steps: the same ~29px overlap at every one).
  it("the run pane's scroller is the scroll child, not the pane that also holds the action bar", () => {
    expect(extractBlock(css, "\n.page-layout-main {")).toMatch(/overflow:\s*hidden/);
    expect(extractBlock(css, "\n.page-layout-main-scroll {")).toMatch(/overflow:\s*auto/);
  });

  it("table header and body rows are --row-h, with a sticky header", () => {
    const th = extractBlock(css, ".data-table thead th {");
    const td = extractBlock(css, ".data-table tbody td {");
    expect(th).toMatch(/height:\s*var\(--row-h\)/);
    expect(th).toMatch(/position:\s*sticky/);
    expect(td).toMatch(/height:\s*var\(--row-h\)/);
  });

  it("Card carries no elevation any more — panes are 1px rules, not floating rectangles", () => {
    const card = extractBlock(css, "\n.card {");
    expect(card).not.toMatch(/box-shadow/);
    // The token itself survives: Popover/Drawer/Dialog/Toast are genuinely above the page.
    expect(css).toMatch(/--shadow-2/);
  });

  it("v3: the work pane has NO cap, and the right pane is --right-pane-w (360/400 by breakpoint)", () => {
    // U1 in one declaration. The 880px cap was the reason a 1280px window showed 900px of nothing
    // beside a form (u0 §1: preprocess 74% dead), and removing it is what lets the work pane take
    // every pixel the right pane does not.
    expect(extractBlock(css, ".page-layout-main {")).not.toMatch(/max-width:\s*880px/);
    expect(extractBlock(css, ".page-layout-panel {")).toMatch(/width:\s*var\(--right-pane-w\)/);
    expect(extractBlock(css, ".page-layout {")).toMatch(/--right-pane-w:\s*360px/);
    expect(extractBlock(css, "@media (min-width: 1440px) {")).toMatch(/--right-pane-w:\s*400px/);
    // A preview pane is a percentage of the content box, floored and ceilinged (DESIGN.md §2.1).
    expect(css).toMatch(/\[data-pane-kind="preview"\]\s*\{\s*width:\s*clamp\(380px, 40%, 560px\)/);
  });

  it("the run shape divides its panes with the 6px handle alone, not with a gap", () => {
    // 1064 content - 2x16 padding - 360 panel - 6 handle = 666, DESIGN.md §2.1's work pane at
    // 1280. A --space-4 gap on each side of the handle would spend 32 of those pixels.
    expect(extractBlock(css, ".page-layout-run .page-layout-body {")).toMatch(/gap:\s*0/);
  });

  it("two-up form rows collapse at 760px, the width below which a label-left row stops fitting", () => {
    expect(css).toMatch(/@container \(max-width: 760px\) \{\s*\.form-grid/);
  });

  it("a full-bleed page negates exactly the shell's own padding token", () => {
    expect(extractBlock(css, ".page-layout-full-bleed {")).toMatch(/margin:\s*calc\(var\(--page-pad\) \* -1\)/);
  });
});

describe("v2 density — the 12px floor", () => {
  // 11px is the chip/eyebrow step. Pairing it with --ink-3 (placeholder/disabled ink, deliberately
  // below the 4.5:1 content floor per tokens.css) produces text nobody can read. Scan every rule
  // in the component stylesheet for that combination.
  it("no rule combines an 11px font-size with --ink-3", () => {
    const offenders: string[] = [];
    for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const body = m[2] ?? "";
      if (/font-size:\s*11px/.test(body) && /color:\s*var\(--ink-3\)/.test(body)) {
        offenders.push((m[1] ?? "").trim());
      }
    }
    expect(offenders).toEqual([]);
  });

  it("base.css's 11px step is the eyebrow/micro step and carries no --ink-3", () => {
    const base = readFileSync(resolve(__dirname, "../../src/renderer/ui/base.css"), "utf8");
    expect(extractBlock(base, ".text-micro {")).toMatch(/font-size:\s*11px/);
    expect(extractBlock(base, ".text-eyebrow {")).toMatch(/color:\s*var\(--ink-2\)/);
    expect(extractBlock(base, ".text-body {")).toMatch(/font-size:\s*13px/);
    expect(extractBlock(base, ".text-body {")).toMatch(/line-height:\s*18px/);
  });
});

describe("shell chrome (plan §1, DESIGN.md §2/§3.3) — app/shell.css", () => {
  const shellCss = readFileSync(resolve(__dirname, "../../src/renderer/app/shell.css"), "utf8");

  // 1280 *inclusive*: 1280x800 is the size DESIGN.md §8 prescribes and the floor the app is built
  // for, and QA measured what the full 216px rail costs there — a 700px work pane against §8's own
  // >=880px floor, and a 764px viewer iframe against the embed's 1000px panel threshold. The rail
  // gives its 160px back at exactly that width, not one pixel below it.
  it("the rail carries labels at >=1440 and icons below it (program Q1)", () => {
    // U7 wanted labels at >=1280, but a 216px rail there leaves a 1064px content box and the
    // Viewer's embed needs >=1200px. Icons below 1440 gives every page the 160px — and means the
    // Viewer needs no special case at all.
    const navRail = readFileSync(resolve(__dirname, "../../src/renderer/app/NavRail.tsx"), "utf8");
    expect(navRail).toContain('LABEL_RAIL_QUERY = "(min-width: 1440px)"');
    expect(navRail).not.toContain("max-width: 1280px");
  });

  it("the content box's padding steps at the same 1440 breakpoint (DESIGN.md §2.1)", () => {
    expect(extractBlock(shellCss, ".shell {")).toMatch(/--page-pad:\s*var\(--space-4\)/);
    expect(extractBlock(shellCss, "@media (min-width: 1440px) {")).toMatch(/--page-pad:\s*var\(--space-6\)/);
  });

  it("ground inversion: the app ground is --app-ground and only the gutters keep --gutter", () => {
    expect(extractBlock(shellCss, ".shell {")).toMatch(/background:\s*var\(--app-ground\)/);
    expect(extractBlock(shellCss, ".nav-rail {")).toMatch(/background:\s*var\(--gutter\)/);
    expect(extractBlock(shellCss, ".jobs-rail {")).toMatch(/background:\s*var\(--gutter\)/);
    // No rule in the shell may paint the old grey ground over the inverted one.
    expect(shellCss).not.toMatch(/background:\s*var\(--bg\)/);
  });

  it("the nav rail is sized by the tokens, not by literals", () => {
    expect(extractBlock(shellCss, ".nav-rail {")).toMatch(/width:\s*var\(--nav-w\)/);
  });

  it("the content box carries exactly the padding a full-bleed page negates", () => {
    const content = extractBlock(shellCss, ".shell-content {");
    expect(content).toMatch(/padding:\s*var\(--page-pad\)/);
    expect(content).toMatch(/overflow:\s*auto/);
    const small = extractBlock(shellCss, "@media (max-width: 899px) {");
    expect(extractBlock(small, ".shell-content {")).toMatch(/padding:\s*var\(--page-pad-sm\)/);
  });

  it("the minimum window is 1024 x 680 (DESIGN.md §2)", () => {
    const shell = extractBlock(shellCss, ".shell {");
    expect(shell).toMatch(/min-width:\s*1024px/);
    expect(shell).toMatch(/min-height:\s*680px/);
  });

  it("the disconnected strip is a warning strip, not a toast", () => {
    const strip = extractBlock(shellCss, ".connection-strip {");
    expect(strip).toMatch(/background:\s*var\(--warning-soft\)/);
    expect(strip).toMatch(/color:\s*var\(--warning\)/);
  });
});
