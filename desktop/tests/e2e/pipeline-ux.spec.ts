/**
 * The Pipeline canvas, driven the way a person drives it.
 *
 * `pipeline.spec.ts` is the D6 *contract* gate: it asserts, over the API, that a four-node graph
 * validates, runs as one group whose `after` chain is the edges, and exports. It deliberately does
 * not touch the canvas, on the grounds that "dragging a React Flow handle is a mouse gesture whose
 * reliability says nothing about whether the pipeline is right".
 *
 * That was true and it left a hole, and the maintainer fell into it: every element on the page
 * could be broken — the palette unstyled, Save silently dead, Delete a no-op, an edge impossible
 * to select — with the whole contract suite green. So this file is the other half. Every test
 * here is a gesture: click, drag, wire, delete, undo, type, save. Offscreen like every spec here.
 */
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;
let scratch: string;

test.beforeAll(async () => {
  scratch = mkdtempSync(join(tmpdir(), "tit-e2e-pipeux-"));
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-pipeux-ud-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
});

test.afterAll(async () => {
  await app?.close();
  rmSync(scratch, { recursive: true, force: true });
});

/** A clean canvas for each test: the page is retained across navigation, so it must be emptied. */
async function freshCanvas() {
  // A dialog left open by the previous test is modal, and its overlay swallows the click on the
  // nav link — which reads as "the Pipeline link does not work" 30 s later. Close it first.
  if (await page.getByRole("dialog").isVisible().catch(() => false)) {
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  await page.getByRole("link", { name: "Pipeline", exact: true }).click();
  await expect(page.getByTestId("pipeline-canvas")).toBeVisible();
  // Select everything and delete it, which is itself the ⌘A + Delete path. The shortcut is a
  // window-level handler, so nothing has to be clicked first — and a positioned click on the
  // canvas is the thing not to do: Playwright scrolls the element into view before it clicks, and
  // the fixed offset then lands on whatever the scroll brought under it (measured: the right
  // pane's job console).
  const cards = page.locator("[data-testid^='pipeline-node-']");
  // Clearing a five-node graph can take more than one ⌘A/Delete round: React Flow applies the
  // selection and the removal in separate commits, so a node added last can miss the first pass.
  for (let attempt = 0; attempt < 4 && (await cards.count()) > 0; attempt++) {
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.press("Delete");
  }
  await expect(cards).toHaveCount(0);
  await expect(page.getByTestId("pipeline-empty")).toBeVisible();
}

/** The centre of an element, in page coordinates. */
async function centre(testId: string) {
  const box = await page.getByTestId(testId).boundingBox();
  if (!box) throw new Error(`no box for ${testId}`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Drag one port handle onto another the way a mouse does — React Flow listens to nothing else. */
async function wire(from: string, to: string) {
  const a = await centre(from);
  const b = await centre(to);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 8 });
  await page.mouse.move(b.x, b.y, { steps: 8 });
  await page.mouse.up();
}

// ---------------------------------------------------------------- adding, moving, deleting ----

test("the empty canvas offers one line and a sample pipeline that actually validates", async () => {
  await freshCanvas();
  await expect(page.getByTestId("pipeline-empty")).toContainText("Add a step or import a pipeline");
  await page.getByTestId("pipeline-sample").click();
  for (const id of ["pre1", "flex1", "sim1", "an1"]) {
    await expect(page.getByTestId(`pipeline-node-${id}`)).toBeVisible();
  }
  // The point of a sample is that it is a pipeline that runs, not four unconfigured cards.
  await expect(page.getByTestId("pipeline-receipt")).toContainText("in one group");
  await expect(page.getByTestId("pipeline-run")).toBeEnabled();
});

test("a palette click adds a card, and a palette drag drops one where it was dropped", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-pre").click();
  await expect(page.getByTestId("pipeline-node-pre1")).toBeVisible();

  // Drag-to-canvas. Playwright's dragTo drives the real HTML5 drag events the page listens for.
  await page.getByTestId("pipeline-add-sim").dragTo(page.getByTestId("pipeline-canvas"), {
    targetPosition: { x: 480, y: 260 },
  });
  await expect(page.getByTestId("pipeline-node-sim1")).toBeVisible();

  const dropped = await page.getByTestId("pipeline-node-sim1").boundingBox();
  const clicked = await page.getByTestId("pipeline-node-pre1").boundingBox();
  // It landed where it was dropped, not on top of the first card.
  expect(Math.abs(dropped!.x - clicked!.x) + Math.abs(dropped!.y - clicked!.y)).toBeGreaterThan(40);
});

