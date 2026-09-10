import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, expectPage, gotoPage, launchElectronApp } from "./_helpers";

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
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await expect(page.getByTestId("overview-table")).toBeVisible({ timeout: 45_000 });
}

/** A fresh notebook, open, with its starter cells. Returns its name. */
async function newNotebook(): Promise<string> {
  await page.getByTestId("nb-new").click();
  await expect(page.getByTestId("nb-notebook")).toBeVisible({ timeout: 15_000 });
  return (await page.getByTestId("nb-notebook").getAttribute("data-notebook")) as string;
}

/** The nth code cell's CodeMirror content element. */
function codeCell(index: number) {
  return page
    .locator('[data-testid="nb-cell"][data-cell-type="code"]')
    .nth(index)
    .locator(".cm-content");
}

/**
 * Replace a code cell's text.
 *
 * `fill()` does not work on a CodeMirror: the text lives in contenteditable
 * lines the editor owns, so this selects all and types, which is what a person
 * does and what CodeMirror's own change pipeline sees.
 */
async function typeInCell(index: number, text: string): Promise<void> {
  const cell = codeCell(index);
  await cell.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Backspace");
  await cell.pressSequentially(text);
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
  await expect(codeCell(0)).toContainText("from tit import catalog, get_path_manager");
  await expect(codeCell(0)).toContainText("import simnibs");

  await typeInCell(0, "print(1+1)");
  await page.keyboard.press("Shift+Enter");

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
  const rendered = markdown.getByTestId("nb-markdown");
  // The starter's own markdown cell is already rendered, not raw source — this
  // is the defect the maintainer reported as "shows as a flat paragraph".
  await expect(rendered.locator("h1")).toHaveText("New TI-Toolbox notebook");
  await expect(rendered.locator("strong").first()).toHaveText("SimNIBS Python");
  await expect(rendered.locator("code").first()).toHaveText("tit");

  await rendered.dblclick();
  const editor = markdown.locator("textarea");
  await expect(editor).toBeVisible();
  await editor.fill("## Edited heading");
  await editor.press("Shift+Enter");
  await expect(rendered.locator("h2")).toHaveText("Edited heading");
});

test("the example notebook renders headings, maths, a mono code block and a table", async () => {
  // The seeded worked example is the one cell that exercises every markdown
  // feature at once, which is why it is what this asserts against.
  const example = page.getByTestId("nb-list-item").filter({ hasText: "getting-started" });
  await expect(example).toBeVisible({ timeout: 15_000 });
  await expect(example).toHaveAttribute("data-example", "1");
  await example.click();
  await expect(page.getByTestId("nb-notebook")).toBeVisible({ timeout: 15_000 });

  const prose = page.getByTestId("nb-markdown").first();
  await expect(prose.locator("h1")).toHaveText("Getting started with TI-Toolbox notebooks");
  await expect(prose.locator("h2")).toHaveText("What it shows");
  await expect(prose.locator("ol li")).toHaveCount(2);
  await expect(prose.locator("em")).toHaveText("nothing to install");
  await expect(prose.locator("a")).toHaveAttribute("href", "https://idossha.github.io/TI-Toolbox/");

  // Maths: a display equation in its own band, and an inline one in the prose.
  await expect(prose.locator(".nb-math-block .katex-display")).toHaveCount(1);
  await expect(prose.locator(".katex")).not.toHaveCount(0);
  await expect(prose).not.toContainText("$$");
  // KaTeX actually laid it out — an unstyled stylesheet-less render is 0-high.
  const mathBox = (await prose.locator(".nb-math-block").boundingBox())!;
  expect(mathBox.height).toBeGreaterThan(16);

  // A fenced block is a <pre> in the MONO face, not prose.
  const code = prose.locator("pre.nb-code code");
  await expect(code).toHaveText("from tit import get_path_manager");
  const font = await code.evaluate((el) => getComputedStyle(el).fontFamily);
  expect(font).toMatch(/IBM Plex Mono|ui-monospace|Menlo|monospace/);

  // A GFM table, with the delimiter row's alignment applied.
  await expect(prose.locator("table th").first()).toHaveText("step");
  await expect(prose.locator("table td").nth(1)).toHaveCSS("text-align", "right");
});

test("shows an error output with its traceback rather than swallowing it", async () => {
  await newNotebook();
  await typeInCell(0, "undefined_name");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByTestId("nb-output-error").first()).toContainText("NameError", {
    timeout: 20_000,
  });
});

