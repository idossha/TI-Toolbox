/**
 * The Simulator's **New montage** form picks its electrodes on the head (maintainer, 2026-10-28:
 * *"show the net on the head when users click on the 'new montage' button … electrodes need to be
 * selectable in a similar fashion like the Ex-search"*), and names them by the one convention:
 * channel k is electrodes Ek+ and Ek-, never "A"/"B" or "Pair k".
 *
 * What it pins, each against the FORM (the source of truth) rather than the pane's own state:
 *  - the form opens on the job row's net — none here, so nothing is drawn until the form's EEG net
 *    select names one — and switching that select redraws;
 *  - four clicks on the head fill E1+, E1-, E2+, E2- in order, and the status line names the slot
 *    the next click sets;
 *  - clicking a set electrode again clears its slot, and the next click refills that slot;
 *  - opening a slot's picker aims the next click at that slot, and lists electrodes set in other
 *    slots as taken;
 *  - "Add 2 channels" moves the cursor to E3+, and the next click on the head fills it;
 *  - switching the net keeps the electrodes both nets have, blanks the rest and moves the cursor
 *    to the first empty slot;
 *  - Cancel returns the pane to the job row (no channel legend, no draft, no net).
 *
 * The aiming is arithmetic (the same projection `scene-pane.spec.ts` uses), so a click that lands
 * on a neighbour fails here. Mock server only; reproduce with
 * `TIT_E2E_OFFSCREEN=1 npx playwright test tests/e2e/simulator-new-montage.spec.ts` after `npm run pree2e`.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp } from "./_helpers";
import { waitForScene } from "./_runPane";
import { cameraPosition, type OrbitCamera } from "../../src/renderer/scene/camera";
import { electrodeSlotName } from "../../src/renderer/pages/_shared/scene/model";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const SHOTS = process.env.TIT_E2E_SHOTS;

let app: ElectronApplication;
let page: Page;
/** The electrodes the tests set, slot by slot: E1+, E1-, E2+, E2-, then E3+. */
let picked: string[] = [];

test.describe.configure({ mode: "serial" });

const active = () => page.locator('[data-page-active="true"]');
const editor = () => active().locator(".card", { hasText: "New montage" });
const slot = (n: number) => editor().locator(`.electrode-slot[data-slot="${n}"]`).getByRole("combobox");
const hint = () => active().getByTestId("scene-pane-hint");

/** Up to `count` markers in front of the camera, well inside the canvas and well apart. */
async function frontMarkers(count: number): Promise<{ id: string; x: number; y: number }[]> {
  await page.waitForFunction(() => window.__scene?.camera.settled === true, null, { timeout: 20_000 });
  const scene = await page.evaluate(() => {
    const s = window.__scene!;
    return { camera: s.camera as OrbitCamera, canvas: s.canvas, markers: s.markers as { id: string; world: [number, number, number] }[] };
  });
  const projections = await page.evaluate(
    (worlds) => worlds.map((w) => window.__scene?.project(w as [number, number, number]) ?? null),
    scene.markers.map((m) => m.world),
  );
  const eye = cameraPosition(scene.camera);
  const { widthCss, heightCss } = scene.canvas;
  const candidates = scene.markers
    .map((m, i) => ({ id: m.id, p: projections[i], d: Math.hypot(m.world[0] - eye[0], m.world[1] - eye[1], m.world[2] - eye[2]) }))
    .filter((c) => c.p?.inFront && c.p.x > 40 && c.p.y > 40 && c.p.x < widthCss - 40 && c.p.y < heightCss - 40)
    .filter((c) => projections.every((o) => o === c.p || !o?.inFront || Math.hypot(o.x - c.p!.x, o.y - c.p!.y) > 18))
    .sort((a, b) => a.d - b.d);
  // Spread the picks out: neighbours of a chosen marker are skipped so each click is unambiguous.
  const out: { id: string; x: number; y: number }[] = [];
  for (const c of candidates) {
    if (out.every((o) => Math.hypot(o.x - c.p!.x, o.y - c.p!.y) > 40)) out.push({ id: c.id, x: c.p!.x, y: c.p!.y });
    if (out.length === count) break;
  }
  expect(out, "not enough well-separated electrodes in front of the camera").toHaveLength(count);
  return out;
}

