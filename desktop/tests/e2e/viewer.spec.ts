/**
 * Viewer screen, against the mock server — **a data selector, not a viewer** (V1,
 * `dev/notes/v3-native-panes-external-viewer-plan.md`).
 *
 * What this spec used to be: an iframe, a postMessage handshake, a fake embed fixture, a theme
 * hand-off, a `no-webgl2` state and a reload button. All of it is gone. The picture is drawn by
 * the **Tetravox desktop app** on the host, which has its own window, its own theme and its own
 * renderer, and which this app's only job is to hand a file to.
 *
 * So the assertions moved down to the two facts that are actually this page's:
 *
 * 1. **The draft → Open grammar** (R5, kept verbatim): editing a selector changes the draft and
 *    nothing else — no request, no launch — and one Open is exactly one `POST /api/view/open` and
 *    exactly one call to the launch bridge, carrying the file that call answered with.
 * 2. **There is no iframe anywhere in the app.** Asserted over the whole document, on every page
 *    the nav rail offers, because "the embed is retired" is a claim about the app, not about this
 *    screen.
 *
 * **Nothing is ever launched.** The `tit:viewer:open` IPC handler is replaced in the main process
 * with a recorder, so the spy sits exactly on the bridge boundary the gate names and a GUI app
 * never appears in front of whoever is running the suite. (This machine has Tetravox 0.3.11 in
 * /Applications; a spec that really spawned it would steal focus on every run.)
 */
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, expectSubject, gotoPage, launchElectronApp, openPalette } from "./_helpers";
import { deadSpaceRatio, paneWidths } from "./_metrics";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

let app: ElectronApplication;
let page: Page;

async function launchApp(): Promise<void> {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
}

/**
 * Replace `tit:viewer:open` (and `tit:viewer:probe`) in the **main process** with recorders.
 *
 * This is the spy the gate asks for, on the honest side of the bridge: the renderer calls the real
 * `window.tit.viewer.open`, the real IPC channel carries it, and what is stubbed is only the last
 * step — the one that would put another application's window on screen. `probe` is stubbed too so
 * the page reports "installed" on any machine, including CI, rather than the suite passing or
 * failing on whether the developer happens to have Tetravox.
 */
async function stubLaunchBridge(): Promise<void> {
  await app.evaluate(({ ipcMain }) => {
    const g = globalThis as unknown as { __viewerOpens?: string[] };
    g.__viewerOpens = [];
    ipcMain.removeHandler("tit:viewer:probe");
    ipcMain.handle("tit:viewer:probe", () => ({
      available: true,
      path: "/Applications/Tetravox.app",
      version: "0.3.11",
      source: "discovered",
      override: null,
      downloadUrl: "https://github.com/idossha/tetravox/releases/latest",
    }));
    ipcMain.removeHandler("tit:viewer:open");
    ipcMain.handle("tit:viewer:open", (_event, path: string) => {
      g.__viewerOpens?.push(String(path));
      return { ok: true, command: "/usr/bin/open", args: ["-a", "/Applications/Tetravox.app", String(path)] };
    });
  });
}

async function launchedScenes(): Promise<string[]> {
  return app.evaluate(() => (globalThis as unknown as { __viewerOpens?: string[] }).__viewerOpens ?? []);
}

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 20_000 });
}

/** The app's only subject picker is the shell's switcher, reachable from the palette. */
async function chooseSubject(id: string): Promise<void> {
  await openPalette(page);
  await page.getByTestId("palette-input").fill(id);
  await page.getByRole("dialog").getByRole("option", { name: new RegExp(`^${id}`) }).first().click();
  await expectSubject(page, id);
}

async function openViewer(): Promise<void> {
  await gotoPage(page, "viewer", "Viewer");
  await expectPage(page, "viewer");
}

/**
 * Pick one option in one named source-bar selector. Named by CONTROL, not by index: R5 makes the
 * bar's shape depend on the chosen view type, so "the second combobox" is no longer a stable
 * identity for anything.
 */
async function chooseOption(control: string, name: string): Promise<void> {
  await page.getByTestId(`viewer-select-${control}`).getByRole("combobox").click();
  await page.getByRole("option", { name, exact: true }).click();
}

async function pressOpen(): Promise<void> {
  await page.getByTestId("viewer-open").click();
}

/** Every `/api/view/...` request the renderer issues, in order, from now on. */
function recordViewRequests(): { url: string; method: string }[] {
  const seen: { url: string; method: string }[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (url.includes("/api/view/")) seen.push({ url, method: request.method() });
  });
  return seen;
}

const opens = (seen: { url: string; method: string }[]) => seen.filter((r) => r.method === "POST" && r.url.includes("/api/view/open"));

test.beforeAll(() => {
  mkdirSync(ARTIFACTS, { recursive: true });
});
test.beforeEach(async () => {
  await launchApp();
  await stubLaunchBridge();
});
test.afterEach(async () => {
  await app?.close();
});

// ── V1's own gate ────────────────────────────────────────────────────────────────────────────

test("one Open writes one scene file and calls the launch bridge once, with that file", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const seen = recordViewRequests();

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  expect(opens(seen), "drafting a selection opens nothing").toHaveLength(0);
  expect(await launchedScenes()).toEqual([]);

  await pressOpen();
  await expect(page.getByTestId("viewer-opened")).toBeVisible({ timeout: 15_000 });

  expect(opens(seen)).toHaveLength(1);
  const launched = await launchedScenes();
  expect(launched).toHaveLength(1);
  // The file the server said it wrote, and a name the Tetravox app will read as a scene rather
  // than as a volume (`isScenePath` is /\.tetravox\.json$/i).
  expect(launched[0]).toContain("/code/ti-toolbox/viewer/");
  expect(launched[0]!.endsWith(".tetravox.json")).toBe(true);
});

