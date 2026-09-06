/**
 * Viewer screen, against the mock server and its **fake embed**.
 *
 * The mock serves `desktop/tests/e2e/fixtures/fake-embed/` at `/tetravox/` (lane W3a): a
 * dependency-free page speaking protocol v1 with no WebGL2 and no WASM. So this spec exercises the
 * whole real path — the iframe URL and its `hostOrigin`, the origin-checked postMessage channel,
 * the `ready`/`load` handshake, the cursor round-trip, the theme hand-off — without needing a
 * GPU-capable renderer bundle. `viewer-real.spec.ts` is the same shape against a real one.
 *
 * v3 (program U5) deleted the host-drawn inspector — Layers, Cursor, Scene — entirely, so this
 * spec no longer asserts a mirrored layer list or a host-side cursor control; it asserts the page
 * that replaced it: the 40 px source bar, the embed filling everything else, the status bar's
 * `ras`/`space`/`renderer` cells fed by the embed's own events, and the three designed states of
 * DESIGN.md §10. The `no-webgl2` and `no-embed` states are produced with `page.route` overrides of
 * `/tetravox/index.html` — no shared mock-server or fixture file changes needed for a state the
 * fake embed cannot itself report on demand.
 *
 * Assertions are on data attributes and the DOM, per DESIGN.md §8.1; the screenshots at the end are
 * evidence for a human, not the test.
 */
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Frame, type FrameLocator, type Page } from "@playwright/test";
import { expectPage, expectSubject, gotoPage, launchElectronApp, openPalette, setTheme } from "./_helpers";
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

function embed(): FrameLocator {
  return page.frameLocator('[data-testid="tetravox-frame"]');
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

async function pressLoad(): Promise<void> {
  await page.getByTestId("viewer-load").click();
}

/** The R5 flow: draft the selection, then command the load. Two acts, deliberately. */
async function selectSimulation(name: string): Promise<void> {
  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", name);
  await pressLoad();
}

/** Every `/api/view/{kind}` request the renderer issues, in order, from now on. */
function recordViewRequests(): string[] {
  const seen: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (url.includes("/api/view/")) seen.push(url);
  });
  return seen;
}

async function embedFrame(): Promise<Frame> {
  // The iframe is mounted by the page, so it can be a tick or two behind the route change; poll
  // for it rather than racing it.
  await expect.poll(() => page.frames().some((f) => f.url().includes("/tetravox/")), { timeout: 15_000 }).toBe(true);
  const frame = page.frames().find((f) => f.url().includes("/tetravox/"));
  if (!frame) throw new Error("the embed iframe is not mounted");
  return frame;
}

/**
 * Count `load` messages the host posts INTO the embed, from inside the embed itself.
 *
 * The host→embed direction is the one R5's gate is about ("one scene-load message"), and the only
 * honest place to count it is the receiving window: a listener added here sees exactly the same
 * events the fake embed's own handler does, without the fixture having to grow a counter for the
 * benefit of one spec.
 */
async function countSceneLoads(): Promise<void> {
  const frame = await embedFrame();
  await frame.evaluate(() => {
    const w = window as unknown as { __sceneLoads?: number };
    if (w.__sceneLoads !== undefined) return;
    w.__sceneLoads = 0;
    window.addEventListener("message", (event: MessageEvent) => {
      const data = event.data as { tvx?: number; type?: string } | null;
      if (data && data.tvx === 1 && data.type === "load") w.__sceneLoads = (w.__sceneLoads ?? 0) + 1;
    });
  });
}

async function sceneLoads(): Promise<number> {
  const frame = await embedFrame();
  return frame.evaluate(() => (window as unknown as { __sceneLoads?: number }).__sceneLoads ?? 0);
}

/** What the embed is actually drawing, as its own layer list reports it. */
async function embedLayerIds(): Promise<string[]> {
  return embed()
    .getByTestId("fake-embed-layers")
    .locator("li")
    .evaluateAll((nodes) => nodes.map((n) => (n as HTMLElement).dataset.layerId ?? ""));
}

/** The host says what it thinks the viewer's state is; that attribute is the contract under test. */
async function expectViewerStatus(status: string): Promise<void> {
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", status, { timeout: 15_000 });
}

