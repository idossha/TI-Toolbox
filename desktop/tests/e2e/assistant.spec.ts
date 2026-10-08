/**
 * The Assistant pane end to end (ARCHITECTURE §6), offscreen, against the mock server: the page
 * finds a CLI on PATH, starts it in a real host PTY in the project folder with the bundled plugin
 * flag and the session's server URL/token in its environment, carries keystrokes to it, reports its
 * exit, and shows the not-installed state for the other CLI. Its Effort and Model menus decide the
 * flags the stand-in receives (Low effort on Sonnet by default, then what the user chose). The second test pins the terminal's
 * geometry: the grid xterm draws and the size the PTY is told both fit the card exactly, above the
 * jobs rail, at several window sizes, in both themes, with the rail expanded too.
 *
 * The CLI is a stand-in `claude`, never the developer's real one: an automated run searches only
 * its own PATH (`assistantSearchPath`), and this spec's PATH holds the stand-in plus /usr/bin:/bin,
 * so `codex` is genuinely absent. `POST /api/__mock/project {host_path}` points the session at a
 * real temporary folder; the next launch's mock reset restores the fixture.
 *
 * The terminal draws on a WebGL canvas, so its text is read from xterm's buffer, which an e2e build
 * (`VITE_SCENE_HOOKS=1`) hangs on the host element as `xterm`. Screenshots of the layout test land
 * in `TIT_E2E_ARTIFACTS` as `assistant-<theme>-<w>x<h>[-rail].png` for review.
 */
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import type { Terminal } from "@xterm/xterm";
import { connectLauncher, launchElectronApp, setTheme } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";
const ARTIFACTS = process.env.TIT_E2E_ARTIFACTS ?? join(__dirname, "artifacts");

let app: ElectronApplication | undefined;
let page: Page;

test.skip(process.platform === "win32", "the stand-in CLI is a POSIX script");
test.afterEach(async () => {
  await app?.close();
  app = undefined;
});

/** A temporary root with bin/, project/ and user-data/, and `claude` written into bin/. */
function standIn(script: string) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "tit-assistant-")));
  const bin = join(root, "bin");
  const project = join(root, "project");
  const userData = join(root, "user-data");
  for (const dir of [bin, project, userData]) mkdirSync(dir);
  writeFileSync(join(bin, "claude"), script);
  chmodSync(join(bin, "claude"), 0o755);
  return { bin, project, userData };
}

async function openAssistant(dirs: { bin: string; project: string; userData: string }, viewport = { width: 1280, height: 900 }) {
  // After the launch: `launchElectronApp` resets the mock, which restores the fixture's host_path.
  app = await launchElectronApp({ userDataDir: dirs.userData, env: { PATH: `${dirs.bin}:/usr/bin:/bin` } });
  const pointed = await fetch(`${SERVER_URL}/api/__mock/project`, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ host_path: dirs.project }),
  });
  expect(pointed.ok).toBe(true);
  page = await app.firstWindow();
  await page.setViewportSize(viewport);
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });
  await page.getByRole("link", { name: "Assistant", exact: true }).click();
  await expect(page.getByTestId("assistant-page")).toBeVisible();
}

type Host = HTMLElement & { xterm?: Terminal };

/** The whole buffer, scrollback included, with soft-wrapped rows joined back into one line. */
const terminalText = () =>
  page.evaluate(() => {
    const term = (document.querySelector('[data-testid="assistant-terminal-claude"]') as Host | null)?.xterm;
    if (!term) return "";
    const buffer = term.buffer.active;
    let text = "";
    for (let i = 0; i < buffer.length; i++) {
      const line = buffer.getLine(i);
      if (!line) continue;
      text += (line.isWrapped || i === 0 ? "" : "\n") + line.translateToString(true);
    }
    return text;
  });

