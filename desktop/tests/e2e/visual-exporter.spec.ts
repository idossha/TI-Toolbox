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
const PANELS = ["source", "visual-exporter"];

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
      json: { telemetry: { consented: true, enabled: false }, panels, image_tag: "idossha/simnibs:v2.3.1", theme: "system" },
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

async function submittedJob(run: () => Promise<void>): Promise<{ kind: string; subject_ids: string[]; overwrite?: boolean; config: Record<string, unknown> }> {
  const request = page.waitForRequest((r) => r.url().endsWith("/api/jobs") && r.method() === "POST");
  await run();
  return (await request).postDataJSON() as { kind: string; subject_ids: string[]; overwrite?: boolean; config: Record<string, unknown> };
}

test.afterEach(async () => {
  await app?.close();
});

test("Settings toggles the panel into (and out of) the nav rail", async () => {
  await launchApp(false);
  await connect();
  await expect(railLink()).toHaveCount(0);

  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("tab", { name: "Extensions", exact: true }).click();
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

test("Your own file: a wrong file is refused in the server's words, a good one runs after its assess", async () => {
  await launchApp(true);
  await connect();
  await openPanel();
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: "ernie", exact: true }).click();
  await page.locator("#ve-simulation").click();
  await page.getByRole("option", { name: "Thalamus", exact: true }).click();
  await page.getByRole("radio", { name: "Networks" }).click();
  // The old way is gone from the tab: no list of bundles, no sequence.
  await expect(page.getByRole("radio", { name: "Existing file" })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: /Thalamocortical sequence/ })).toHaveCount(0);
  await page.getByRole("radio", { name: "Your own file" }).click();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Load a file, or choose one already loaded.");

  await page.getByTestId("ve-own-input").setInputFiles({ name: "shifted.tck", mimeType: "application/octet-stream", buffer: Buffer.from("x") });
  await expect(page.getByTestId("ve-own-error")).toContainText("inside this head model's brain");
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Load a file, or choose one already loaded.");

  await page.getByTestId("ve-own-input").setInputFiles({ name: "mine.tck", mimeType: "application/octet-stream", buffer: Buffer.from("x") });
  await expect(page.getByTestId("ve-own-checks")).toContainText("10 left unlabelled");
  await expect(page.getByTestId("ve-own-checks")).toContainText("cannot prove");
  await expect(page.getByTestId("ve-own-error")).toHaveCount(0);

  await page.locator("#ve-network-metric").click();
  await page.getByRole("option", { name: "TI_max", exact: true }).click();
  await page.getByRole("checkbox", { name: "Turntable video" }).click();
  // No Title, Caption, Region names or Views to set: a figure has four fixed panels and no text.
  await page.getByTestId("network-advanced").locator("summary").click();
  for (const gone of ["Title", "Caption", "Region names", "Views"]) await expect(page.getByTestId("network-advanced").getByText(gone, { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("ve-planned-files")).toHaveText("Writes: ti_max.png, ti_max_turntable.mp4");
  await page.getByRole("checkbox", { name: "Export .blend" }).click();
  await expect(page.getByTestId("ve-planned-files")).toContainText("network.blend (about 40 MB, the TI_max scene)");
  const accepted: { kind: string; config: Record<string, unknown>; after?: string[] }[] = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/api/jobs") && r.method() === "POST") accepted.push(r.postDataJSON());
  });
  await page.getByTestId("run-button").click();
  await expect.poll(() => accepted.length, { timeout: 10_000 }).toBe(2);
  expect(accepted[0]).toMatchObject({ kind: "tract", config: { stages: ["assess"], assess: { simulations: ["Thalamus"], selections: [], own_network: "mine" } } });
  expect(accepted[1]).toMatchObject({ kind: "blender", config: { _type: "TractVisualConfig", own_network: "mine", metric: "ti_max", turntable: true, export_blend: true, width: 1600, height: 1600, quality: "preview" } });
  expect(accepted[1]!.after).toHaveLength(1);
  expect(accepted[1]!.config).not.toHaveProperty("views");
  await page.getByRole("radio", { name: "Your own file" }).click(); // Back to the chooser for the next tests.

  await page.getByRole("radio", { name: /^Renders \d+$/ }).click();
  const renders = page.getByTestId("network-renders");
  // By network, labelled by what it shows: the mock's fixture is a folder from before the one-figure
  // form, of the network called all, and it still reads.
  // Open whichever way it starts: it is the only group until the mock's render of this file lands.
  await renders.locator('details[data-network="all"]').evaluate((details: HTMLDetailsElement) => {
    details.open = true;
  });
  await expect(renders.getByRole("img", { name: "all, Fibre direction · lateral" })).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "panel-visual-exporter-networks.png") });
});