test("interrupts a running cell", async () => {
  await newNotebook();
  // The mock's one simulated long run (see its `kernelExecute`).
  await typeInCell(0, "sleep(30)");
  await page.keyboard.press("ControlOrMeta+Enter");

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

  await typeInCell(0, "print('round trip')");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByTestId("nb-output").first()).toContainText("round trip", { timeout: 20_000 });

  await page.getByTestId("nb-save").click();
  await expect(page.getByTestId("nb-save")).toHaveText("Saved");

  // A reload is the honest test of a round trip: the session's in-memory copy
  // is gone, so what comes back is what the server actually wrote.
  await page.reload();
  await gotoPage(page, "notebooks", "Notebooks");
  await page.getByTestId("nb-list-item").filter({ hasText: name }).click();
  await expect(page.getByTestId("nb-notebook")).toBeVisible({ timeout: 15_000 });
  await expect(codeCell(0)).toContainText("print('round trip')");
  await expect(page.getByTestId("nb-output").first()).toContainText("round trip");
});

test("lists, opens and deletes notebooks", async () => {
  const first = await newNotebook();
  await page.getByTestId("nb-new").click();
  // Two of the author's own, plus the seeded example.
  await expect(page.getByTestId("nb-list-item")).toHaveCount(3, { timeout: 15_000 });
  // The author's work sorts above the example, never below it.
  await expect(page.getByTestId("nb-list-item").last()).toHaveAttribute("data-example", "1");

  await page.getByTestId("nb-list-item").filter({ hasText: first }).click();
  await expect(page.getByTestId("nb-notebook")).toHaveAttribute("data-notebook", first);

  await page
    .locator("li", { has: page.getByTestId("nb-list-item").filter({ hasText: first }) })
    .getByRole("button", { name: `Delete ${first}` })
    .click();
  await expect(page.getByTestId("nb-list-item")).toHaveCount(2, { timeout: 15_000 });
});

test("Jupyter's command-mode keys act on the cell list", async () => {
  await newNotebook();
  const cells = page.locator('[data-testid="nb-cell"]');
  const before = await cells.count();

  await codeCell(0).click();
  // Escape leaves edit mode; `b` then inserts below. Both are only safe as
  // bare keystrokes because editing is modal.
  await page.keyboard.press("Escape");
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

test("a code cell is a real editor: Python is highlighted", async () => {
  await newNotebook();
  const cell = codeCell(0);
  // CodeMirror, not a textarea — the defect the maintainer reported was a
  // "plain monospace" cell with no colouring.
  await expect(page.getByTestId("nb-code-editor").first()).toBeVisible();
  await expect(page.locator('[data-cell-type="code"] textarea')).toHaveCount(0);

  await typeInCell(0, "def go(n):\n    return 'x' * n  # comment\n");

  // The lexer ran: keyword, string and comment each got their own token class,
  // and each resolves to a different colour.
  const keyword = cell.locator("span", { hasText: /^def$/ }).first();
  const comment = cell.locator(".cm-comment, span").filter({ hasText: "# comment" }).first();
  await expect(keyword).toBeVisible();
  const colours = await cell.evaluate((el) => {
    const seen = new Set<string>();
    for (const span of el.querySelectorAll("span")) {
      const colour = getComputedStyle(span).color;
      if (colour) seen.add(colour);
    }
    return [...seen];
  });
  // A textarea has exactly one colour; a highlighted cell has several.
  expect(colours.length).toBeGreaterThan(2);
  await expect(comment).toBeVisible();
});

test("completion comes from the kernel, on ⇥ and on typing", async () => {
  await newNotebook();
  // A kernel has to be up first: a keystroke must never start one.
  await typeInCell(0, "print('ready')");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByTestId("nb-output").first()).toContainText("ready", { timeout: 20_000 });
  // A second cell to complete in: the starter notebook ships exactly one.
  await page.getByRole("button", { name: "+ Code" }).click();
  await expect(page.locator('[data-testid="nb-cell"][data-cell-type="code"]')).toHaveCount(2);

  await typeInCell(1, "get_p");

  // Typing opens it: the matches came back over /ws/kernels, from the kernel's
  // own namespace, and both are there.
  const popup = page.locator(".cm-tooltip-autocomplete");
  await expect(popup).toBeVisible({ timeout: 15_000 });
  await expect(popup).toContainText("get_path_manager");
  await expect(popup).toContainText("get_project");

  // Let the round trip the LAST keystroke started settle before ⇥.
  //
  // `activateOnTyping` fires a query per character, so the popup can be showing
  // the answer to an earlier one while a newer is still in flight. ⇥ swallows
  // the key while a query is pending — deliberately, so it cannot indent into
  // the middle of a word the kernel is completing — and the accept would then
  // need a second press. A person presses again; a test has to wait.
  await page.waitForTimeout(500);

  // ⇥ accepts the selected option — Jupyter's gesture — and inserts what the
  // KERNEL said, over the range the kernel chose.
  await page.keyboard.press("Tab");
  await expect(codeCell(1)).toContainText("get_path_manager");
  await expect(popup).toHaveCount(0);
});

test("a dotted completion shows the member, and inserts the whole path", async () => {
  await newNotebook();
  await typeInCell(0, "print('ready')");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByTestId("nb-output").first()).toContainText("ready", { timeout: 20_000 });
  // A second cell to complete in: the starter notebook ships exactly one.
  await page.getByRole("button", { name: "+ Code" }).click();
  await expect(page.locator('[data-testid="nb-cell"][data-cell-type="code"]')).toHaveCount(2);

  await typeInCell(1, "catalog.subject_");
  const popup = page.locator(".cm-tooltip-autocomplete");
  await expect(popup).toBeVisible({ timeout: 15_000 });
  // The popup lists the MEMBER. The kernel returns `catalog.subject_ids` and
  // replaces the whole dotted expression, so showing the match verbatim would
  // make every option read "catalog.…" and be unreadable.
  await expect(popup).toContainText("subject_ids");
  await expect(popup).toContainText("subject_detail");
  // …and not one of them reads "catalog.…", which is the readability half.
  await expect(popup).not.toContainText("catalog.");
  // Let the round trip the LAST keystroke started settle before ⇥.
  //
  // `activateOnTyping` fires a query per character, so the popup can be showing
  // the answer to an earlier one while a newer is still in flight. ⇥ swallows
  // the key while a query is pending — deliberately, so it cannot indent into
  // the middle of a word the kernel is completing — and the accept would then
  // need a second press. A person presses again; a test has to wait.
  await page.waitForTimeout(500);

  // Accepting leaves the whole path in the cell: the range the option replaces
  // starts after `catalog.`, so the prefix the author typed stays put. Which of
  // the two is selected is CodeMirror's fuzzy ranking and not this app's
  // decision, so the assertion is on the shape rather than on one of them.
  await page.keyboard.press("Tab");
  await expect(codeCell(1)).toHaveText(/^catalog\.subject_(ids|detail)$/);
});

