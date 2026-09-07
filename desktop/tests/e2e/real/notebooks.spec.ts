import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp } from "../_helpers";

/**
 * Notebooks against the **real** container.
 *
 * `tests/e2e/notebooks.spec.ts` proves the wiring against a fake kernel that
 * knows `print()` and arithmetic. What only a real server can prove is the
 * claim the whole feature exists for: **simnibs and TI-Toolbox methods are
 * usable from a cell** — the kernel is the container's SimNIBS Python with
 * `tit` on its path, so `from tit import catalog, get_path_manager`,
 * `simnibs.__version__` and `tit.calc.get_TI_vectors` all work with nothing
 * installed and nothing configured.
 *
 * It runs the seeded worked example end to end and asserts its **rich**
 * outputs — a matplotlib PNG and two DataFrame tables — because a notebook
 * whose only output is printed text has not shown that a notebook beats a
 * script.
 *
 * It writes into `<project>/code/ti-toolbox/notebooks/` and cleans up after
 * itself; the example it runs is the one the server seeds.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;

/** A full SimNIBS interpreter takes seconds to come up; a FEM-busy box, more. */
const KERNEL_TIMEOUT = 180_000;

let app: ElectronApplication;
let page: Page;

// Serial, and generously timed: these tests start a real SimNIBS Python, import
// `tit` and `simnibs` in it, and read a real field off disk. The suite default
// of 60 s is sized for the mock server and caps this run long before the work
// is done — the per-assertion timeouts below are the real deadlines.
test.describe.configure({ mode: "serial", timeout: 6 * 60_000 });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-nb-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await gotoPage(page, "notebooks", "Notebooks");
  await expectPage(page, "notebooks");
});

test.afterAll(async () => {
  await app?.close();
});

function codeCells() {
  return page.locator('[data-testid="nb-cell"][data-cell-type="code"]');
}

/** The nth code cell's CodeMirror content element. */
function codeCell(index: number) {
  return codeCells().nth(index).locator(".cm-content");
}

/** `fill()` cannot drive a CodeMirror; a person selects all and types. */
async function typeInCell(index: number, text: string): Promise<void> {
  const cell = codeCell(index);
  await cell.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Backspace");
  await cell.pressSequentially(text);
}

function cellOutput(index: number) {
  return codeCells().nth(index).getByTestId("nb-output");
}

let notebookName = "";

test("a new notebook's starter cell runs green and names the real project", async () => {
  await page.getByTestId("nb-new").click();
  await expect(page.getByTestId("nb-notebook")).toBeVisible({ timeout: 30_000 });
  notebookName = (await page.getByTestId("nb-notebook").getAttribute("data-notebook")) as string;

  const cell = codeCell(0);
  await expect(cell).toContainText("from tit import catalog, get_path_manager");
  await expect(cell).toContainText("from tit.sim import SimulationConfig");
  await expect(cell).toContainText("from tit.analyzer import Analyzer");

  await cell.click();
  await page.keyboard.press("ControlOrMeta+Enter");

  // The assertion is the OUTPUT TEXT, not "the kernel went idle" — a kernel
  // that starts and imports nothing would pass that and prove nothing. The
  // first version of this cell called `pm.project_root`, which does not exist;
  // this is the test that would have caught it.
  await expect(cellOutput(0)).toBeVisible({ timeout: KERNEL_TIMEOUT });
  await expect(cellOutput(0)).toContainText("project  /mnt/", { timeout: KERNEL_TIMEOUT });
  await expect(cellOutput(0)).toContainText("simnibs  4.");
  await expect(cellOutput(0)).toContainText("subjects [");
  await expect(page.getByTestId("nb-output-error")).toHaveCount(0);
  await expect(page.getByTestId("nb-kernel-status")).toContainText("SimNIBS + TI-Toolbox");
});