test.beforeAll(() => {
  mkdirSync(ARTIFACTS, { recursive: true });
});
test.beforeEach(launchApp);
test.afterEach(async () => {
  await app?.close();
});

test("mounts the embed with the host origin and loads a scene into it", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();

  // The URL contract (docs/EMBED.md §2): embed mode on, and the one origin the embed will accept
  // messages from, percent-encoded.
  const frame = page.getByTestId("tetravox-frame");
  await expect(frame).toHaveAttribute("src", new RegExp(`^${SERVER_URL}/tetravox/index\\.html\\?embed=1&hostOrigin=`));
  await expect(frame).toHaveAttribute("src", new RegExp(encodeURIComponent(SERVER_URL).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  // Both flags, and only these two — see TetravoxFrame.tsx's header for why.
  await expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin");

  await selectSimulation("Thalamus");
  await expectViewerStatus("ready");

  // There is no host-side mirror any more (U5 deleted the Layers block): the scene reaching the
  // embed is proven by the embed's OWN layer list, drawn from what `load` handed it.
  await expect(embed().getByTestId("fake-embed-layers").locator("li")).not.toHaveCount(0);

  // No inspector anywhere: none of its testids exist in the DOM at all.
  for (const testid of ["viewer-inspector", "viewer-layers", "viewer-scene-link", "viewer-inspector-toggle"]) {
    await expect(page.getByTestId(testid)).toHaveCount(0);
  }
  await expect(page.getByRole("button", { name: "Serialize" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Capture" })).toHaveCount(0);
});

test("⌘⇧V hands focus to the embed's iframe (app/Shell.tsx's focusViewerCanvas)", async () => {
  // Shell.tsx's own shortcut targets `.shell-content canvas` — a selector for the retired
  // in-process engine. Since the postMessage embed replaced it, focus has to land on the iframe
  // itself (`[data-testid="tetravox-frame"]`) via `frame.focus()`, plus the store's own
  // `focusCanvas()` telling the embed's crosshair/nav to take over (viewer/store.ts).
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await selectSimulation("Thalamus");
  await expectViewerStatus("ready");

  // Start with focus somewhere else on the page so the shortcut has to move it. `.focus()` inside
  // the poll, not just the read: right after a scene lands there is still async settling on this
  // page (queries for the RAS/space/renderer status cells), and a re-render in that window can
  // steal an already-set focus straight back — retrying the act, not only the assertion, is what
  // makes this robust rather than a one-shot `.focus()` racing that settling.
  await expect
    .poll(async () => {
      await page.getByTestId("viewer-reload").focus();
      return page.evaluate(() => document.activeElement?.getAttribute("data-testid"));
    })
    .toBe("viewer-reload");

  // Same reasoning for the shortcut itself: re-press it inside the poll rather than once before a
  // one-shot read, so an incidental focus-stealing re-render in this same settling window does not
  // turn a real fix into a flaky test.
  const mod = process.platform === "darwin" ? "Meta+Shift+v" : "Control+Shift+v";
  await expect
    .poll(async () => {
      await page.keyboard.press(mod);
      return page.evaluate(() => document.activeElement?.getAttribute("data-testid"));
    })
    .toBe("tetravox-frame");
});

test("the source bar's reload button remounts the frame", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await selectSimulation("Thalamus");
  await expectViewerStatus("ready");

  let requests = 0;
  await page.route("**/tetravox/index.html**", (route) => {
    requests++;
    return route.continue();
  });

  await page.getByTestId("viewer-reload").click();
  // A remount re-fetches the iframe document and re-runs the handshake — the embed answers again.
  await expect.poll(() => requests, { timeout: 10_000 }).toBeGreaterThan(0);
  await expectViewerStatus("ready");
});

test("hands the embed the app's resolved theme, on connect and on every change", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await selectSimulation("Thalamus");
  await expectViewerStatus("ready");

  // The fake embed records the last `setTheme` it was handed on its own <body>. Light is the app's
  // starting palette here, so this also proves the message is sent unprompted at handshake time and
  // not only on a change.
  await expect(embed().locator("body")).toHaveAttribute("data-theme", "light", { timeout: 10_000 });

  await setTheme(page, "dark");
  await expect(embed().locator("body")).toHaveAttribute("data-theme", "dark", { timeout: 10_000 });

  await setTheme(page, "light");
  await expect(embed().locator("body")).toHaveAttribute("data-theme", "light", { timeout: 10_000 });
});

test("stays quiet about 3D when the scene has no mesh", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await selectSimulation("Thalamus");
  await expectViewerStatus("ready");

  // The mock server's simulation scene is two volumes, both visible: the 3D pane is empty and there
  // is nothing the user could switch on, so the hint must NOT appear. (The hidden-mesh true positive
  // is a unit assertion — tests/unit/viewer-page.test.ts — the mock fixture carries no mesh at all.)
  await expect(page.getByTestId("viewer-3d-hint")).toHaveCount(0);
});

test("the embed fills the content box at both sizes — no right pane, low dead space", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await selectSimulation("Thalamus");
  await expectViewerStatus("ready");

  const measured: Record<number, { work: number; right: number; frame: number; dead: number }> = {};
  for (const width of [1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const panes = await paneWidths(page);
    const box = await page.getByTestId("tetravox-frame").boundingBox();
    const dead = await deadSpaceRatio(page);
    measured[width] = { work: panes.work, right: panes.right, frame: Math.round(box?.width ?? 0), dead: dead.ratio };
  }
  console.log("viewer panes:", JSON.stringify(measured));

  // U5/U1: the Viewer has no right pane at any width — `paneWidths().right` reads 0 (§2.1's
  // enforceable form), and the work pane (source bar + embed) is the whole content box.
  expect(measured[1280]!.right).toBe(0);
  expect(measured[1440]!.right).toBe(0);
  // The nav rail is icons below 1440 and labels at/above it for every page (program Q1: "the
  // Viewer needs no special case"), so the content box is ~1224px at BOTH sizes (56px icon rail
  // at 1280, 216px label rail at 1440 — the two are equal by construction: 1440-216 = 1280-56).
  // >=1200 is the floor this page must clear at either size; a wireframe figure of ">=1360 at
  // 1440" predates that resolution and is no longer reachable without forcing the icon rail,
  // which Q1 explicitly says the Viewer does not do — see b5-viewer-notes.md.
  expect(measured[1280]!.frame).toBeGreaterThanOrEqual(1200);
  expect(measured[1440]!.frame).toBeGreaterThanOrEqual(1200);
  expect(measured[1280]!.dead).toBeLessThanOrEqual(0.12);
  expect(measured[1440]!.dead).toBeLessThanOrEqual(0.12);
});

test("names a server with no viewer bundle, and draws no source bar for it", async () => {
  await connect();
  await chooseSubject("ernie");

  await page.route("**/api/capabilities", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.tetravox_embed = { available: false, version: "0.1.0", protocol: 1 };
    await route.fulfill({ response: res, json: body });
  });

  await openViewer();
  await expect(page.getByTestId("viewer-not-bundled")).toBeVisible();
  await expect(page.getByTestId("viewer-not-bundled")).toContainText("This server has no viewer bundle");
  await expect(page.getByTestId("viewer-not-bundled")).toContainText("0.1.0");
  await expect(page.getByTestId("viewer-source-bar")).toHaveCount(0);
  await expect(page.getByTestId("tetravox-host")).toHaveCount(0);

  // §11: there is no status bar for the viewer to report into any more.
  await expect(page.locator("[data-status-cell]")).toHaveCount(0);
});

