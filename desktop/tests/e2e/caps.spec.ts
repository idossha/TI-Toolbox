import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, launchElectronApp } from "./_helpers";
import { subjectsSummary } from "./_subjects";

/**
 * EEG caps panel, against the mock server (2026-10-16): the Settings-gated rail row opens the
 * panel already on ernie (the first subject with a head model, 2026-10-20) with its first net
 * inspected, its table filled and its electrodes drawn — no click needed; the caps list shows status; the inspection shows the mock's planted
 * collapsed pair (GSN-HydroCel-185 E1/E2, 0.5 mm) as a warning; Apply on a cap already on the
 * subject opens the in-page existing-outputs dialog instead of a native confirm(), and Replace
 * resends with `overwrite: true` — asserted on the request body, not a toast.
 *
 * Offscreen by default on macOS (`offscreenEnv`). Screenshot: `artifacts/caps-panel.png`.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");
const PANELS = ["caps"];

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-caps-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  // The rail gates a panel on the server's settings.panels, and the mock's seed lacks this one.
  await page.route("**/api/settings", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({ json: { telemetry: { consented: true, enabled: false }, panels: PANELS, image_tag: null, theme: "system" } });
  });
  await page.addInitScript((p: string[]) => {
    window.localStorage.setItem("tit-enabled-panels", JSON.stringify(p));
    window.localStorage.setItem("tit-enabled-panels-synced", "1");
  }, PANELS);
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
});

test.afterAll(async () => {
  await app?.close();
});

test("lists caps, warns on collapsed electrodes, and confirms before replacing", async () => {
  await page.getByRole("link", { name: "EEG caps", exact: true }).click();
  await expectPage(page, "panel-caps");
  // Opens populated: subject, first net, stats, electrodes table and the drawn markers.
  await expect(subjectsSummary(page)).toContainText("ernie");
  await expect(page.getByTestId("caps-summary")).toContainText("256 electrodes");
  await expect(page.getByTestId("caps-electrodes").locator("tbody tr")).toHaveCount(256);
  await expect(page.locator('[data-page-active="true"]').getByTestId("scene-pane-host")).toHaveAttribute("data-state", "ready");
  await expect.poll(() => page.evaluate(() => window.__scenePane?.markers ?? 0)).toBe(256);

  const caps = page.getByTestId("caps-table");
  // Names without ".csv", as every other net picker shows them; no "outdated" status.
  await expect(caps.getByRole("row", { name: /EEG10-10_UI_Jurak_2007 .*not on subject/ })).toBeVisible();
  await expect(caps.getByRole("row", { name: /GSN-HydroCel-185 .*on subject/ })).toBeVisible();
  await expect(caps.getByText(/\.csv|outdated/)).toHaveCount(0);
  // The mock ships GSN as TI-Toolbox's own caps and Jurak as SimNIBS's.
  await expect(caps.getByRole("row", { name: /GSN-HydroCel-185 TI-Toolbox/ })).toBeVisible();
  await expect(caps.getByRole("row", { name: /EEG10-10_UI_Jurak_2007 SimNIBS/ })).toBeVisible();

  // The first net on the subject is inspected by default; clicking a cap's row inspects that one.
  await expect(page.getByTestId("caps-summary")).toContainText("256 electrodes");
  await caps.getByRole("cell", { name: "GSN-HydroCel-185", exact: true }).click();
  await expect(page.getByTestId("caps-summary")).toContainText("185 electrodes");
  await expect(page.getByTestId("caps-warning").first()).toContainText("E1–E2 0.5 mm");
  await expect(page.getByTestId("caps-electrodes").locator("tbody tr")).toHaveCount(185);
  await expect(page.getByTestId("caps-scene").locator("canvas")).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "caps-panel.png") });

  const bodies: unknown[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/caps/warp")) bodies.push(req.postDataJSON());
  });
  await caps.getByRole("checkbox", { name: "Select GSN-HydroCel-185" }).click();
  await page.getByTestId("caps-apply").click();
  await expect(page.getByTestId("existing-outputs-detail")).toBeVisible();
  expect(bodies).toEqual([]);
  await page.getByTestId("existing-outputs-replace").click();
  // The wire carries the cap's FILE name -- the only name the real /api/caps/warp knows
  // (`PathManager.list_eeg_caps`; `tests/test_caps_name_roundtrip.py`) -- though the table shows the stem.
  await expect.poll(() => bodies).toEqual([{ subject: "ernie", caps: ["GSN-HydroCel-185.csv"], overwrite: true }]);

  await caps.getByRole("checkbox", { name: "Select EEG10-10_UI_Jurak_2007" }).click();
  await page.getByTestId("caps-apply").click();
  await expect(caps.getByRole("row", { name: /EEG10-10_UI_Jurak_2007 .*on subject/ })).toBeVisible();
  expect(bodies[1]).toEqual({ subject: "ernie", caps: ["EEG10-10_UI_Jurak_2007.csv"], overwrite: false });
});

test("explains the panel behind its (i) and lays the electrodes table out compactly", async () => {
  await page.setViewportSize({ width: 2000, height: 1100 });
  const electrodes = page.getByTestId("caps-electrodes");
  await expect(electrodes.locator("thead th")).toHaveText(["Label", "Nearest electrode", "Spacing to nearest (mm)", "Distance to scalp (mm)"]);
  // Columns hug their values: the table is narrower than its card.
  const table = await electrodes.locator("table").boundingBox();
  const card = await electrodes.boundingBox();
  expect(table!.width).toBeLessThan(card!.width * 0.8);
  await electrodes.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(ARTIFACTS, "caps-table.png") });

  await page.getByTestId("caps-help").click();
  const help = page.getByTestId("caps-help-content");
  await expect(help).toContainText("eeg_positions");
  await expect(help).toContainText("Electrode,x,y,z,name");
  await expect(help.getByText("Read more")).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "caps-help.png") });
  await page.keyboard.press("Escape");
  await page.getByTestId("caps-inspect-help").click();
  await expect(page.getByTestId("caps-inspect-help-content")).toContainText("Compare with");
  await page.screenshot({ path: join(ARTIFACTS, "caps-inspect-help.png") });
  await page.keyboard.press("Escape");
});