test("a card can be dragged, and where it is put is what gets saved", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-pre").click();
  const before = (await page.getByTestId("pipeline-node-pre1").boundingBox())!;
  await page.mouse.move(before.x + 60, before.y + 12);
  await page.mouse.down();
  await page.mouse.move(before.x + 220, before.y + 140, { steps: 10 });
  await page.mouse.up();
  const after = (await page.getByTestId("pipeline-node-pre1").boundingBox())!;
  expect(after.x).toBeGreaterThan(before.x + 80);

  // And the *document* moved with it — undo puts it back, which it could not do if the drag had
  // only moved React Flow's own copy.
  await page.getByTestId("pipeline-undo").click();
  const undone = (await page.getByTestId("pipeline-node-pre1").boundingBox())!;
  expect(Math.abs(undone.x - before.x)).toBeLessThan(24);
});

test("a step is deleted by the toolbar button, by the context menu and by the Delete key", async () => {
  await freshCanvas();

  // 1. the toolbar's trash button
  await page.getByTestId("pipeline-add-pre").click();
  await page.getByTestId("pipeline-node-pre1").click();
  await page.getByTestId("pipeline-delete").click();
  await expect(page.getByTestId("pipeline-node-pre1")).toHaveCount(0);

  // 2. right-click ▸ Delete step
  await page.getByTestId("pipeline-add-pre").click();
  await page.getByTestId("pipeline-node-pre1").click({ button: "right" });
  await expect(page.getByTestId("pipeline-menu")).toBeVisible();
  await page.getByTestId("pipeline-menu-delete").click();
  await expect(page.getByTestId("pipeline-node-pre1")).toHaveCount(0);

  // 3. select and press Delete — the path that used to remove the card for one frame and then
  //    put it straight back, because `onNodesDelete` never reached the document.
  await page.getByTestId("pipeline-add-pre").click();
  await page.getByTestId("pipeline-node-pre1").click();
  await page.keyboard.press("Delete");
  await expect(page.getByTestId("pipeline-node-pre1")).toHaveCount(0);
});

// ------------------------------------------------------------------------------- wiring -------

test("a legal wire connects, and the receipt turns into the plan it makes", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-pre").click();
  await page.getByTestId("pipeline-add-sim").dragTo(page.getByTestId("pipeline-canvas"), {
    targetPosition: { x: 520, y: 240 },
  });
  await expect(page.getByTestId("pipeline-node-sim1")).toBeVisible();

  // The Simulator has no subjects of its own, so it says so on its own card.
  await expect(page.getByTestId("pipeline-need-sim1-subjects")).toBeVisible();

  await wire("pipeline-out-pre1-subjects", "pipeline-in-sim1-subjects");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  // Wiring the port clears the chip — the whole point of the chip.
  await expect(page.getByTestId("pipeline-need-sim1-subjects")).toHaveCount(0);
});

test("an illegal wire is refused with its reason, and no edge appears", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-pre").click();
  await page.getByTestId("pipeline-add-sim").dragTo(page.getByTestId("pipeline-canvas"), {
    targetPosition: { x: 520, y: 240 },
  });
  await wire("pipeline-out-pre1-subjects", "pipeline-in-sim1-subjects");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);

  // The same wire a second time: Subjects is already bound, and the canvas has to say so.
  await wire("pipeline-out-pre1-subjects", "pipeline-in-sim1-subjects");
  await expect(page.getByTestId("pipeline-refusal")).toContainText("already wired");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
});

test("a wire can be selected and deleted", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-pre").click();
  await page.getByTestId("pipeline-add-sim").dragTo(page.getByTestId("pipeline-canvas"), {
    targetPosition: { x: 520, y: 240 },
  });
  await wire("pipeline-out-pre1-subjects", "pipeline-in-sim1-subjects");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);

  // Right-click the wire ▸ Delete wire. (Selecting an edge at all was impossible before
  // `onEdgesChange` existed, which is what made the Delete key a no-op on one.)
  await page.locator(".react-flow__edge-interaction").first().click({ button: "right", force: true });
  await expect(page.getByTestId("pipeline-menu")).toBeVisible();
  await page.getByTestId("pipeline-menu-delete").click();
  await expect(page.locator(".react-flow__edge")).toHaveCount(0);
  await expect(page.getByTestId("pipeline-need-sim1-subjects")).toBeVisible();
});

