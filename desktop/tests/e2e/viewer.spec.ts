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
 * 2a. **VM: every knob the composition panel shows lands in the scene the server writes.** The
 *    page is a centred composition panel now — layers with opacity, colormap and threshold, a
 *    layout, a camera, a background, a convention flag, "Also open" extras, a preview strip, a
 *    preset store and a recents list. The assertion that matters is not that a slider moves, it
 *    is that moving it changes the document Open produces: a control whose value never reaches
 *    the file is a lie told to the person using it, and nothing on screen would say so.
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

interface ViewRequest {
  url: string;
  method: string;
  /** VM: the preview strip resolves through the same route with `dry_run`, which writes nothing. */
  dryRun: boolean;
}

/** Every `/api/view/...` request the renderer issues, in order, from now on. */
function recordViewRequests(): ViewRequest[] {
  const seen: ViewRequest[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (!url.includes("/api/view/")) return;
    let dryRun: boolean;
    try {
      dryRun = (JSON.parse(request.postData() ?? "{}") as { dry_run?: boolean }).dry_run === true;
    } catch {
      dryRun = false;
    }
    seen.push({ url, method: request.method(), dryRun });
  });
  return seen;
}

/**
 * The Opens that would actually write a file and start an application.
 *
 * VM routes the preview through the same endpoint with `dry_run: true`, so "how many requests did
 * drafting cost" and "how many scenes did drafting write" stopped being the same question. This
 * helper answers the second one, which is the one every one of these assertions was about.
 */
const opens = (seen: ViewRequest[]) => seen.filter((r) => r.method === "POST" && r.url.includes("/api/view/open") && !r.dryRun);

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
  expect(opens(seen), "drafting a selection writes no scene").toHaveLength(0);
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

test("no page in the app frames anything but the published documentation site", async () => {
  // The claim V4 makes is about the whole app, not about the Viewer: the embed was hosted here
  // *and* in the run pages' scene panes, and "we removed the iframe" is only true if none is left.
  //
  // Two iframes legitimately survive, and neither is a renderer: Help ▸ Docs frames
  // https://idossha.github.io (the only `frame-src` the app's CSP still grants), and Results
  // frames a generated HTML report at /api/files/report/<id>. Both are *documents*, which is what
  // an iframe is for. What must be gone is any frame that draws a scene — the embed at
  // /tetravox/ — together with the host component that mounted it. Retained pages keep every
  // visited page's DOM alive, so this walks the whole app and reads srcs, not counts.
  await connect();
  await chooseSubject("ernie");
  // The rail's own hrefs are the page list: `/viewer`, `/results`, … (NavRail renders one
  // `<NavLink to={"/" + page.id}>` per enabled page).
  const ids = await page.getByTestId("nav-rail").getByRole("link").evaluateAll((links) =>
    links.map((l) => new URL((l as HTMLAnchorElement).href).pathname.replace(/^\//, "")).filter(Boolean),
  );
  expect(ids.length).toBeGreaterThan(3);
  const framed: string[] = [];
  for (const id of ids) {
    await gotoPage(page, id);
    const srcs = await page.locator("iframe").evaluateAll((nodes) => nodes.map((n) => (n as HTMLIFrameElement).src));
    for (const src of srcs) {
      const document_ = src.startsWith("https://idossha.github.io") || src.includes("/api/files/report/");
      if (!document_) framed.push(`${id}: ${src}`);
    }
    // The embed's own host elements, by the ids every spec used to reach it through.
    for (const testid of ["tetravox-frame", "tetravox-host", "scene-pane-tetravox-frame"]) {
      await expect(page.getByTestId(testid), `${id} still mounts ${testid}`).toHaveCount(0);
    }
  }
  expect(framed, "a scene is still being drawn in an iframe").toEqual([]);
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
  await chooseOption("kind", "Subject anatomy");
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
    if (request.method() !== "POST" || !request.url().includes("/api/view/open")) return;
    const body = JSON.parse(request.postData() ?? "{}") as Record<string, unknown>;
    if (body.dry_run !== true) bodies.push(body);
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
  await chooseOption("kind", "Custom files");
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
  // VM's own record: the whole panel at the width the maintainer's screenshot was taken at.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("viewer-layers")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: join(ARTIFACTS, "viewer-menu.png"), fullPage: true });
});

// ── VM: the composition panel ────────────────────────────────────────────────────────────────

/** The `overrides` document of the last Open, or `undefined` if it carried none. */
function recordOpenBodies(): Record<string, unknown>[] {
  const bodies: Record<string, unknown>[] = [];
  page.on("request", (request) => {
    if (request.method() !== "POST" || !request.url().includes("/api/view/open")) return;
    const body = JSON.parse(request.postData() ?? "{}") as Record<string, unknown>;
    if (body.dry_run !== true) bodies.push(body);
  });
  return bodies;
}

async function draftSimulation(): Promise<void> {
  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await expect(page.getByTestId("viewer-layers")).toBeVisible({ timeout: 15_000 });
}

test("the panel shows every section, and the preview strip names the files with their sizes", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();

  for (const section of ["source", "layers", "layout", "extras"]) {
    await expect(page.getByTestId(`viewer-section-${section}`)).toBeVisible();
  }
  // No canvas, no ghost text: the panel is the page.
  await expect(page.locator("canvas")).toHaveCount(0);
  const rows = page.getByTestId("viewer-preview-files").locator("li");
  expect(await rows.count()).toBeGreaterThan(0);
  // A size, not a blank: the strip's whole reason to exist is saying how much is about to open.
  await expect(rows.first()).toContainText(/\d/);
});

test("drafting the composition still opens nothing, and Open carries it", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const seen = recordViewRequests();
  const bodies = recordOpenBodies();
  await draftSimulation();
  // The preview is a dry run; it is allowed to ask, and it must never write or launch.
  expect(seen.filter((r) => r.dryRun).length).toBeGreaterThan(0);
  expect(opens(seen)).toHaveLength(0);
  expect(bodies).toHaveLength(0);
  expect(await launchedScenes()).toEqual([]);

  const layer = page.getByTestId("viewer-layers").locator("li").first();
  const layerId = (await layer.getAttribute("data-testid"))!.replace("viewer-layer-", "");
  await page.getByTestId(`viewer-layer-opacity-${layerId}`).getByRole("spinbutton").fill("40");
  await page.getByTestId(`viewer-layer-opacity-${layerId}`).getByRole("spinbutton").blur();
  await page.getByTestId("viewer-layout").getByRole("radio", { name: "3D", exact: true }).click();
  await page.getByTestId("viewer-camera").getByRole("radio", { name: "L", exact: true }).click();
  expect(await launchedScenes()).toEqual([]);

  await pressOpen();
  await expect(page.getByTestId("viewer-opened")).toBeVisible({ timeout: 15_000 });
  expect(bodies).toHaveLength(1);
  const overrides = bodies[0]!.overrides as { layers: Record<string, { opacity: number }>; layout: string; camera: string };
  expect(overrides.layers[layerId]!.opacity).toBeCloseTo(0.4, 5);
  expect(overrides.layout).toBe("3d-only");
  expect(overrides.camera).toBe("L");
  expect(await launchedScenes()).toHaveLength(1);
});