test("editor settings apply live and persist across a reload", async () => {
  await newNotebook();
  await expect(page.getByTestId("nb-code-editor").first()).toBeVisible();
  await expect(page.locator(".cm-gutters")).toHaveCount(0);

  await page.getByTestId("nb-settings-open").click();
  const panel = page.getByTestId("nb-settings");
  await expect(panel).toBeVisible();

  // Line numbers on, font size up: both reconfigure the live editor rather
  // than rebuilding it.
  await panel.getByTestId("nb-pref-lineNumbers").click();
  await expect(page.locator(".cm-gutters").first()).toBeVisible();
  await panel.getByRole("radio", { name: "16" }).click();
  await expect(page.getByTestId("nb-notebook")).toHaveAttribute("style", /--nb-font-size: 16px/);

  await page.keyboard.press("Escape");
  await page.reload();
  await gotoPage(page, "notebooks", "Notebooks");
  await page.getByTestId("nb-list-item").first().click();
  await expect(page.getByTestId("nb-code-editor").first()).toBeVisible({ timeout: 15_000 });
  // Persisted, per machine, like `app/executionPrefs.ts`.
  await expect(page.locator(".cm-gutters").first()).toBeVisible();
  await expect(page.getByTestId("nb-notebook")).toHaveAttribute("style", /--nb-font-size: 16px/);

  // Put it back, so the next spec starts from the documented defaults.
  await page.getByTestId("nb-settings-open").click();
  await page.getByTestId("nb-pref-reset").click();
  await expect(page.locator(".cm-gutters")).toHaveCount(0);
});

test("turning autocompletion off stops the round trip", async () => {
  await newNotebook();
  await typeInCell(0, "print('ready')");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByTestId("nb-output").first()).toContainText("ready", { timeout: 20_000 });
  // A second cell to complete in: the starter notebook ships exactly one.
  await page.getByRole("button", { name: "+ Code" }).click();
  await expect(page.locator('[data-testid="nb-cell"][data-cell-type="code"]')).toHaveCount(2);

  await page.getByTestId("nb-settings-open").click();
  await page.getByTestId("nb-settings").getByTestId("nb-pref-autocomplete").click();
  await page.keyboard.press("Escape");

  await typeInCell(1, "get_p");
  await page.keyboard.press("Tab");
  // Tab indents instead, and no popup appears.
  await expect(page.locator(".cm-tooltip-autocomplete")).toHaveCount(0);

  await page.getByTestId("nb-settings-open").click();
  await page.getByTestId("nb-pref-reset").click();
});