test("names a machine with no WebGL2", async () => {
  await page.route("**/tetravox/index.html**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body:
        "<!doctype html><html><body><script>" +
        'window.parent.postMessage({ tvx: 1, type: "ready", version: "fake", caps: { webgl2: false, renderer: "SwiftShader" } }, "*");' +
        "</script></body></html>",
    }),
  );

  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await selectSimulation("Thalamus");
  await expectViewerStatus("no-webgl2");

  await expect(page.getByTestId("viewer-no-webgl2")).toContainText("cannot run the 3D viewer");
  await expect(page.getByTestId("viewer-no-webgl2")).toContainText("SwiftShader");
  await expect(page.getByTestId("viewer-no-webgl2").getByRole("button")).toHaveCount(0);
});

test("names a frame that never answers, and its own Reload viewer button remounts it", async () => {
  let requests = 0;
  await page.route("**/tetravox/index.html**", (route) => {
    requests++;
    return route.fulfill({ contentType: "text/html", body: "<!doctype html><html><body></body></html>" });
  });

  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await selectSimulation("Thalamus");
  await expectViewerStatus("no-embed");

  await expect(page.getByTestId("viewer-no-embed")).toContainText("did not answer");
  expect(requests).toBe(1);

  await page.getByTestId("viewer-no-embed").getByRole("button", { name: "Reload viewer" }).click();
  await expect.poll(() => requests, { timeout: 5_000 }).toBe(2);
});

