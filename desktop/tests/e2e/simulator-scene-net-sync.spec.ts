/**
 * The Simulator's Scene tab draws the net the user is looking at (maintainer, 2026-10-28, subject
 * 101): *"the viewer does not update when the user clicks between different jobs that have
 * different nets loaded"* and *"when the user clicks on New montage, it doesn't show the
 * electrodes; only when the user switches the net to another net does it suddenly load"*.
 *
 * The rule pinned here, read off the pane (`window.__scenePane`, the legend's "Electrodes N" row
 * and the marker ids): while the New montage form is open the pane draws the FORM's net; otherwise
 * it draws the selected job row's net, montage or not — whatever net was touched last, and whether
 * or not a New montage was cancelled or saved in between.
 *
 * Two nets of different sizes make a stale pane loud: the mock's `EGI_template` is E1-E256 and
 * `GSN-HydroCel-185` is E1-E185 (`electrodesFor` in tests/mock-server/server.mjs), so E200 is on
 * the first only. A third net is warped onto ernie (`POST /api/caps/warp`), as BioSemi-64-10-10
 * was onto subject 101: a cap the packaged guide does not carry, which is the first bug — the pane
 * drew named montages on the guide only, so that net had no electrodes to show until the user
 * switched to a guide net. The mock's default-size net is E1-E128.
 *
 * Mock server only; after `npm run pree2e`:
 * `TIT_E2E_OFFSCREEN=1 npx playwright test tests/e2e/simulator-scene-net-sync.spec.ts`.
 * `TIT_E2E_SHOTS=<dir>` also writes the three screenshots the fix was reviewed with.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { addJobRow, jobBlank, jobRows, setJobNet, setJobSubject } from "./_jobs";
import { waitForScene } from "./_runPane";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SHOTS = process.env.TIT_E2E_SHOTS;

/** The three nets and what each one's pane must show. */
const BIG = { net: "EGI_template", n: 256, has: "E200" };
const SMALL = { net: "GSN-HydroCel-185", n: 185, has: "E185", lacks: "E200" };
/** On ernie's own eeg_positions only, never on the guide. */
const WARPED = { net: "EEG10-10_UI_Jurak_2007.csv", n: 128, has: "E128", lacks: "E129" };

let app: ElectronApplication;
let page: Page;

// Each test starts from the two rows `beforeAll` builds and selects what it needs, so a failure
// in one does not hide the others (the worker restarts and re-runs `beforeAll`).
test.describe.configure({ mode: "default" });

const active = () => page.locator('[data-page-active="true"]');
// By a field, not the title: the title becomes `Edit montage "<name>"` once a name is typed.
const editor = () => active().locator(".card", { hasText: "Montage name" });
const formNet = () => editor().locator(".field", { hasText: "EEG net" }).getByRole("combobox");
const row = (i: number) => jobRows(page).nth(i);
const bare = (net: string | null | undefined) => (net ?? "").replace(/\.csv$/i, "");

/** The pane draws `net`: its name on the debug handle, its count in the legend, its electrodes. */
async function expectPaneNet(expected: { net: string; n: number; has: string; lacks?: string }): Promise<void> {
  await expect.poll(() => page.evaluate(() => window.__scenePane?.net ?? null).then(bare), { timeout: 20_000 }).toBe(bare(expected.net));
  await expect
    .poll(() => page.evaluate(() => window.__scenePane?.markers ?? 0), { timeout: 20_000, message: `${expected.net} has ${expected.n} electrodes` })
    .toBe(expected.n);
  await expect(active().locator('[data-testid="scene-legend"] li', { hasText: "Electrodes" }).locator(".scene-legend-detail")).toHaveText(String(expected.n));
  const ids = await page.evaluate(() => (window.__scene?.markers ?? []).map((m: { id: string }) => m.id));
  expect(ids).toContain(expected.has);
  if (expected.lacks) expect(ids).not.toContain(expected.lacks);
}

async function selectRow(i: number): Promise<void> {
  await jobBlank(row(i)).click();
  await expect(row(i)).toHaveAttribute("data-active", "true");
}

