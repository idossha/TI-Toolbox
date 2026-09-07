import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectReal, expectPage, gotoPage, launchElectronApp } from "../_helpers";

/**
 * Notebooks against the **real** container.
 *
 * `tests/e2e/notebooks.spec.ts` proves the wiring against a fake kernel that
 * knows `print()` and arithmetic. What only a real server can prove is the one
 * claim the whole feature exists for: the kernel is the container's SimNIBS
 * Python with `tit` on its path, so `from tit import get_path_manager` works in
 * a cell with nothing installed and nothing configured — which is what "the
 * TI-Toolbox environment is automatically loaded" means.
 *
 * It writes one notebook into `<project>/code/ti-toolbox/notebooks/` and
 * deletes it again.
 */
const SERVER_URL = process.env.TIT_E2E_SERVER_URL as string;
const TOKEN = process.env.TIT_E2E_TOKEN as string;

let app: ElectronApplication;
let page: Page;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const userDataDir = mkdtempSync(join(tmpdir(), "tit-e2e-real-nb-"));
  app = await launchElectronApp({ userDataDir });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectReal(page, { url: SERVER_URL, token: TOKEN });
  await gotoPage(page, "notebooks", "Notebooks");
  await expectPage(page, "notebooks");
});

test.afterAll(async () => {
  await app?.close();
});

function codeCell(index: number) {
  return page
    .locator('[data-testid="nb-cell"][data-cell-type="code"]')
    .nth(index)
    .locator("textarea");
}

let notebookName = "";

test("a new notebook's starter cell imports tit and prints the real project root", async () => {
  await page.getByTestId("nb-new").click();
  await expect(page.getByTestId("nb-notebook")).toBeVisible({ timeout: 20_000 });
  notebookName = (await page.getByTestId("nb-notebook").getAttribute("data-notebook")) as string;

  const cell = codeCell(0);
  await expect(cell).toHaveValue(/from tit import get_path_manager/);

  await cell.click();
  await cell.press("Control+Enter");

  // The kernel is a full SimNIBS Python interpreter and takes seconds to come
  // up, so this waits like a person would.
  const output = page
    .locator('[data-testid="nb-cell"][data-cell-type="code"]')
    .first()
    .getByTestId("nb-output");
  await expect(output).toBeVisible({ timeout: 120_000 });
  // The assertion is the OUTPUT TEXT, not "the kernel went idle" — a kernel
  // that starts and imports nothing would pass that and prove nothing.
  await expect(output).toContainText("project: /mnt/", { timeout: 120_000 });
  await expect(page.getByTestId("nb-output-error")).toHaveCount(0);
  await expect(page.getByTestId("nb-kernel-status")).toContainText("SimNIBS + TI-Toolbox");
});

test("restart clears the kernel's state, and a cell runs again after it", async () => {
  await page.getByTestId("nb-restart").click();
  await expect(page.getByTestId("nb-kernel-status")).toHaveAttribute("data-state", "idle", {
    timeout: 120_000,
  });

  const cell = codeCell(0);
  await cell.click();
  await cell.fill("import tit, sys; print('tit', tit.__file__.split('/')[-2], 'py', sys.version_info[:2])");
  await cell.press("Control+Enter");
  await expect(page.getByTestId("nb-output").first()).toContainText("tit tit", { timeout: 120_000 });
  // Execution counts restart at 1 — the visible proof that the interpreter is a
  // new one rather than the old one with its variables intact.
  await expect(page.locator(".nb-cell__count").first()).toHaveText("[1]");
});

test("deleting the notebook takes its kernel with it", async () => {
  await page
    .locator("li", { has: page.getByTestId("nb-list-item").filter({ hasText: notebookName }) })
    .getByRole("button", { name: `Delete ${notebookName}` })
    .click();
  await expect(page.getByTestId("nb-list-item").filter({ hasText: notebookName })).toHaveCount(0, {
    timeout: 20_000,
  });

  // No kernel is left running: the cap is two per container, so a page that
  // leaked one would make the third notebook of a session unopenable.
  const kernels = await page.evaluate(async (base) => {
    const res = await fetch(new URL("/api/kernels", base).href);
    return (await res.json()) as { kernels: unknown[] };
  }, SERVER_URL);
  expect(kernels.kernels).toHaveLength(0);
});