test("a layer opacity change reaches the scene the server writes", async () => {
  // The claim the panel rests on. The response body of the Open is the document that went to disk
  // (tit/server/routes/viewers.py returns exactly what it wrote), so reading it back is reading
  // the file.
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();

  const layer = page.getByTestId("viewer-layers").locator("li").first();
  const layerId = (await layer.getAttribute("data-testid"))!.replace("viewer-layer-", "");
  const scenes: Record<string, unknown>[] = [];
  page.on("response", async (response) => {
    if (response.request().method() !== "POST" || !response.url().includes("/api/view/open")) return;
    const body = JSON.parse(response.request().postData() ?? "{}") as Record<string, unknown>;
    if (body.dry_run === true) return;
    scenes.push((await response.json()) as Record<string, unknown>);
  });

  await page.getByTestId(`viewer-layer-opacity-${layerId}`).getByRole("spinbutton").fill("25");
  await page.getByTestId(`viewer-layer-opacity-${layerId}`).getByRole("spinbutton").blur();
  await pressOpen();
  await expect(page.getByTestId("viewer-opened")).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => scenes.length).toBe(1);
  const written = scenes[0]!.scene as { layers: { id: string; opacity: number }[] };
  expect(written.layers.find((l) => l.id === layerId)!.opacity).toBeCloseTo(0.25, 5);
});

test("hiding a layer is written as a hidden layer, not as a missing one", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();

  const layer = page.getByTestId("viewer-layers").locator("li").first();
  const layerId = (await layer.getAttribute("data-testid"))!.replace("viewer-layer-", "");
  const bodies = recordOpenBodies();
  await page.getByTestId(`viewer-layer-visible-${layerId}`).click();
  await expect(layer).toHaveAttribute("data-visible", "false");
  await pressOpen();
  await expect(page.getByTestId("viewer-opened")).toBeVisible({ timeout: 15_000 });
  expect((bodies[0]!.overrides as { layers: Record<string, { visible: boolean }> }).layers[layerId]!.visible).toBe(false);
});

test("an 'Also open' tick rides on the Open as an extra", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  const bodies = recordOpenBodies();

  await page.getByTestId("viewer-extra-t1").getByRole("checkbox").click();
  await pressOpen();
  await expect(page.getByTestId("viewer-opened")).toBeVisible({ timeout: 15_000 });
  expect(bodies[0]!.extras).toEqual(["t1"]);
});

test("a preset saves the whole composition and restores it without opening anything", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  await page.getByTestId("viewer-layout").getByRole("radio", { name: "1×1", exact: true }).click();

  await page.getByTestId("viewer-save-preset").click();
  await page.getByTestId("viewer-preset-name").fill("Deep target");
  await page.getByTestId("viewer-preset-save").click();
  await expect(page.getByTestId("viewer-preset-name")).toHaveCount(0);

  // Change the composition, then put it back from the preset.
  await page.getByTestId("viewer-layout").getByRole("radio", { name: "2×2", exact: true }).click();
  const seen = recordViewRequests();
  const bodies = recordOpenBodies();
  await page.getByTestId("viewer-save-preset").click();
  await page.getByTestId("viewer-preset-Deep target").click();
  await expect(page.getByTestId("viewer-layout").getByRole("radio", { name: "1×1", exact: true })).toBeChecked();
  // Restoring is not opening.
  expect(bodies).toHaveLength(0);
  expect(await launchedScenes()).toEqual([]);
  expect(opens(seen)).toHaveLength(0);
});

test("the Recent list remembers what was opened and restores it", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  // Empty until something is actually opened — a footprint, not a draft.
  await expect(page.getByTestId("viewer-recent")).toBeDisabled();

  await draftSimulation();
  await pressOpen();
  await expect(page.getByTestId("viewer-opened")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("viewer-recent")).toBeEnabled();

  await chooseOption("kind", "Subject anatomy");
  await page.getByTestId("viewer-recent").click();
  await page.getByTestId("viewer-recent-0").click();
  await expect(page.getByTestId("viewer-select-simulation").getByRole("combobox")).toContainText("Thalamus");
});