test("signature help opens on `(`, on ⇧⇥, and dismisses on Esc and past the `)`", async () => {
  await newNotebook();
  await typeInCell(0, "print('ready')");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByTestId("nb-output").first()).toContainText("ready", { timeout: 20_000 });
  await page.getByRole("button", { name: "+ Code" }).click();
  await expect(page.locator('[data-testid="nb-cell"][data-cell-type="code"]')).toHaveCount(2);

  // Typing the open paren asks the kernel. Nothing else does — a round trip per
  // keystroke is what the `(`-only trigger exists to avoid.
  await typeInCell(1, "get_path_manager(");
  const tip = page.getByTestId("nb-signature");
  await expect(tip).toBeVisible({ timeout: 15_000 });
  await expect(tip.locator(".nb-signature__sig")).toContainText("get_path_manager(");
  await expect(tip.locator(".nb-signature__doc")).toHaveText(
    "The mock kernel's answer for this name.",
  );
  // The docstring's SECOND paragraph is not in the tooltip: a summary, not a
  // document, or it covers the code it describes.
  await expect(tip).not.toContainText("second paragraph");
  // Nor are IPython's trailing fields.
  await expect(tip).not.toContainText("Type:");

  // It survives typing arguments — the call has not changed.
  await codeCell(1).pressSequentially("pm");
  await expect(tip).toBeVisible();

  // Esc dismisses the tooltip and does NOT leave edit mode: one Escape, one
  // meaning, and the cell keeps focus.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("nb-signature")).toHaveCount(0);
  await expect(page.locator(".cm-editor.cm-focused")).toHaveCount(1);

  // ⇧⇥ asks again explicitly, from inside the same call.
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByTestId("nb-signature")).toBeVisible({ timeout: 15_000 });

  // Typing past the closing paren dismisses it, because there is no longer a
  // call around the cursor.
  await codeCell(1).pressSequentially(")");
  await page.keyboard.press("End");
  await expect(page.getByTestId("nb-signature")).toHaveCount(0);

  // A second Escape, with nothing to dismiss, leaves edit mode as it always did.
  await page.keyboard.press("Escape");
  await expect(page.locator(".cm-editor.cm-focused")).toHaveCount(0);
});

test("signature help off means no tooltip and no round trip", async () => {
  await newNotebook();
  await typeInCell(0, "print('ready')");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByTestId("nb-output").first()).toContainText("ready", { timeout: 20_000 });

  await page.getByTestId("nb-settings-open").click();
  await page.getByTestId("nb-settings").getByTestId("nb-pref-signatureHelp").click();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "+ Code" }).click();
  await typeInCell(1, "get_path_manager(");
  await expect(page.getByTestId("nb-signature")).toHaveCount(0);

  await page.getByTestId("nb-settings-open").click();
  await page.getByTestId("nb-pref-reset").click();
});

test("the kernel pill is the status and the recovery", async () => {
  await newNotebook();
  const pill = page.getByTestId("nb-kernel-status");
  await expect(pill).toHaveAttribute("data-state", "off");

  // Clicking it with no kernel starts one — the state a user is actually in
  // when they press a button labelled with a restart icon.
  await pill.click();
  await expect(pill).toHaveAttribute("data-state", "idle", { timeout: 20_000 });
  await expect(pill).toContainText("SimNIBS + TI-Toolbox");

  await typeInCell(0, "print('alive')");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByTestId("nb-output").first()).toContainText("alive", { timeout: 20_000 });
});

test("the empty state offers the example, and opens it", async () => {
  // Nothing is open on arrival; the page says what a notebook here runs on and
  // gives the one action worth taking first.
  const empty = page.getByTestId("nb-notebook");
  await expect(empty).toHaveCount(0);
  const action = page.getByRole("button", { name: "Open the example" });
  await expect(action).toBeVisible({ timeout: 15_000 });
  await action.click();
  await expect(page.getByTestId("nb-notebook")).toHaveAttribute(
    "data-notebook",
    "examples/getting-started.ipynb",
    { timeout: 15_000 },
  );
});

test("⌘S saves from outside a cell, and leaving the page flushes", async () => {
  const name = await newNotebook();
  await typeInCell(0, "print('saved by cmd-s')");
  await expect(page.getByTestId("nb-save")).toHaveText("Save");

  // Focus is deliberately NOT in the editor: the editor has its own ⌘S, and
  // this is the page-level one that used to be missing.
  await page.getByTestId("nb-list").click();
  await page.keyboard.press("ControlOrMeta+s");
  await expect(page.getByTestId("nb-save")).toHaveText("Saved", { timeout: 15_000 });

  // Now the leave-flush: edit, navigate away before autosave fires, come back.
  await typeInCell(0, "print('flushed on leave')");
  await expect(page.getByTestId("nb-save")).toHaveText("Save");
  await gotoPage(page, "jobs", "Jobs");
  await expectPage(page, "jobs");
  await gotoPage(page, "notebooks", "Notebooks");
  await page.reload();
  await gotoPage(page, "notebooks", "Notebooks");
  await page.getByTestId("nb-list-item").filter({ hasText: name }).click();
  await expect(codeCell(0)).toContainText("print('flushed on leave')", { timeout: 15_000 });
});
