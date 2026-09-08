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

/**
 * Compose a scene the way the Menu asks for one: expand a simulation's branch, tick a field row.
 *
 * The `Type`/`Simulation` dropdowns this replaces are gone — the tree has no view type (see
 * `pages/viewer/Tree.tsx`). Ticking a *field* row is also what moves the draft, so the window chip
 * and the scene's per-layer defaults describe the layer that was chosen.
 */
async function composeSimulationField(
  target: Page,
  simulation: string,
  fileName: string,
  alsoTick: string[] = [],
): Promise<void> {
  await expect(target.getByTestId("viewer-tree")).toBeVisible({ timeout: 30_000 });
  for (const extra of alsoTick) {
    const box = target.getByTestId(`viewer-tree-node-${extra}`).getByRole("checkbox");
    await expect(box).toBeVisible({ timeout: 30_000 });
    if ((await box.getAttribute("data-state")) !== "checked") await box.click();
  }
  const branch = target.getByTestId(`viewer-tree-sim-${simulation}`);
  await expect(branch).toBeVisible({ timeout: 30_000 });
  if ((await branch.getAttribute("data-open")) !== "true") {
    await target.getByTestId(`viewer-tree-sim-${simulation}-toggle`).click();
  }
  const box = target.getByTestId(`viewer-tree-node-${fileName}`).getByRole("checkbox");
  await expect(box).toBeVisible({ timeout: 30_000 });
  if ((await box.getAttribute("data-state")) !== "checked") await box.click();
  await expect(target.getByTestId("viewer-plan")).not.toHaveAttribute("data-resolving", "true", { timeout: 30_000 });
}

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

  // The Menu is a tree now (2026-09-07): expand the simulation, tick its grey-matter field.
  await composeSimulationField(page, "Thalamus", "grey_Thalamus_TI_subject_TI_max.nii.gz");

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

/**
 * The defaults a scene actually opens at, on real volumes (2026-09-07).
 *
 * The maintainer's complaint was about numbers — "very strange defaults ... 5.078e-09 ... it would
 * be much more reasonable to set more logical thresholds, for example 95 to 99.9 of the electric
 * field", and panes so zoomed out "the head is a small square". Only real NIfTIs can prove this:
 * every number below is derived from `sub-101/L_Insula`'s own voxels, and the mock has none.
 *
 * The assertion is made against the scene document the app posted into the embed, cross-checked
 * against the statistics sidecar the server wrote for those same files. That is the strongest
 * check available from out here: the embed is a bare viewport in this presentation (`EMBED.md`
 * §"the viewport retains ... shell shortcuts are inactive"), so it exposes no layer panel to read
 * values off, and the page does not offer `serialize`. What can be proved is that the engine was
 * handed these exact values and answered `ready` rather than rejecting them — plus a screenshot,
 * which is what the complaint was made from in the first place.
 */
