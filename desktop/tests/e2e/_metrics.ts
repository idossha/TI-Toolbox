/**
 * The instrument every v3 build lane and the critic panel measure with (DESIGN.md §12.1, program
 * U10, `dev/notes/v3-ui-program/u0-design-notes.md` §3.8).
 *
 * "An agent judges numbers, not pictures." A screenshot is an artifact a human opens later; the
 * assertions are made on the three functions below and on the `metrics.json` they feed. Nothing
 * here asserts — the readers return numbers so a lane's own spec can state its own limits.
 *
 * All three read the shell's DOM contract, which is why the contract is testids and not classes:
 *   [data-testid="shell-content"]     the content box (app/Shell.tsx)
 *   [data-testid="nav-rail"]          the nav rail (app/NavRail.tsx)
 *   [data-testid="page-work"]         the work pane (ui/Layout.tsx)
 *   [data-testid="page-right-pane"]   the right pane — ABSENT when a page has none, never empty
 * Page measurements read only `[data-page-active="true"]`: visited hidden tabs keep their DOM,
 * but must not contribute dimensions or have their remembered scroll positions reset by a capture.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import type { Page } from "@playwright/test";
import { setTheme, type Theme } from "./_helpers";

export interface DOMRectLike {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface DeadSpace {
  ratio: number;
  samples: number;
  dead: number;
  rect: DOMRectLike;
}

/**
 * Fraction of a 16 px grid over `selector` whose topmost element is not content (DESIGN.md §12.1).
 *
 * The `< 25 % of the sampled rect` clause on background-colour is load-bearing: without it a page
 * could paint one giant surface and score zero, which is exactly the failure U1 exists to catch. A
 * chip, a tile or a table header is small enough to count; a pane's own ground is not.
 *
 * Two caller obligations the number is only honest with (u0 §1.1): take it AFTER the page's own
 * loaded marker (a skeleton is content and would flatter it), and with the work pane scrolled to
 * the top, because `elementFromPoint` reads the viewport.
 */
export async function deadSpaceRatio(
  page: Page,
  selector = '[data-testid="shell-content"]',
  step = 16,
): Promise<DeadSpace> {
  return page.evaluate(
    ({ selector, step }) => {
      const root = Array.from(document.querySelectorAll(selector)).find((el) => !el.closest('[data-page-active="false"]'));
      if (!root) throw new Error(`deadSpaceRatio: no element for ${selector}`);
      const r = root.getBoundingClientRect();
      const rectArea = r.width * r.height;
      const TAGS = new Set(["CANVAS", "IFRAME", "IMG", "SVG", "VIDEO", "INPUT", "SELECT", "TEXTAREA", "BUTTON", "A"]);

      const isContent = (el: Element | null): boolean => {
        if (!el || !root.contains(el)) return false;
        if (TAGS.has(el.tagName)) return true;
        if (el.childElementCount === 0 && (el.textContent ?? "").trim() !== "") return true;
        const cs = getComputedStyle(el);
        const bg = cs.backgroundColor;
        const transparent = bg === "transparent" || /rgba\(\s*0,\s*0,\s*0,\s*0\s*\)/.test(bg);
        if (!transparent) {
          const b = el.getBoundingClientRect();
          if (b.width * b.height < rectArea * 0.25) return true; // a chip, a tile, a table header
        }
        if (cs.backgroundImage !== "none") return true;
        return false;
      };

      let samples = 0;
      let dead = 0;
      for (let y = r.top + 8; y < r.bottom - 1; y += step) {
        for (let x = r.left + 8; x < r.right - 1; x += step) {
          samples++;
          if (!isContent(document.elementFromPoint(x, y))) dead++;
        }
      }
      return {
        ratio: samples ? dead / samples : 0,
        samples,
        dead,
        rect: { x: r.x, y: r.y, width: r.width, height: r.height },
      };
    },
    { selector, step },
  );
}

export interface PaneWidths {
  nav: number;
  content: number;
  work: number;
  right: number;
  /** The gap between the work pane's right edge and the right pane's left edge (the drag handle). */
  gap: number;
}

/**
 * The four widths §12.3 states its limits in, rounded. An absent or hidden pane reports `0` —
 * that is how "never an empty pane" (U1) is asserted rather than described.
 */
