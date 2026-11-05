import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, getServerPanels, gotoPage, launchElectronApp, setServerPanels, waitForJobTerminal } from "../_helpers";

/**
 * The Networks tab's Assess networks against a real server: the real preflight's reason for a subject
 * with no tractogram, one real assess job writing all.trx into a tract folder without a question
 * (it replaces no other network's file), its finish listing the network without a reload, then the
 * real plan's Replace question over that all.trx.
 *
 * Needs a disposable subject: TIT_E2E_ASSESS_SUBJECT has a tractogram and network, and its
 * TIT_E2E_ASSESS_SIMULATION has a `tract/` folder with no `.trx` in it (this spec writes all.trx
 * there). TIT_E2E_ASSESS_NO_TRACT_SUBJECT has a simulation and no tractogram.
 *   TIT_E2E_ASSESS_SUBJECT=CHN TIT_E2E_ASSESS_SIMULATION=LH2 TIT_E2E_ASSESS_NO_TRACT_SUBJECT=ernie \
 *   TIT_E2E_ASSESS_SHOTS=<dir> npx playwright test --project=real tests/e2e/real/visual-exporter-assess.spec.ts
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;
const SUBJECT = process.env.TIT_E2E_ASSESS_SUBJECT;
const SIMULATION = process.env.TIT_E2E_ASSESS_SIMULATION;
const NO_TRACT = process.env.TIT_E2E_ASSESS_NO_TRACT_SUBJECT;
const SHOTS = process.env.TIT_E2E_ASSESS_SHOTS ?? join(tmpdir(), "tit-assess-shots");

test.skip(!SUBJECT || !SIMULATION || !NO_TRACT, "skipping: TIT_E2E_ASSESS_SUBJECT, _SIMULATION and _NO_TRACT_SUBJECT name no copied project's subjects");
test.describe.configure({ mode: "serial" });

let app: ElectronApplication;
let page: Page;
let panelsAsFound: string[] = [];

async function choose(selector: string, name: string | RegExp): Promise<void> {
  await page.locator(selector).click();
  await page.getByRole("option", typeof name === "string" ? { name, exact: true } : { name }).first().click();
}

test.beforeAll(async () => {
  mkdirSync(SHOTS, { recursive: true });
  panelsAsFound = await getServerPanels(SERVER_URL, TOKEN);
  if (!panelsAsFound.includes("visual-exporter")) await setServerPanels(SERVER_URL, TOKEN, [...panelsAsFound, "visual-exporter"]);
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-real-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  const offer = page.getByRole("dialog", { name: "Add example data?" });
  await offer.waitFor({ timeout: 10_000 }).then(() => offer.getByRole("button", { name: "Close dialog" }).click(), () => undefined);
  await gotoPage(page, "panel-visual-exporter", "3D visual exporter");
  await expectPage(page, "panel-visual-exporter");
  await page.getByRole("radio", { name: "Networks" }).click();
});

test.afterAll(async () => {
  await setServerPanels(SERVER_URL, TOKEN, panelsAsFound);
  await app?.close();
});

test("a subject with no tractogram gets the server's reason, not a button", async () => {
  await choose("#ve-subject", NO_TRACT!);
  await choose("#ve-simulation", /./);
  await page.getByRole("checkbox", { name: /Thalamocortical sequence/ }).click();
  const reason = page.getByTestId("ve-assess-missing");
  await expect(reason).toContainText(`tractogram for sub-${NO_TRACT}`, { timeout: 30_000 });
  await expect(reason).toContainText("Tractography");
  await expect(page.getByTestId("ve-assess-networks")).toHaveCount(0);
  await page.screenshot({ path: join(SHOTS, "01-assess-missing.png") });
  await page.getByRole("checkbox", { name: /Thalamocortical sequence/ }).click();
});

test("all.trx is written beside what the folder holds with no question, and its finish lists it", async () => {
  test.setTimeout(45 * 60_000);
  await choose("#ve-subject", SUBJECT!);
  await choose("#ve-simulation", SIMULATION!);
  await page.getByRole("radio", { name: "Existing file" }).click();
  const assess = page.getByTestId("ve-assess-networks");
  await expect(assess).toBeEnabled({ timeout: 30_000 });
  await page.screenshot({ path: join(SHOTS, "02-assess-offered.png") });
  const accepted = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  await assess.click();
  const job = (await (await accepted).json()) as { id: string; kind: string };
  expect(job.kind).toBe("tract");
  await expect(page.getByTestId("page-right-pane").getByTestId("job-terminal-identity")).toContainText("tract", { timeout: 60_000 });
  await page.screenshot({ path: join(SHOTS, "03-assess-running.png") });
  const finished = await waitForJobTerminal(page, { url: SERVER_URL, token: TOKEN, jobId: job.id, timeoutMs: 40 * 60_000, pollMs: 10_000 });
  expect(finished.state, `job ${job.id}`).toBe("succeeded");
  await expect(page.locator("#ve-network")).toContainText("all", { timeout: 30_000 });
  await page.screenshot({ path: join(SHOTS, "04-assess-listed.png") });
});