test("sub-101/L_Insula opens windowed p95–p99.9, fitted, and crosshaired on the field peak", async () => {
  await selectSubject(page, "101");
  await gotoPage(page, "viewer", "Viewer");
  await expectPage(page, "viewer");
  // Chosen in the Viewer's **own** picker, not only the shell's. Both subjects in this project
  // have an `L_Insula`, so a subject that did not actually change leaves every locator below
  // matching — against the wrong subject's files, which is how this test first passed while
  // measuring ernie.
  await page.getByTestId("viewer-select-subject").getByRole("combobox").click();
  await page.getByRole("option", { name: "101", exact: true }).click();
  await expect(page.getByTestId("viewer-select-subject")).toContainText("101");
  // Start from this subject's own set. A list carried over from the previous test would otherwise
  // compose a scene spanning two subjects — see the assertion on that below, which is the thing
  // that caught it.
  const reset = page.getByTestId("viewer-files-reset");
  if ((await reset.count()) > 0) await reset.click();
  await expect(page.getByTestId("viewer-plan")).not.toHaveAttribute("data-resolving", "true", { timeout: 30_000 });

  await composeSimulationField(page, "L_Insula", "grey_L_Insula_TI_subject_TI_max.nii.gz", ["T1.nii.gz"]);

  // The card says the window before anything opens — the whole point of showing it.
  const summary = page.getByTestId("viewer-window-summary");
  await expect(summary).toBeVisible({ timeout: 30_000 });
  await expect(summary).toContainText("p95–p99.9");
  // The card keeps the previous selection's numbers while the next one resolves, greyed — so the
  // chip is only comparable to what Open returns once the page says it has stopped resolving.
  // Without this the two disagree by exactly one selection, which is the feature working.
  await expect(page.getByTestId("viewer-plan")).not.toHaveAttribute("data-resolving", "true", { timeout: 30_000 });
  // Read the chip **before** Open. It describes the composition on screen; pressing Open navigates
  // to the Tetravox sub-page, and reading it afterwards reads a card that is no longer the subject
  // of the assertion.
  const shownBeforeOpen = (await summary.textContent()) ?? "";

  const opened = page.waitForResponse(
    (r) => r.url().includes("/api/view/open") && r.request().method() === "POST" && r.status() === 200,
  );
  await page.getByTestId("viewer-open").click();
  const body = (await (await opened).json()) as {
    view: {
      layers: { id: string; kind: string; visible: boolean; colormap?: string; scale?: Record<string, number | string>; threshold?: Record<string, unknown> }[];
      slices: { camera: { mmPerPx: number } }[];
      view3d: { camera: { target: number[]; distance: number } };
      cursor: number[];
    };
  };
  const view = body.view;

  // ── the field overlay ──────────────────────────────────────────────────────────────────────
  // The **visible** heat layer, which is the same one `lib.ts::windowSummary` describes. A
  // simulation scene also carries the whole-head and WM copies of the field as hidden layers, and
  // asserting on one of those would compare the chip against a window nobody is looking at.
  const field = view.layers.find((l) => l.kind === "volume" && l.visible && l.scale?.kind === "heat");
  expect(field, "the simulation scene must carry a visible heat field layer").toBeDefined();
  // Every field layer, visible or not, gets the same rule — that is the rule, not a special case.
  for (const heat of view.layers.filter((l) => l.kind === "volume" && l.scale?.kind === "heat")) {
    expect(heat.threshold!.lo, `${heat.id} floors at its own p95`).toBeCloseTo(heat.scale!.min as number, 9);
    expect(heat.threshold!.mode).toBe("hide");
    expect(heat.scale!.min as number, `${heat.id} does not open at "every non-zero voxel"`).toBeGreaterThan(1e-4);
  }
  const min = field!.scale!.min as number;
  const max = field!.scale!.max as number;

  // The defect, pinned: the window used to open at the smallest non-zero voxel, 5.08e-09 V/m.
  expect(min).toBeGreaterThan(1e-4);
  expect(max).toBeGreaterThan(min);
  expect(field!.threshold!.lo).toBeCloseTo(min, 9);
  expect(field!.threshold!.hi, "an open top — null reads back as +Infinity").toBeNull();
  expect(field!.threshold!.mode, "clamp would paint the sub-threshold voxels rather than hide them").toBe("hide");

  // Cross-check: the number the Menu showed a person and the number the engine was handed are the
  // same number, reached by different code (`lib.ts::windowSummary` off the resolved scene, and
  // the scene itself). Three significant figures, which is what the chip prints.
  // The numbers the Menu showed are a real layer's window in the scene it opened — the two are
  // reached by different code (`lib.ts::windowSummary` off the preview, and the scene itself) and
  // must agree. Matched against *any* heat layer rather than the first visible one: which layer is
  // visible depends on what was composed, and this is a claim about the numbers, not the order.
  const heatWindows = view.layers
    .filter((l) => l.scale?.kind === "heat")
    .map((l) => [Number((l.scale!.min as number).toPrecision(3)).toString(), Number((l.scale!.max as number).toPrecision(3)).toString()]);
  expect(heatWindows.length).toBeGreaterThan(0);
  expect(
    heatWindows.some(([lo, hi]) => shownBeforeOpen.includes(lo) && shownBeforeOpen.includes(hi)),
    `the Menu showed "${shownBeforeOpen}", which is no layer's window in ${JSON.stringify(heatWindows)}`,
  ).toBe(true);

  // ── one subject per scene ──────────────────────────────────────────────────────────────────
  // Every dataset comes from the subject that was chosen. A scene that quietly spans two subjects
  // overlays one person's field on another's anatomy, which is wrong in a way no reader can see.
  const paths = (body.view as unknown as { datasets: { path: string }[] }).datasets.map((d) => d.path);
  for (const path of paths) {
    if (path.includes("/derivatives/SimNIBS/sub-")) {
      expect(path, `a dataset from another subject: ${path}`).toContain("sub-101");
    }
  }

  // ── the anatomy ────────────────────────────────────────────────────────────────────────────
  // By name, which the naming rule above makes exact: every layer is its file's basename, so
  // "the T1" is `T1.nii.gz` and not "whichever grey linear volume came first".
  const t1 = view.layers.find((l) => (l as unknown as { name: string }).name === "T1.nii.gz");
  expect(t1, "the scene must carry a T1 base layer").toBeDefined();
  // p2–p98, not min–max: sub-101's T1 maxes at 3238 on a few scalp-fat voxels.
  expect(t1!.scale!.hi as number).toBeLessThan(3000);
  expect(t1!.scale!.lo as number).toBeGreaterThanOrEqual(0);

  // ── sizing ─────────────────────────────────────────────────────────────────────────────────
  // Fitted to the head, not the engine's fixed 0.5 mm/px. A ~190 mm head across a 512 px pane is
  // a shade under 0.5; the assertion that matters is that all three panes carry the *same*,
  // data-derived number rather than the constant 0.6 this module used to emit.
  const mmPerPx = view.slices.map((s) => s.camera.mmPerPx);
  expect(new Set(mmPerPx).size, "every 2D pane fits the same scene").toBe(1);
  expect(mmPerPx[0]).toBeGreaterThan(0.05);
  expect(mmPerPx[0]).not.toBeCloseTo(0.6, 6);
  // A head fills a 512 px pane at roughly 0.4–0.6 mm/px; anything outside that is not a head.
  expect(mmPerPx[0]).toBeGreaterThan(0.2);
  expect(mmPerPx[0]).toBeLessThan(1.0);

  // The 3D camera frames the head rather than sitting at a fixed 350 mm from the world origin.
  expect(view.view3d.camera.target.some((c) => Math.abs(c) > 1e-6), "the 3D camera targets the data").toBe(true);
  expect(view.view3d.camera.distance).not.toBeCloseTo(350, 6);

  // ── location ───────────────────────────────────────────────────────────────────────────────
  // The crosshair is on the field's peak. World (0,0,0) is the scanner origin, which for a
  // subject-space head volume is off in a corner of the field of view.
  expect(view.cursor.some((c) => Math.abs(c) > 1e-6), "the crosshair must not sit at world zero").toBe(true);

  // ── every layer is named by its file ───────────────────────────────────────────────────────
  // Maintainer, on the Tetravox LAYERS panel: *"Please do not change the name of the files that we
  // load into the viewer. For example, `labeling.nii.gz` should be `labeling.nii.gz` and not
  // [Atlas]."* Asserted against the **real** scene because it is the real panel that showed the
  // curated names, and because only a real resolve produces the mesh and electrode layers whose
  // labels (`Head mesh · magnE · pair 2`) were the worst of them.
  const datasets = new Map((body.view as unknown as { datasets: { id: string; name: string; path: string }[] }).datasets.map((d) => [d.id, d]));
  for (const layer of view.layers) {
    const dataset = datasets.get((layer as unknown as { datasetId: string }).datasetId)!;
    const basename = decodeURIComponent(dataset.path.split("/").pop() ?? "");
    expect((layer as unknown as { name: string }).name, `layer ${layer.id} is not named by its file`).toBe(basename);
    expect(dataset.name).toBe(basename);
  }

  // ── and the engine accepted all of it ──────────────────────────────────────────────────────
  const host = page.getByTestId("tetravox-host");
  await expect(host).toHaveAttribute("data-viewer-status", "ready", { timeout: 60_000 });
  await expect(page.getByTestId("viewer-error")).toHaveCount(0);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(2_000); // let the engine redraw at the new size
  await page.screenshot({ path: process.env.TIT_E2E_SHOT ?? "test-results/viewer-defaults-after.png" });

  console.log(
    `sub-101/L_Insula defaults: window [${min}, ${max}] V/m · threshold.lo ${field!.threshold!.lo} ` +
      `· mmPerPx ${mmPerPx[0]} · cursor [${view.cursor.map((c) => c.toFixed(1)).join(", ")}]`,
  );
});