export async function paneWidths(page: Page): Promise<PaneWidths> {
  return page.evaluate(() => {
    const width = (sel: string): number => {
      const el = document.querySelector(sel);
      return el ? Math.round(el.getBoundingClientRect().width) : 0;
    };
    const work = document.querySelector('[data-page-active="true"] [data-testid="page-work"]:not([hidden])');
    const right = document.querySelector('[data-page-active="true"] [data-testid="page-right-pane"]:not([hidden])');
    const gap =
      work && right
        ? Math.round(right.getBoundingClientRect().left - work.getBoundingClientRect().right)
        : 0;
    return {
      nav: width('[data-testid="nav-rail"]'),
      content: width('[data-testid="shell-content"]'),
      work: width('[data-page-active="true"] [data-testid="page-work"]'),
      right: width('[data-page-active="true"] [data-testid="page-right-pane"]'),
      gap,
    };
  });
}

export interface FirstScreen {
  total: number;
  visible: number;
  /** Accessible names of the controls below the fold, so a failure says *which* one fell off. */
  hidden: string[];
}

/**
 * Every Tier-1 control of a run page, and whether it is on the first screen with the work pane
 * scrolled to the top (DESIGN.md §8, §12.1). A page marks its always-open sections `data-tier="1"`.
 */
export async function firstScreenControls(page: Page): Promise<FirstScreen> {
  return page.evaluate(() => {
    const work = document.querySelector('[data-page-active="true"] [data-testid="page-work"]');
    if (!work) return { total: 0, visible: 0, hidden: [] as string[] };
    const scroller = (work.querySelector("[data-page-work-scroll]") ?? work) as HTMLElement;
    scroller.scrollTop = 0;
    const bottom = work.getBoundingClientRect().bottom;
    const nodes = Array.from(
      work.querySelectorAll<HTMLElement>(
        '[data-tier="1"] input, [data-tier="1"] select, [data-tier="1"] textarea, [data-tier="1"] button, ' +
          '[data-tier="1"] [role="combobox"], [data-tier="1"] [role="radiogroup"], [data-tier="1"] [role="switch"]',
      ),
    );
    const name = (el: HTMLElement): string =>
      el.getAttribute("aria-label") ??
      el.getAttribute("name") ??
      (el.textContent ?? "").trim().slice(0, 40) ??
      el.tagName;
    const hidden: string[] = [];
    let visible = 0;
    for (const el of nodes) {
      const r = el.getBoundingClientRect();
      // A zero-size control is inside a collapsed disclosure; Tier 1 is never collapsed, so it
      // being zero-size means it is not on this screen either.
      if (r.height > 0 && r.bottom <= bottom + 0.5) visible++;
      else hidden.push(name(el));
    }
    return { total: nodes.length, visible, hidden };
  });
}

export interface PageMetrics {
  page: string;
  theme: Theme;
  width: number;
  height: number;
  deadSpaceRatio: number;
  samples: number;
  dead: number;
  panes: PaneWidths;
  firstScreenControls: FirstScreen;
  /** The shell's registered status cells, by id — §11's "only registered cells" made measurable. */
  statusCells: string[];
  /** Height of any page header on screen. §8: 0 px everywhere but Settings and Help. */
  pageHeaderHeight: number;
  screenshot: string;
}

/** `tests/e2e/artifacts/<runId>/`, agreeing with `playwright.config.ts`'s TIT_E2E_ARTIFACTS. */
export function artifactDir(runId: string): string {
  const configured = process.env.TIT_E2E_ARTIFACTS;
  if (configured && basename(configured) === runId) return configured;
  return join(__dirname, "artifacts", runId);
}

/**
 * Sets the theme and the viewport, lets the page settle, screenshots into the run's artifact
 * directory and returns the row `metrics.json` is built from.
 *
 * `waitFor` is the page's own loaded marker — pass a locator/predicate that is only true once the
 * page has data. Without it the metric measures a skeleton, which counts as content and flatters
 * the ratio (u0 §1.1).
 */