async function chooseFormNet(net: string): Promise<void> {
  await formNet().click();
  await page.getByRole("option", { name: net, exact: true }).click();
  await expect(formNet()).toHaveText(net);
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-net-sync-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  // After the launch, whose mock reset clears every warp.
  const warp = await fetch(`${SERVER_URL}/api/caps/warp`, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ subject: "ernie", caps: [WARPED.net] }),
  });
  expect(warp.status, await warp.text()).toBe(200);

  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  await waitForScene(page);

  // Two jobs on two nets, neither with a montage; row 2's net is the one touched last.
  await setJobSubject(page, row(0), "ernie");
  await setJobNet(page, row(0), BIG.net);
  await setJobSubject(page, await addJobRow(page), "ernie");
  await setJobNet(page, row(1), SMALL.net);
  await expect(jobRows(page)).toHaveCount(2);
});

test.afterAll(async () => {
  await app?.close();
});

test("selecting a job row draws that row's net, montage or not", async () => {
  await selectRow(0);
  await expectPaneNet(BIG);
  // A row with no montage names none: no "Showing:" chip.
  await expect(active().getByTestId("scene-pane-showing")).toHaveCount(0);
  await selectRow(1);
  await expectPaneNet(SMALL);
  await selectRow(0);
  await expectPaneNet(BIG);
});

test("New montage draws the form's net; Cancel returns to the selected row's net", async () => {
  await selectRow(0);
  await active().getByRole("button", { name: "New montage", exact: true }).click();
  await expect(editor()).toBeVisible();
  // The form starts on the selected row's net, which is the one the pane was already drawing.
  await expect(formNet()).toHaveText(BIG.net);
  await expectPaneNet(BIG);
  await chooseFormNet(SMALL.net);
  await expectPaneNet(SMALL);
  await editor().getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor()).toHaveCount(0);
  if (SHOTS) await page.screenshot({ path: join(SHOTS, "2-row1-after-new-montage-cancel.png") });
  await expectPaneNet(BIG);
  await selectRow(1);
  await expectPaneNet(SMALL);
  if (SHOTS) await page.screenshot({ path: join(SHOTS, "3-row2-other-net.png") });
  await selectRow(0);
  await expectPaneNet(BIG);
});

test("after New montage → Save, the pane still follows the selected row", async () => {
  await selectRow(1);
  await active().getByRole("button", { name: "New montage", exact: true }).click();
  await expect(formNet()).toHaveText(SMALL.net);
  await editor().getByPlaceholder("e.g. F3_F4").fill("net_sync_check");
  const slots = editor().locator(".electrode-slot");
  for (const [i, electrode] of ["E1", "E2", "E3", "E4"].entries()) {
    await slots.nth(i).getByRole("combobox").click();
    await page.getByRole("dialog").getByPlaceholder("Filter electrodes…").fill(electrode);
    await page.getByTestId(`pair-${Math.floor(i / 2)}-${i % 2 === 0 ? "a" : "b"}-row-${electrode}`).click();
    await page.getByRole("dialog").getByRole("button", { name: "Done", exact: true }).click();
  }
  await editor().getByRole("button", { name: "Save montage", exact: true }).click();
  await expect(editor()).toHaveCount(0);
  await selectRow(0);
  await expectPaneNet(BIG);
  await selectRow(1);
  await expectPaneNet(SMALL);
});

test("a net the guide does not carry is drawn on a subject that has it, with or without the form", async () => {
  await selectRow(0);
  await setJobNet(page, row(0), WARPED.net);
  await expectPaneNet(WARPED);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.subject ?? null)).toBe("ernie");

  await active().getByRole("button", { name: "New montage", exact: true }).click();
  await expect(formNet()).toHaveText(WARPED.net);
  await expectPaneNet(WARPED);
  await expect(active().getByTestId("scene-pane-hint")).toHaveText("Click an electrode to set E1+ (Channel 1).");
  await expect(active().getByTestId("scene-toggles")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: join(SHOTS, "1-new-montage-net-visible.png") });
  await editor().getByRole("button", { name: "Cancel", exact: true }).click();
  await expectPaneNet(WARPED);
  await selectRow(1);
  await expectPaneNet(SMALL);
});
