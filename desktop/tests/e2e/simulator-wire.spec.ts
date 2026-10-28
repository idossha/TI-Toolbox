import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page, type Request } from "@playwright/test";
import { answerExistingOutputs, connectLauncher, expectPage, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { addJobRow, clearJobRows, configureMontageJob, jobCurrents, jobDetail, jobRows, setJobMontage, setJobNet, setJobSubject } from "./_jobs";

/**
 * What the Simulator SENDS is what the user set and sees, against the mock server.
 *
 * Every expected value is read off the visible UI state the test sets (the channel inputs, the
 * coordinates typed into the free-hand table), never from a mock response:
 *  1. an mTI catalog montage row posts one current per visible input, equal to them;
 *  2. a plan step whose config names no intensities shows 1.0 mA per channel and saves exactly
 *     that (it used to save [0, 0]);
 *  3. the free-hand editor refuses to save until every electrode is placed, then saves four
 *     distinct coordinates, none at the origin;
 *  4. a hand-written 3-pair montage is shown as not runnable, with the reason on its row.
 * (Two rows that resolve to one output folder being blocked is run-collision.spec.ts's.)
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const auth = { Authorization: `Bearer ${TOKEN}` };
/** A hand-written montage_list.json entry the editor could never produce: 3 pairs. */
const THREE_PAIR = `${SERVER_URL}/api/catalog/montages/GSN-HydroCel-185/multi_polar/three_pair`;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page.getByTestId("nav-rail")).toBeVisible({ timeout: 20_000 });
  await openPalette(page);
  await page.getByTestId("palette-input").fill("ernie");
  await page.getByRole("dialog").getByRole("option", { name: /^ernie/ }).first().click();
  await expect(page.getByTestId("shell-content")).toHaveAttribute("data-subject", "ernie", { timeout: 10_000 });
  // Stored before the Simulator first reads the catalog (the app caches it for a minute); the
  // catalog stores what it is given, as a hand edit of montage_list.json would.
  const put = await page.request.put(THREE_PAIR, { headers: auth, data: { pairs: [["E24", "E124"], ["E67", "E77"], ["E36", "E104"]] } });
  expect(put.ok()).toBe(true);
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
});

test.afterAll(async () => {
  // The mock server outlives this spec: leave its montage list as the other specs expect it.
  await page?.request.delete(THREE_PAIR, { headers: auth });
  await app?.close();
});

/** The numbers the row's current inputs show, in channel order. */
async function shownCurrents(row: ReturnType<typeof jobRows>): Promise<number[]> {
  const inputs = jobCurrents(row);
  const values: number[] = [];
  for (let i = 0; i < (await inputs.count()); i += 1) values.push(Number(await inputs.nth(i).inputValue()));
  return values;
}

test("an mTI montage row posts exactly the four currents its inputs show", async () => {
  // The page seeds one blank row on arrival; wait for it, so clearing removes it.
  await expect(jobRows(page)).toHaveCount(1, { timeout: 15_000 });
  await clearJobRows(page);
  const row = await addJobRow(page);
  await configureMontageJob(page, row, { subject: "ernie", net: "GSN-HydroCel-185", montage: "mTI_F3F4_P3P4 · mTI" });
  await expect(jobCurrents(row)).toHaveCount(4);
  // Make the channels distinguishable, so an order or padding slip cannot pass.
  for (const [i, value] of [[1, "1.5"], [3, "0.7"]] as const) {
    await jobCurrents(row).nth(i).fill(value);
    await jobCurrents(row).nth(i).press("Tab");
  }
  const shown = await shownCurrents(row);
  expect(shown).toEqual([1, 1.5, 1, 0.7]);

  const bodies: Record<string, unknown>[] = [];
  const collect = (r: Request) => {
    if (r.method() === "POST" && /\/api\/jobs(\/groups)?$/.test(new URL(r.url()).pathname)) bodies.push(r.postDataJSON() as Record<string, unknown>);
  };
  page.on("request", collect);
  await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 15_000 });
  await page.getByTestId("run-button").click();
  await answerExistingOutputs(page);
  await expect.poll(() => bodies.length, { timeout: 20_000 }).toBeGreaterThan(0);
  page.off("request", collect);

  const group = bodies[0] as { subject_configs?: { config: Record<string, unknown> }[]; config?: Record<string, unknown> };
  // One job: its per-subject config (the group also repeats it as its base `config`).
  const configs = group.subject_configs ? group.subject_configs.map((e) => e.config) : [group.config!];
  expect(configs).toHaveLength(1);
  expect(configs[0]!.intensities).toEqual(shown);
  expect((configs[0]!.montages as { electrode_pairs: unknown[] }[])[0]!.electrode_pairs).toHaveLength(4);
});