test("takes the light and dark screenshots of the viewer page", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await selectSimulation("Thalamus");
  await expectViewerStatus("ready");
  await page.screenshot({ path: join(ARTIFACTS, "viewer-light.png") });

  await setTheme(page, "dark");
  await page.screenshot({ path: join(ARTIFACTS, "viewer-dark.png") });
});

// =================================================================================================
// R5 — selection is explicit, loading is a command (desktop/IMPLEMENTATION_PLAN.md).
//
// The gate is stated in counts, and counts are what these assert: how many `GET /api/view/{kind}`
// requests left the renderer, and how many `load` messages reached the embed. A page that "looks
// right" while quietly refetching on every keystroke passes a screenshot and fails this.
// =================================================================================================

test("navigating to the Viewer and editing the draft issues zero view requests and zero scene loads", async () => {
  await connect();
  await chooseSubject("ernie");
  const views = recordViewRequests();

  await openViewer();
  await countSceneLoads();

  // Initial navigation: the embed is mounted and idle, and the page says what to do next.
  await expect(page.getByTestId("viewer-nothing-loaded")).toBeVisible();
  await expect(page.getByTestId("viewer-source-bar")).toHaveAttribute("data-loaded-key", "");
  expect(views).toEqual([]);
  expect(await sceneLoads()).toBe(0);

  // Four draft edits across three view types, each of which the v2 page would have fetched for.
  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await page.getByTestId("viewer-source-bar").getByRole("radio", { name: "MNI" }).click();
  await chooseOption("kind", "Subject");
  await expect(page.getByTestId("viewer-source-bar")).toHaveAttribute("data-dirty", "true");

  // The catalog calls behind those menus did happen — that is the point of the distinction — but
  // not one of them was a view request, and nothing was handed to the embed.
  expect(views).toEqual([]);
  expect(await sceneLoads()).toBe(0);
  await expect(page.getByTestId("viewer-nothing-loaded")).toBeVisible();
});

test("one Load issues exactly one view request, carrying the values the bar is showing", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await countSceneLoads();

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  const views = recordViewRequests();
  await pressLoad();
  await expectViewerStatus("ready");

  expect(views).toHaveLength(1);
  const url = new URL(views[0]!);
  expect(url.pathname).toBe("/api/view/simulation");
  expect(url.searchParams.get("subject")).toBe("ernie");
  expect(url.searchParams.get("simulation")).toBe("Thalamus");
  expect(await sceneLoads()).toBe(1);

  // The draft is now the loaded selection: the bar is clean and the two keys agree.
  const bar = page.getByTestId("viewer-source-bar");
  await expect(bar).toHaveAttribute("data-dirty", "false");
  const loadedKey = await bar.getAttribute("data-loaded-key");
  expect(loadedKey).toBe(await bar.getAttribute("data-draft-key"));

  // Pressing Load again is a second command and therefore a second request — never an automatic
  // one. (This is what proves the count above is a real cap, not just a slow first render.)
  await pressLoad();
  await expect.poll(() => views.length, { timeout: 10_000 }).toBe(2);
});

