import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, launchElectronApp } from "./_helpers";
import { openSubjects, subjectRow } from "./_subjects";

/**
 * EEG caps panel, against the mock server (2026-10-16): the Settings-gated rail row opens the
 * panel; picking ernie lists the caps with their status; the inspection shows the mock's planted
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
  await openSubjects(page);
  await subjectRow(page, "ernie").click();

  const caps = page.getByTestId("caps-table");
  await expect(caps.getByRole("row", { name: /EEG10-10_UI_Jurak_2007\.csv.*not on subject/ })).toBeVisible();
  await expect(caps.getByRole("row", { name: /GSN-HydroCel-185.*outdated/ })).toBeVisible();

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
  await expect.poll(() => bodies).toEqual([{ subject: "ernie", caps: ["GSN-HydroCel-185"], overwrite: true }]);

  await caps.getByRole("checkbox", { name: "Select EEG10-10_UI_Jurak_2007.csv" }).click();
  await page.getByTestId("caps-apply").click();
  await expect(caps.getByRole("row", { name: /EEG10-10_UI_Jurak_2007\.csv.*on subject/ })).toBeVisible();
  expect(bodies[1]).toEqual({ subject: "ernie", caps: ["EEG10-10_UI_Jurak_2007.csv"], overwrite: false });
});