// ------------------------------------------------------------------------------ the editor ----

test("double-click opens the step's own form — the real one, not a placeholder", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-pre").click();
  await page.getByTestId("pipeline-node-pre1").dblclick();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // Pre-processing's real stage switches, from the page's own list — and no Subjects field, since
  // the cohort belongs to the cohort node and reaches this one over the wire.
  await expect(dialog.getByLabel("SimNIBS head model (charm)")).toBeVisible();
  await expect(dialog.getByLabel("Subjects", { exact: true })).toHaveCount(0);
  await dialog.getByLabel("Tissue analysis").click();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("pipeline-node-pre1")).toBeVisible();
});

test("a JSON-edited kind opens, refuses bad JSON out loud, and saves good JSON", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-leadfield").click();
  await page.getByTestId("pipeline-node-leadfield1").dblclick();
  const json = page.getByTestId("pipeline-json");
  await expect(json).toBeVisible();

  await json.fill("{ not json");
  await expect(page.getByRole("dialog")).toContainText("Not valid JSON");

  await json.fill('{"subject_ids": ["ernie"], "eeg_net": "GSN-HydroCel-185.csv"}');
  await expect(page.getByRole("dialog")).not.toContainText("Not valid JSON");
  await page.keyboard.press("Escape");
  // The card counts the subjects it was handed; only the cohort node prints their ids.
  await expect(page.getByTestId("pipeline-node-leadfield1")).toContainText("1 subject");
});

test("a 'needs: subjects' chip on a node with no cohort opens its editor", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-sim").click();
  // The chip is the server's `missing_input` finding: this Simulator has no cohort wired to it,
  // and under this model there is no field on the Simulator that could supply one — so the chip
  // opens the node and the fix is to wire a Subjects node to it.
  await page.getByTestId("pipeline-need-sim1-subjects").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
});

test("the receipt's Fix link focuses the step it is about", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-sim").click();
  await expect(page.getByTestId("pipeline-problem-sim1")).toBeVisible();
  await page.getByTestId("pipeline-fix-sim1").click();
  await expect(page.locator(".react-flow__node.selected")).toHaveCount(1);
});

// ------------------------------------------------------- the receipt, and what it refuses ------

test("unconnected steps are one sentence, not a wall of warnings", async () => {
  await freshCanvas();
  // Three independent cohorts, each with a subject: a legal pipeline with nothing wrong with it.
  for (let i = 0; i < 3; i++) {
    await page.getByTestId("pipeline-add-subjects").click();
    await page.getByTestId(`pipeline-node-subjects${i + 1}`).dblclick();
    await page.getByTestId("pipeline-subjects").getByRole("row", { name: /^ernie\b/ }).click();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  const receipt = page.getByTestId("pipeline-receipt");
  await expect(receipt).toContainText("in one group");
  await expect(page.getByTestId("pipeline-notes")).toContainText("3 steps run independently");
  // The old page printed this sentence once per node, as a warning, next to the real errors.
  await expect(receipt).not.toContainText("will run on its own");
  await expect(page.getByTestId("pipeline-run")).toBeEnabled();
});

test("Run is disabled with the reason on it while a required input is unbound", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-analyzer").click();
  const run = page.getByTestId("pipeline-run");
  await expect(run).toBeDisabled();
  await expect(run).toHaveAttribute("title", /problem/);
  await expect(page.getByTestId("pipeline-problem-analyzer1")).toContainText("needs subjects");
});

// ------------------------------------------------------------------- save, load, import, export