test("runs the user's CLI in a host terminal with the plugin and the session attached", async () => {
  const dirs = standIn(
    [
      "#!/bin/sh",
      'if [ "$1" = auth ]; then exit 0; fi',
      'printf "stand-in claude args=%s\\r\\n" "$*"',
      'printf "cwd=%s server=%s token=%s\\r\\n" "$PWD" "$TIT_SERVER_URL" "${TIT_SERVER_TOKEN:+present}"',
      "read line",
      'printf "got:%s\\r\\n" "$line"',
      "",
    ].join("\n"),
  );
  await openAssistant(dirs);
  await expect(page.getByText("TI-Toolbox never sees your credentials")).toBeVisible();
  await expect(page.getByText("Not started")).toBeVisible();

  await page.getByRole("button", { name: "Start Claude Code" }).click();
  await expect.poll(terminalText, { timeout: 15_000 }).toContain("stand-in claude args=--plugin-dir ");
  await expect(page.getByText("Running", { exact: true })).toBeVisible();
  const text = await terminalText();
  expect(text).toContain("agent-plugin");
  expect(text).toMatch(/args=--plugin-dir \S+ --effort low --model sonnet\r?\n?$/m);
  expect(text).toContain(`cwd=${dirs.project}`);
  expect(text).toContain(`server=${SERVER_URL} token=present`);

  // Clicking the card focuses the terminal: the keystrokes reach the CLI.
  await page.getByTestId("assistant-terminal-claude").click();
  await page.keyboard.type("hello");
  await page.keyboard.press("Enter");
  await expect.poll(terminalText).toContain("got:hello");
  await expect.poll(terminalText).toContain("Claude Code exited with code 0");
  await expect(page.getByText("Exited (code 0)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Claude Code" })).toBeVisible();

  // A choice is remembered and reaches the next start's flags.
  await page.getByRole("combobox", { name: "Effort" }).click();
  await page.getByRole("option", { name: "High" }).click();
  await page.getByRole("combobox", { name: "Model" }).click();
  await page.getByRole("option", { name: "Haiku" }).click();
  await page.getByRole("button", { name: "Start Claude Code" }).click();
  await expect.poll(terminalText, { timeout: 15_000 }).toContain("--effort high --model haiku");

  await page.getByRole("radio", { name: "Codex" }).click();
  await expect(page.getByText("Codex is not installed")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Codex" })).toBeDisabled();

  // The token reached the CLI's environment and nowhere in the app's own log.
  const mainLog = readFileSync(join(dirs.userData, "logs", "main.log"), "utf8");
  expect(mainLog).toContain("assistant: started claude");
  expect(mainLog).not.toContain(TOKEN);
});

/**
 * A Claude Code–shaped screen: the block-glyph logo, a transcript longer than any window (grey
 * highlight rows, every ANSI colour, URLs), then a full-width input box and the status line on the
 * terminal's last row, which states the size the PTY reports. Node by absolute path, since the
 * spec's PATH has no node on it.
 */
const CLAUDE_LIKE = [
  `#!${process.execPath}`,
  'if (process.argv[2] === "auth") process.exit(0);',
  "const out = process.stdout;",
  'const O = "\\x1b[38;2;215;119;87m", R = "\\x1b[0m";',
  'let text = ` ${O}▐▛███▜▌${R}   Claude Code v2.1.293\\r\\n${O}▝▜█████▛▘${R}  stand-in · TI-Toolbox e2e\\r\\n  ${O}▘▘ ▝▝${R}    ${process.cwd()}\\r\\n\\r\\n`;',
  "for (let i = 1; i <= 120; i++) {",
  '  if (i % 10 === 1) text += `\\x1b[48;2;55;55;55m\\x1b[38;2;255;255;255m > user prompt ${i} \\x1b[0m\\r\\n`;',
  '  else text += `⏺ \\x1b[1mStep ${i}\\x1b[0m read https://example.org/docs/${i} \\x1b[2m(dim detail)\\x1b[0m\\r\\n  ⎿  \\x1b[30mblack\\x1b[0m \\x1b[31mred\\x1b[0m \\x1b[32mgreen\\x1b[0m \\x1b[33myellow\\x1b[0m \\x1b[34mblue\\x1b[0m \\x1b[35mmagenta\\x1b[0m \\x1b[36mcyan\\x1b[0m \\x1b[37mwhite\\x1b[0m \\x1b[90mgrey\\x1b[0m \\x1b[97mbright-white\\x1b[0m\\r\\n`;',
  "}",
  // Like the real CLI, a resize clears the screen and scrollback and draws everything again.
  "const draw = () => {",
  "  const cols = out.columns, rows = out.rows;",
  '  out.write(`\\x1b[2J\\x1b[3J\\x1b[H${text}\\r\\n╭${"─".repeat(cols - 2)}╮\\r\\n│ > ${" ".repeat(cols - 5)}│\\r\\n╰${"─".repeat(cols - 2)}╯\\r\\n  \\x1b[2m-- INSERT --\\x1b[0m \\x1b[38;2;175;135;255m▸▸ auto mode on\\x1b[0m \\x1b[2m(shift+tab to cycle)\\x1b[0m  rows=${rows} cols=${cols}`);',
  "};",
  "draw();",
  'out.on("resize", draw);',
  "process.stdin.resume();",
  "",
].join("\n");