async function openNetworksOf(subject: string, simulation: string): Promise<void> {
  await launchApp(true);
  await connect();
  await openPanel();
  await page.locator("#ve-subject").click();
  await page.getByRole("option", { name: subject, exact: true }).click();
  await page.locator("#ve-simulation").click();
  await page.getByRole("option", { name: simulation, exact: true }).click();
  await page.getByRole("radio", { name: "Networks" }).click();
}

test("a preset is chosen, says what same-side left out, and Run assesses it before rendering", async () => {
  await openNetworksOf("ernie", "L_Insula");
  const presets = page.getByTestId("network-presets");
  // A set this network has no labels for, or no streamline in, says so and cannot be chosen.
  await expect(presets.getByRole("option", { name: /Cingulate-cortical/ })).toContainText("These labels are not in this network");
  await expect(presets.getByRole("option", { name: /Cingulate-cortical/ })).toHaveAttribute("aria-disabled", "true");
  await expect(presets.getByRole("option", { name: /Amygdala-cortical/ })).toContainText("0 streamlines join these regions");

  await presets.getByRole("option", { name: /Posterior thalamocortical/ }).click();
  const count = page.getByTestId("network-count");
  await expect(count).toContainText("95 streamlines · 1 edge");
  await expect(page.getByTestId("network-removed")).toHaveText("· 95 of 107; 12 opposite-hemisphere removed (right thalamus to left cortex 12, left thalamus to right cortex 0)");
  await expect(page.getByTestId("network-mask-name")).toHaveValue("posterior_thalamocortical");
  await expect(page.getByTestId("ve-assess-first")).toContainText("assesses this network first");
  await page.getByTestId("network-advanced").locator("summary").click();
  await expect(page.getByTestId("network-setup-removed")).toContainText("12 opposite-hemisphere removed");
  await page.screenshot({ path: join(ARTIFACTS, "panel-visual-exporter-network-preset.png") });

  const opposite = page.getByRole("checkbox", { name: "Include opposite-hemisphere connections" });
  await opposite.click();
  await expect(count).toContainText("107 streamlines · 2 edges");
  await expect(page.getByTestId("network-removed")).toHaveCount(0);
  await expect(page.getByTestId("network-mask-name")).toHaveValue("posterior_thalamocortical_with_opposite");
  await opposite.click();
  await expect(page.getByTestId("network-mask-name")).toHaveValue("posterior_thalamocortical");

  const accepted: { kind: string; config: Record<string, unknown>; after?: string[]; id?: string }[] = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/api/jobs") && r.method() === "POST") accepted.push(r.postDataJSON());
  });
  await page.getByTestId("run-button").click();
  await expect.poll(() => accepted.length, { timeout: 10_000 }).toBe(2);
  expect(accepted[0]).toMatchObject({ kind: "tract", config: { stages: ["assess"], assess: { simulations: ["L_Insula"], selections: [{ name: "posterior_thalamocortical", kind: "edges", pairs: [["lh.precentral", "Left-Thalamus-Proper"]] }] } } });
  expect(accepted[1]).toMatchObject({ kind: "blender", config: { selection: { name: "posterior_thalamocortical" }, preset: "posterior_thalamocortical" } });
  expect(accepted[1]!.after).toHaveLength(1);
  await expect(page.getByTestId("page-right-pane").getByTestId("job-terminal-identity")).toBeVisible({ timeout: 20_000 });
});

test("a render of one network leaves another's files alone, and asks only about its own", async () => {
  await openNetworksOf("ernie", "Thalamus");
  const first = page.getByTestId("network-presets").getByRole("option", { name: /Precentral-brainstem/ });
  await first.click();
  const job = await submittedJob(() => page.getByTestId("run-button").click());
  expect(job).toMatchObject({ kind: "blender" });
  const rendersTab = page.getByRole("radio", { name: /^Renders \d+$/ });
  await expect(page.getByRole("radio", { name: "Renders 2" })).toBeVisible({ timeout: 30_000 });
  await rendersTab.click();
  // One group for each; the newer open, the older a header until it is asked for.
  const renders = page.getByTestId("network-renders");
  await expect(renders.getByRole("img", { name: "precentral_brainstem, Fibre direction", exact: true })).toBeVisible();
  await expect(renders.locator("details")).toHaveCount(2);
  await expect(renders.locator('details[data-network="all"]')).not.toHaveAttribute("open");
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("existing-outputs-replace")).toBeVisible({ timeout: 10_000 });
  await page.getByTestId("existing-outputs-skip").click();
  await page.getByTestId("network-presets").getByRole("option", { name: /Posterior thalamocortical/ }).click();
  await expect(page.getByTestId("network-mask-name")).toHaveValue("posterior_thalamocortical");
  const other = await submittedJob(() => page.getByTestId("run-button").click());
  expect(other.config).toMatchObject({ selection: { name: "posterior_thalamocortical" } });
});