export async function captureScreen(
  page: Page,
  opts: {
    runId: string;
    pageId: string;
    theme: Theme;
    width: number;
    height: number;
    waitFor?: () => Promise<void>;
  },
): Promise<PageMetrics> {
  await page.setViewportSize({ width: opts.width, height: opts.height });
  await setTheme(page, opts.theme);
  if (opts.waitFor) await opts.waitFor();
  // A skeleton is content to `deadSpaceRatio`, so wait it out rather than measuring it. Best
  // effort: a page with no skeleton at all resolves immediately, and one that never settles is
  // measured anyway with the number it earned.
  await page
    .waitForFunction(() => Array.from(document.querySelectorAll(".skeleton")).every((el) => el.closest('[data-page-active="false"]')), undefined, { timeout: 5_000 })
    .catch(() => undefined);
  await page.evaluate(() => {
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('[data-page-active="true"] [data-page-work-scroll]'))) el.scrollTop = 0;
  });

  const dir = artifactDir(opts.runId);
  mkdirSync(dir, { recursive: true });
  const screenshot = `${opts.pageId}-${opts.theme}-${opts.width}x${opts.height}.png`;
  await page.screenshot({ path: join(dir, screenshot) });

  const dead = await deadSpaceRatio(page);
  const panes = await paneWidths(page);
  const first = await firstScreenControls(page);
  const statusCells = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>("[data-status-cell]")).map(
      (el) => el.dataset.statusCell ?? "",
    ),
  );
  const pageHeaderHeight = await page.evaluate(() => {
    const el = document.querySelector('[data-page-active="true"] .page-header');
    return el ? Math.round(el.getBoundingClientRect().height) : 0;
  });

  return {
    page: opts.pageId,
    theme: opts.theme,
    width: opts.width,
    height: opts.height,
    deadSpaceRatio: Number(dead.ratio.toFixed(4)),
    samples: dead.samples,
    dead: dead.dead,
    panes,
    firstScreenControls: first,
    statusCells,
    pageHeaderHeight,
    screenshot,
  };
}

/** Writes `tests/e2e/artifacts/<runId>/metrics.json` (DESIGN.md §12.2's shape). */
export async function writeMetrics(runId: string, rows: PageMetrics[]): Promise<void> {
  const dir = artifactDir(runId);
  mkdirSync(dir, { recursive: true });
  const body = { runId, capturedAt: new Date().toISOString(), pages: rows };
  writeFileSync(join(dir, "metrics.json"), `${JSON.stringify(body, null, 2)}\n`);
}

export interface Obstructed {
  /** Accessible-ish name of the control that cannot be reached. */
  name: string;
  /** The element the browser's own hit test returned at the control's centre instead. */
  covering: string;
  /** `main.scrollTop` at which it was measured. */
  scrollTop: number;
}

export interface ActionBarReach {
  /** Steps of the work pane's scroll range that were scanned. */
  steps: number;
  scrollHeight: number;
  clientHeight: number;
  /** Interactive elements examined at each step. */
  controls: number;
  /** Controls whose own centre hit-tests to something else — the L4 defect, made measurable. */
  obstructed: Obstructed[];
}

/**
 * L4 made measurable: **no interactive control is under the action bar at any scroll position.**
 *
 * The failure it catches (lane UC, on the real container): `.page-layout-main` was the scroller
 * AND the action bar's flex parent, so the bar rendered inside the overflowing content and no
 * scroll position — Playwright's `scrollIntoViewIfNeeded` included — ever cleared it. UC found the
 * same ~29 px overlap at every one of 17 scroll offsets. `force: true` does not rescue a click
 * there: Chromium's hit-testing still resolves the point to the bar, so the click is swallowed
 * silently. Hence this reads `elementFromPoint` — the browser's own answer — rather than comparing
 * rectangles, which would miss a bar that is transparent or a control that is merely clipped.
 *
 * Scans the whole scroll range in `step` px and, at each stop, hit-tests the centre of every
 * enabled interactive control in the work pane. A control is obstructed when the element at its
 * centre is neither itself nor one of its descendants/ancestors.
 */