/** Every box the fit depends on, plus what the CLI drew on the terminal's last two rows. */
const geometry = () =>
  page.evaluate(() => {
    const host = document.querySelector('[data-testid="assistant-terminal-claude"]') as Host;
    const term = host.xterm!;
    const box = (el: Element | null) => {
      const r = el!.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, width: r.width, height: r.height };
    };
    const buffer = term.buffer.active;
    const row = (i: number) => buffer.getLine(buffer.viewportY + i)?.translateToString(true) ?? "";
    const shell = document.querySelector(".shell-content") as HTMLElement;
    const assistant = document.querySelector('[data-testid="assistant-page"]') as HTMLElement;
    return {
      renderer: host.dataset.renderer,
      rows: term.rows,
      cols: term.cols,
      screen: box(host.querySelector(".xterm-screen")),
      host: box(host),
      card: box(host.parentElement),
      rail: box(document.querySelector(".jobs-rail")),
      viewport: { width: innerWidth, height: innerHeight },
      lastRow: row(term.rows - 1),
      boxBottom: row(term.rows - 2),
      overflow: {
        shellY: shell.scrollHeight - shell.clientHeight,
        shellX: shell.scrollWidth - shell.clientWidth,
        pageX: document.documentElement.scrollWidth - innerWidth,
        assistantX: assistant.scrollWidth - assistant.clientWidth,
      },
    };
  });

async function expectFits(label: string) {
  // Settled: the debounced fit has run (the grid is no taller than its host and no shorter by a
  // row) and the CLI has redrawn for the size the PTY was then sent. A timeout here is the defect.
  await expect
    .poll(async () => {
      const g = await geometry();
      const cell = g.screen.height / g.rows;
      return g.screen.height <= g.host.height + 0.5 && g.host.height - g.screen.height < cell && g.lastRow.includes(`rows=${g.rows} cols=${g.cols}`);
    }, { message: `${label}: the grid settled at the host's size and the CLI redrew for it`, timeout: 10_000 })
    .toBe(true);
  const g = await geometry();
  const cell = { height: g.screen.height / g.rows, width: g.screen.width / g.cols };
  const slack = 0.5; // sub-pixel rounding of fractional device-pixel cells
  // The grid fits its host, the host fits the card, the card ends above the rail, the rail is on screen.
  expect(g.rows * cell.height, `${label}: rows*cellHeight within the host`).toBeLessThanOrEqual(g.host.height + slack);
  expect(g.screen.top, label).toBeGreaterThanOrEqual(g.host.top - slack);
  expect(g.screen.bottom, label).toBeLessThanOrEqual(g.host.bottom + slack);
  expect(g.screen.right, label).toBeLessThanOrEqual(g.host.right + slack);
  expect(g.host.bottom, label).toBeLessThanOrEqual(g.card.bottom);
  expect(g.card.bottom, `${label}: card above the jobs rail`).toBeLessThanOrEqual(g.rail.top);
  expect(g.rail.bottom, label).toBeLessThanOrEqual(g.viewport.height + slack);
  // Exact: no spare row the fit left unused, and no partial row.
  expect(g.host.bottom - g.screen.bottom, `${label}: less than one row spare`).toBeLessThan(cell.height);
  // The last row is the status line and the row above it the box's closing edge, whole: the PTY's
  // width is the terminal's width, so the corner is in the last column rather than wrapped or cut.
  expect(g.lastRow).toContain("-- INSERT --");
  expect(g.boxBottom).toMatch(/^╰─+╯$/);
  expect(g.boxBottom.length).toBe(g.cols);
  // Nothing scrolls the page or spills sideways.
  expect(g.overflow, `${label}: no page overflow`).toEqual({ shellY: 0, shellX: 0, pageX: 0, assistantX: 0 });
  if (process.platform === "darwin" || process.env.CI) expect(g.renderer, "WebGL draws the block glyphs").toBe("webgl");
}

test("the terminal's rows fit the card exactly, above the jobs rail, at every size and in both themes", async () => {
  test.setTimeout(120_000);
  await openAssistant(standIn(CLAUDE_LIKE));
  await page.getByRole("button", { name: "Start Claude Code" }).click();
  await expect.poll(terminalText, { timeout: 15_000 }).toContain("Claude Code v2.1.293");

  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    for (const [width, height] of [[1280, 900], [1024, 680], [1680, 1050]] as const) {
      await page.setViewportSize({ width, height });
      await expectFits(`${theme} ${width}x${height}`);
      await page.screenshot({ path: join(ARTIFACTS, `assistant-${theme}-${width}x${height}.png`) });
    }
    // The top of the scrollback: the logo's block glyphs, for review.
    await page.setViewportSize({ width: 1280, height: 900 });
    await expectFits(`${theme} 1280x900 again`);
    await page.evaluate(() => (document.querySelector('[data-testid="assistant-terminal-claude"]') as Host).xterm!.scrollToTop());
    await page.screenshot({ path: join(ARTIFACTS, `assistant-${theme}-logo.png`) });
    await page.evaluate(() => (document.querySelector('[data-testid="assistant-terminal-claude"]') as Host).xterm!.scrollToBottom());
  }

  // The rail expands into the content column: the terminal shrinks with it and still fits.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "Expand jobs rail" }).click();
  await expectFits("rail expanded");
  await page.screenshot({ path: join(ARTIFACTS, "assistant-dark-1280x900-rail.png") });
});

