/**
 * The Simulator's Scene tab shows what the user is working on — one focus, the scene derived
 * from it (maintainer, 2026-10-28): *"the simulator loads up and it looks like some net is already
 * loaded, even though an EEG net in the job is not even selected. When the user tries to add a new
 * montage, the net is not updated … then if they cancel and open/select another job, the job does
 * not update unless they manipulate the job's parameters. When the user interacts with an element,
 * the state must change to reflect what is happening."*
 *
 * The rule pinned here (ARCHITECTURE §7.2): the focus is a job row, the montage form or the
 * placement form, set only by what the user last touched, and the pane draws exactly that —
 *  - a row: its subject's head, its net's electrodes only if the row has a net, its channels;
 *  - the montage form: the form's net (the focused row's when it opened, else none until chosen),
 *    its draft channels, picking on;
 *  - the placement form: the placement subject's head and the placed positions;
 *  - closing a form returns to the row focused before; clicking a row while a form is open
 *    focuses the row and leaves the form open, and touching the form focuses it again.
 *
 * Read off the pane (`window.__scenePane`, the legend's "Electrodes N", the channel chips) and the
 * markers' ids. Two nets of different sizes make a stale pane loud: the mock's `EGI_template` is
 * E1-E256 and `GSN-HydroCel-185` is E1-E185 (`electrodesFor` in tests/mock-server/server.mjs); a
 * third net is warped onto ernie (`POST /api/caps/warp`), so the guide lacks it. Montage F3_F4 on
 * EGI_template is E36/E24 · E45/E58 (tests/fixtures/montage_list.json).
 *
 * Every test launches a fresh app: scenario (a) is the first frame a user sees, and the others must
 * not inherit one another's state. Mock server only; after `npm run pree2e`:
 * `TIT_E2E_OFFSCREEN=1 npx playwright test tests/e2e/simulator-scene-focus.spec.ts`.
 * `TIT_E2E_SHOTS=<dir>` writes a screenshot per step.
 */
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { addJobRow, jobBlank, jobRows, setJobMontage, setJobNet, setJobSubject } from "./_jobs";
import { waitForScene } from "./_runPane";
import { cameraPosition, type OrbitCamera } from "../../src/renderer/scene/camera";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SHOTS = process.env.TIT_E2E_SHOTS;

interface NetCase {
  net: string;
  n: number;
  has: string;
  lacks?: string;
}
const BIG: NetCase = { net: "EGI_template", n: 256, has: "E200" };
const SMALL: NetCase = { net: "GSN-HydroCel-185", n: 185, has: "E185", lacks: "E200" };
/** On ernie's own eeg_positions only, never on the guide. */
const WARPED: NetCase = { net: "EEG10-10_UI_Jurak_2007.csv", n: 128, has: "E128", lacks: "E129" };

let app: ElectronApplication;
let page: Page;

const active = () => page.locator('[data-page-active="true"]');
const editor = () => active().locator(".card", { hasText: "Montage name" });
const formNet = () => editor().locator(".field", { hasText: "EEG net" }).getByRole("combobox");
const placementEditor = () => active().locator(".card", { hasText: "New free-hand placement" });
const row = (i: number) => jobRows(page).nth(i);
const bare = (net: string | null | undefined) => (net ?? "").replace(/\.csv$/i, "");
const pane = () => page.evaluate(() => window.__scenePane ?? null);

async function shot(name: string): Promise<void> {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, `${test.info().title.slice(0, 1)}-${name}.png`) });
}

/** The pane draws `expected`: its name on the debug handle, its count in the legend, its electrodes. */
async function expectPaneNet(expected: NetCase): Promise<void> {
  await expect.poll(async () => bare((await pane())?.net), { timeout: 20_000 }).toBe(bare(expected.net));
  await expect
    .poll(async () => (await pane())?.markers ?? 0, { timeout: 20_000, message: `${expected.net} has ${expected.n} electrodes` })
    .toBe(expected.n);
  await expect(active().locator('[data-testid="scene-legend"] li', { hasText: "Electrodes" }).locator(".scene-legend-detail")).toHaveText(
    new RegExp(`(^| of )${expected.n}( selected)?$`),
  );
  const ids = await page.evaluate(() => (window.__scene?.markers ?? []).map((m: { id: string }) => m.id));
  expect(ids).toContain(expected.has);
  if (expected.lacks) expect(ids).not.toContain(expected.lacks);
}