test("Save names the pipeline in a dialog and it appears in Saved with its size", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-sample").click();
  await page.getByTestId("pipeline-save").click();
  // `window.prompt` is not implemented in Electron, so the old Save was silently a no-op here.
  await page.getByTestId("pipeline-save-name").fill("ux gate");
  await page.getByTestId("pipeline-save-confirm").click();
  const entry = page.getByTestId("pipeline-saved-ux gate");
  await expect(entry).toBeVisible();
  await expect(entry).toContainText("5 steps");

  // And it loads back.
  await freshCanvas();
  await page.getByTestId("pipeline-saved-ux gate").click();
  await expect(page.getByTestId("pipeline-node-an1")).toBeVisible();
});

test("Import JSON… reads a document off disk", async () => {
  await freshCanvas();
  const file = join(scratch, "imported.json");
  writeFileSync(
    file,
    JSON.stringify({
      version: 1,
      name: "imported",
      nodes: [
        { id: "sub1", kind: "subjects", config: { subject_ids: ["ernie"] }, position: { x: 40, y: 40 } },
        { id: "pre1", kind: "pre", config: { create_m2m: true }, position: { x: 300, y: 40 } },
      ],
      edges: [{ from: "sub1", to: "pre1", port: "subjects" }],
    }),
  );
  await page.getByTestId("pipeline-import-input").setInputFiles(file);
  await expect(page.getByTestId("pipeline-node-sub1")).toBeVisible();
  await expect(page.getByTestId("pipeline-node-sub1")).toContainText("ernie");
  await expect(page.getByTestId("pipeline-node-pre1")).toContainText("1 subject");
});

test("Export notebook writes a real .ipynb through the Electron save dialog", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-sample").click();

  // Stub the *main process* dialog, so the bridge, the IPC handler and the file write are all
  // real — only the modal the OS would draw is replaced.
  const target = join(scratch, "exported.ipynb");
  await app.evaluate(({ dialog }, path) => {
    (dialog as unknown as { showSaveDialog: unknown }).showSaveDialog = async () => ({ canceled: false, filePath: path });
  }, target);

  await page.getByTestId("pipeline-export").click();
  await expect(page.getByText(/Notebook written to/)).toBeVisible({ timeout: 10_000 });

  const notebook = JSON.parse(readFileSync(target, "utf8")) as {
    nbformat: number;
    metadata: { ti_toolbox: { pipeline: { nodes: { id: string }[] } } };
  };
  expect(notebook.nbformat).toBe(4);
  expect(notebook.metadata.ti_toolbox.pipeline.nodes.map((n) => n.id)).toEqual(["sub1", "pre1", "flex1", "sim1", "an1"]);
});

// ------------------------------------------------------------------------------- keyboard ------

test("⌘A selects every step, Escape clears it, ⌘Z and ⇧⌘Z step through the history", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-pre").click();
  await page.getByTestId("pipeline-add-sim").click();

  await page.keyboard.press("ControlOrMeta+a");
  await expect(page.locator(".react-flow__node.selected")).toHaveCount(2);

  await page.keyboard.press("Escape");
  await expect(page.locator(".react-flow__node.selected")).toHaveCount(0);

  await page.keyboard.press("ControlOrMeta+z");
  await expect(page.locator("[data-testid^='pipeline-node-']")).toHaveCount(1);
  await page.keyboard.press("ControlOrMeta+Shift+z");
  await expect(page.locator("[data-testid^='pipeline-node-']")).toHaveCount(2);
});

// ------------------------------------------------------------------ the canvas's own controls --

test("the canvas has working zoom, fit and a minimap", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-sample").click();
  const viewport = page.locator(".react-flow__viewport");
  const before = await viewport.getAttribute("style");
  await page.locator(".react-flow__controls-zoomin").click();
  await expect(viewport).not.toHaveAttribute("style", before ?? "");
  await page.locator(".react-flow__controls-fitview").click();
  await expect(page.locator(".react-flow__minimap")).toBeVisible();
});

// ------------------------------------------------------------------------------ the design -----

