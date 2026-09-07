/**
 * Viewer screen, against the mock server — **a menu and a viewer, in one tab**
 * (V1 · VM2 · VE, `docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer){VX,VM,VM2}.md`).
 *
 * What this spec was for one day: a host-installed **Tetravox desktop app**, launched over an
 * Electron IPC bridge, with a spy sitting on `tit:viewer:open` and an assertion that no iframe
 * survived anywhere in the app. The maintainer reversed that. The picture is drawn **here**, in
 * this window, by the Tetravox **embed** served from the image at `/tetravox/` — so there is no
 * host install, no launch bridge, and no `window.tit.viewer`. An Open costs exactly one thing:
 * `POST /api/view/open`.
 *
 * The page is two sub-pages — `/viewer/menu` and `/viewer/tetravox`, two indented rows in the nav
 * rail — served by one always-mounted component, and the assertions follow that shape:
 *
 * 1. **The draft → Open grammar** (R5, kept): editing a selector edits the draft and nothing else
 *    — no write — and one Open is exactly one non-dry-run `POST /api/view/open`, after which the
 *    page is on the **Viewer** sub-page with that scene in the frame.
 * 2. **VM2: the editable "what will open" list *is* the scene.** Remove a row and that dataset is
 *    gone from the scene the server writes; add the atlas and it is there; reorder and the layer
 *    order follows. Read off the Open's response body, which is byte-for-byte what went to disk.
 * 3. **Tab retention.** Navigating to the Menu sub-item and back to Tetravox must keep the *same
 *    iframe element* — same document, same wasm heap, same camera — and must cost no new request.
 *    That is the single most valuable assertion in this file: it is the whole reason both panes
 *    stay mounted and the inactive one is merely `display:none`.
 * 4. **Exactly one embed frame, and only on the Tetravox sub-page.** The run pages' 3-D panes are
 *    lane NR's own native WebGL2 renderer (`pages/_shared/scene/ScenePane`) and frame nothing;
 *    Help ▸ Docs legitimately frames the published documentation site. Asserted by walking every
 *    page the rail offers, because "one renderer" is a claim about the app, not about this screen.
 *
 * **Counting, stated plainly, because it is the gate.** VM routes the file list's preview through
 * the *same* endpoint with `dry_run: true`, so "how many requests" and "how many scenes were
 * written" are different questions. Every count here reads the request's post body and keeps only
 * the ones with `dry_run !== true`.
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

/** Which sub-page is on screen — the attribute both panes carry, never a visibility guess. */
async function expectSub(which: "menu" | "viewer"): Promise<void> {
  await expect(page.getByTestId(`viewer-sub-${which}`)).toHaveAttribute("data-active", "true", { timeout: 15_000 });
}

/**
 * Wait out an Open.
 *
 * Open switches to the Viewer sub-page, so the Menu — and `viewer-opened` with it — is
 * `display:none` from that moment: still in the document (it is the same component, never
 * unmounted), never *visible*. So the settled state is "the Viewer pane is active", and the
 * receipt is asserted by presence.
 */
async function expectOpened(): Promise<void> {
  await expectSub("viewer");
  await expect(page.getByTestId("viewer-opened")).toHaveCount(1);
}

/**
 * Move between the Viewer's two sub-pages the way a person does it.
 *
 * They are real routes (`/viewer/menu`, `/viewer/tetravox`) reached from real rail rows, indented
 * under Viewer — not an in-page control — so this is ordinary navigation, and the retention rule
 * below is a claim about navigating away and back, not about a local state toggle.
 *
 * **Below 1440 the rail is icons and draws no sub-items at all** (`NavRail.tsx`: there is no room
 * to indent a labelled row under a 56px icon), and the palette is then the only place they can be
 * reached by name. This suite runs at 1280, so the fallback is the path most of these tests take —
 * and taking it is itself the assertion that the narrow rail did not simply strand the sub-page.
 */
async function gotoSub(which: "menu" | "tetravox"): Promise<void> {
  const railItem = page.getByTestId(`nav-subitem-viewer-${which}`);
  if ((await railItem.count()) > 0) {
    await railItem.click();
  } else {
    const label = which === "menu" ? "Viewer · Menu" : "Viewer · Tetravox";
    await openPalette(page);
    await page.getByTestId("palette-input").fill(label);
    await page.getByRole("dialog").getByRole("option", { name: label }).first().click();
    await expect(page.getByTestId("palette-input")).toHaveCount(0);
  }
  await expectSub(which === "menu" ? "menu" : "viewer");
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
 * The Opens that would actually write a scene file and put a picture on screen.
 *
 * VM routes the preview through the same endpoint with `dry_run: true`, so "how many requests did
 * drafting cost" and "how many scenes did drafting write" stopped being the same question. This
 * helper answers the second one, which is the one every assertion below is about.
 */
const opens = (seen: ViewRequest[]) => seen.filter((r) => r.method === "POST" && r.url.includes("/api/view/open") && !r.dryRun);

test.beforeAll(() => {
  mkdirSync(ARTIFACTS, { recursive: true });
});
test.beforeEach(launchApp);
test.afterEach(async () => {
  await app?.close();
});

// ── V1's own gate, as VE left it ─────────────────────────────────────────────────────────────

test("one Open is one request, and it writes one scene file", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const seen = recordViewRequests();

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  expect(opens(seen), "drafting a selection writes no scene").toHaveLength(0);

  await pressOpen();
  await expectOpened();

  expect(opens(seen)).toHaveLength(1);
  // The receipt names the file the server said it wrote, under the project's own viewer directory
  // and with a name Tetravox reads as a scene rather than as a volume (`/\.tetravox\.json$/i`).
  await expect(page.getByTestId("viewer-opened")).toContainText("/code/ti-toolbox/viewer/");
  await expect(page.getByTestId("viewer-opened")).toContainText(".tetravox.json");
});