/** No net at all: no name, no markers, no "Electrodes" legend row. */
async function expectNoNet(): Promise<void> {
  await expect.poll(async () => (await pane())?.net ?? null, { timeout: 20_000 }).toBeNull();
  await expect.poll(async () => (await pane())?.markers ?? -1, { timeout: 20_000 }).toBe(0);
  await expect(active().locator('[data-testid="scene-legend"] li', { hasText: "Electrodes" })).toHaveCount(0);
}

async function expectChips(chips: string[]): Promise<void> {
  await expect(active().getByTestId("channel-legend").locator(".channel-chip-name")).toHaveText(chips);
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

async function openNewMontage(): Promise<void> {
  await active().getByRole("button", { name: "New montage", exact: true }).click();
  await expect(editor()).toBeVisible();
}

/** Two rows on ernie: row 1 on BIG, row 2 on SMALL, neither with a montage. */
async function twoRows(): Promise<void> {
  await setJobSubject(page, row(0), "ernie");
  await setJobNet(page, row(0), BIG.net);
  await setJobSubject(page, await addJobRow(page), "ernie");
  await setJobNet(page, row(1), SMALL.net);
  await expect(jobRows(page)).toHaveCount(2);
}

/** Up to `count` well-separated electrodes on the near side of the head, as canvas offsets —
 *  nearest the camera first, because a marker behind the head projects inside the canvas too. */
async function frontMarkers(count: number): Promise<{ id: string; x: number; y: number }[]> {
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const scene = await page.evaluate(() => {
    const s = window.__scene!;
    const markers = s.markers as { id: string; world: [number, number, number] }[];
    return { camera: s.camera as OrbitCamera, canvas: s.canvas, markers: markers.map((m) => ({ id: m.id, world: m.world, p: s.project(m.world) })) };
  });
  const eye = cameraPosition(scene.camera);
  const distance = (w: [number, number, number]) => Math.hypot(w[0] - eye[0], w[1] - eye[1], w[2] - eye[2]);
  const { widthCss, heightCss } = scene.canvas;
  const near = scene.markers
    .filter(({ p }) => p?.inFront && p.x > 60 && p.y > 60 && p.x < widthCss - 60 && p.y < heightCss - 60)
    .filter((m) => scene.markers.every((o) => o === m || !o.p?.inFront || Math.hypot(o.p.x - m.p!.x, o.p.y - m.p!.y) > 18))
    .sort((a, b) => distance(a.world) - distance(b.world));
  const out: { id: string; x: number; y: number }[] = [];
  for (const { id, p } of near) {
    if (out.every((o) => Math.hypot(o.x - p!.x, o.y - p!.y) > 40)) out.push({ id, x: p!.x, y: p!.y });
    if (out.length === count) break;
  }
  expect(out, "not enough well-separated electrodes in front of the camera").toHaveLength(count);
  return out;
}

async function clickCanvas(x: number, y: number): Promise<void> {
  const box = (await active().getByTestId("scene-canvas").boundingBox())!;
  await page.mouse.click(box.x + x, box.y + y);
}

test.beforeEach(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-scene-focus-")) });
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
  await expect(jobRows(page)).toHaveCount(1);
});

test.afterEach(async () => {
  await app?.close();
});

test("a. a fresh page whose one row has no net draws no electrodes", async () => {
  await expect(row(0).getByRole("combobox", { name: "EEG net", exact: true })).toHaveText("Choose a net");
  await shot("fresh");
  await expectNoNet();
  await expectChips([]);
  await expect(active().getByTestId("scene-pane-hint")).toHaveText("Choose an EEG net to see its electrodes.");
});

test("b. the scene follows the row the user picks or adds", async () => {
  await setJobSubject(page, row(0), "ernie");
  await setJobNet(page, row(0), BIG.net);
  await expectPaneNet(BIG);
  await shot("row1-big");
  await setJobSubject(page, await addJobRow(page), "ernie");
  // Add job focuses the new row.
  await expect(row(1)).toHaveAttribute("data-active", "true");
  await setJobNet(page, row(1), SMALL.net);
  await expectPaneNet(SMALL);
  await shot("row2-small");
  await selectRow(0);
  await expectPaneNet(BIG);
  await selectRow(1);
  await expectPaneNet(SMALL);
  // Removing the focused row focuses its neighbour.
  await active().getByRole("button", { name: "Remove job 2", exact: true }).click();
  await expect(row(0)).toHaveAttribute("data-active", "true");
  await expectPaneNet(BIG);
});