/**
 * A surface, with its parcellation on it — against the real embed (2026-09-07).
 *
 * Maintainer, on the Menu chipping `lh.central`, `lh.pial` and `lh.white` as MESH beside the true
 * `Head mesh (ernie)`: *"Please distinguish between NIfTI, mesh, and a surface — a mesh is a
 * tetrahedral FEM, a surface is just a triangular 2-D surface. Refer to the latest Tetravox
 * release."* Tetravox 0.4.0 (protocol 3) makes a surface its own layer kind with `.annot`, morph
 * and data-GIfTI attachments; this is the first scene TI-Toolbox emits one for.
 *
 * **Why this cannot be a mock test.** Everything on this path fails *successfully*. A surface sent
 * as a mesh loads — it is a triangle-only mesh and the engine takes it. A sidecar the embed cannot
 * fetch is skipped, and `loaded` still arrives: the geometry is there, nothing errors, and the
 * surface is simply solid-coloured with the parcellation missing. The only thing that tells the
 * two apart from the outside is `colorMode` on the engine's own `layers` event, and only a real
 * engine emits one. `ernie` has real `lh.central.gii` and real `lh.*.annot` files; both are read.
 */
test("a surface opens as a surface, coloured by the parcellation attached to it", async () => {
  await selectSubject(page, "ernie");
  await gotoPage(page, "viewer", "Viewer");
  await expectPage(page, "viewer");
  await expect(page.getByTestId("viewer-tree")).toBeVisible({ timeout: 30_000 });
  // Wait for the plan to be **this** subject's before ticking anything. The card keeps the
  // previous selection's rows while the next one resolves (greyed), and a tick composes onto the
  // rows on screen — so ticking early would build a scene half from the previous test's `sub-101`.
  // The first run of this test did exactly that and was caught by the server's 422 rather than by
  // a wrong picture, which is the guard doing its job; this is the sequencing that avoids it.
  await expect(page.getByTestId("viewer-plan")).not.toHaveAttribute("data-resolving", "true", { timeout: 30_000 });
  // Re-pick the subject in the page's *own* selector, not only the shell's: that is the edit
  // which clears `simulation`/`analysis`/`field`, so the baseline underneath the ticks is ernie's
  // anatomy rather than the previous test's simulation scene.
  await page.getByTestId("viewer-select-subject").getByRole("combobox").click();
  await page.getByRole("option", { name: "ernie", exact: true }).click();
  await expect(page.getByTestId("viewer-plan")).not.toHaveAttribute("data-resolving", "true", { timeout: 30_000 });

  // The chip is the classification, read back off the real m2m directory: exactly one MESH in
  // this branch, and the sheets are not it.
  await expect(page.getByTestId("viewer-tree-chip-ernie.msh")).toHaveText("MESH");
  await expect(page.getByTestId("viewer-tree-chip-lh.central.gii")).toHaveText("SURFACE");

  // The parcellation is offered *under* the surface, from `segmentation/` — a directory away from
  // the geometry, which is why nothing had ever offered it.
  // ernie has three left sheets (`central`, `pial`, `white`) and they share a vertex numbering, so
  // the same three parcellations are offered under each — the row is named by the surface it
  // hangs under, not by the file alone.
  const annot = page.getByTestId("viewer-tree-attachment-lh.central.gii-lh.ernie_DK40.annot");
  await expect(annot).toBeVisible({ timeout: 30_000 });
  await expect(annot).toHaveAttribute("data-depth", "1");

  for (const id of [
    "viewer-tree-node-T1.nii.gz",
    "viewer-tree-node-lh.central.gii",
    "viewer-tree-attachment-lh.central.gii-lh.ernie_DK40.annot",
  ]) {
    const box = page.getByTestId(id).getByRole("checkbox");
    await expect(box).toBeEnabled({ timeout: 30_000 });
    if ((await box.getAttribute("data-state")) !== "checked") await box.click();
  }
  await expect(page.getByTestId("viewer-plan")).not.toHaveAttribute("data-resolving", "true", { timeout: 30_000 });

  // Both are rows of the composition — the list is what a person chose, and unticking the
  // parcellation there has to work. What the attachment is *not* is a dataset: the assertions on
  // the wire below are where that shows.
  await expect(page.getByTestId("viewer-file-lh.central.gii")).toHaveCount(1);
  await expect(page.getByTestId("viewer-file-lh.ernie_DK40.annot")).toHaveCount(1);

  const openButton = page.getByTestId("viewer-open");
  await expect(openButton).toBeEnabled({ timeout: 30_000 });
  // Not filtered to 200: a refusal is a result this test must be able to report, and a predicate
  // that only matches success turns one into a bare timeout that says nothing about why.
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/view/open") && r.request().method() === "POST" && !r.url().includes("dry_run"), { timeout: 60_000 }),
    openButton.click(),
  ]);
  expect(response.status(), await response.text()).toBe(200);
  const body = await response.json();

  // What went on the wire: a surface dataset carrying its sidecar by a path relative to its own
  // directory, and a layer whose colour source is the annotation.
  const view = body.view as {
    datasets: { name: string; kind: string; sidecars?: { fields?: { path: string }[] } }[];
    layers: { name: string; kind: string; colorMode?: string; annotation?: { name: string } }[];
  };
  // Exactly one dataset for the sheet, and **none** for the parcellation: an attachment has no
  // geometry, so it is not a dataset at all.
  expect(view.datasets.filter((d) => d.name === "lh.central.gii")).toHaveLength(1);
  expect(view.datasets.filter((d) => d.name.endsWith(".annot"))).toEqual([]);
  expect(view.datasets.filter((d) => d.kind === "surface").map((d) => d.name)).toEqual(["lh.central.gii"]);
  const dataset = view.datasets.find((d) => d.name === "lh.central.gii")!;
  expect(dataset.kind).toBe("surface");
  expect(dataset.sidecars?.fields).toEqual([{ path: "../segmentation/lh.ernie_DK40.annot" }]);
  const layer = view.layers.find((l) => l.name === "lh.central.gii")!;
  expect(layer.kind).toBe("surface");
  expect(layer.colorMode).toBe("annotation");
  // The **file name**, extension and all — the embed names the node field after the file it
  // attached, and a stem or a role word matches nothing on the dataset.
  expect(layer.annotation?.name).toBe("lh.ernie_DK40.annot");
  // The sheet is never smuggled through as the FEM domain: no `.gii` is ever a mesh layer.
  expect(view.layers.filter((l) => l.kind === "mesh" && l.name.endsWith(".gii"))).toEqual([]);
  expect(view.layers.filter((l) => l.kind === "surface").map((l) => l.name)).toEqual(["lh.central.gii"]);

  const host = page.getByTestId("tetravox-host");
  await expect(host).toHaveAttribute("data-viewer-status", "ready", { timeout: 60_000 });
  await expect(page.getByTestId("viewer-error")).toHaveCount(0);

  // And what the **engine** says it drew. This is the assertion the rest of the test exists for:
  // a 404'd sidecar would leave everything above true and this line reading `surface:solid`.
  await expect(host).toHaveAttribute("data-viewer-layer-kinds", /surface:annotation/, { timeout: 60_000 });
});
