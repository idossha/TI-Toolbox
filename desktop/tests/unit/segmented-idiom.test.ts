/**
 * DESIGN.md §4.2 rule 9, enforced over the source tree: **a small exclusive choice is a
 * `SegmentedControl`**.
 *
 * Lane FIX-D wrote the rule and converted six call sites; eight more, outside the files it owned,
 * still rendered the identical idea as a `RadioGroup` — including `ui/CoordinateInput.tsx`'s
 * subject/MNI space, which is the same choice `pages/_shared/roi/RoiPicker.tsx` renders as a
 * segment 40 px away in the same dialog flow. A rule that only one lane's files obey is not a
 * rule, and no e2e spec can catch a page nobody wrote a spec for, so the guard is a scan.
 *
 * `RadioGroup` is not banned: it is what a segment cannot carry (five or more options, or options
 * that each need a sentence — `layout="cards"`). Anything that keeps it says so here, with the
 * reason, so the exception is a decision on the record rather than an oversight.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "../../src/renderer");

/**
 * Files that keep a `RadioGroup` on purpose, each with the reason a segment cannot carry it.
 * Anything not listed here is a defect the moment it renders one.
 */
const ALLOWED = new Map<string, string>([
  ["ui/Toggle.tsx", "defines the component"],
  ["dev/Gallery.tsx", "documents both components — the gallery IS the catalog of primitives"],
]);

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sources(path));
    else if (entry.name.endsWith(".tsx") || entry.name.endsWith(".ts")) out.push(path);
  }
  return out;
}

describe("DESIGN.md §4.2 rule 9 — one idiom for a small exclusive choice", () => {
  it("no file renders a <RadioGroup> except the ones that state why", () => {
    const offenders: string[] = [];
    for (const path of sources(SRC)) {
      const rel = relative(SRC, path);
      if (ALLOWED.has(rel)) continue;
      const text = readFileSync(path, "utf8");
      for (const match of text.matchAll(/<RadioGroup[\s/>]/g)) {
        offenders.push(`${rel}:${text.slice(0, match.index).split("\n").length}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("every SegmentedControl call site names the choice, so a spec and a screen reader can address it", () => {
    const missing: string[] = [];
    for (const path of sources(SRC)) {
      const rel = relative(SRC, path);
      if (rel === "ui/SegmentedControl.tsx") continue;
      const text = readFileSync(path, "utf8");
      // Each `<SegmentedControl … />` element, whether one line or many. It is always
      // self-closing (the component takes no children), so `/>` ends it — a bare `>` would end
      // it inside the first `(v) => …` handler instead.
      for (const match of text.matchAll(/<SegmentedControl\b[\s\S]*?\/>/g)) {
        const element = match[0];
        if (!/aria-label[=\s]/.test(element)) {
          const line = text.slice(0, match.index).split("\n").length;
          missing.push(`${rel}:${line}`);
        }
      }
    }
    expect(missing).toEqual([]);
  });
});