test("Open moves to the Viewer sub-page and shows the scene", async () => {
  // VE's brief, verbatim: "the user configures in the Menu, hits Open, is moved to the Viewer
  // where the Tetravox embed is". The frame is only proof if it actually answered — an iframe
  // that mounted and stayed silent sits at `idle` forever — so this waits on the store's own
  // status attribute leaving "idle" rather than on a timeout.
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const seen = recordViewRequests();

  // Before any Open the Viewer sub-page is honest about being empty, and frames nothing.
  await gotoSub("tetravox");
  await expect(page.getByTestId("viewer-empty")).toBeVisible();
  await expect(page.getByTestId("viewer-empty-menu")).toBeVisible();
  await expect(page.getByTestId("tetravox-frame")).toHaveCount(0);
  await page.getByTestId("viewer-empty-menu").click();
  await expectSub("menu");

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await pressOpen();
  await expectOpened();

  expect(opens(seen)).toHaveLength(1);
  await expect(page.getByTestId("viewer-strip")).toBeVisible();
  await expect(page.getByTestId("viewer-strip-name")).toHaveText("simulation.tetravox.json");

  const host = page.getByTestId("tetravox-host");
  // Visible, not merely mounted: an embed the layout has collapsed to zero height is an embed
  // nobody can see, and every other assertion in this file would still pass with it.
  await expect(host).toBeVisible();
  // "ready" is the embed having taken the scene; "no-webgl2" would be this machine having no
  // context. Either is an answer; `idle` is silence, and silence is the failure this catches.
  await expect(host).not.toHaveAttribute("data-viewer-status", "idle", { timeout: 20_000 });
  await expect(host).toHaveAttribute("data-viewer-status", "ready", { timeout: 20_000 });
  await expect(page.getByTestId("tetravox-frame")).toHaveAttribute("src", /\/tetravox\//);
});

test("going back to the Menu keeps the scene, and costs nothing", async () => {
  // The retention contract, and the reason the two sub-pages are one always-mounted component.
  // Unmounting the frame would silently reload the engine and drop the camera and the wasm heap,
  // and nothing on screen would say so — so this asserts on the *identity of the element*, by a
  // marker stamped on it before the round trip, not on "an iframe is present afterwards".
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const seen = recordViewRequests();

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await pressOpen();
  await expectOpened();
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 20_000 });
  const nameBefore = await page.getByTestId("viewer-strip-name").textContent();
  expect(opens(seen)).toHaveLength(1);

  await page.getByTestId("tetravox-frame").evaluate((node) => {
    (node as HTMLIFrameElement).dataset.e2eIdentity = "the-one-and-only";
  });

  await gotoSub("menu");
  // The frame is hidden, not gone: it is still in the document with its marker intact.
  await expect(page.getByTestId("tetravox-frame")).toHaveCount(1);
  await expect(page.getByTestId("tetravox-frame")).toHaveAttribute("data-e2e-identity", "the-one-and-only");
  // The Menu is fully usable again, with the selection the person left there.
  await expect(page.getByTestId("viewer-select-simulation").getByRole("combobox")).toContainText("Thalamus");

  await gotoSub("tetravox");
  // Same element, same document, same scene — and the round trip asked the server for nothing.
  await expect(page.getByTestId("tetravox-frame")).toHaveCount(1);
  await expect(page.getByTestId("tetravox-frame")).toHaveAttribute("data-e2e-identity", "the-one-and-only");
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready");
  await expect(page.getByTestId("viewer-strip-name")).toHaveText(nameBefore ?? "");
  expect(opens(seen), "switching sub-pages must not re-open anything").toHaveLength(1);
});

test("Reload re-posts the scene without a new request", async () => {
  // The strip's Reload is the cheap one: the scene the page already has, posted to the frame
  // again. It is not a new resolution, so it must not touch the server.
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const seen = recordViewRequests();

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await pressOpen();
  await expectOpened();
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 20_000 });
  const before = opens(seen).length;
  expect(before).toBe(1);

  await page.getByTestId("viewer-reload").click();
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 20_000 });
  await expect(page.getByTestId("viewer-strip-name")).toHaveText("simulation.tetravox.json");
  expect(opens(seen), "Reload re-sends the scene it already has").toHaveLength(before);
});

test("opening again replaces the scene in the same frame", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const seen = recordViewRequests();

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await pressOpen();
  await expectOpened();
  await expect(page.getByTestId("viewer-strip-name")).toHaveText("simulation.tetravox.json");
  expect(opens(seen)).toHaveLength(1);

  await gotoSub("menu");
  await chooseOption("kind", "Subject anatomy");
  await pressOpen();
  await expectOpened();

  expect(opens(seen), "a second Open is exactly one more request").toHaveLength(2);
  await expect(page.getByTestId("viewer-strip-name")).toHaveText("subject.tetravox.json");
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 20_000 });
  // One frame, still — a second Open is a new scene in the same engine, not a second viewer.
  await expect(page.getByTestId("tetravox-frame")).toHaveCount(1);
});

