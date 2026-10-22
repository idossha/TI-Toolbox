// @vitest-environment jsdom
/**
 * `resolvePage` ignores a page's own `PageDef.shortcut`: the ⌘-number is the page's index in
 * `NAV_ORDER`, and the only other chord is a `SHORTCUT_ALIASES` key. A page that still declares a
 * shortcut is read by people, so it must name the key that really reaches it — until 2026-10-22 the
 * Analyzer said "6", the Optimizer "4", Overview "1", Pre-processing "2" and the Viewer "7", none of
 * which was its key.
 *
 * Read off the raw page modules, before `resolvePage` overwrites the field.
 */
import { describe, expect, it } from "vitest";

// jsdom ships no `matchMedia`; a page module reaches uPlot through the `ui` barrel at module scope.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

const { NAV_ORDER, SHORTCUT_ALIASES } = await import("../../src/renderer/app/registry");

type RawPage = { id: string; shortcut?: string };
const loaders = import.meta.glob("../../src/renderer/pages/*/index.tsx") as Record<string, () => Promise<{ default: RawPage }>>;
const raw: RawPage[] = await Promise.all(Object.values(loaders).map(async (load) => (await load()).default));

/** The chord that reaches `id`, from the two maps the keyboard handler reads. */
function keyFor(id: string): string | undefined {
  const index = (NAV_ORDER as readonly string[]).indexOf(id);
  if (index >= 0) return String(index);
  return Object.entries(SHORTCUT_ALIASES).find(([, target]) => target === id)?.[0];
}

describe("a page's declared shortcut is the key that reaches it", () => {
  it("reads every workflow page, so the agreement check is not vacuous", () => {
    const ids = raw.map((p) => p.id);
    for (const id of NAV_ORDER) expect(ids).toContain(id);
  });

  it.each(raw.filter((p) => p.shortcut !== undefined).map((p) => [p.id, p.shortcut] as const))(
    "%s declares %s",
    (id, declared) => {
      expect(declared).toBe(keyFor(id));
    },
  );
});