export async function actionBarReach(page: Page, step = 40): Promise<ActionBarReach> {
  return page.evaluate((step) => {
    const work = document.querySelector('[data-page-active="true"] [data-testid="page-work"]') as HTMLElement | null;
    if (!work) return { steps: 0, scrollHeight: 0, clientHeight: 0, controls: 0, obstructed: [] };
    const scroller = (work.querySelector("[data-page-work-scroll]") ?? work) as HTMLElement;
    const label = (el: Element): string => {
      const h = el as HTMLElement;
      return (
        h.getAttribute("aria-label") ??
        h.getAttribute("data-testid") ??
        h.getAttribute("name") ??
        `${el.tagName.toLowerCase()}${el.className ? `.${String(h.className).split(" ")[0]}` : ""}` +
          (h.textContent ? ` "${h.textContent.trim().slice(0, 24)}"` : "")
      );
    };
    const start = scroller.scrollTop;
    const obstructed: Obstructed[] = [];
    let controls = 0;
    let steps = 0;
    const max = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
    for (let top = 0; ; top += step) {
      const at = Math.min(top, max);
      scroller.scrollTop = at;
      steps++;
      const nodes = Array.from(
        scroller.querySelectorAll<HTMLElement>(
          'input, select, textarea, button, [role="combobox"], [role="switch"], [role="radio"], [role="checkbox"], [role="tab"], a[href]',
        ),
      ).filter((el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true");
      for (const el of nodes) {
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) continue; // collapsed disclosure, or visually hidden
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        // Only judge a control the scroll position actually put on screen, and only when its
        // centre is a pixel clear of the scrollport's own edges: a control centred exactly ON the
        // boundary hit-tests to whatever owns the next pixel (the action bar, which begins there),
        // which is a measurement artifact and not an unreachable control. One still below the fold
        // at this step gets its turn at a later one.
        const port = scroller.getBoundingClientRect();
        if (cy <= port.top + 1 || cy >= port.bottom - 1) continue;
        controls++;
        const hit = document.elementFromPoint(cx, cy);
        if (!hit) continue;
        if (hit === el || el.contains(hit) || hit.contains(el)) continue;
        obstructed.push({ name: label(el), covering: label(hit), scrollTop: at });
      }
      if (at >= max) break;
    }
    scroller.scrollTop = start;
    return {
      steps,
      scrollHeight: scroller.scrollHeight,
      clientHeight: scroller.clientHeight,
      controls,
      obstructed,
    };
  }, step);
}

export interface Overflow {
  /** `document.scrollingElement`'s horizontal overflow — must be 0, the page never scrolls sideways. */
  page: number;
  /** Elements wider than their own scrollport that are NOT their own `overflow-x` container. */
  offenders: { selector: string; scrollWidth: number; clientWidth: number }[];
}

/**
 * §4.3 made measurable: **the page never scrolls sideways**; wide content scrolls inside its own
 * container. An element counts as an offender only when it overflows horizontally *and* its
 * computed `overflow-x` is `visible` — i.e. it pushes the overflow up to an ancestor.
 */
export async function horizontalOverflow(page: Page): Promise<Overflow> {
  return page.evaluate(() => {
    const root = document.scrollingElement as HTMLElement;
    const offenders: { selector: string; scrollWidth: number; clientWidth: number }[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('[data-testid="shell-content"] *'))) {
      if (el.closest('[data-page-active="false"]')) continue;
      if (el.scrollWidth - el.clientWidth <= 1) continue;
      if (getComputedStyle(el).overflowX !== "visible") continue;
      offenders.push({
        selector:
          el.getAttribute("data-testid") ??
          `${el.tagName.toLowerCase()}${el.className ? `.${String(el.className).split(" ")[0]}` : ""}`,
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      });
    }
    return { page: Math.max(0, root.scrollWidth - root.clientWidth), offenders };
  });
}

export interface DeadBand {
  y0: number;
  y1: number;
  ratio: number;
  samples: number;
}

export interface DeadProfile {
  content: number;
  work: number;
  right: number;
  /** Horizontal bands of the work pane, top to bottom — where the emptiness actually is. */
  bands: DeadBand[];
}

/**
 * `deadSpaceRatio` split by pane and by horizontal band.
 *
 * A single number says a page is 61 % empty; it does not say whether that is a right pane with
 * nothing in it, a form whose second column is unused, or 200 px of nothing above the action bar —
 * and those three have nothing in common as fixes. This is the diagnostic the layout rounds are
 * steered by; the gate stays the single number.
 */