test("exactly one page frames a scene, and it is the Viewer", async () => {
  // The inverse of what VX asserted for a day. The embed is back, so "no iframe anywhere" is
  // wrong; what is true, and worth holding, is that there is exactly *one* of it. The run pages'
  // 3-D panes are lane NR's own native WebGL2 renderer (`pages/_shared/scene/ScenePane`): they
  // mount `scene-pane-host` and frame nothing. Two other iframes are legitimate and neither is a
  // renderer — Help ▸ Docs frames https://idossha.github.io (the only other `frame-src` the app's
  // CSP grants) and Results frames a generated HTML report at /api/files/report/<id>. Both are
  // *documents*, which is what an iframe is for.
  //
  // Retained pages keep every visited page's DOM alive, so each page is read through its own
  // `[data-page-panel]` rather than off the whole document.
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await pressOpen();
  await expectOpened();

  // The Viewer sub-page hosts exactly one embed frame, and it is served from this app's own
  // /tetravox/ — not from anywhere else.
  const embeds = page.locator('[data-page-panel="viewer"] iframe');
  await expect(embeds).toHaveCount(1);
  await expect(embeds.first()).toHaveAttribute("src", /^https?:\/\/[^/]+\/tetravox\//);

  // The rail's own hrefs are the page list: `/viewer`, `/results`, … (NavRail renders one
  // `<NavLink to={"/" + page.id}>` per enabled page).
  const hrefs = await page.getByTestId("nav-rail").getByRole("link").evaluateAll((links) =>
    links.map((l) => new URL((l as HTMLAnchorElement).href).pathname.split("/").filter(Boolean)[0] ?? ""),
  );
  // The Viewer contributes three rows — itself and its two sub-items — and they are all one
  // retained page, so the walk is over distinct pages, not over rail rows.
  const ids = [...new Set(hrefs.filter(Boolean))];
  expect(ids.length).toBeGreaterThan(3);
  const framed: string[] = [];
  for (const id of ids) {
    await gotoPage(page, id);
    const panel = page.locator(`[data-page-panel="${id}"]`);
    await expect(panel).toHaveCount(1);
    const srcs = await panel.locator("iframe").evaluateAll((nodes) => nodes.map((n) => (n as HTMLIFrameElement).src));
    for (const src of srcs) {
      const document_ = src.startsWith("https://idossha.github.io") || src.includes("/api/files/report/");
      if (document_) continue;
      if (id === "viewer" && /\/tetravox\//.test(src)) continue;
      framed.push(`${id}: ${src}`);
    }
    // Lane NR's panes draw in this window with their own WebGL2 context; wherever one is mounted,
    // there must be no frame inside it.
    const panes = panel.getByTestId("scene-pane-host");
    for (let index = 0; index < (await panes.count()); index += 1) {
      await expect(panes.nth(index).locator("iframe"), `${id}: a scene pane is framing something`).toHaveCount(0);
    }
    if (id !== "viewer") {
      await expect(panel.getByTestId("tetravox-frame"), `${id} mounts an embed frame of its own`).toHaveCount(0);
    }
  }
  expect(framed, "a scene is being drawn in an iframe outside the Viewer").toEqual([]);
});

// ── R5's grammar, unchanged in substance ─────────────────────────────────────────────────────

test("navigating to the Viewer and editing the draft opens nothing", async () => {
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
  await expectSub("menu");
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
  await expectOpened();

  expect(bodies).toHaveLength(1);
  expect(bodies[0]).toMatchObject({ kind: "simulation", subject: "ernie", simulation: "Thalamus" });
});

test("an incomplete selection is refused before the wire, and opens nothing", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const seen = recordViewRequests();

  // `custom` needs a path; leaving it empty is a mistake to *name*, not a request to make — and
  // the page names it on the button itself rather than waiting for a click to punish. Refusing in
  // the control is stronger than refusing after it: there is no moment at which a request could
  // have escaped.
  await chooseOption("kind", "Custom files");
  const openButton = page.getByTestId("viewer-open");
  await expect(openButton).toBeDisabled();
  await expect(openButton).toHaveAttribute("title", /Choose .*[Pp]ath/);
  expect(opens(seen)).toHaveLength(0);
  // Refused means the person is left where they were, with the mistake named in front of them.
  await expectSub("menu");
  await expect(page.getByTestId("tetravox-frame")).toHaveCount(0);
});

test("a deep link fills the controls and still opens nothing", async () => {
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
  // A link prefills the Menu; it never jumps someone into a picture they did not ask for.
  await expectSub("menu");
});

test("a failed Open names the failure and shows no scene", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  // Only the *real* Open fails. The list resolves through the same route with `dry_run: true`,
  // and Open is disabled until it has rows — so failing both would test a disabled button rather
  // than a failed request.
  await page.route("**/api/view/open", (route) => {
    const body = JSON.parse(route.request().postData() ?? "{}") as { dry_run?: boolean };
    if (body.dry_run === true) return route.continue();
    return route.fulfill({ status: 500, json: { detail: "boom" } });
  });

  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await pressOpen();
  await expect(page.getByTestId("viewer-view-error")).toBeVisible({ timeout: 15_000 });
  await expectSub("menu");
  await expect(page.getByTestId("tetravox-frame")).toHaveCount(0);
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
  // than the embed's 0.12: the Menu is a selector and a short summary, so most of it is *meant*
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
  // VM2's own record: the Menu at the width the maintainer's screenshots were taken at.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("viewer-preview-files")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: join(ARTIFACTS, "viewer-menu-v2.png"), fullPage: true });
  // …and the Viewer sub-page with a scene actually in the frame.
  await pressOpen();
  await expectOpened();
  await expect(page.getByTestId("tetravox-host")).toHaveAttribute("data-viewer-status", "ready", { timeout: 20_000 });
  await page.screenshot({ path: join(ARTIFACTS, "viewer-embed-v2.png"), fullPage: false });
});