test("the node card is at the app's density, not React Flow's", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-pre").click();
  const card = page.getByTestId("pipeline-node-pre1");

  // The screenshot the revamp started from had a card whose type was ~40px and whose box was
  // roughly three times this. `pipeline.css` named tokens that did not exist, so every one of
  // these properties was dropped by the browser without a word.
  const style = await card.evaluate((el) => {
    const s = getComputedStyle(el);
    return {
      fontSize: parseFloat(s.fontSize),
      padding: parseFloat(s.paddingTop),
      border: s.borderTopWidth,
      background: s.backgroundColor,
      width: el.getBoundingClientRect().width,
    };
  });
  expect(style.fontSize).toBe(13);
  expect(style.padding).toBe(8);
  expect(style.border).toBe("1px");
  expect(style.background).not.toBe("rgba(0, 0, 0, 0)");
  expect(style.width).toBeLessThan(240);

  // And the port handles carry their per-type hue, which the same silence had removed.
  const handle = await page
    .getByTestId("pipeline-out-pre1-subjects")
    .evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(handle).not.toBe("rgba(0, 0, 0, 0)");
});

test("the whole page has no undefined custom property left in it", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-sample").click();
  // Read it from the live document rather than from the file, so a token that exists in
  // `tokens.css` but is not in scope on this page still counts as missing.
  const missing = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const names = new Set<string>();
    for (const sheet of Array.from(document.styleSheets)) {
      let rules: CSSRuleList;
      try {
        rules = sheet.cssRules;
      } catch {
        continue;
      }
      for (const rule of Array.from(rules)) {
        const text = rule.cssText;
        if (!text.includes(".pipeline-")) continue;
        for (const m of text.matchAll(/var\(\s*(--[a-z0-9-]+)\s*\)/gi)) names.add(m[1]!);
      }
    }
    return [...names].filter((n) => root.getPropertyValue(n).trim() === "").sort();
  });
  expect(missing).toEqual([]);
});

// -------------------------------------------------- the cohort node, and the readiness gate ----
//
// The mock's three subjects, from `tests/fixtures/overview.json`:
//   ernie    raw · head model · leadfield · 3 simulations   — ready for everything
//   101      raw · head model ·           · 1 simulation
//   MNI152        · head model ·           · no simulations, and **no raw**
// and the 30-subject project (`POST /api/__mock/project {"subjects": 30}`) has S016: raw, no head
// model, no simulations — the raw-only case.

/** Put a cohort node on the canvas and choose *ids* in its editor. */
async function cohort(...ids: string[]) {
  await page.getByTestId("pipeline-add-subjects").click();
  await expect(page.getByTestId("pipeline-node-subjects1")).toBeVisible();
  await page.getByTestId("pipeline-node-subjects1").dblclick();
  await expect(page.getByTestId("pipeline-subjects")).toBeVisible();
  // A plain click in a `SelectionList` *replaces* the selection, like any listbox; adding to it is
  // a ⌘/Ctrl-click. Clicking each id in turn left only the last one chosen.
  for (const [i, id] of ids.entries()) {
    await page
      .getByTestId("pipeline-subjects")
      .getByRole("row", { name: new RegExp(`^${id}\\b`) })
      .click(i === 0 ? undefined : { modifiers: ["ControlOrMeta"] });
  }
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  // The card prints the cohort, so this also proves the choice reached the document — without it
  // a later refusal is ambiguous between "not ready" and "no subjects chosen at all".
  for (const id of ids) await expect(page.getByTestId("pipeline-node-subjects1")).toContainText(id);
}

async function switchProject(subjects: 3 | 30) {
  await page.evaluate(
    async (n) =>
      void (await fetch("/api/__mock/project", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ subjects: n }),
      })),
    subjects,
  );
  // The readiness the drag gate reads is a cached query (`staleTime: 30s`), so switching the
  // project on the server is not enough — the app has to fetch it again.
  await page.reload();
  await page.getByRole("link", { name: "Pipeline", exact: true }).click();
  await expect(page.getByTestId("pipeline-canvas")).toBeVisible();
}

test("the cohort node lists the project's subjects with the Overview's own readiness columns", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-add-subjects").click();
  await page.getByTestId("pipeline-node-subjects1").dblclick();
  const list = page.getByTestId("pipeline-subjects");
  await expect(list).toBeVisible();
  for (const id of ["ernie", "101", "MNI152"]) {
    await expect(list.getByRole("row", { name: new RegExp(`^${id}\\b`) })).toBeVisible();
  }
  // Four columns and no more: the subject and its three presence dots. What a subject is *ready
  // for* is deliberately not spelled out here — that sentence is the drag's refusal and the
  // receipt's, and a third copy restated a conclusion these dots already support.
  await expect(list).toContainText("Head model");
  await expect(list).not.toContainText("Ready for");
  await expect(list).not.toContainText("ready for");

  // The facts are still there to key on, without a column printing them.
  await expect(list.getByRole("row", { name: /^ernie\b/ })).toHaveAttribute(
    "data-caps",
    "raw,m2m,leadfield,simulation",
  );
  await expect(list.getByRole("row", { name: /^MNI152\b/ })).toHaveAttribute("data-caps", "m2m");
  await page.keyboard.press("Escape");
});

