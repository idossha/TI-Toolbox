import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp, selectSubject } from "../_helpers";

/**
 * Viewer → Open, against the **real** container and the embed it bakes (IB).
 *
 * The mock's version of this loop is `tests/e2e/viewer.spec.ts`. What only a real server can
 * prove is the whole delivery stack end to end: `/api/view/open` resolving sub-ernie's real
 * simulation, the iframe loading the bundle the image serves at `/tetravox/` (not the mock's
 * `fake-embed`), and that bundle answering `ready` after taking the scene — a real Tetravox
 * engine, wasm and all, drawn by this window on the host's GPU.
 *
 * Dataset 000 has sub-ernie with a `Thalamus` simulation; nothing here writes into it except the
 * scene file `/api/view/open` always writes under `<project>/code/ti-toolbox/viewer/`.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
});

test.afterAll(async () => {
  await app?.close();
});

test("the served embed is a real bundle, not the placeholder", async () => {
  // Read through the app's own session so the request carries the token the way the iframe's will.
  const manifest = await page.evaluate(async (base) => {
    const res = await fetch(new URL("/tetravox/manifest.json", base).href);
    return { status: res.status, csp: res.headers.get("content-security-policy"), body: await res.json() };
  }, SERVER_URL);
  expect(manifest.status).toBe(200);
  expect(manifest.body.version).not.toContain("placeholder");
  expect(typeof manifest.body.protocol).toBe("number");
  expect(manifest.csp ?? "").toContain("wasm-unsafe-eval");
});

test("Open on sub-ernie lands on the Tetravox sub-page with the embed ready", async () => {
  await selectSubject(page, "ernie");
  await gotoPage(page, "viewer", "Viewer");
  await expectPage(page, "viewer");

  await page.getByTestId("viewer-select-kind").getByRole("combobox").click();
  await page.getByRole("option", { name: "Simulation", exact: true }).click();
  await page.getByTestId("viewer-select-simulation").getByRole("combobox").click();
  await page.getByRole("option", { name: "Thalamus", exact: true }).click();

  await page.getByTestId("viewer-open").click();
  await expect(page.getByTestId("viewer-sub-viewer")).toHaveAttribute("data-active", "true", { timeout: 15_000 });
  await expect(page.getByTestId("viewer-opened")).toContainText(".tetravox.json");
  await expect(page.getByTestId("viewer-strip-name")).toHaveText("simulation.tetravox.json");

  const host = page.getByTestId("tetravox-host");
  await expect(host).toBeVisible();
  // `idle` is silence; `no-webgl2` would be this machine; `ready` is the engine having taken
  // sub-ernie's scene. A real bundle is bigger than the mock's, so the budget is wider.
  await expect(host).not.toHaveAttribute("data-viewer-status", "idle", { timeout: 60_000 });
  await expect(host).toHaveAttribute("data-viewer-status", "ready", { timeout: 60_000 });
  await expect(page.getByTestId("tetravox-frame")).toHaveAttribute("src", /\/tetravox\//);
  await expect(page.getByTestId("viewer-error")).toHaveCount(0);
});
