import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, selectSubject } from "../_helpers";
import { createAndSelectMontage, deleteMontage } from "./_simMontage";

/**
 * The montage table's config shape, against the real dev container: one uni-polar and one
 * multi-polar montage built through the UI, and the `SimulationConfig` the page produces for each
 * asserted on the wire. Nothing is submitted — the plan request carries the same `config`
 * `buildSimulationConfig` sends to `POST /api/jobs`, so no FEM is ever started.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const RUN_ID = process.env.TIT_E2E_RUN_ID ?? "real";
const NET = "BioSemi-128-A1.csv";
const TI_NAME = `smoke-ui-${RUN_ID}-shape-ti`;
const MTI_NAME = `smoke-ui-${RUN_ID}-shape-mti`;

let app: ElectronApplication;
let page: Page;
const planned: Record<string, unknown>[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-shape-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  page.on("request", (request) => {
    if (request.method() !== "POST" || !request.url().includes("/api/plan/sim")) return;
    const body = request.postDataJSON() as { config?: Record<string, unknown> } | null;
    if (body?.config) planned.push(body.config);
  });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await selectSubject(page, "101");
  await gotoPage(page, "simulator", "Simulator");
  await expectPage(page, "simulator");
});

test.afterAll(async () => {
  await deleteMontage(page, TI_NAME).catch(() => undefined);
  await deleteMontage(page, MTI_NAME).catch(() => undefined);
  await app?.close();
});

function lastConfigFor(name: string): Record<string, unknown> {
  const hit = [...planned].reverse().find((c) => {
    const montages = c.montages as { name?: string }[] | undefined;
    return montages?.[0]?.name === name;
  });
  if (!hit) throw new Error(`no plan request carried montage ${name}: ${JSON.stringify(planned.map((c) => c.montages))}`);
  return hit;
}

test("a uni-polar montage plans as a 2-pair, 2-current SimulationConfig", async () => {
  test.setTimeout(180_000);
  await createAndSelectMontage(page, {
    net: NET,
    name: TI_NAME,
    pairs: [
      ["A1", "A2"],
      ["B1", "B2"],
    ],
  });
  // The plan grid's column is the montage *source*, not the montage name (`RunControls.tsx`'s
  // `stageFor: sourceOfJob`), so the montage this test built is proved by the plan REQUEST it
  // triggered, not by a per-name cell that no longer exists.
  await expect(page.getByTestId("plan-cell-101-montage")).toBeVisible({ timeout: 30_000 });
  await expect.poll(() => planned.some((c) => (c.montages as { name?: string }[] | undefined)?.[0]?.name === TI_NAME), {
    timeout: 30_000,
  }).toBe(true);

  const config = lastConfigFor(TI_NAME);
  expect(config).toMatchObject({
    subject_id: "101",
    conductivity: "scalar",
    intensities: [1, 1],
    electrode_shape: "ellipse",
    electrode_dimensions: [8, 8],
    gel_thickness: 4,
    output_fields: ["TI_max"],
    montages: [
      {
        _type: "Montage",
        name: TI_NAME,
        mode: "net",
        eeg_net: NET,
        electrode_pairs: [
          ["A1", "A2"],
          ["B1", "B2"],
        ],
      },
    ],
  });
});

test("a multi-polar montage plans as a 4-pair, 4-current SimulationConfig", async () => {
  test.setTimeout(180_000);
  for (const button of await page.getByRole("button", { name: /^Remove row / }).all()) await button.click().catch(() => undefined);
  await createAndSelectMontage(page, {
    net: NET,
    name: MTI_NAME,
    pairs: [
      ["A1", "A2"],
      ["B1", "B2"],
      ["A3", "A4"],
      ["B3", "B4"],
    ],
  });
  await expect(page.getByTestId("plan-cell-101-montage")).toBeVisible({ timeout: 30_000 });
  await expect.poll(() => planned.some((c) => (c.montages as { name?: string }[] | undefined)?.[0]?.name === MTI_NAME), {
    timeout: 30_000,
  }).toBe(true);

  const config = lastConfigFor(MTI_NAME);
  expect(config).toMatchObject({
    subject_id: "101",
    intensities: [1, 1, 1, 1],
    montages: [
      {
        _type: "Montage",
        name: MTI_NAME,
        mode: "net",
        eeg_net: NET,
        electrode_pairs: [
          ["A1", "A2"],
          ["B1", "B2"],
          ["A3", "A4"],
          ["B3", "B4"],
        ],
      },
    ],
  });
  console.log("REAL montage config shapes:", JSON.stringify({ ti: lastConfigFor(TI_NAME), mti: config }, null, 1));
});
