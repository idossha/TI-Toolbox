/**
 * Every `var(--…)` in `pages/pipeline/pipeline.css` must name a token that exists.
 *
 * This test exists because the first version of that file did not. It was written against a token
 * vocabulary from some other design system — `--surface-default`, `--text-muted`, `--font-size-sm`,
 * `--border-subtle`, `--radius-md`, `--shadow-sm`, `--accent-primary` — 36 references, none of
 * them defined in `ui/tokens.css` or anywhere else. CSS drops a declaration whose custom property
 * is undefined **and reports nothing**: no console warning, no build error, no failing test. So
 * every visual property on the node card, the palette and the port handles was thrown away, the
 * card inherited React Flow's default type and grew to roughly three times this app's density,
 * and the page shipped looking broken while every one of its behaviours worked.
 *
 * A guard has to be able to fail, so: flip any `var(--line)` in `pipeline.css` to
 * `var(--line-subtle)` and this test goes red naming it.
 *
 * Scope is deliberately this one page. Eight references in four *other* stylesheets
 * (`jobs-rail.css`, `scene-pane.css`, `optimizer.css`, `viewer-page.css`) are undefined in the
 * same way; they belong to other lanes and are not this one's to change. Widening the glob to
 * `src/renderer/**\/*.css` is the follow-up, and it is a one-line edit here once those are fixed.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(__dirname, "../../src/renderer");
const tokens = readFileSync(resolve(root, "ui/tokens.css"), "utf8");
const pipeline = readFileSync(resolve(root, "pages/pipeline/pipeline.css"), "utf8");

/** Custom properties this stylesheet may use: every one `tokens.css` defines, plus its own. */
function declared(...sources: string[]): Set<string> {
  const names = new Set<string>();
  for (const source of sources) {
    for (const match of source.matchAll(/(^|[;{\s])(--[a-z0-9-]+)\s*:/gi)) names.add(match[2]!);
  }
  return names;
}

/** Only the *first* argument of a `var()` has to exist — a second argument is the fallback. */
function referenced(source: string): string[] {
  return [...source.matchAll(/var\(\s*(--[a-z0-9-]+)\s*\)/gi)].map((m) => m[1]!);
}

describe("pages/pipeline/pipeline.css uses only tokens that exist", () => {
  it("references no undefined custom property", () => {
    const known = declared(tokens, pipeline);
    const unknown = [...new Set(referenced(pipeline))].filter((name) => !known.has(name)).sort();
    expect(unknown).toEqual([]);
  });

  it("still checks something — tokens.css really does define the app's vocabulary", () => {
    const known = declared(tokens);
    for (const token of ["--ink", "--surface", "--line", "--accent", "--row-h", "--space-2"]) {
      expect(known).toContain(token);
    }
    expect(referenced(pipeline).length).toBeGreaterThan(30);
  });
});
