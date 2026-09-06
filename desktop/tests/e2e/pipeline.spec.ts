/**
 * D6's mock-side gate, driven through the built app against the mock server.
 *
 * The claim under test is the one the whole feature rests on: a four-node
 * pre -> flex -> sim -> analyzer pipeline **validates**, **runs as one job group** whose `after`
 * chain is the document's edges, shows **one** group in Jobs, and **exports** a notebook whose
 * metadata carries the pipeline back.
 *
 * The graph is built through the REST API rather than by dragging wires: dragging a React Flow
 * handle is a mouse gesture whose reliability says nothing about whether the pipeline is right,
 * and the drag-refusal path has its own assertion below via `canConnect`'s reason surface.
 * Offscreen by default, like every other spec here.
 */
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

let app: ElectronApplication;
let page: Page;

const FOUR_NODE = {
  version: 1,
  name: "gate",
  nodes: [
    { id: "pre1", kind: "pre", config: { subject_ids: ["ernie"], create_m2m: true }, position: { x: 0, y: 0 } },
    { id: "flex1", kind: "flex", config: { goal: "mean", postproc: "max_TI" }, position: { x: 300, y: 140 } },
    { id: "sim1", kind: "sim", config: { conductivity: "scalar" }, position: { x: 600, y: 0 } },
    {
      id: "an1",
      kind: "analyzer",
      config: { space: "mesh", analysis_type: "spherical", center: [1, 2, 3], radius: 5 },
      position: { x: 900, y: 140 },
    },
  ],
  edges: [
    { from: "pre1", to: "flex1", port: "subjects" },
    { from: "pre1", to: "sim1", port: "subjects" },
    { from: "flex1", to: "sim1", port: "montages" },
    { from: "sim1", to: "an1", port: "subjects" },
    { from: "sim1", to: "an1", port: "simulation" },
  ],
};

/** Same-origin fetch from inside the app, so the session cookie authenticates it. */
async function apiPost(path: string, body: unknown, parse: "json" | "text" = "json") {
  return page.evaluate(
    async ([p, payload, mode]) => {
      const response = await fetch(p as string, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      return { status: response.status, body: mode === "text" ? await response.text() : await response.json() };
    },
    [path, body, parse] as const,
  );
}

test.beforeAll(async () => {
  app = await launchElectronApp({ userDataDir: mkdtempSync(join(tmpdir(), "tit-e2e-pipeline-")) });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 20_000 });
});

test.afterAll(async () => {
  await app?.close();
});

test("the Pipeline page is the sixth rail row and reaches an empty canvas", async () => {
  await page.getByRole("link", { name: "Pipeline", exact: true }).click();
  await expect(page.getByTestId("pipeline-canvas")).toBeVisible();
  await expect(page.getByTestId("pipeline-receipt")).toBeVisible();
});

test("adding a step from the palette puts a card on the canvas", async () => {
  await page.getByRole("link", { name: "Pipeline", exact: true }).click();
  await page.getByTestId("pipeline-add-sim").click();
  await expect(page.getByTestId("pipeline-node-sim1")).toBeVisible();
  // An unconfigured Simulator cannot run, and the receipt says why rather than failing later —
  // grouped under the step it is about, keyed on the issue's `port` rather than on its sentence.
  await expect(page.getByTestId("pipeline-problem-sim1")).toContainText("needs subjects");
  await expect(page.getByTestId("pipeline-run")).toBeDisabled();
});

test("the four-node pipeline validates and its receipt is the DAG", async () => {
  const { status, body } = await apiPost("/api/pipelines/validate", FOUR_NODE);
  expect(status).toBe(200);
  const validation = body as { ok: boolean; order: string[]; jobs: { label: string; after: string[] }[] };
  expect(validation.ok).toBe(true);
  expect(validation.order).toEqual(["pre1", "flex1", "sim1", "an1"]);

  const byLabel = Object.fromEntries(validation.jobs.map((j) => [j.label, j]));
  expect(byLabel["pre1:0"]!.after).toEqual([]);
  expect(byLabel["flex1:0"]!.after).toEqual(["pre1:0"]);
  expect(byLabel["sim1:resolve:montages"]!.after).toEqual(["flex1:0"]);
  expect(byLabel["sim1:0"]!.after.sort()).toEqual(["pre1:0", "sim1:resolve:montages"]);
  expect(byLabel["an1:resolve:simulation"]!.after).toEqual(["sim1:0"]);
  expect(byLabel["an1:0"]!.after.sort()).toEqual(["an1:resolve:simulation", "sim1:0"]);
});