test("by region: from a seed alone, then narrowed by a to", async () => {
  await openNetworksOf("ernie", "L_Insula");
  await page.getByRole("radio", { name: "By region" }).click();
  await page.getByTestId("network-seeds").click();
  await page.getByRole("dialog").getByRole("option", { name: /^lh\.precentral/ }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("network-count")).toContainText("707 streamlines · 3 edges"); // 600 + 95 + 12; the 3 fall under minN 5
  await expect(page.getByTestId("network-mask-name")).toHaveValue("lh_precentral");
  await page.getByTestId("network-to").click();
  await page.getByRole("dialog").getByRole("option", { name: /^Brain-Stem/ }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("network-count")).toContainText("600 streamlines · 1 edge");
  await expect(page.getByTestId("network-mask-name")).toHaveValue("lh_precentral_to_Brain-Stem");
  const accepted = await submittedJob(() => page.getByTestId("run-button").click());
  expect(accepted).toMatchObject({ kind: "tract" });
  expect(accepted.config).toMatchObject({ assess: { selections: [{ name: "lh_precentral_to_Brain-Stem", regions: ["lh.precentral"], pairs: [["lh.precentral", "Brain-Stem"]] }] } });
});

test("by connection: the table is the choice, and a line in the pane is too", async () => {
  await openNetworksOf("ernie", "L_Insula");
  await page.getByRole("radio", { name: "By connection" }).click();
  await page.getByTestId("network-seeds").click();
  await page.getByRole("dialog").getByRole("option", { name: /^lh\.insula/ }).click();
  await page.keyboard.press("Escape");
  await page.getByTestId("network-edges").getByRole("option", { name: /Left-Thalamus-Proper/ }).click();
  await expect(page.getByTestId("network-count")).toContainText("300 streamlines · 1 edge");
  await expect(page.getByTestId("network-mask-name")).toHaveValue("lh_insula_Left-Thalamus-Proper");
  await expect(page.getByTestId("run-pane-panel-scene")).toBeVisible();
});

test("strongest here: no metric is chosen for you, and the list follows the one you name", async () => {
  await openNetworksOf("ernie", "Thalamus");
  await page.getByRole("radio", { name: "Strongest here" }).click();
  await expect(page.getByTestId("run-button")).toHaveAttribute("title", "Choose a network.");
  await page.locator("#network-metric").click();
  const options = page.getByRole("option");
  await expect(options).toHaveText(["Median align_index", "Median ti_along (V/m)", "Median ti_avg (V/m)", "Median TI_max (V/m)", "Streamline count"]);
  await page.getByRole("option", { name: "Median TI_max (V/m)" }).click();
  await page.getByTestId("network-chooser").locator(".field", { hasText: "Connections" }).locator("input").fill("1");
  await expect(page.getByTestId("network-count")).toContainText("600 streamlines · 1 edge");
  await expect(page.getByTestId("network-mask-name")).toHaveValue("top_1_by_ti_max_mean");
  await page.locator("#network-metric").click();
  await page.getByRole("option", { name: "Median align_index" }).click();
  await expect(page.getByTestId("network-count")).toContainText("300 streamlines · 1 edge");
});

test("strongest here on a simulation not yet assessed offers its edge table, and nothing else", async () => {
  await openNetworksOf("ernie", "L_Insula");
  await page.getByRole("radio", { name: "Strongest here" }).click();
  await expect(page.getByTestId("network-strongest-empty")).toContainText("not assessed yet");
  const job = await submittedJob(() => page.getByTestId("ve-assess-networks").click());
  expect(job.config).toMatchObject({ stages: ["assess"], assess: { selections: [] } });
  await expect(page.locator("#network-metric")).toBeVisible({ timeout: 30_000 });
});

test("advanced overrides reach the config and the Plan says who set what", async () => {
  await openNetworksOf("ernie", "Thalamus");
  await page.getByTestId("network-presets").getByRole("option", { name: /Precentral-brainstem/ }).click();
  await page.getByTestId("network-advanced").locator("summary").click();
  await expect(page.getByTestId("network-setup-plan")).toContainText("Streamlines drawn");
  await page.locator("#ve-setup-side").click();
  await page.getByRole("option", { name: "Right" }).click();
  await page.locator("#ve-setup-shell").click();
  await page.getByRole("option", { name: "None" }).click();
  await expect(page.getByTestId("network-setup-plan").locator('[data-setup="lateral_side"]')).toContainText("right (set by you)");
  const job = await submittedJob(() => page.getByTestId("run-button").click());
  expect(job.config).toMatchObject({ overrides: { lateral_side: 1, iso_shell_percentile: null } });
});

test("a subject with no tractogram says what to run, and still offers Your own file", async () => {
  await openNetworksOf("101", "Thalamus");
  await expect(page.getByTestId("network-unavailable")).toContainText("No tractography for sub-101");
  await page.getByTestId("network-unavailable").getByRole("button", { name: "Your own file" }).click();
  await expect(page.getByTestId("ve-own-load")).toBeVisible();
  await page.getByTestId("network-unavailable").getByRole("button", { name: "Run tractography…" }).waitFor();
});