test("c. New montage draws the focused row's net at once, follows the form's net, and Cancel returns to the row", async () => {
  await twoRows();
  await selectRow(0);
  await openNewMontage();
  await expect(formNet()).toHaveText(BIG.net);
  await expectPaneNet(BIG);
  await expect(active().getByTestId("scene-pane-hint")).toHaveText("Click an electrode to set E1+ (Channel 1).");
  await shot("form-big");
  await chooseFormNet(SMALL.net);
  await expectPaneNet(SMALL);
  await shot("form-switched-small");
  await editor().getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor()).toHaveCount(0);
  await expect(row(0)).toHaveAttribute("data-active", "true");
  await expectPaneNet(BIG);
  await shot("cancel-back-to-row1");
  await selectRow(1);
  await expectPaneNet(SMALL);
});

test("d. New montage from a row with no net draws no electrodes until the form names one", async () => {
  await openNewMontage();
  await expect(formNet()).toHaveText("Choose a net");
  await expectNoNet();
  // The draft's own empty channels, and the pane says why there is nothing to click.
  await expectChips(["E1+ — · E1- —", "E2+ — · E2- —"]);
  await expect(active().getByTestId("scene-pane-hint")).toHaveText("Choose an EEG net to see its electrodes.");
  await shot("form-no-net");
  await chooseFormNet(BIG.net);
  await expectPaneNet(BIG);
  await editor().getByRole("button", { name: "Cancel", exact: true }).click();
  await expectNoNet();
  await expectChips([]);
});

test("e. clicking a row while drafting shows the row; touching the form shows the draft again", async () => {
  await twoRows();
  await selectRow(0);
  await openNewMontage();
  await expectPaneNet(BIG);
  const picks = await frontMarkers(2);
  for (const m of picks) await clickCanvas(m.x, m.y);
  const chips = [`E1+ ${picks[0]!.id} · E1- ${picks[1]!.id}`, "E2+ — · E2- —"];
  await expectChips(chips);
  await shot("draft-two-picks");
  await selectRow(1);
  await expectPaneNet(SMALL);
  await expectChips([]);
  // The form is still open with its picks, just not what the scene shows.
  await expect(editor()).toBeVisible();
  await expect(editor().locator('.electrode-slot[data-slot="0"]').getByRole("combobox")).toHaveText(picks[0]!.id);
  await shot("row2-while-form-open");
  // A click on an electrode of the row's net hands the scene back to the open draft, untouched.
  const [other] = await frontMarkers(1);
  await clickCanvas(other!.x, other!.y);
  await expectPaneNet(BIG);
  await expectChips(chips);
  await selectRow(1);
  await expectPaneNet(SMALL);
  // So does touching the form.
  await editor().getByPlaceholder("e.g. F3_F4").click();
  await expect(row(1)).not.toHaveAttribute("data-active", "true");
  await expectPaneNet(BIG);
  await expectChips(chips);
  await expect(active().getByTestId("scene-pane-hint")).toHaveText("Click an electrode to set E2+ (Channel 2).");
  await shot("back-to-form");
});

test("f. Save returns the scene to the row, whose montage list has the new montage", async () => {
  await twoRows();
  await selectRow(1);
  await openNewMontage();
  await expect(formNet()).toHaveText(SMALL.net);
  await editor().getByPlaceholder("e.g. F3_F4").fill("focus_check");
  const slots = editor().locator(".electrode-slot");
  for (const [i, electrode] of ["E1", "E2", "E3", "E4"].entries()) {
    await slots.nth(i).getByRole("combobox").click();
    await page.getByRole("dialog").getByPlaceholder("Filter electrodes…").fill(electrode);
    await page.getByTestId(`pair-${Math.floor(i / 2)}-${i % 2 === 0 ? "a" : "b"}-row-${electrode}`).click();
    await page.getByRole("dialog").getByRole("button", { name: "Done", exact: true }).click();
  }
  await expectChips(["E1+ E1 · E1- E2", "E2+ E3 · E2- E4"]);
  await editor().getByRole("button", { name: "Save montage", exact: true }).click();
  await expect(editor()).toHaveCount(0);
  await expect(row(1)).toHaveAttribute("data-active", "true");
  await expectPaneNet(SMALL);
  await expectChips([]);
  await shot("saved-back-to-row2");
  await setJobMontage(page, row(1), "focus_check · TI");
  await expectChips(["E1+ E1 · E1- E2", "E2+ E3 · E2- E4"]);
  await expectPaneNet(SMALL);
});