test("running it creates exactly one job group, and Jobs shows one group", async () => {
  const { status, body } = await apiPost("/api/pipelines/run", { pipeline: FOUR_NODE, parallel_subjects: 1 });
  expect(status).toBe(201);
  const result = body as { group_id: string; pipeline: string; jobs: { id: string; group_id: string }[] };
  expect(result.pipeline).toBe("gate");
  expect(new Set(result.jobs.map((j) => j.group_id))).toEqual(new Set([result.group_id]));
  expect(result.jobs.length).toBe(6);

  // The `after` chain the server actually stamped on the jobs, resolved to real ids.
  const details = await page.evaluate(
    async (ids: string[]) =>
      Promise.all(ids.map(async (id) => (await (await fetch(`/api/jobs/${id}`)).json()) as { spec: { kind: string; after?: string[] } })),
    result.jobs.map((j) => j.id),
  );
  const ids = result.jobs.map((j) => j.id);
  const kinds = details.map((d) => d.spec.kind);
  expect(kinds).toEqual(["pre", "flex", "tools", "sim", "tools", "analyzer"]);
  expect(details[0]!.spec.after ?? []).toEqual([]);
  expect(details[1]!.spec.after).toEqual([ids[0]]);
  expect(details[2]!.spec.after).toEqual([ids[1]]);
  expect(new Set(details[3]!.spec.after)).toEqual(new Set([ids[0], ids[2]]));
  expect(details[4]!.spec.after).toEqual([ids[3]]);
  expect(new Set(details[5]!.spec.after)).toEqual(new Set([ids[3], ids[4]]));

  const groups = await page.evaluate(async () => {
    const jobs = (await (await fetch("/api/jobs")).json()) as { group_id: string | null }[];
    return [...new Set(jobs.map((j) => j.group_id).filter(Boolean))];
  });
  expect(groups).toEqual([result.group_id]);
});

test("export returns a notebook that carries the pipeline back in its metadata", async () => {
  const { status, body } = await apiPost("/api/pipelines/export?format=ipynb", FOUR_NODE, "text");
  expect(status).toBe(200);
  const notebook = JSON.parse(body as string) as {
    nbformat: number;
    cells: { cell_type: string; source: string }[];
    metadata: { ti_toolbox: { pipeline: typeof FOUR_NODE } };
  };
  expect(notebook.nbformat).toBe(4);
  expect(notebook.metadata.ti_toolbox.pipeline.nodes.map((n) => n.id)).toEqual(["pre1", "flex1", "sim1", "an1"]);
  expect(notebook.cells[0]!.source).toContain("```mermaid");
  expect(notebook.cells[0]!.source).toContain("flex1 -->|montages| sim1");
});

test("an illegal wire is refused, not silently dropped", async () => {
  const { status, body } = await apiPost("/api/pipelines/validate", {
    ...FOUR_NODE,
    edges: [...FOUR_NODE.edges, { from: "an1", to: "flex1", port: "subjects" }],
  });
  expect(status).toBe(200);
  const validation = body as { ok: boolean; issues: { message: string }[] };
  expect(validation.ok).toBe(false);
  expect(validation.issues.map((i) => i.message).join(" ")).toContain("cycle");
});

test("the canvas renders the four-node graph (screenshot evidence)", async () => {
  // Loads the saved document through the page's own Saved list, so what is captured is what a
  // user sees, not a hand-built DOM.
  await page.evaluate(async (doc) => {
    await fetch("/api/pipelines/screenshot", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(doc),
    });
  }, FOUR_NODE);
  // Reload so the palette's Saved list refetches; the page is retained across navigation, so
  // clicking away and back would show the list as it was before the PUT above.
  await page.reload();
  await page.getByRole("link", { name: "Pipeline", exact: true }).click();
  await page.getByRole("button", { name: "screenshot" }).click();
  for (const id of ["pre1", "flex1", "sim1", "an1"]) {
    await expect(page.getByTestId(`pipeline-node-${id}`)).toBeVisible();
  }
  await expect(page.getByTestId("pipeline-receipt")).toContainText("6 jobs in one group");
  mkdirSync(ARTIFACTS, { recursive: true });
  await page.screenshot({ path: join(ARTIFACTS, "pipeline-canvas.png") });
});

test("save and load round-trip a document", async () => {
  const saved = await page.evaluate(async (doc) => {
    const put = await fetch("/api/pipelines/e2e%20saved", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(doc),
    });
    const list = (await (await fetch("/api/pipelines")).json()) as { name: string }[];
    const loaded = (await (await fetch("/api/pipelines/e2e%20saved")).json()) as { name: string; nodes: { id: string }[] };
    return { putStatus: put.status, names: list.map((e) => e.name), loaded };
  }, FOUR_NODE);
  expect(saved.putStatus).toBe(200);
  expect(saved.names).toContain("e2e saved");
  expect(saved.loaded.name).toBe("e2e saved");
  expect(saved.loaded.nodes.map((n) => n.id)).toEqual(["pre1", "flex1", "sim1", "an1"]);
});
