/**
 * The Viewer against the REAL Tetravox embed bundle — WebGL2, WASM, real NIfTI bytes.
 *
 * Skipped unless `TIT_TETRAVOX_EMBED_DIR` names a built embed (`index.html` + `manifest.json`),
 * because that bundle is a released artifact of another repository and is not in this tree
 * (D1/D3, `dev/notes/v3-docker-streamline-plan.md`). Two ways to satisfy it:
 *
 *   # against a local tetravox embed build, with the mock serving it and real files:
 *   TIT_TETRAVOX_EMBED_DIR=/Users/idohaber/00_development/tetravox-wt-embed/packages/embed/dist \
 *   TIT_MOCK_EMBED_DIR=$TIT_TETRAVOX_EMBED_DIR \
 *   TIT_MOCK_DATA_ROOT=/Users/idohaber/datasets/000 \
 *     npx playwright test tests/e2e/viewer-real.spec.ts
 *
 *   # against the container image, which ships the embed at /opt/tetravox/embed:
 *   TIT_TETRAVOX_EMBED_DIR=/opt/tetravox/embed \
 *   TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=... \
 *     npx playwright test tests/e2e/viewer-real.spec.ts
 *
 * What it proves that `viewer.spec.ts` cannot: that a real engine accepts the ViewSpec v2
 * `tit.server` builds and that its dataset workers can actually fetch `/api/files/raw/...` from
 * inside a `sandbox="allow-scripts allow-same-origin"` iframe with the session cookie — real bytes,
 * a real GL context, no fake standing in for either.
 */
import { existsSync, mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, expectSubject, gotoPage, launchElectronApp, openPalette } from "./_helpers";

const EMBED_DIR = process.env.TIT_TETRAVOX_EMBED_DIR;
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

const HAVE_EMBED = EMBED_DIR !== undefined && EMBED_DIR !== "" && existsSync(join(EMBED_DIR, "index.html"));

test.describe("viewer against the real Tetravox embed", () => {
  test.skip(!HAVE_EMBED, "set TIT_TETRAVOX_EMBED_DIR to a built embed (index.html + manifest.json)");

  let app: ElectronApplication;
  let page: Page;

  test.beforeAll(() => {
    mkdirSync(ARTIFACTS, { recursive: true });
  });

  test.beforeEach(async () => {
    app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
    page = await app.firstWindow();
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test.afterEach(async () => {
    await app?.close();
  });

  test("loads sub-ernie's Thalamus scene and renders a real frame", async () => {
    await expect(page).toHaveURL(/^app:\/\/launcher\//);
    await page.fill("#server-url", SERVER_URL);
    await page.fill("#token", TOKEN);
    await page.click("#connect");
    await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });

    await openPalette(page);
    await page.getByTestId("palette-input").fill("ernie");
    await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
    await expectSubject(page, "ernie");

    await gotoPage(page, "viewer", "Viewer");
    await expectPage(page, "viewer");

    // R5: draft the selection, then command the load. Selectors are named by control, since the
    // bar's shape now depends on the chosen view type.
    for (const [control, option] of [
      ["kind", "Simulation"],
      ["simulation", "Thalamus"],
    ]) {
      await page.getByTestId(`viewer-select-${control}`).getByRole("combobox").click();
      await page.getByRole("option", { name: option, exact: true }).click();
    }
    await page.getByTestId("viewer-load").click();

    // A real engine takes real time: 13 MB of T1 plus a field volume, decompressed in a worker.
    await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 120_000 });
    // `data-renderer` is `ready.caps.renderer` — proof of a real GL context, and the one thing a
    // fake embed cannot report honestly. It used to be the status bar's `renderer` cell; §11
    // removed the bar, so the fact lives on the host element instead of disappearing with it.
    await expect(page.getByTestId("tetravox-host")).not.toHaveAttribute("data-renderer", "");

    await page.screenshot({ path: join(ARTIFACTS, "viewer-real.png") });
  });
});