// ── VM2: the file list is the scene ──────────────────────────────────────────────────────────

/** The bodies of the Opens that would actually write a file (dry runs excluded). */
function recordOpenBodies(): Record<string, unknown>[] {
  const bodies: Record<string, unknown>[] = [];
  page.on("request", (request) => {
    if (request.method() !== "POST" || !request.url().includes("/api/view/open")) return;
    const body = JSON.parse(request.postData() ?? "{}") as Record<string, unknown>;
    if (body.dry_run !== true) bodies.push(body);
  });
  return bodies;
}

/** The scenes those Opens produced — the response body is byte-for-byte what went to disk. */
function recordWrittenScenes(): { scene: { datasets: { path: string }[]; layers: { name: string }[] } }[] {
  const scenes: { scene: { datasets: { path: string }[]; layers: { name: string }[] } }[] = [];
  page.on("response", (response) => {
    if (response.request().method() !== "POST" || !response.url().includes("/api/view/open")) return;
    const body = JSON.parse(response.request().postData() ?? "{}") as Record<string, unknown>;
    if (body.dry_run === true) return;
    void response
      .json()
      .then((json) => scenes.push(json as { scene: { datasets: { path: string }[]; layers: { name: string }[] } }))
      .catch(() => undefined);
  });
  return scenes;
}

async function draftSimulation(): Promise<void> {
  await chooseOption("kind", "Simulation");
  await chooseOption("simulation", "Thalamus");
  await expect(page.getByTestId("viewer-preview-files")).toBeVisible({ timeout: 15_000 });
  await settledOn(/TI_max/);
}

/**
 * Wait until the rows on screen are **this** selection's, identified by one of them.
 *
 * Since the card keeps the previous selection's rows while the next one resolves (2026-09-07), a
 * visible `viewer-preview-files` no longer means "this selection has resolved" — it can be the
 * previous one, greyed. Three specs in this file failed exactly that way: they captured the
 * *subject* view's rows as their baseline and then attributed the simulation's own resolve to the
 * list edit they made next.
 *
 * Matching a row is deliberate rather than polling the page's `data-resolving` flag. That flag is
 * correct, but reading it straight after a click races React's flush — Playwright can observe the
 * pre-click DOM, where nothing is resolving yet, and proceed. A row that only the new selection
 * produces cannot be true of the old one, whenever it is read.
 */
async function settledOn(row: RegExp): Promise<void> {
  await expect.poll(rowNames, { timeout: 15_000 }).toEqual(expect.arrayContaining([expect.stringMatching(row)]));
  await expect(page.getByTestId("viewer-plan")).not.toHaveAttribute("data-resolving", "true", { timeout: 15_000 });
}

const rowNames = () => page.getByTestId("viewer-preview-files").locator("li .viewer-file-name").allTextContents();
const datasetNames = (written: { scene: { datasets: { path: string }[] } }) =>
  written.scene.datasets.map((d) => d.path.split("/").pop());

test("the page is a source card and one file list — nothing else", async () => {
  // The maintainer's correction, as an assertion. VM's sections are gone, not merely collapsed.
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();

  await expect(page.getByTestId("viewer-section-source")).toBeVisible();
  await expect(page.getByTestId("viewer-plan")).toBeVisible();
  for (const gone of ["viewer-section-layers", "viewer-section-layout", "viewer-section-extras", "viewer-layers"]) {
    await expect(page.getByTestId(gone), `${gone} should not exist any more`).toHaveCount(0);
  }
  // No canvas *here*: appearance, camera and crosshair are the embed's, and the embed is the
  // other sub-page. The Menu is a list.
  await expect(page.getByTestId("viewer-sub-menu").locator("canvas")).toHaveCount(0);
  // Each row names a file, says what it is and how big it is.
  const first = page.getByTestId("viewer-preview-files").locator("li").first();
  await expect(first).toContainText(/volume|mesh/);
  await expect(first).toContainText(/\d/);
});

test("removing a row removes that dataset from the scene the server writes", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  const before = await rowNames();
  expect(before.length).toBeGreaterThan(1);

  const scenes = recordWrittenScenes();
  await page.getByTestId(`viewer-file-remove-${before[0]!}`).click();
  await expect.poll(rowNames).toEqual(before.slice(1));

  await pressOpen();
  await expectOpened();
  await expect.poll(() => scenes.length).toBe(1);
  expect(datasetNames(scenes[0]!)).toEqual(before.slice(1));
  expect(datasetNames(scenes[0]!)).not.toContain(before[0]);
});

test("adding the atlas puts it in the list and in the written scene", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  const before = await rowNames();

  const scenes = recordWrittenScenes();
  await page.getByTestId("viewer-add").click();
  await page.getByTestId("viewer-add-labeling.nii.gz").click();
  await expect.poll(rowNames).toEqual([...before, "labeling.nii.gz"]);

  await pressOpen();
  await expectOpened();
  await expect.poll(() => scenes.length).toBe(1);
  expect(datasetNames(scenes[0]!)).toEqual([...before, "labeling.nii.gz"]);
});

