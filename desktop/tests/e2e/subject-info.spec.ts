import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { launchElectronApp, setTheme } from "./_helpers";

/**
 * The Subject Info Viewer panel (`pages/panels/subject-info/`), migrated from
 * `tit/gui/extensions/subject_info_viewer.py`.
 *
 * The three things this proves, and the failure each prevents:
 *
 *  - **Settings ▸ Optional tools really gates the rail row.** A panel whose checkbox does nothing
 *    visible is a checkbox the user cannot trust; the panel id must survive the round trip through
 *    `settings.panels`, the localStorage mirror (`pages/panels/_shared.ts`) and `app/registry.ts`.
 *  - **The page reads ONE subject.** `SubjectsField`'s `single` mode is what stops a user ticking
 *    three subjects and wondering which one the cards describe.
 *  - **The cards are the subject's own inventory**, from `GET /api/subjects/{id}/info` — not the
 *    project-wide grid that lives on Overview.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

let app: ElectronApplication;
let page: Page;

async function launchApp(): Promise<void> {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
}

/**
 * The toggle, both ways. `app/registry.ts` gates a panel row on `settings.panels` live (its
 * `enabledPages` reads `getSettings`), so this asserts the rail actually follows the checkbox
 * rather than that a fresh profile happens to start empty.
 */
async function setSubjectInfoPanel(on: boolean): Promise<void> {
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  const row = page.locator("label", { hasText: "Everything one subject has on disk" });
  await expect(row).toBeVisible();
  const box = row.getByRole("checkbox");
  if ((await box.getAttribute("data-state")) !== (on ? "checked" : "unchecked")) await box.click();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled({ timeout: 20_000 });
}

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
});

test.beforeEach(launchApp);
test.afterEach(async () => {
  await app?.close();
});

test("the panel is gated by Settings, reads one subject, and lists that subject's inventory", async () => {
  await connect();
  await setTheme(page, "light");

  // Off → the rail row goes; on → it comes back. A checkbox that changes nothing visible is a
  // checkbox the user cannot trust.
  await setSubjectInfoPanel(false);
  await expect(page.getByTestId("nav-item-panel-subject-info")).toHaveCount(0, { timeout: 20_000 });
  await setSubjectInfoPanel(true);
  await expect(page.getByTestId("nav-item-panel-subject-info")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("nav-item-panel-subject-info").click();

  const detail = page.getByTestId("subject-info-detail");
  await expect(detail).toBeVisible();
  // The empty state is a sentence about what to do, not a blank pane.
  await expect(detail.getByText("Choose a subject to see everything it has on disk.")).toBeVisible();

  await page.getByTestId("subject-row-ernie").click();

  // The summary the Qt dialog's "Export Selected Subjects" JSON carried, on screen.
  await expect(detail.getByText("Head model")).toBeVisible({ timeout: 20_000 });
  await expect(detail.getByText("m2m_ernie").first()).toBeVisible();
  await expect(detail.getByText("Thalamus").first()).toBeVisible();
  await expect(detail.getByText("sub-ernie_T2w.nii.gz")).toBeVisible();
  await expect(detail.getByText("Free-hand sets")).toBeVisible();
  await expect(detail.getByText("custom_4electrode")).toBeVisible();

  await page.screenshot({ path: join(ARTIFACTS, "subject-info-light.png") });

  // `single` mode: picking a second subject replaces the first rather than adding to it, so the
  // cards always describe exactly the subject whose row is selected.
  await page.getByTestId("subject-row-101").click();
  await expect(detail.getByText("m2m_101").first()).toBeVisible({ timeout: 20_000 });
  await expect(detail.getByText("m2m_ernie")).toHaveCount(0);
});