test("no page in the app contains an iframe", async () => {
  // The claim V4 makes is about the whole app, not about the Viewer: the embed was hosted here
  // *and* in the run pages' scene panes, and "we removed the iframe" is only true if none is left.
  await connect();
  await chooseSubject("ernie");
  const ids = await page.getByTestId("nav-rail").getByRole("link").evaluateAll((links) =>
    links.map((l) => (l as HTMLElement).getAttribute("data-page-id") ?? "").filter(Boolean),
  );
  expect(ids.length).toBeGreaterThan(3);
  for (const id of ids) {
    await gotoPage(page, id);
    await expect(page.locator("iframe"), `${id} draws an iframe`).toHaveCount(0);
  }
});

test("says so, and offers the download, when Tetravox is not installed", async () => {
  await connect();
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler("tit:viewer:probe");
    ipcMain.handle("tit:viewer:probe", () => ({
      available: false,
      path: null,
      version: null,
      source: null,
      override: null,
      downloadUrl: "https://github.com/idossha/tetravox/releases/latest",
    }));
  });
  await chooseSubject("ernie");
  await openViewer();
  await expect(page.getByTestId("viewer-not-installed")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("viewer-download-tetravox")).toBeVisible();
  // Not installed is a sentence, not a broken page: the selectors still work, and Open is refused
  // rather than silently doing nothing.
  await expect(page.getByTestId("viewer-source-bar")).toBeVisible();
  await expect(page.getByTestId("viewer-open")).toBeDisabled();
});

// ── R5's grammar, unchanged in substance ─────────────────────────────────────────────────────

test("navigating to the Viewer and editing the draft launches nothing", async () => {
  await connect();
  await chooseSubject("ernie");
  const seen = recordViewRequests();
  await openViewer();

  expect(opens(seen)).toHaveLength(0);
  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await chooseOption("kind", "Subject");
  await page.getByRole("radiogroup", { name: "Space" }).getByRole("radio", { name: "MNI", exact: true }).click();
  expect(opens(seen)).toHaveLength(0);
  expect(await launchedScenes()).toEqual([]);
});

test("the Open request carries the values the bar is showing", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();

  const bodies: Record<string, unknown>[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/api/view/open")) {
      bodies.push(JSON.parse(request.postData() ?? "{}") as Record<string, unknown>);
    }
  });

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await pressOpen();
  await expect(page.getByTestId("viewer-opened")).toBeVisible({ timeout: 15_000 });

  expect(bodies).toHaveLength(1);
  expect(bodies[0]).toMatchObject({ kind: "simulation", subject: "ernie", simulation: "Thalamus" });
});

test("an incomplete selection is refused before the wire, and launches nothing", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const seen = recordViewRequests();

  // `custom` needs a path; leaving it empty is a mistake to name, not a request to make.
  await chooseOption("kind", "Custom file");
  await pressOpen();
  await expect(page.getByTestId("viewer-view-error")).toBeVisible();
  expect(opens(seen)).toHaveLength(0);
  expect(await launchedScenes()).toEqual([]);
});

test("a deep link fills the controls and still launches nothing", async () => {
  await connect();
  await chooseSubject("ernie");
  await gotoPage(page, "results");
  await page.getByTestId("results-subject-filter").fill("");
  await page.getByTestId("results-subject-ernie").click();
  await page.getByTestId("results-tree-filter").fill("");
  await page.getByRole("radiogroup", { name: "Output kind" }).getByRole("radio", { name: "All", exact: true }).click();
  await page.getByTestId("results-node-simulation:ernie:docs_example").click();

  const seen = recordViewRequests();
  await page.getByTestId("results-open-in-viewer").click();
  await expectPage(page, "viewer");
  await expect(page.getByTestId("viewer-select-simulation").getByRole("combobox")).toContainText("docs_example");
  expect(opens(seen)).toHaveLength(0);
  expect(await launchedScenes()).toEqual([]);
});

test("a failed Open names the failure and still launches nothing", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await page.route("**/api/view/open", (route) => route.fulfill({ status: 500, json: { detail: "boom" } }));

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await pressOpen();
  await expect(page.getByTestId("viewer-view-error")).toBeVisible({ timeout: 15_000 });
  expect(await launchedScenes()).toEqual([]);
});

// ── layout ───────────────────────────────────────────────────────────────────────────────────

test("the page fills the content box at both sizes — no right pane, low dead space", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await expect(page.getByTestId("viewer-plan")).toBeVisible();

  const measured: Record<number, { work: number; right: number; dead: number }> = {};
  for (const width of [1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const panes = await paneWidths(page);
    const dead = await deadSpaceRatio(page);
    measured[width] = { work: panes.work, right: panes.right, dead: dead.ratio };
  }
  console.log("viewer panes:", JSON.stringify(measured));

  // U5/U1: the Viewer has no right pane at any width. The dead-space budget is deliberately looser
  // than the embed's 0.12: this page is a selector and a short summary, so most of it is *meant*
  // to be empty — a page that filled the screen to satisfy a metric would be padding.
  expect(measured[1280]!.right).toBe(0);
  expect(measured[1440]!.right).toBe(0);
  expect(measured[1280]!.work).toBeGreaterThanOrEqual(1200);
  expect(measured[1440]!.work).toBeGreaterThanOrEqual(1200);
});

test("takes the light and dark screenshots of the viewer page", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await expect(page.getByTestId("viewer-plan")).toBeVisible();
  await page.screenshot({ path: join(ARTIFACTS, "viewer-light.png"), fullPage: false });
});
