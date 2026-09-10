import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, launchElectronApp } from "./_helpers";

/**
 * 3D Visual Exporter — the whole migration path in one file: the Settings toggle turns the panel
 * on, the nav rail gains its row, the page builds a config for each of the four modes, and Run
 * submits a `blender` job whose body is asserted against the contract rather than a toast.
 *
 * The assertion that matters most is the last one in each mode block: what actually reached
 * `POST /api/jobs`. 2.5.0's outputs are only reproducible if the config carries the same fields
 * its Qt `_run` sent (`keep_meshes`, the STL-then-PLY pair, the negated `show_full_net`), and a
 * toast would happily appear for a config missing every one of them.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");
const PANELS = ["source", "quick-notes", "subject-info", "visual-exporter"];

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  mkdirSync(ARTIFACTS, { recursive: true });
});

async function launchApp(enablePanel: boolean): Promise<void> {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-ve-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  const panels = enablePanel ? PANELS : PANELS.filter((p) => p !== "visual-exporter");
  // Same reason as panels-forms.spec.ts: the rail gates a panel on the *server's* settings.panels,
  // and the mock's seed does not include this one.
  await page.route("**/api/settings", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      json: { telemetry: { consented: true, enabled: false }, panels, image_tag: "idossha/simnibs:v2.3.1", allow_unsafe_overrides: false, theme: "system" },
    });
  });
  await page.addInitScript((p: string[]) => {
    window.localStorage.setItem("tit-enabled-panels", JSON.stringify(p));
    window.localStorage.setItem("tit-enabled-panels-synced", "1");
  }, panels);
}

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
}

const railLink = () => page.getByRole("link", { name: "3D visual exporter", exact: true });

async function openPanel(): Promise<void> {
  await railLink().click();
  await expectPage(page, "panel-visual-exporter");
  await expect(page.getByTestId("page-right-pane").getByTestId("extension-plan")).toBeVisible();
  await expect(page.getByTestId("page-right-pane").getByTestId("job-terminal")).toBeAttached();

}

async function chooseSubjectAndSimulation(): Promise<void> {
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: "ernie", exact: true }).click();
  await page.locator("#ve-simulation").click();
  await page.getByRole("option").first().click();
}

async function submittedJob(run: () => Promise<void>): Promise<{ kind: string; subject_ids: string[]; config: Record<string, unknown> }> {
  const request = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await run();
  return (await request).postDataJSON() as { kind: string; subject_ids: string[]; config: Record<string, unknown> };
}

test.afterEach(async () => {
  await app?.close();
});

test("Settings toggles the panel into (and out of) the nav rail", async () => {
  await launchApp(false);
  await connect();
  await expect(railLink()).toHaveCount(0);

  await page.getByRole("link", { name: "Settings", exact: true }).click();
  // The toggle exists and is off — the maintainer's own requirement ("in the settings we should be
  // able to toggle them on and off to form the left side menu bar").
  const toggle = page.getByRole("checkbox").filter({ has: page.locator("xpath=..") }).nth(0);
  await expect(page.getByText("3D visual exporter", { exact: true })).toBeVisible();
  expect(await toggle.count()).toBeGreaterThan(0);

  await app.close();

  // With the id enabled, the row is there and reaches the page.
  await launchApp(true);
  await connect();
  await openPanel();
  await page.screenshot({ path: join(ARTIFACTS, "panel-visual-exporter.png") });
});

test("cortical regions mode submits the STL and PLY jobs the Qt extension ran", async () => {
  await launchApp(true);
  await connect();
  await openPanel();
  await chooseSubjectAndSimulation();

  await expect(page.getByText("Cortical regions", { exact: true }).first()).toBeVisible();
  await page.getByTestId("ve-regions-trigger").click();
  await page.getByRole("option").first().click();
  await page.getByRole("button", { name: "Done" }).click();

  const first = await submittedJob(() => page.getByTestId("run-button").click());
  expect(first.kind).toBe("blender");
  expect(first.subject_ids).toEqual(["ernie"]);
  expect(first.config).toMatchObject({ _type: "RegionConfig", format: "stl", keep_meshes: true, skip_regions: false });
  // The pair: the second request is the same config in PLY. A single job here would be the
  // regression — 2.5.0 always wrote both formats from one click.
  await expect(page.getByText(/Queued: 2 exports/)).toBeVisible({ timeout: 20_000 });
});

test("montage mode negates the checkbox and carries the electrode dimensions", async () => {
  await launchApp(true);
  await connect();
  await openPanel();
  await chooseSubjectAndSimulation();

  await page.getByRole("radio", { name: "Montage visualizer" }).click();
  await page.getByRole("checkbox", { name: /only montage electrodes/ }).click();

  // The Plan card names the directory the exporter will actually write into, rather than the
  // "cannot be previewed here" warning it used to show for every mode.
  await expect(page.getByText(/visual_exports\/sub-ernie\/montage_publication/)).toBeVisible({ timeout: 20_000 });

  const job = await submittedJob(() => page.getByTestId("run-button").click());
  expect(job.config).toMatchObject({ _type: "MontageConfig", show_full_net: false, electrode_diameter_mm: 10, electrode_height_mm: 6 });
});

test("sub-cortical mode picks labels from the volume and runs without a simulation", async () => {
  await launchApp(true);
  await connect();
  await openPanel();
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: "ernie", exact: true }).click();

  await page.getByRole("radio", { name: "Sub-cortical" }).click();

  // The label browser (GET /api/catalog/nifti/labels) answers for this subject, so the picker is
  // the control and the free-text field is not rendered at all.
  await page.getByTestId("ve-labels-trigger").click();
  // The checkbox column, not a bare row click: in the one selection grammar a plain click selects
  // exactly ONE row (SelectionList's doc comment), so clicking two rows in turn would leave one
  // label chosen, not two.
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("option", { name: /Left-Thalamus/ }).locator(".checkbox-root").click();
  await dialog.getByRole("option", { name: /Right-Thalamus/ }).locator(".checkbox-root").click();
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.locator("#ve-labels")).toHaveCount(0);

  const picked = await submittedJob(() => page.getByTestId("run-button").click());
  expect(picked.config).toMatchObject({ _type: "SubcorticalConfig", labels: [10, 49], simulation_name: "" });
});

test("the label browser falls back to the typed field when the volume cannot be read", async () => {
  await launchApp(true);
  await connect();
  // 404 is what the server returns for a subject with no segmentation volume, a path outside the
  // project jail, and an unreadable file alike — all three land on the 2.5.0 text field.
  await page.route("**/api/catalog/nifti/labels*", (route) => route.fulfill({ status: 404, json: { detail: "no readable label volume" } }));
  await openPanel();
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: "ernie", exact: true }).click();
  await page.getByRole("radio", { name: "Sub-cortical" }).click();

  await expect(page.getByTestId("ve-labels-trigger")).toHaveCount(0);
  await page.fill("#ve-labels", "10, thalamus");
  // A blocked run prints no digest — the reason is the primary's own `title` (ui/Chrome.tsx), and
  // clicking it says so in a toast rather than doing nothing (DESIGN.md §6.3).
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", /Invalid label format/);
  await page.getByTestId("run-button").click();
  await expect(page.getByText(/Invalid label format/)).toBeVisible();

  await page.fill("#ve-labels", "10, 49");
  const job = await submittedJob(() => page.getByTestId("run-button").click());
  expect(job.config).toMatchObject({ _type: "SubcorticalConfig", labels: [10, 49], simulation_name: "" });
});