test("reordering the list reorders the scene's layers", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  const before = await rowNames();
  expect(before.length).toBeGreaterThan(1);

  const scenes = recordWrittenScenes();
  // The keyboard affordance, not the drag: a list you can only reorder with a mouse is a list
  // some people cannot reorder, and Playwright's drag is the flakiest thing in this suite.
  await page.getByTestId(`viewer-file-down-${before[0]!}`).click();
  const expected = [before[1]!, before[0]!, ...before.slice(2)];
  await expect.poll(rowNames).toEqual(expected);

  await pressOpen();
  await expectOpened();
  await expect.poll(() => scenes.length).toBe(1);
  expect(datasetNames(scenes[0]!)).toEqual(expected);
});

test("Reset puts the view type's own list back", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  const before = await rowNames();

  await page.getByTestId(`viewer-file-remove-${before[0]!}`).click();
  await expect.poll(rowNames).toEqual(before.slice(1));
  await page.getByTestId("viewer-files-reset").click();
  await expect.poll(rowNames).toEqual(before);
  // Reset is "let the source decide again", not "remember what I had": the link goes away with it.
  await expect(page.getByTestId("viewer-files-reset")).toHaveCount(0);
});

test("editing the list costs no write until Open", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  // Recording starts AFTER the source has resolved: choosing a source is allowed exactly one
  // request (the view type's own file list). What must cost nothing is every edit after it.
  const before = await rowNames();
  const seen = recordViewRequests();
  const bodies = recordOpenBodies();

  await page.getByTestId(`viewer-file-remove-${before[0]!}`).click();
  await expect.poll(rowNames).toEqual(before.slice(1));
  await page.getByTestId("viewer-add").click();
  await page.getByTestId("viewer-add-labeling.nii.gz").click();
  await expect.poll(rowNames).toEqual([...before.slice(1), "labeling.nii.gz"]);

  // VE: editing the list costs the server NOTHING at all — not a write, and not a dry run either.
  // It used to cost one `POST /api/view/open?dry_run` per click, and that route reads every volume
  // in the scene to compute its percentile window (~150 ms warm, ~860 ms cold), which is what the
  // maintainer saw as "the menu acts way too slow … it does computation when I add or remove
  // things". The rows now come from two source-keyed queries and the edit is local.
  expect(seen.filter((r) => r.dryRun).length, "an edit re-resolved on the server").toBe(0);
  expect(opens(seen), "editing the list writes no scene").toHaveLength(0);
  expect(bodies).toHaveLength(0);
  await expectSub("menu");

  await pressOpen();
  await expectOpened();
  expect(opens(seen)).toHaveLength(1);
  // The list travels as container paths, in the list's order; the names are what the rows show.
  const sent = bodies[0]!.files as string[];
  expect(sent.map((p) => p.split("/").pop())).toEqual([...before.slice(1), "labeling.nii.gz"]);
});

test("changing the source resets the list to that source's own files", async () => {
  // Keeping the old rows would silently open the previous selection's data under a new heading.
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  const simulationRows = await rowNames();
  await page.getByTestId(`viewer-file-remove-${simulationRows[0]!}`).click();
  await expect.poll(rowNames).toEqual(simulationRows.slice(1));

  await chooseOption("kind", "Subject anatomy");
  await expect(page.getByTestId("viewer-files-reset")).toHaveCount(0);
  await expect.poll(rowNames).not.toEqual(simulationRows.slice(1));
});

test("a preset saves the edited list and restores it without opening anything", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  const before = await rowNames();
  await page.getByTestId(`viewer-file-remove-${before[0]!}`).click();
  await expect.poll(rowNames).toEqual(before.slice(1));

  await page.getByTestId("viewer-save-preset").click();
  await page.getByTestId("viewer-preset-name").fill("Deep target");
  await page.getByTestId("viewer-preset-save").click();
  await expect(page.getByTestId("viewer-preset-name")).toHaveCount(0);

  await page.getByTestId("viewer-files-reset").click();
  await expect.poll(rowNames).toEqual(before);

  const seen = recordViewRequests();
  const bodies = recordOpenBodies();
  await page.getByTestId("viewer-save-preset").click();
  await page.getByTestId("viewer-preset-Deep target").click();
  await expect.poll(rowNames).toEqual(before.slice(1));
  // Restoring is not opening.
  expect(opens(seen)).toHaveLength(0);
  expect(bodies).toHaveLength(0);
  await expectSub("menu");
  await expect(page.getByTestId("tetravox-frame")).toHaveCount(0);
});

test("the Recent list remembers what was opened and restores it", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  // Empty until something is actually opened — a footprint, not a draft.
  await expect(page.getByTestId("viewer-recent")).toBeDisabled();

  await draftSimulation();
  await pressOpen();
  await expectOpened();
  await gotoSub("menu");
  await expect(page.getByTestId("viewer-recent")).toBeEnabled();

  await chooseOption("kind", "Subject anatomy");
  await page.getByTestId("viewer-recent").click();
  await page.getByTestId("viewer-recent-0").click();
  await expect(page.getByTestId("viewer-select-simulation").getByRole("combobox")).toContainText("Thalamus");
});