async function clickMarker(m: { x: number; y: number }): Promise<void> {
  const box = await active().getByTestId("scene-canvas").boundingBox();
  if (!box) throw new Error("no scene canvas on the active page");
  await page.mouse.click(box.x + m.x, box.y + m.y);
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-new-montage-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
  await waitForScene(page);
});

test.afterAll(async () => {
  await app?.close();
});

test("New montage draws the form's net on the head and names the slots Ek+ / Ek-", async () => {
  await active().getByRole("button", { name: "New montage", exact: true }).click();
  await expect(editor()).toBeVisible();
  // The fresh job row has no net, so neither has the form: nothing to pick yet.
  const netSelect = editor().locator(".field", { hasText: "EEG net" }).getByRole("combobox");
  await expect(netSelect).toHaveText("Choose a net");
  await expect.poll(() => page.evaluate(() => window.__scenePane?.markers ?? -1)).toBe(0);
  const net = "EGI_template";
  await netSelect.click();
  await page.getByRole("option", { name: net, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.__scenePane?.net ?? null)).toBe(net);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.markers ?? 0)).toBeGreaterThan(0);
  // The form speaks the convention before anything is picked.
  await expect(editor().locator(".electrode-pair-index")).toHaveText(["Channel 1", "Channel 2"]);
  await expect(editor().locator(".electrode-slot-role")).toHaveText(["E1+", "E1-", "E2+", "E2-"]);
  await expect(slot(0)).toHaveText("Choose…");
  await expect(editor().getByRole("button", { name: "Add 2 channels", exact: true })).toBeVisible();
  await expect(hint()).toHaveText("Click an electrode to set E1+ (Channel 1).");
});

test("four clicks fill E1+, E1-, E2+, E2- in order; clicking one again clears it", async () => {
  const picks = await frontMarkers(4);
  for (const [i, m] of picks.entries()) {
    await clickMarker(m);
    await expect(slot(i)).toHaveText(m.id, { timeout: 10_000 });
  }
  picked = picks.map((m) => m.id);
  await expect(active().getByTestId("channel-legend").locator(".channel-chip-name")).toHaveText([
    `E1+ ${picks[0]!.id} · E1- ${picks[1]!.id}`,
    `E2+ ${picks[2]!.id} · E2- ${picks[3]!.id}`,
  ]);
  if (SHOTS) {
    await page.screenshot({ path: join(SHOTS, "new-montage-two-channels.png") });
    await active().getByTestId("scene-pane-host").screenshot({ path: join(SHOTS, "scene-chips-status.png") });
  }

  // E1- again: unassigned, and the next click refills that very slot.
  await clickMarker(picks[1]!);
  await expect(slot(1)).toHaveText("Choose…");
  await expect(hint()).toHaveText("Click an electrode to set E1- (Channel 1).");
  await clickMarker(picks[1]!);
  await expect(slot(1)).toHaveText(picks[1]!.id);
});

test("opening a slot's picker aims the next click at that slot, and lists the others' electrodes as taken", async () => {
  await slot(2).click();
  // One electrode cannot be two poles: E1+'s electrode is listed in E2+'s picker, named, not pickable.
  // (The list is windowed, so filter to the electrode first.)
  await page.getByRole("dialog").getByPlaceholder("Filter electrodes…").fill(picked[0]!);
  await expect(page.getByTestId(`pair-1-a-reason-${picked[0]}`)).toHaveText("Already E1+");
  await page.getByRole("dialog").getByRole("button", { name: "Done", exact: true }).click();
  await expect(hint()).toHaveText("Click an electrode to set E2+ (Channel 2).");
  await expect(editor().locator('.electrode-slot[data-slot="2"]')).toHaveAttribute("data-active-slot", "true");
});