test("atlas A and atlas B produce distinguishable requested ids", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();

  const views = recordViewRequests();
  await chooseOption("kind", "Subject");

  const options = await page.getByTestId("viewer-select-atlas").getByRole("combobox").click().then(async () => {
    const items = await page.getByRole("option").allInnerTexts();
    await page.keyboard.press("Escape");
    return items;
  });
  expect(options.length).toBeGreaterThanOrEqual(2);

  await chooseOption("atlas", options[0]!);
  await pressLoad();
  await expectViewerStatus("ready");
  await chooseOption("atlas", options[1]!);
  await pressLoad();
  await expectViewerStatus("ready");

  // Two loads, two requests, two DIFFERENT requested atlas ids. (The option's label is a display
  // name — "DKT + aseg subcortical" — while the wire carries the catalog's id, so the assertion is
  // on the ids being present and distinguishable, not on them equalling the menu text.)
  expect(views).toHaveLength(2);
  const asked = views.map((u) => new URL(u).searchParams.get("atlas"));
  expect(asked[0]).toBeTruthy();
  expect(asked[1]).toBeTruthy();
  expect(asked[0]).not.toBe(asked[1]);
});

test("a failed Load keeps the previous scene and attaches the error to the attempted selection", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await countSceneLoads();

  await selectSimulation("Thalamus");
  await expectViewerStatus("ready");
  const before = await embedLayerIds();
  expect(before.length).toBeGreaterThan(0);
  const loadedKey = await page.getByTestId("viewer-source-bar").getAttribute("data-loaded-key");
  const loadsBefore = await sceneLoads();

  // The next view request fails. Everything about the previous scene must survive it.
  await page.route("**/api/view/**", (route) => route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"boom"}' }));
  await chooseOption("kind", "Subject");
  await pressLoad();

  await expect(page.getByTestId("viewer-view-error")).toBeVisible();
  await expect(page.getByTestId("viewer-view-error")).toContainText("Could not build the view");
  expect(await embedLayerIds()).toEqual(before);
  expect(await sceneLoads()).toBe(loadsBefore);
  await expect(page.getByTestId("viewer-source-bar")).toHaveAttribute("data-loaded-key", loadedKey ?? "");
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready");

  // The error belongs to the attempted selection: go back to one that did load and it is gone,
  // without anything being refetched.
  await chooseOption("kind", "Simulation");
  await expect(page.getByTestId("viewer-view-error")).toHaveCount(0);
});

test("a deep link fills the controls and still issues zero view requests before Load", async () => {
  await connect();
  await chooseSubject("ernie");
  const views = recordViewRequests();

  // The real deep link: Results' own "Open in viewer", which navigates to
  // /viewer?kind=simulation&subject=&simulation= (pages/results/index.tsx::viewerSearch).
  await gotoPage(page, "results", "Results");
  await page.getByTestId("results-open-in-viewer").click();
  await expectPage(page, "viewer");

  // Prefilled: the type the link named is the type the bar shows, and its simulation selector
  // exists (it does not for kind=subject) — so the controls followed the link.
  await expect(page.getByTestId("viewer-select-simulation")).toBeVisible();
  await expect(page.getByTestId("viewer-source-bar")).toHaveAttribute("data-draft-key", /^simulation&/);

  // And nothing was loaded: no view request, no scene, the "press Load" hint still on screen.
  expect(views).toEqual([]);
  await expect(page.getByTestId("viewer-nothing-loaded")).toBeVisible();
  await expect(page.getByTestId("viewer-source-bar")).toHaveAttribute("data-loaded-key", "");

  // Load is still available and still explicit.
  await pressLoad();
  await expectViewerStatus("ready");
  expect(views).toHaveLength(1);
});

test("Reload re-sends the loaded scene and never loads the draft", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await selectSimulation("Thalamus");
  await expectViewerStatus("ready");

  const loadedKey = await page.getByTestId("viewer-source-bar").getAttribute("data-loaded-key");
  const views = recordViewRequests();

  // Draft something else, then reload: recovery restores what was loaded, not what is drafted.
  await chooseOption("kind", "Subject");
  await page.getByTestId("viewer-reload").click();
  await expectViewerStatus("ready");

  expect(views).toEqual([]);
  await expect(page.getByTestId("viewer-source-bar")).toHaveAttribute("data-loaded-key", loadedKey ?? "");
  await expect(page.getByTestId("viewer-source-bar")).toHaveAttribute("data-dirty", "true");
});