test("g. New placement draws the placement on its subject; Cancel returns to the row", async () => {
  await twoRows();
  await selectRow(0);
  await active().getByRole("button", { name: "New placement", exact: true }).click();
  await expect(placementEditor()).toBeVisible();
  await expect.poll(async () => (await pane())?.space ?? null, { timeout: 20_000 }).toBe("subject-ras");
  await expect.poll(async () => (await pane())?.subject ?? null).toBe("ernie");
  await expect(active().getByTestId("scene-pane-host")).toHaveAttribute("data-gesture", "place", { timeout: 20_000 });
  await expect.poll(async () => (await pane())?.markers ?? -1).toBe(0);
  await page.getByTestId("freehand-row-0").click();
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const box = (await active().getByTestId("scene-canvas").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect.poll(async () => (await pane())?.markers ?? -1).toBe(1);
  await shot("placement-one-dot");
  await placementEditor().getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(placementEditor()).toHaveCount(0);
  await expect(row(0)).toHaveAttribute("data-active", "true");
  await expect.poll(async () => (await pane())?.subject).toBeNull();
  await expectPaneNet(BIG);
  await shot("placement-cancel-row1");
});

test("h. Edit montage opens the form on that montage's net and channels", async () => {
  await twoRows();
  await setJobMontage(page, row(0), "F3_F4 · TI");
  await expectChips(["E1+ E36 · E1- E24", "E2+ E45 · E2- E58"]);
  await selectRow(1);
  await expectPaneNet(SMALL);
  await row(0).getByRole("button", { name: "Edit F3_F4", exact: true }).click();
  await expect(editor()).toBeVisible();
  await expect(formNet()).toHaveText(BIG.net);
  await expectPaneNet(BIG);
  await expectChips(["E1+ E36 · E1- E24", "E2+ E45 · E2- E58"]);
  await expect(active().getByTestId("scene-pane-hint")).toHaveText(/^Click an electrode to set E\d[+-] \(Channel \d\)\.$/);
  await shot("edit-f3f4");
  await editor().getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(row(0)).toHaveAttribute("data-active", "true");
  await expectPaneNet(BIG);
});

test("i. a net the guide lacks is drawn on the subject's head, for the row and for the form", async () => {
  await setJobSubject(page, row(0), "ernie");
  await setJobNet(page, row(0), WARPED.net);
  await expectPaneNet(WARPED);
  await expect.poll(async () => (await pane())?.subject ?? null).toBe("ernie");
  await openNewMontage();
  await expect(formNet()).toHaveText(WARPED.net);
  await expectPaneNet(WARPED);
  await expect.poll(async () => (await pane())?.subject ?? null).toBe("ernie");
  await shot("warped-form");
});

test("j. leaving the Simulator and coming back keeps the focus and the form", async () => {
  await twoRows();
  await selectRow(1);
  await expectPaneNet(SMALL);
  await gotoPage(page, "overview", "Overview");
  await gotoPage(page, "simulator", "Simulator");
  await waitForScene(page);
  await expect(row(1)).toHaveAttribute("data-active", "true");
  await expectPaneNet(SMALL);
  await selectRow(0);
  await openNewMontage();
  await chooseFormNet(SMALL.net);
  await gotoPage(page, "overview", "Overview");
  await gotoPage(page, "simulator", "Simulator");
  await waitForScene(page);
  await expect(editor()).toBeVisible();
  await expect(formNet()).toHaveText(SMALL.net);
  await expectPaneNet(SMALL);
  await shot("back-form-small");
  await editor().getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(row(0)).toHaveAttribute("data-active", "true");
  await expectPaneNet(BIG);
});