test("subjects with only raw data are refused by everything but Pre-processing", async () => {
  // Asserted against the server rather than by dragging, and deliberately: the mock's default
  // project has no raw-only subject (its three are ernie, 101 and MNI152, and other lanes' specs
  // assert that list exactly, so a fourth cannot be added), which leaves the 30-subject project —
  // and choreographing a cohort plus two steps plus three wires there proved to be a test about
  // mouse gestures rather than about the rule. The rule itself is asserted on the canvas by the
  // three tests below, and twice more over the same table in `tests/unit/pipeline-graph.test.ts`
  // and `tests/test_pipeline_readiness.py`.
  await freshCanvas();
  await switchProject(30);
  try {
    const graph = (nodes: object[], edges: object[]) => ({ version: 1, name: "raw only", nodes, edges });
    const validate = async (doc: object) =>
      page.evaluate(async (body) => {
        const response = await fetch("/api/pipelines/validate", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        return (await response.json()) as { ok: boolean; issues: { code?: string; message: string }[] };
      }, doc);

    const cohortNode = { id: "s1", kind: "subjects", config: { subject_ids: ["S016"] } };

    // Straight to the Simulator: refused, and the reason names the subject.
    const toSim = await validate(
      graph([cohortNode, { id: "m1", kind: "sim", config: { conductivity: "scalar" } }], [
        { from: "s1", to: "m1", port: "subjects" },
      ]),
    );
    expect(toSim.ok).toBe(false);
    expect(toSim.issues.some((i) => i.code === "not_ready" && i.message.includes("S016 has no head model"))).toBe(true);

    // Through Pre-processing first: fine, because Pre-processing is what makes the head model.
    const throughPre = await validate(
      graph(
        [
          cohortNode,
          { id: "p1", kind: "pre", config: { create_m2m: true } },
          { id: "m1", kind: "sim", config: { conductivity: "scalar" } },
        ],
        [
          { from: "s1", to: "p1", port: "subjects" },
          { from: "p1", to: "m1", port: "subjects" },
        ],
      ),
    );
    expect(throughPre.issues.filter((i) => i.code === "not_ready")).toEqual([]);
    expect(throughPre.ok).toBe(true);
  } finally {
    await switchProject(3);
  }
});

test("subjects with a head model but no simulation reach the Simulator, not the Analyzer", async () => {
  await freshCanvas();
  await cohort("MNI152");
  await page.getByTestId("pipeline-add-sim").dragTo(page.getByTestId("pipeline-canvas"), {
    targetPosition: { x: 480, y: 120 },
  });
  await page.getByTestId("pipeline-add-analyzer").dragTo(page.getByTestId("pipeline-canvas"), {
    targetPosition: { x: 480, y: 320 },
  });

  await wire("pipeline-out-subjects1-subjects", "pipeline-in-sim1-subjects");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);

  await wire("pipeline-out-subjects1-subjects", "pipeline-in-analyzer1-subjects");
  await expect(page.getByTestId("pipeline-refusal")).toContainText("MNI152 has no simulations");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
});

test("subjects that already have a simulation go straight to the Analyzer", async () => {
  await freshCanvas();
  await cohort("ernie");
  await page.getByTestId("pipeline-add-analyzer").dragTo(page.getByTestId("pipeline-canvas"), {
    targetPosition: { x: 480, y: 200 },
  });
  await wire("pipeline-out-subjects1-subjects", "pipeline-in-analyzer1-subjects");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  await expect(page.getByTestId("pipeline-refusal")).toHaveCount(0);
});

