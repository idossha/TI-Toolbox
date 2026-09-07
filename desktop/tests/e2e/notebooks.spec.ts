import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { expectPage, gotoPage, launchElectronApp } from "./_helpers";

/**
 * The Notebooks page against the mock server's fake kernel.
 *
 * What this can prove is the wiring — a cell's code reaches a kernel, its
 * output comes back attributed to that cell, the reply ends the run, and the
 * document round-trips through the server. What it cannot prove is that the
 * kernel is a real SimNIBS Python with `tit` on its path; that is
 * `tests/e2e/real/notebooks.spec.ts`, which runs `from tit import
 * get_path_manager` against the container and asserts the printed path.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication;
let page: Page;

async function connect(): Promise<void> {
  await expect(page).toHaveURL(/^app:\/\/launcher\//);
  await page.fill("#server-url", SERVER_URL);
  await page.fill("#token", TOKEN);
  await page.click("#connect");
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
}

/** A fresh notebook, open, with its starter cells. Returns its name. */
async function newNotebook(): Promise<string> {
  await page.getByTestId("nb-new").click();
  await expect(page.getByTestId("nb-notebook")).toBeVisible({ timeout: 15_000 });
  return (await page.getByTestId("nb-notebook").getAttribute("data-notebook")) as string;
}

/** The nth code cell's textarea. */
function codeCell(index: number) {
  return page.locator('[data-testid="nb-cell"][data-cell-type="code"]').nth(index).locator("textarea");
}

test.beforeEach(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-nb-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connect();
  // Every spec starts from an empty project: the mock's notebook store and its
  // kernels are per-process, and a leftover kernel would hit the limit of two.
  await page.evaluate(async (base) => {
    await fetch(new URL("/api/__mock/reset", base).href, { method: "POST" });
  }, SERVER_URL);
  await gotoPage(page, "notebooks", "Notebooks");
  await expectPage(page, "notebooks");
});

test.afterEach(async () => {
  await app?.close();
});

test("creates a notebook, runs print(1+1), and shows 2", async () => {
  await newNotebook();

  // The starter cell is the maintainer's ask made visible: a new notebook
  // already imports tit rather than telling the reader that it could.
  await expect(codeCell(0)).toHaveValue(/from tit import get_path_manager/);

  const cell = codeCell(0);
  await cell.click();
  await cell.fill("print(1+1)");
  await cell.press("Shift+Enter");

  const output = page.locator('[data-testid="nb-cell"][data-cell-type="code"]').first().getByTestId("nb-output");
  await expect(output).toContainText("2", { timeout: 20_000 });
  // The kernel started because a cell was run, and the pill says which one.
  await expect(page.getByTestId("nb-kernel-status")).toContainText("SimNIBS + TI-Toolbox");
  await expect(page.getByTestId("nb-kernel-status")).toHaveAttribute("data-state", "idle", {
    timeout: 20_000,
  });
  // ⇧↵ steps to the next cell, Jupyter's gesture — the starter notebook has
  // one code cell, so running the last one inserts and selects a new one.
  await expect(page.locator('[data-testid="nb-cell"][data-cell-type="code"]')).toHaveCount(2);
});

test("renders a markdown cell, and edits it again on double-click", async () => {
  await newNotebook();
  const markdown = page.locator('[data-testid="nb-cell"][data-cell-type="markdown"]').first();
  // The starter's own markdown cell is already rendered, not raw source.
  await expect(markdown.getByTestId("nb-markdown").locator("h1")).toHaveText(
    "New TI-Toolbox notebook",
  );
  await markdown.getByTestId("nb-markdown").dblclick();
  const editor = markdown.locator("textarea");
  await expect(editor).toBeVisible();
  await editor.fill("## Edited heading");
  await editor.press("Shift+Enter");
  await expect(markdown.getByTestId("nb-markdown").locator("h2")).toHaveText("Edited heading");
});

test("shows an error output with its traceback rather than swallowing it", async () => {
  await newNotebook();
  const cell = codeCell(0);
  await cell.click();
  await cell.fill("undefined_name");
  await cell.press("Control+Enter");
  await expect(page.getByTestId("nb-output-error").first()).toContainText("NameError", {
    timeout: 20_000,
  });
});

test("interrupts a running cell", async () => {
  await newNotebook();
  const cell = codeCell(0);
  await cell.click();
  // The mock's one simulated long run (see its `kernelExecute`).
  await cell.fill("sleep(30)");
  await cell.press("Control+Enter");

  await expect(page.getByTestId("nb-kernel-status")).toHaveAttribute("data-state", "busy", {
    timeout: 20_000,
  });
  await page.getByTestId("nb-interrupt").click();
  await expect(page.getByTestId("nb-output-error").first()).toContainText("KeyboardInterrupt", {
    timeout: 20_000,
  });
  await expect(page.getByTestId("nb-kernel-status")).toHaveAttribute("data-state", "idle");
});

test("saves and reloads: an edit and its output survive a round trip", async () => {
  const name = await newNotebook();

  const cell = codeCell(0);
  await cell.click();
  await cell.fill("print('round trip')");
  await cell.press("Control+Enter");
  await expect(page.getByTestId("nb-output").first()).toContainText("round trip", { timeout: 20_000 });

  await page.getByTestId("nb-save").click();
  await expect(page.getByTestId("nb-save")).toHaveText("Saved");

  // A reload is the honest test of a round trip: the session's in-memory copy
  // is gone, so what comes back is what the server actually wrote.
  await page.reload();
  await gotoPage(page, "notebooks", "Notebooks");
  await page.getByTestId("nb-list-item").filter({ hasText: name }).click();
  await expect(page.getByTestId("nb-notebook")).toBeVisible({ timeout: 15_000 });
  await expect(codeCell(0)).toHaveValue("print('round trip')");
  await expect(page.getByTestId("nb-output").first()).toContainText("round trip");
});

test("lists, opens and deletes notebooks", async () => {
  const first = await newNotebook();
  await page.getByTestId("nb-new").click();
  await expect(page.getByTestId("nb-list-item")).toHaveCount(2, { timeout: 15_000 });

  await page.getByTestId("nb-list-item").filter({ hasText: first }).click();
  await expect(page.getByTestId("nb-notebook")).toHaveAttribute("data-notebook", first);

  await page
    .locator("li", { has: page.getByTestId("nb-list-item").filter({ hasText: first }) })
    .getByRole("button", { name: `Delete ${first}` })
    .click();
  await expect(page.getByTestId("nb-list-item")).toHaveCount(1, { timeout: 15_000 });
});

test("Jupyter's command-mode keys act on the cell list", async () => {
  await newNotebook();
  const cells = page.locator('[data-testid="nb-cell"]');
  const before = await cells.count();

  const cell = codeCell(0);
  await cell.click();
  // Escape leaves edit mode; `b` then inserts below. Both are only safe as
  // bare keystrokes because editing is modal.
  await cell.press("Escape");
  await page.keyboard.press("b");
  await expect(cells).toHaveCount(before + 1);

  // `dd` deletes, `z` puts it back — Jupyter's one-slot undo.
  await page.keyboard.press("d");
  await page.keyboard.press("d");
  await expect(cells).toHaveCount(before);
  await page.keyboard.press("z");
  await expect(cells).toHaveCount(before + 1);

  // `m` re-types the selected cell as markdown.
  await page.keyboard.press("m");
  await expect(page.locator('[data-testid="nb-cell"][data-cell-type="markdown"]')).toHaveCount(2);
});