test("the effort and model menus fit the header without wrapping, in both themes", async () => {
  test.setTimeout(90_000);
  await openAssistant(standIn('#!/bin/sh\nif [ "$1" = auth ]; then exit 0; fi\nsleep 60\n'), { width: 1024, height: 700 });
  await expect(page.getByRole("combobox", { name: "Effort" })).toBeVisible();
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    for (const width of [1024, 1440]) {
      await page.setViewportSize({ width, height: 700 });
      // Measured once the resize has settled: right after 1440 -> 1024 the row reads 5px wider
      // than its box for a frame (seen only on the dark pass, the only one that shrinks into 1024).
      await expect(async () => {
        const rows = await page.evaluate(() =>
          [".assistant-toolbar", ".assistant-hints"].map((selector) => {
            const row = document.querySelector(selector)!;
            const box = row.getBoundingClientRect();
            return {
              selector,
              height: box.height,
              overflow: row.scrollWidth - row.clientWidth,
              // Every child inside the row, and one line: nothing wrapped under another.
              outside: [...row.children].filter((el) => el.getBoundingClientRect().right > box.right + 0.5).length,
            };
          }),
        );
        const truncated = await page.evaluate(() =>
          ["Effort", "Model"].map((name) => {
            const value = document.querySelector(`button[aria-label="${name}"] .picker-value`)!;
            // scrollWidth reads 0 for this flex item: compare the text's own width instead.
            const text = document.createRange();
            text.selectNodeContents(value);
            return Math.max(0, Math.round(text.getBoundingClientRect().width - value.getBoundingClientRect().width));
          }),
        );
        for (const row of rows) {
          expect(row.height, `${theme} ${width} ${row.selector}: one 28px line`).toBeLessThanOrEqual(28);
          expect(row.overflow, `${theme} ${width} ${row.selector}: nothing spills out`).toBeLessThanOrEqual(0);
          expect(row.outside, `${theme} ${width} ${row.selector}: every control inside`).toBe(0);
        }
        expect(truncated, `${theme} ${width}: both menus show their whole value`).toEqual([0, 0]); // ellipsis would make the range wider than its box
      }).toPass({ timeout: 5_000 });
      await page.screenshot({ path: join(ARTIFACTS, `assistant-effort-${theme}-${width}.png`), clip: { x: 0, y: 0, width, height: 140 } });
    }
  }

  // Running, with a change waiting for a restart: the row is at its widest and still one line.
  await page.setViewportSize({ width: 1024, height: 700 });
  await page.getByRole("button", { name: "Start Claude Code" }).click();
  await expect(page.getByText("Running", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Effort" }).click();
  await page.getByRole("option", { name: "High" }).click();
  await expect(page.getByText("Applies on restart")).toBeVisible();
  const widest = await page.evaluate(() =>
    [".assistant-toolbar", ".assistant-hints"].map((selector) => {
      const row = document.querySelector(selector)!;
      const right = row.getBoundingClientRect().right;
      return { height: row.getBoundingClientRect().height, overflow: row.scrollWidth - row.clientWidth, outside: [...row.children].filter((el) => el.getBoundingClientRect().right > right + 0.5).length };
    }),
  );
  await page.screenshot({ path: join(ARTIFACTS, "assistant-effort-dark-1024-restart.png"), clip: { x: 0, y: 0, width: 1024, height: 140 } });
  for (const row of widest) expect(row).toEqual({ height: 28, overflow: 0, outside: 0 });
});

/**
 * Paths the CLI prints are links (ARCHITECTURE §5 `assistant.openPath`): a project path, absolute
 * or relative, gets xterm's hover pointer; a path outside the project does not; a click on one that
 * does not exist says so; main refuses `..` out of the project. Automated runs validate and never
 * open Finder/Explorer (`mayShowSystemUi`). Hover screenshot: `TIT_E2E_ARTIFACTS/assistant-path-links.png`.
 */
test("a project path the CLI prints is a link main checks against the project folder", async () => {
  const dirs = standIn(
    [
      "#!/bin/sh",
      'if [ "$1" = auth ]; then exit 0; fi',
      'printf "Wrote %s/derivatives/SimNIBS/sub-CHN/flex-search/insula/opt.json\\r\\n" "$PWD"',
      'printf "Relative: derivatives/SimNIBS/sub-CHN/flex-search/insula and derivatives/missing.nii.gz\\r\\n"',
      'printf "Outside: /etc/hosts\\r\\n"',
      "read line",
      "",
    ].join("\n"),
  );
  const run = join(dirs.project, "derivatives", "SimNIBS", "sub-CHN", "flex-search", "insula");
  mkdirSync(run, { recursive: true });
  writeFileSync(join(run, "opt.json"), "{}");
  await openAssistant(dirs);
  await page.getByRole("button", { name: "Start Claude Code" }).click();
  await expect.poll(terminalText, { timeout: 15_000 }).toContain("Outside: /etc/hosts");

  /** The screen point over the third character of *needle* (viewport rows; cell size from the screen box). */
  const pointAt = (needle: string) =>
    page.evaluate((needle) => {
      const host = document.querySelector('[data-testid="assistant-terminal-claude"]') as Host;
      const term = host.xterm!;
      const screen = host.querySelector(".xterm-screen")!.getBoundingClientRect();
      const buffer = term.buffer.active;
      for (let row = 0; row < term.rows; row++) {
        const col = buffer.getLine(buffer.viewportY + row)?.translateToString(true).indexOf(needle) ?? -1;
        if (col >= 0) return { x: screen.left + ((col + 2.5) * screen.width) / term.cols, y: screen.top + ((row + 0.5) * screen.height) / term.rows };
      }
      throw new Error(`${needle} is not on screen`);
    }, needle);
  const pointer = () => page.evaluate(() => !!document.querySelector('[data-testid="assistant-terminal-claude"] .xterm-cursor-pointer'));
  const hover = async (needle: string) => {
    const { x, y } = await pointAt(needle);
    await page.mouse.move(x, y, { steps: 4 });
  };
  const click = async (needle: string) => {
    const { x, y } = await pointAt(needle);
    await page.mouse.click(x, y);
  };

  await hover(`${dirs.project}/derivatives`);
  await expect.poll(pointer).toBe(true);
  await hover("/etc/hosts");
  await expect.poll(pointer).toBe(false);
  await hover("derivatives/SimNIBS/sub-CHN/flex-search/insula and");
  await expect.poll(pointer).toBe(true);
  // Offscreen capture shrinks the WebGL text canvas (the other assistant shots show it too), so the
  // review shot is taken after a forced context loss, on xterm's DOM fallback, still hovering.
  await page.evaluate(() => {
    const canvas = [...document.querySelectorAll('[data-testid="assistant-terminal-claude"] canvas')].find((c) => (c as HTMLCanvasElement).getContext("webgl2"));
    ((canvas as HTMLCanvasElement).getContext("webgl2")!.getExtension("WEBGL_lose_context"))!.loseContext();
  });
  await expect(page.getByTestId("assistant-terminal-claude")).toHaveAttribute("data-renderer", "dom");
  // Another cell of the same link: xterm skips a move that stays in the cell it last resolved.
  await hover("SimNIBS/sub-CHN/flex-search/insula and");
  await expect.poll(pointer).toBe(true);
  mkdirSync(ARTIFACTS, { recursive: true });
  await page.getByTestId("assistant-terminal-claude").screenshot({ path: join(ARTIFACTS, "assistant-path-links.png") });

  // A real folder is accepted without a word (offscreen: validated, not opened); a missing file is refused aloud.
  await click("derivatives/SimNIBS/sub-CHN/flex-search/insula and");
  await click("derivatives/missing.nii.gz");
  await expect(page.getByText("Could not open derivatives/missing.nii.gz")).toBeVisible();
  await expect(page.getByText(/Could not open derivatives\/SimNIBS/)).toHaveCount(0);

  const asked = (path: string) => page.evaluate((path) => window.tit!.assistant!.openPath(path), path);
  expect(await asked("derivatives/SimNIBS/sub-CHN/flex-search/insula/opt.json")).toEqual({ ok: true });
  expect(await asked(join(run, "opt.json"))).toEqual({ ok: true });
  expect(await asked("../user-data")).toEqual({ ok: false, error: "../user-data is outside the project folder." });
  expect(await asked("/etc/hosts")).toMatchObject({ ok: false });
});