test("Add 2 channels opens E3+ and E3- … E4-, and the next click on the head fills E3+", async () => {
  await editor().getByRole("button", { name: "Add 2 channels", exact: true }).click();
  await expect(editor().locator(".electrode-slot-role")).toHaveText(["E1+", "E1-", "E2+", "E2-", "E3+", "E3-", "E4+", "E4-"]);
  await expect(hint()).toHaveText("Click an electrode to set E3+ (Channel 3).");
  const next = (await frontMarkers(5)).find((m) => !picked.includes(m.id))!;
  await clickMarker(next);
  await expect(slot(4)).toHaveText(next.id, { timeout: 10_000 });
  picked.push(next.id);
});

test("switching the form's EEG net redraws the head's net, keeps the electrodes both nets have and blanks the rest", async () => {
  const netSelect = editor().locator(".field", { hasText: "EEG net" }).getByRole("combobox");
  const before = (await netSelect.innerText()).trim();
  // The mock's nets (`electrodesFor` in tests/mock-server/server.mjs): EGI_template is E1-E256 and
  // GSN-HydroCel-185 is E1-E185, so an electrode above E185 is on the first net only.
  expect(before, "the net the first test chose").toBe("EGI_template");
  // E3- from the form: an electrode the other net lacks, so the switch has a slot to blank.
  const onlyHere = ["E256", "E255", "E254"].find((n) => !picked.includes(n))!;
  await slot(5).click();
  await page.getByRole("dialog").getByPlaceholder("Filter electrodes…").fill(onlyHere);
  await page.getByTestId(`pair-2-b-row-${onlyHere}`).click();
  await page.getByRole("dialog").getByRole("button", { name: "Done", exact: true }).click();
  await expect(slot(5)).toHaveText(onlyHere);
  const draft = [...picked, onlyHere];

  const markersBefore = await page.evaluate(() => window.__scenePane?.markers ?? 0);
  await netSelect.click();
  const names = (await page.getByRole("option").allInnerTexts()).map((n) => n.trim());
  const other = names.find((n) => n && n !== before);
  expect(other, "the mock catalog offers only one net — this spec needs two").toBeTruthy();
  await page.getByRole("option", { name: other!, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.__scenePane?.net ?? null), { timeout: 20_000 }).toBe(other);
  await expect.poll(() => page.evaluate(() => window.__scenePane?.markers ?? 0), { timeout: 20_000 }).not.toBe(markersBefore);

  // Each slot keeps its electrode if the new net has it and is emptied if not; the cursor moves to
  // the first empty slot.
  const onNew = new Set(await page.evaluate(() => (window.__scene?.markers ?? []).map((m: { id: string }) => m.id)));
  const expected = draft.map((n) => (onNew.has(n) ? n : "Choose…"));
  expect(expected[5], `${onlyHere} is not on ${other}`).toBe("Choose…");
  for (const [i, text] of expected.entries()) await expect(slot(i)).toHaveText(text, { timeout: 10_000 });
  const firstEmpty = expected.indexOf("Choose…");
  await expect(hint()).toHaveText(`Click an electrode to set ${electrodeSlotName(firstEmpty)} (Channel ${Math.floor(firstEmpty / 2) + 1}).`);
  await expect(editor().locator(`.electrode-slot[data-slot="${firstEmpty}"]`)).toHaveAttribute("data-active-slot", "true");
});

test("Cancel returns the pane to the job row", async () => {
  await editor().getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor()).toHaveCount(0);
  await expect(active().getByTestId("channel-legend")).toHaveCount(0);
  // The row still has no net: the form's net went with the form.
  await expect.poll(() => page.evaluate(() => window.__scenePane?.net ?? null)).toBeNull();
  await expect(hint()).toHaveText("Choose an EEG net to see its electrodes.");
});