export async function deadSpaceProfile(page: Page, bands = 8, step = 16): Promise<DeadProfile> {
  return page.evaluate(
    ({ bands, step }) => {
      const isContentFactory = (root: Element, rectArea: number) => {
        const TAGS = new Set(["CANVAS", "IFRAME", "IMG", "SVG", "VIDEO", "INPUT", "SELECT", "TEXTAREA", "BUTTON", "A"]);
        return (el: Element | null): boolean => {
          if (!el || !root.contains(el)) return false;
          if (TAGS.has(el.tagName)) return true;
          if (el.childElementCount === 0 && (el.textContent ?? "").trim() !== "") return true;
          const cs = getComputedStyle(el);
          const bg = cs.backgroundColor;
          const transparent = bg === "transparent" || /rgba\(\s*0,\s*0,\s*0,\s*0\s*\)/.test(bg);
          if (!transparent) {
            const b = el.getBoundingClientRect();
            if (b.width * b.height < rectArea * 0.25) return true;
          }
          if (cs.backgroundImage !== "none") return true;
          return false;
        };
      };
      const ratioOf = (sel: string): number => {
        const root = document.querySelector(sel);
        if (!root) return 0;
        const r = root.getBoundingClientRect();
        const isContent = isContentFactory(root, r.width * r.height);
        let samples = 0;
        let dead = 0;
        for (let y = r.top + 8; y < r.bottom - 1; y += step) {
          for (let x = r.left + 8; x < r.right - 1; x += step) {
            samples++;
            if (!isContent(document.elementFromPoint(x, y))) dead++;
          }
        }
        return samples ? dead / samples : 0;
      };

      const work = document.querySelector('[data-page-active="true"] [data-testid="page-work"]');
      const out: DeadBand[] = [];
      if (work) {
        const r = work.getBoundingClientRect();
        const isContent = isContentFactory(work, r.width * r.height);
        const h = r.height / bands;
        for (let b = 0; b < bands; b++) {
          const y0 = r.top + b * h;
          const y1 = y0 + h;
          let samples = 0;
          let dead = 0;
          for (let y = y0 + 4; y < y1 - 1; y += step) {
            for (let x = r.left + 8; x < r.right - 1; x += step) {
              samples++;
              if (!isContent(document.elementFromPoint(x, y))) dead++;
            }
          }
          out.push({ y0: Math.round(y0), y1: Math.round(y1), ratio: samples ? dead / samples : 0, samples });
        }
      }
      return {
        content: ratioOf('[data-testid="shell-content"]'),
        work: ratioOf('[data-page-active="true"] [data-testid="page-work"]'),
        right: ratioOf('[data-page-active="true"] [data-testid="page-right-pane"]'),
        bands: out,
      };
    },
    { bands, step },
  );
}

export interface ChildDead {
  label: string;
  y0: number;
  height: number;
  ratio: number;
  samples: number;
}

/**
 * The dead-space profile one level down: every descendant matching `childSelector` inside
 * `rootSelector`, with its own ratio and its height.
 *
 * `deadSpaceProfile`'s bands say *where* on the page the emptiness is; this says *which component*
 * it belongs to, which is the difference between "the bottom third is empty" and "the Electrodes
 * section is 78 % empty and 230 px tall". Diagnostic only — no gate reads it.
 */
export async function deadSpaceByChild(
  page: Page,
  rootSelector = '[data-testid="page-work"]',
  childSelector = ".form-section, [data-tier], .run-work > *",
  step = 16,
): Promise<ChildDead[]> {
  return page.evaluate(
    ({ rootSelector, childSelector, step }) => {
      const root = Array.from(document.querySelectorAll(rootSelector)).find((el) => !el.closest('[data-page-active="false"]'));
      if (!root) return [];
      const rr = root.getBoundingClientRect();
      const rectArea = rr.width * rr.height;
      const TAGS = new Set(["CANVAS", "IFRAME", "IMG", "SVG", "VIDEO", "INPUT", "SELECT", "TEXTAREA", "BUTTON", "A"]);
      const isContent = (el: Element | null): boolean => {
        if (!el || !root.contains(el)) return false;
        if (TAGS.has(el.tagName)) return true;
        if (el.childElementCount === 0 && (el.textContent ?? "").trim() !== "") return true;
        const cs = getComputedStyle(el);
        const bg = cs.backgroundColor;
        const transparent = bg === "transparent" || /rgba\(\s*0,\s*0,\s*0,\s*0\s*\)/.test(bg);
        if (!transparent) {
          const b = el.getBoundingClientRect();
          if (b.width * b.height < rectArea * 0.25) return true;
        }
        if (cs.backgroundImage !== "none") return true;
        return false;
      };
      const out: ChildDead[] = [];
      const seen = new Set<Element>();
      for (const el of Array.from(root.querySelectorAll<HTMLElement>(childSelector))) {
        if (seen.has(el)) continue;
        seen.add(el);
        const r = el.getBoundingClientRect();
        if (r.height < 8 || r.width < 8) continue;
        let samples = 0;
        let dead = 0;
        for (let y = Math.max(r.top, rr.top) + 4; y < Math.min(r.bottom, rr.bottom) - 1; y += step) {
          for (let x = r.left + 4; x < r.right - 1; x += step) {
            samples++;
            if (!isContent(document.elementFromPoint(x, y))) dead++;
          }
        }
        const title = el.querySelector(".form-section-title")?.textContent?.trim();
        out.push({
          label: title ?? el.getAttribute("data-fill-section") ?? el.getAttribute("data-testid") ?? el.className.split(" ")[0] ?? el.tagName,
          y0: Math.round(r.top),
          height: Math.round(r.height),
          ratio: samples ? dead / samples : 0,
          samples,
        });
      }
      return out;
    },
    { rootSelector, childSelector, step },
  );
}
