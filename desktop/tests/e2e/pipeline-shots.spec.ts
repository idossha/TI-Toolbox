/**
 * Before/after evidence for the Pipeline canvas revamp, at 1440.
 *
 * The "before" is not a screenshot of an older build. It is **this** build with the largest cause
 * of the defect put back: `pipeline.css`'s custom properties renamed to the vocabulary the original
 * file used — `--surface-default`, `--text-muted`, `--font-size-sm`, `--border-subtle`,
 * `--radius-md`, `--shadow-sm`, `--accent-primary` — none of which `ui/tokens.css` defines. A
 * browser drops a declaration whose custom property is undefined and reports nothing, so the card
 * loses its padding, border, background, radius and shadow in one silent go.
 *
 * Doing it this way, rather than by rebuilding an old commit, keeps the two images different in
 * nothing but the thing under discussion — same graph, same viewport, same data — and does not
 * require checking an old tree out from under the other lanes building in this worktree.
 *
 * **What this shot does not restage, and should not be read as restaging.** Two other things made
 * the card in the maintainer's screenshot look enormous, and both are fixed in the page rather than
 * in the stylesheet, so neither is undone here:
 *
 *  - the right pane's `clamp(320px, 45vw, …)` default left the canvas **348 px** wide (measured),
 *    so one card filled it;
 *  - `fitView` ran with React Flow's own `maxZoom` of 2 and nothing else on the canvas to fit, so a
 *    single card was scaled up to twice its size. `fitViewOptions={{ maxZoom: 1 }}` caps it now.
 *
 * The type itself is the one thing the rename cannot take away, and the comment inside the
 * injection says why: this rewrite states sizes in literal px, and even with them deleted the card
 * inherits the app's own 13 px body type rather than growing. The apparent ~40 px in the screenshot
 * is 13 px through a 2× canvas zoom in a 348 px box.
 */
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = join(__dirname, "artifacts");

/** The exact renames that turn the fixed stylesheet back into the broken one. */
const BROKEN_TOKENS: [string, string][] = [
  ["--surface-2", "--surface-sunken"],
  ["--surface", "--surface-default"],
  ["--ink-2", "--text-muted"],
  ["--ink", "--text-primary"],
  ["--line-strong", "--border-strong"],
  ["--line", "--border-subtle"],
  ["--accent-soft", "--accent-soft-x"],
  ["--accent", "--accent-primary"],
  ["--radius-card", "--radius-md"],
  ["--radius-control", "--radius-sm"],
  ["--radius-chip", "--radius-pill"],
  ["--shadow-2", "--shadow-md"],
];

let app: ElectronApplication;
let page: Page;

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-pipeshot-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  mkdirSync(ARTIFACTS, { recursive: true });
});

test.afterAll(async () => {
  await app?.close();
});

async function sampleCanvas() {
  await page.getByRole("link", { name: "Pipeline", exact: true }).click();
  await expect(page.getByTestId("pipeline-canvas")).toBeVisible();
  const cards = page.locator("[data-testid^='pipeline-node-']");
  if ((await cards.count()) === 0) {
    await page.getByTestId("pipeline-sample").click();
    await expect(page.getByTestId("pipeline-node-an1")).toBeVisible();
  }
  await expect(page.getByTestId("pipeline-receipt")).toBeVisible();
}

/** Settled: validation has come back and the page is in the state a reader would judge it in. */
async function settled() {
  await expect(page.getByTestId("pipeline-receipt")).toContainText("in one group");
  await expect(page.getByTestId("pipeline-run")).toBeEnabled();
}

test("after — the revamped canvas", async () => {
  await sampleCanvas();
  await settled();
  await page.screenshot({ path: join(ARTIFACTS, "pipeline-after.png") });
});

test("before — the same canvas with the stylesheet's undefined tokens restored", async () => {
  await sampleCanvas();
  await settled();

  const broke = await page.evaluate((renames) => {
    let rewritten = 0;
    for (const sheet of Array.from(document.styleSheets)) {
      let rules: CSSRule[];
      try {
        rules = Array.from(sheet.cssRules);
      } catch {
        continue;
      }
      for (let i = rules.length - 1; i >= 0; i--) {
        const rule = rules[i]!;
        if (!rule.cssText.includes(".pipeline-")) continue;
        let text = rule.cssText;
        for (const [real, fake] of renames) text = text.split(`var(${real})`).join(`var(${fake})`);
        // The original spelled every size `var(--font-size-xs)` / `var(--font-size-sm)` and so had
        // no font-size at all; this rewrite states them in literal px, so they are deleted here to
        // match. (It changes little on screen — with none of its own the card inherits the app's
        // 13 px body type — which is exactly why the header above says the screenshot's apparent
        // 40 px was the canvas zoom, not the stylesheet.)
        text = text.replace(/(^|[;{]\s*)font-size:[^;}]*;?/g, "$1");
        if (text === rule.cssText) continue;
        try {
          sheet.deleteRule(i);
          sheet.insertRule(text, i);
          rewritten++;
        } catch {
          /* a rule the parser will not take back is not one worth failing over */
        }
      }
    }
    return rewritten;
  }, BROKEN_TOKENS);

  // The reproduction has to actually reproduce: if nothing was rewritten, the shot is a duplicate
  // of the "after" and proves nothing.
  expect(broke).toBeGreaterThan(10);

  // The defect, measured on the live card: it has lost its border, its own background, its radius
  // and its shadow — every one of them dropped without a word because the token did not exist.
  const card = page.getByTestId("pipeline-node-pre1");
  const style = await card.evaluate((el) => {
    const s = getComputedStyle(el);
    return { border: s.borderTopWidth, background: s.backgroundColor, radius: s.borderTopLeftRadius, shadow: s.boxShadow };
  });
  expect(style.border).toBe("0px");
  expect(style.background).toBe("rgba(0, 0, 0, 0)");
  expect(style.radius).toBe("0px");
  expect(style.shadow).toBe("none");

  await page.screenshot({ path: join(ARTIFACTS, "pipeline-before.png") });
});