test("a plan step that names no intensities shows 1.0 mA per channel and saves exactly that", async () => {
  const res = await page.request.post(`${SERVER_URL}/api/proposals`, {
    headers: auth,
    data: {
      title: "Simulate F3-F4",
      client: "Claude Code",
      steps: [
        {
          id: "simstep",
          kind: "sim",
          subject_ids: ["ernie"],
          config: { montages: [{ name: "F3_F4", mode: "net", eeg_net: "GSN-HydroCel-185", electrode_pairs: [["E24", "E124"], ["E67", "E77"]] }], conductivity: "scalar" },
        },
      ],
    },
  });
  expect(res.status()).toBe(201);
  const id = (await res.json()).id as string;
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await page.getByTestId("proposal-step-simstep").getByRole("button", { name: "Edit" }).click();
  await page.getByTestId("proposal-editor-simstep").getByRole("button", { name: "Open in form" }).click();
  await expect(page.getByRole("link", { name: "Simulator", exact: true })).toHaveAttribute("aria-current", "page");

  const row = jobRows(page).first();
  await expect(jobRows(page)).toHaveCount(1);
  await expect(row).toHaveAttribute("data-runnable", "true");
  const shown = await shownCurrents(row);
  expect(shown).toEqual([1, 1]);

  const patches: Record<string, unknown>[] = [];
  const collect = (r: Request) => {
    if (r.method() === "PATCH" && new URL(r.url()).pathname === `/api/proposals/${id}/steps/simstep`) patches.push(r.postDataJSON() as Record<string, unknown>);
  };
  page.on("request", collect);
  await page.getByTestId("plan-step-save").click();
  await expect.poll(() => patches.length, { timeout: 15_000 }).toBeGreaterThan(0);
  page.off("request", collect);
  expect((patches[0]!.config as Record<string, unknown>).intensities).toEqual(shown);
  const stored = await (await page.request.get(`${SERVER_URL}/api/proposals/${id}`, { headers: auth })).json();
  expect(stored.steps[0].config.intensities).toEqual(shown);
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
});

test("the free-hand editor saves only placed, distinct electrodes", async () => {
  await page.getByRole("button", { name: "New placement", exact: true }).click();
  await page.locator("#sim-freehand-name").fill("wire_check");
  const save = page.getByRole("button", { name: "Save placement", exact: true });
  const coords: [number, number, number][] = [
    [61.2, 10.4, 40.1],
    [-60.5, 12, 38.7],
    [5.3, 72.8, 31.9],
    [3.1, -74.6, 33],
  ];
  async function place(i: number, [x, y, z]: [number, number, number]) {
    for (const [axis, v] of [["X", x], ["Y", y], ["Z", z]] as const) {
      const input = page.getByRole("spinbutton", { name: `Position ${i + 1} ${axis}`, exact: true });
      await input.fill(String(v));
      await input.press("Tab");
    }
  }
  for (let i = 0; i < 3; i += 1) await place(i, coords[i]!);
  // Three of four placed: refused, and the reason names the one left.
  await expect(save).toBeDisabled();
  await expect(page.getByTestId("freehand-placement-problem")).toHaveText("Place every electrode on the scalp: E2- is not placed yet.");
  await expect(save).toHaveAttribute("title", "Place every electrode on the scalp: E2- is not placed yet.");

  await place(3, coords[3]!);
  await expect(save).toBeEnabled();
  await expect(page.getByTestId("freehand-placement-problem")).toHaveCount(0);
  const puts: Record<string, unknown>[] = [];
  const collect = (r: Request) => {
    if (r.method() === "PUT" && new URL(r.url()).pathname === "/api/catalog/freehand/wire_check") puts.push(r.postDataJSON() as Record<string, unknown>);
  };
  page.on("request", collect);
  await save.click();
  await expect.poll(() => puts.length, { timeout: 15_000 }).toBe(1);
  page.off("request", collect);
  const sent = (puts[0]!.electrode_positions as { x: number; y: number; z: number }[]).map((p) => [p.x, p.y, p.z]);
  expect(sent).toEqual(coords);
  expect(new Set(sent.map((p) => p.join(","))).size).toBe(4);
  expect(sent.some((p) => p.every((v) => v === 0))).toBe(false);
});

test("a hand-written 3-pair montage is shown as not runnable, with the reason on its row", async () => {
  await clearJobRows(page);
  const row = await addJobRow(page);
  await setJobSubject(page, row, "ernie");
  await setJobNet(page, row, "GSN-HydroCel-185");
  await setJobMontage(page, row, "three_pair · mTI");
  await expect(row).toHaveAttribute("data-runnable", "false");
  await expect(jobDetail(row).getByTestId("job-row-problem")).toHaveText("3 channels: a montage needs 2 channels (TI) or an even number from 4 (mTI).");
  await expect(page.getByTestId("run-button")).toBeDisabled();
});