test("the worked example runs every cell green, with a plot and tables", async () => {
  // Free the kernel: the container allows two, and this spec wants one for the
  // example without depending on the reaper.
  await page.getByTestId("nb-restart").click();
  await expect(page.getByTestId("nb-kernel-status")).toHaveAttribute("data-state", "idle", {
    timeout: KERNEL_TIMEOUT,
  });

  const example = page.getByTestId("nb-list-item").filter({ hasText: "getting-started" });
  await expect(example).toBeVisible({ timeout: 30_000 });
  await expect(example).toHaveAttribute("data-example", "1");
  await example.click();
  await expect(page.getByTestId("nb-notebook")).toHaveAttribute(
    "data-notebook",
    "examples/getting-started.ipynb",
    { timeout: 30_000 },
  );

  // The prose renders as prose, against the real file rather than the mock's.
  const prose = page.getByTestId("nb-markdown").first();
  await expect(prose.locator("h1")).toHaveText("Getting started with TI-Toolbox notebooks");
  await expect(prose.locator(".nb-math-block .katex-display")).toHaveCount(1);
  await expect(prose.locator("table th").first()).toHaveText("step");

  await expect(codeCells()).toHaveCount(4);
  await page.getByTestId("nb-run-all").click();
  await expect(page.getByTestId("nb-kernel-status")).toHaveAttribute("data-state", "idle", {
    timeout: KERNEL_TIMEOUT,
  });

  // 1 — the environment. Real SimNIBS, real project, real subjects.
  await expect(cellOutput(0)).toContainText("simnibs     4.", { timeout: KERNEL_TIMEOUT });
  await expect(cellOutput(0)).toContainText("project     /mnt/");

  // 2 — a pandas DataFrame renders as a real HTML TABLE, not as its text repr.
  await expect(cellOutput(1).locator("table")).toHaveCount(1, { timeout: KERNEL_TIMEOUT });
  await expect(cellOutput(1).locator("th", { hasText: "simulations" })).toBeVisible();

  // 3 — a real TI-Toolbox computation. Orthogonal 1 V/m carriers give an
  // envelope of magnitude 1; `tit.calc.get_TI_vectors` is what produced it.
  await expect(cellOutput(2).locator("table")).toHaveCount(1, { timeout: KERNEL_TIMEOUT });
  await expect(cellOutput(2).locator("th", { hasText: "TI envelope" })).toBeVisible();

  // 4 — a real field off disk, and a matplotlib figure rendered inline as PNG.
  await expect(cellOutput(3)).toContainText("non-zero voxels", { timeout: KERNEL_TIMEOUT });
  const figure = cellOutput(3).locator("img.nb-output__image");
  await expect(figure).toHaveCount(1);
  await expect(figure).toHaveAttribute("src", /^data:image\/png;base64,/);
  // A PNG that decoded and laid out, not a broken-image box.
  const drawn = await figure.evaluate((el) => {
    const image = el as HTMLImageElement;
    return { w: image.naturalWidth, h: image.naturalHeight };
  });
  expect(drawn.w).toBeGreaterThan(200);
  expect(drawn.h).toBeGreaterThan(100);

  // Nothing in the worked example may raise.
  await expect(page.getByTestId("nb-output-error")).toHaveCount(0);
});

test("restart clears the kernel's state, and a cell runs again after it", async () => {
  // Back to this spec's own notebook: the seeded example is reference material
  // and a test that types into it leaves the next reader a modified copy.
  await page.getByTestId("nb-list-item").filter({ hasText: notebookName }).click();
  await expect(page.getByTestId("nb-notebook")).toHaveAttribute("data-notebook", notebookName, {
    timeout: 30_000,
  });

  await page.getByTestId("nb-restart").click();
  await expect(page.getByTestId("nb-kernel-status")).toHaveAttribute("data-state", "idle", {
    timeout: KERNEL_TIMEOUT,
  });

  await typeInCell(0, "import tit, sys; print('tit ok', sys.version_info[:2])");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(cellOutput(0)).toContainText("tit ok", { timeout: KERNEL_TIMEOUT });
  // Execution counts restart at 1 — the visible proof that the interpreter is a
  // new one rather than the old one with its variables intact.
  // Waited for, not sampled: the output arrives on iopub and the count is
  // settled by the shell reply, so the two are not the same instant.
  await expect(page.locator(".nb-cell__count").first()).toHaveText("[1]", { timeout: 30_000 });
});

test("the real kernel completes `from tit import get_pa`", async () => {
  // The claim this exists for: completion is answered by the SimNIBS kernel's
  // own namespace through IPython/jedi — no language server, nothing installed
  // — so it knows names that only exist because `tit` is importable there.
  await typeInCell(0, "from tit import get_pa");

  // Typing opens it; the matches came back over /ws/kernels from IPython's
  // completer, against the namespace of an interpreter where `tit` is real.
  const popup = page.locator(".cm-tooltip-autocomplete");
  await expect(popup).toBeVisible({ timeout: KERNEL_TIMEOUT });
  await expect(popup).toContainText("get_path_manager");

  // ⇥ accepts, as it does in Jupyter.
  await page.keyboard.press("Tab");
  await expect(codeCell(0)).toContainText("from tit import get_path_manager");

  // And it runs, which is the only proof the completion was a real name.
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByTestId("nb-output-error")).toHaveCount(0, { timeout: KERNEL_TIMEOUT });
});

test("the real kernel highlights Python in the cell", async () => {
  await typeInCell(0, "def go(n):\n    return 'x' * n  # a comment\n");
  const colours = await codeCell(0).evaluate((el) => {
    const seen = new Set<string>();
    for (const span of el.querySelectorAll("span")) seen.add(getComputedStyle(span).color);
    return [...seen];
  });
  expect(colours.length).toBeGreaterThan(2);
});

test("deleting a notebook takes its own kernel with it", async () => {
  const count = async (): Promise<number> => {
    const body = await page.evaluate(async (base) => {
      const res = await fetch(new URL("/api/kernels", base).href);
      return (await res.json()) as { kernels: unknown[] };
    }, SERVER_URL);
    return body.kernels.length;
  };
  const before = await count();
  expect(before).toBeGreaterThan(0);

  await page
    .locator("li", { has: page.getByTestId("nb-list-item").filter({ hasText: notebookName }) })
    .getByRole("button", { name: `Delete ${notebookName}` })
    .click();
  await expect(page.getByTestId("nb-list-item").filter({ hasText: notebookName })).toHaveCount(0, {
    timeout: 30_000,
  });

  // ITS kernel, not every kernel: the worked example was opened in this run too
  // and is still holding one, which is the point of a per-notebook session. The
  // cap is two per container, so a page that leaked one would make the next
  // notebook of the session unopenable — that is what this counts.
  await expect.poll(count, { timeout: 30_000 }).toBe(before - 1);
});