// ── performance (VE, 2026-09-06) ─────────────────────────────────────────────────────────────
//
// Maintainer, on the live Menu: *"the menu acts way too slow — it looks like it does computation
// when I add or remove things; and sending it and launching into Tetravox is also very, very
// slow."* It did both, and the two causes were different:
//
//   * every list edit re-resolved through `POST /api/view/open?dry_run`, and that route reads
//     every volume in the scene to compute a percentile window (`tit/viewspec.py`);
//   * so did every Open, paying the same ~150 ms warm / ~860 ms cold before it could answer.
//
// Server-side that is a cache keyed on each file's identity (`tests/test_viewspec.py`). Client-side
// the edit no longer asks. These are the assertions that keep both true — budgets deliberately
// well above the measured numbers, so they catch a *reintroduced request*, not a slow CI box.

test("twenty list edits cost the server nothing and never block a frame", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  const before = await rowNames();
  expect(before.length, "need at least two rows to add and remove").toBeGreaterThan(1);

  // After the source has resolved. Choosing a source may ask once; editing may not ask at all.
  const seen = recordViewRequests();

  // Long tasks are the honest measure of "does it compute when I add or remove things": a handler
  // that only mutates an array yields inside a frame, one that resolves a scene does not.
  await page.evaluate(() => {
    const w = window as unknown as { __veLongTasks: number };
    w.__veLongTasks = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) w.__veLongTasks += entry.duration;
    }).observe({ entryTypes: ["longtask"] });
  });

  // A file from the "+ Add…" catalogue, so it can be put back. (A row the view type produced but
  // the catalogue does not offer — a simulation output — can be removed and only restored with
  // Reset; that is VM2's picker, unchanged here.)
  const target = "labeling.nii.gz";
  for (let i = 0; i < 10; i += 1) {
    await page.getByTestId("viewer-add").click();
    await page.getByTestId(`viewer-add-${target}`).click();
    await expect.poll(rowNames).toContain(target);
    await page.getByTestId(`viewer-file-remove-${target}`).click();
    await expect.poll(rowNames).not.toContain(target);
  }

  const longTasks = await page.evaluate(() => (window as unknown as { __veLongTasks: number }).__veLongTasks);
  // Zero requests is the assertion that matters — the long-task budget is the backstop for a
  // future edit path that does the work in the renderer instead of on the server.
  expect(seen, "a list edit went to the server").toHaveLength(0);
  expect(longTasks, `20 edits blocked the main thread for ${longTasks} ms`).toBeLessThan(50);
});

test("Open is one fast request, and the scene reaches the frame straight after it", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();

  const seen = recordViewRequests();
  const responsePromise = page.waitForResponse(
    (r) => r.url().includes("/api/view/open") && r.request().method() === "POST",
  );
  const t0 = Date.now();
  await pressOpen();
  await responsePromise;
  const responded = Date.now();

  await expectSub("viewer");
  await expect(page.getByTestId("tetravox-host")).toBeVisible();
  const shown = Date.now();

  const serverMs = responded - t0;
  const postMs = shown - responded;
  console.log(`viewer open timings: click->response ${serverMs} ms, response->scene on screen ${postMs} ms`);

  expect(opens(seen), "Open must be exactly one request").toHaveLength(1);
  expect(seen.filter((r) => r.dryRun), "Open must not re-resolve first").toHaveLength(0);
  expect(serverMs, `POST /api/view/open took ${serverMs} ms`).toBeLessThan(200);
  // Navigating to the Tetravox sub-page and posting the ViewSpec into the already-mounted iframe
  // is state and one postMessage. It must not wait on a re-fetch of the bundle or a remount.
  expect(postMs, `the scene took ${postMs} ms to reach the frame after the response`).toBeLessThan(1000);
});

// ── the first Open (VE, 2026-09-06) ──────────────────────────────────────────────────────────
//
// Reported: *"Open lands on Tetravox but the scene only appears after Reload."* The cause was in
// `viewer/store.ts` and is written up there: the frame is mounted only once there is something to
// show, so the first Open of a session calls `loadScene` while no channel exists and the scene can
// only be delivered by the `ready` handler — and `disconnect()`, which React runs as the mount
// effect's cleanup, used to null the pending scene out from under it. Reload "worked" only because
// it called `loadScene` again with a channel already open.
//
// **The defect is dev-only, and this spec cannot catch it.** React's StrictMode (`main.tsx`)
// double-invokes effects — mount, clean up, mount — in a DEVELOPMENT build and not in a production
// one, and Playwright runs the production bundle. So `disconnect()` never ran between the Open and
// the handshake here, and reintroducing the null leaves this test green (measured, not assumed).
// The maintainer runs `npm run dev`, which is why he hit it on every first Open and the suite
// never did.
//
// `tests/unit/viewer-store.test.ts` is therefore the test that pins the bug: it drives the
// mount/cleanup/mount sequence directly and fails red with the null restored. What this one is
// worth keeping for is the property, not the regression — a fresh app, one Open, one load message,
// a scene on screen, and no Reload clicked anywhere.