test("a mixed cohort is refused by name — the ready subjects are not blamed", async () => {
  await freshCanvas();
  await cohort("ernie", "MNI152");
  await page.getByTestId("pipeline-add-analyzer").dragTo(page.getByTestId("pipeline-canvas"), {
    targetPosition: { x: 480, y: 200 },
  });
  await wire("pipeline-out-subjects1-subjects", "pipeline-in-analyzer1-subjects");
  const refusal = page.getByTestId("pipeline-refusal");
  await expect(refusal).toContainText("MNI152 has no simulations");
  await expect(refusal).not.toContainText("ernie");
  await expect(page.locator(".react-flow__edge")).toHaveCount(0);
});

test("a processing node is never configured from the node upstream of it", async () => {
  await freshCanvas();
  await cohort("ernie");
  await page.getByTestId("pipeline-add-sim").dragTo(page.getByTestId("pipeline-canvas"), {
    targetPosition: { x: 480, y: 200 },
  });
  await wire("pipeline-out-subjects1-subjects", "pipeline-in-sim1-subjects");

  // The Simulator runs over the cohort's subject, but its own config stays its own: the card
  // states the subject count it was handed, and says nothing about montages it was not given.
  const card = page.getByTestId("pipeline-node-sim1");
  await expect(card).toContainText("1 subject");
  await expect(card).not.toContainText("from optimizer");

  // And the document keeps the cohort in exactly one place. Saved and read back, `subject_ids`
  // appears on the `subjects` node and on nothing else — which is the whole model in one
  // assertion: before this, every node carried its own copy and two of them could disagree.
  await page.getByTestId("pipeline-save").click();
  await page.getByTestId("pipeline-save-name").fill("one cohort");
  await page.getByTestId("pipeline-save-confirm").click();
  await expect(page.getByTestId("pipeline-saved-one cohort")).toBeVisible();

  const saved = await page.evaluate(
    async () => (await (await fetch("/api/pipelines/one%20cohort")).json()) as {
      nodes: { id: string; kind: string; config: Record<string, unknown> }[];
    },
  );
  const carryingSubjects = saved.nodes.filter((n) => n.config?.subject_ids !== undefined);
  expect(carryingSubjects.map((n) => n.kind)).toEqual(["subjects"]);
  expect(carryingSubjects[0]!.config.subject_ids).toEqual(["ernie"]);
});


test("a simulator configuration rejection names the node before Run", async () => {
  await freshCanvas();
  await page.route("**/api/pipelines/validate", async (route) => {
    await route.fulfill({ json: { ok: false, order: ["sim1"], jobs: [], issues: [{ level: "error", node_id: "sim1", message: "sim1: config is not a valid SimulationConfig: missing montages" }] } });
  });
  try {
    await page.getByTestId("pipeline-sample").click();
    await expect(page.getByTestId("pipeline-problem-sim1")).toContainText("missing montages");
    await expect(page.getByTestId("pipeline-run")).toBeDisabled();
    await page.getByTestId("pipeline-node-sim1").dblclick();
    await expect(page.getByRole("dialog").getByRole("textbox", { name: "Montages", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
  } finally {
    await page.unroute("**/api/pipelines/validate");
  }
});

test("a late run rejection keeps its useful server detail", async () => {
  await freshCanvas();
  await page.getByTestId("pipeline-sample").click();
  // A distinct document avoids reusing the intentionally rejected validation response above.
  await page.getByTestId("pipeline-node-sim1").dblclick();
  await page.getByRole("textbox", { name: "Node name", exact: true }).fill("Late simulation");
  await page.keyboard.press("Escape");
  await page.route("**/api/pipelines/run", async (route) => route.fulfill({ status: 422, json: { detail: { message: "pipeline does not validate", issues: [{ message: "Simulate it needs a montage", node_id: "sim1" }] } } }));
  // This case reaches admission; existing-output confirmation has separate coverage.
  await page.route("**/api/plan/*", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    if (Array.isArray(data.jobs)) for (const job of data.jobs) job.exists = false;
    await route.fulfill({ response, json: data });
  });
  try {
    await expect(page.getByTestId("pipeline-run")).toBeEnabled();
    await page.getByTestId("pipeline-run").click();
    await expect(page.getByText("Could not run the pipeline: Simulate it needs a montage", { exact: true })).toBeVisible();
  } finally { await page.unroute("**/api/pipelines/run"); await page.unroute("**/api/plan/*"); }
});