test("the first Open of a session draws the scene without a Reload", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();

  // Every `load` the page posts into the frame, counted at the source. `postMessage` is patched in
  // the page rather than observed through the embed, so a scene that is never sent is a zero here
  // instead of a timeout somewhere else.
  await page.evaluate(() => {
    const w = window as unknown as { __veLoads: number };
    w.__veLoads = 0;
    const proto = window.HTMLIFrameElement.prototype as unknown as { contentWindow: unknown };
    const original = Object.getOwnPropertyDescriptor(proto, "contentWindow")!.get!;
    Object.defineProperty(proto, "contentWindow", {
      get(this: HTMLIFrameElement) {
        const win = original.call(this) as Window | null;
        if (win === null || (win as unknown as { __vePatched?: boolean }).__vePatched) return win;
        const post = win.postMessage.bind(win);
        (win as unknown as { __vePatched: boolean }).__vePatched = true;
        win.postMessage = ((message: unknown, ...rest: unknown[]) => {
          if ((message as { type?: string } | null)?.type === "load") w.__veLoads += 1;
          return (post as (...a: unknown[]) => unknown)(message, ...rest);
        }) as typeof win.postMessage;
        return win;
      },
      configurable: true,
    });
  });

  await pressOpen();
  await expectSub("viewer");

  // The scene is on screen: the embed reached a state it can only reach by having been given one,
  // and the host is showing its layers. 2 s, and no Reload click anywhere in this test.
  await expect(page.getByTestId("tetravox-host")).toBeVisible({ timeout: 2_000 });
  await expect
    .poll(async () => page.getByTestId("tetravox-host").getAttribute("data-viewer-status"), { timeout: 2_000 })
    .not.toBe("idle");

  const afterFirst = await page.evaluate(() => (window as unknown as { __veLoads: number }).__veLoads);
  expect(afterFirst, `the first Open sent ${afterFirst} load messages`).toBe(1);

  // A second Open replaces it with exactly one more.
  await gotoSub("menu");
  const rows = await rowNames();
  await page.getByTestId(`viewer-file-remove-${rows[rows.length - 1]!}`).click();
  await expect.poll(rowNames).toHaveLength(rows.length - 1);
  await pressOpen();
  await expectSub("viewer");
  await expect
    .poll(async () => page.evaluate(() => (window as unknown as { __veLoads: number }).__veLoads), { timeout: 5_000 })
    .toBe(2);
});

// ── the rail group (VE, 2026-09-06) ──────────────────────────────────────────────────────────

test("only the active sub-item is highlighted, never the group row with it", async () => {
  // The sub-items exist only where the rail carries labels (>= 1440, `NavRail.tsx`).
  await page.setViewportSize({ width: 1440, height: 900 });
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const group = page.getByTestId("nav-item-viewer");
  const menu = page.getByTestId("nav-subitem-viewer-menu");
  if ((await menu.count()) === 0) test.skip(true, "the icon rail draws no sub-items below 1440");

  await expect(menu).toHaveAttribute("aria-current", "page");
  // The group is not the page — it is what the page is inside. Two lit rows for one screen is a
  // rail that cannot be read at a glance.
  await expect(group, "the group row is highlighted together with its sub-item").not.toHaveAttribute("aria-current", "page");
  await expect(group).toHaveAttribute("data-contains-active", "true");
});

test("the group collapses, remembers it, and its label still opens Menu", async () => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  const chevron = page.getByTestId("nav-chevron-viewer");
  if ((await chevron.count()) === 0) test.skip(true, "the icon rail draws no sub-items below 1440");
  const menu = page.getByTestId("nav-subitem-viewer-menu");

  await expect(chevron).toHaveAttribute("aria-expanded", "true");
  await expect(menu).toBeVisible();

  await chevron.click();
  await expect(chevron).toHaveAttribute("aria-expanded", "false");
  await expect(menu, "collapsing hid nothing").toBeHidden();
  // Collapsed, the chevron is what says the group can be opened again.
  await expect(chevron).toBeVisible();
  // The list it controls is named, so the state is announced rather than merely drawn.
  const controls = await chevron.getAttribute("aria-controls");
  expect(controls).toBe("nav-subitems-viewer");

  // The label is still a link to the group's first sub-item — collapsing is not disabling.
  await page.getByTestId("nav-item-viewer").click();
  await expectSub("menu");
  await expect(chevron, "navigating re-expanded the group").toHaveAttribute("aria-expanded", "false");

  // Remembered across a reload of the renderer.
  await page.reload();
  await expect(page.getByTestId("nav-chevron-viewer")).toHaveAttribute("aria-expanded", "false", { timeout: 20_000 });

  await page.getByTestId("nav-chevron-viewer").click();
  await expect(page.getByTestId("nav-subitem-viewer-menu")).toBeVisible();
});

// ── the menu's own latency (2026-09-07) ──────────────────────────────────────────────────────
//
// Maintainer, on the live Menu: *"there is still a lot of loading time once the user starts
// manipulating the input data"* — with a screenshot of the "what will open" card sitting on
// "Resolving…" after changing Field to TI_max.
//
// Two causes, both fixed, both asserted here. The server read every volume in the scene twice per
// resolve and cached the answer only in memory (`tests/test_viewspec_defaults.py`). The client
// asked on every keystroke, with no debounce and nothing to cancel a superseded request, and
// blanked the card to "Resolving…" while it waited — so a resolve that now takes ~10 ms still
// looked like a reload, because the list disappeared and came back.

test("changing Field keeps the previous list on screen instead of blanking to Resolving…", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();

  const before = await rowNames();
  expect(before.length, "need a resolved list to keep").toBeGreaterThan(0);

  // Watch the card for the whole field change. The defect was a *flash*: a poll after the fact
  // would miss it, so the observer records every state the card passes through.
  await page.evaluate(() => {
    const w = window as unknown as { __veBlanked: boolean };
    w.__veBlanked = false;
    const card = document.querySelector('[data-testid="viewer-plan"]');
    if (card === null) return;
    new MutationObserver(() => {
      const list = card.querySelector('[data-testid="viewer-preview-files"]');
      const rows = list?.querySelectorAll("li").length ?? 0;
      // "Resolving…" on screen, or a list that momentarily has no rows: both are the blank.
      if (card.querySelector('[data-testid="viewer-resolving"]') !== null || (list !== null && rows === 0)) {
        w.__veBlanked = true;
      }
    }).observe(card, { childList: true, subtree: true });
  });

  await chooseOption("field", "TI_normal");
  await expect.poll(rowNames).not.toEqual([]);
  // Give a superseded resolve room to land late and repaint, if one could.
  await page.waitForTimeout(500);

  const blanked = await page.evaluate(() => (window as unknown as { __veBlanked: boolean }).__veBlanked);
  expect(blanked, 'the card blanked to "Resolving…" while re-resolving a selection it already had rows for').toBe(false);
  expect((await rowNames()).length).toBeGreaterThan(0);
});

test("stepping through Field debounces into far fewer resolves than steps", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();

  const seen = recordViewRequests();
  // Four changes in quick succession — what walking a `<select>` with the arrow keys looks like.
  for (const field of ["TI_normal", "TI_max", "TI_normal", "TI_max"]) {
    await chooseOption("field", field);
  }
  await expect.poll(rowNames).not.toEqual([]);
  await page.waitForTimeout(600);

  const resolves = seen.filter((r) => r.dryRun);
  // Not "exactly one": the steps are real user interactions and some will outlast the 150 ms
  // window. The claim is that a debounce exists at all — without one this is four, every time.
  expect(resolves.length, `four field changes cost ${resolves.length} resolves`).toBeLessThan(4);
  expect(opens(seen), "drafting must still write nothing").toHaveLength(0);
});

test("the card names the window the overlay will open at, before anything opens", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();

  // The defaults were previously invisible until Tetravox had the scene, in another window.
  const summary = page.getByTestId("viewer-window-summary");
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("p95–p99.9");
  await expect(summary).toContainText("V/m");
});

// ── saving a scene (2026-09-07) ──────────────────────────────────────────────────────────────
//
// Maintainer: *"we should be integrating scene saving where users can essentially save scenes —
// not only the input selection but also the scene for the user — and we should be very opinionated
// about that and save it in the Tetravox [scene format]."*
//
// What makes this a *scene* rather than a second copy of the selection is that the document comes
// from the embed's own `serialize` — the camera someone flew to and the window they widened, not
// the document the server built. The fake embed echoes the scene it was loaded with, so the
// round-trip is observable here; the real engine's version is the same message.

test("Save scene writes a .tetravox.json, and it comes back in the list", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  await pressOpen();
  await expectOpened();

  // Only once the embed has something to serialize.
  const save = page.getByTestId("viewer-scene-save-open");
  await expect(save).toBeEnabled({ timeout: 15_000 });
  await save.click();

  // The name is pre-filled by the server, so the common case is press-and-done.
  const nameField = page.getByTestId("viewer-scene-name");
  await expect(nameField).toHaveValue(/ernie/, { timeout: 10_000 });
  const name = await nameField.inputValue();
  expect(name, "the default name says what the scene is of").toContain("Thalamus");

  await page.getByTestId("viewer-scene-save").click();
  await expect(page.getByTestId("viewer-scene-saved")).toContainText(".tetravox.json", { timeout: 15_000 });

  // And it is listed back in the Menu, ready to reopen.
  await gotoSub("menu");
  const list = page.getByTestId("viewer-saved-scenes-open");
  await expect(list).toBeEnabled({ timeout: 10_000 });
  await list.click();
  await expect(page.getByTestId("viewer-saved-scenes").getByRole("button")).toHaveCount(1);
  await expect(page.getByTestId("viewer-saved-scenes")).toContainText(name);
});

test("reopening a saved scene puts it back in the same frame", async () => {
  await connect();
  await chooseSubject("ernie");
  await openViewer();
  await draftSimulation();
  await pressOpen();
  await expectOpened();
  await page.getByTestId("viewer-scene-save-open").click();
  await expect(page.getByTestId("viewer-scene-name")).toHaveValue(/ernie/, { timeout: 10_000 });
  const name = await page.getByTestId("viewer-scene-name").inputValue();
  await page.getByTestId("viewer-scene-save").click();
  await expect(page.getByTestId("viewer-scene-saved")).toBeVisible({ timeout: 15_000 });

  await gotoSub("menu");
  await page.getByTestId("viewer-saved-scenes-open").click();
  const slug = name.replace(/ /g, "_");
  const seen = recordViewRequests();
  await page.getByTestId(`viewer-saved-scene-${slug}`).click();

  // Reopening a saved scene is a read of a document that already exists — it must not re-resolve
  // the selection, because the whole point of having saved it is that it is not derived any more.
  await expectSub("viewer");
  await expect(page.getByTestId("viewer-strip-name")).toHaveText(`${slug}.tetravox.json`);
  await expect(page.getByTestId("tetravox-host")).toBeVisible();
  expect(opens(seen), "reopening a saved scene must write no new scene").toHaveLength(0);
  expect(seen.filter((r) => r.dryRun), "reopening a saved scene must not re-resolve").toHaveLength(0);
});
