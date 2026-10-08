/**
 * The Assistant pane end to end (ARCHITECTURE §6), offscreen, against the mock server: the page
 * finds a CLI on PATH, starts it in a real host PTY in the project folder with the bundled plugin
 * flag and the session's server URL/token in its environment, carries keystrokes to it, reports its
 * exit, and shows the not-installed state for the other CLI.
 *
 * The CLI is a stand-in `claude` shell script, never the developer's real one: an automated run
 * searches only its own PATH (`assistantSearchPath`), and this spec's PATH holds the stand-in plus
 * /usr/bin:/bin, so `codex` is genuinely absent. `POST /api/__mock/project {host_path}` points the
 * session at a real temporary folder; the next launch's mock reset restores the fixture.
 */
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { connectLauncher, launchElectronApp } from "./_helpers";

const SERVER_URL = process.env.TIT_E2E_SERVER_URL ?? "http://127.0.0.1:8790";
const TOKEN = process.env.TIT_E2E_TOKEN ?? "mock-token";

let app: ElectronApplication | undefined;
let page: Page;

test.skip(process.platform === "win32", "the stand-in CLI is a POSIX shell script");
test.afterEach(async () => {
  await app?.close();
  app = undefined;
});

test("runs the user's CLI in a host terminal with the plugin and the session attached", async () => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "tit-assistant-")));
  const bin = join(root, "bin");
  const project = join(root, "project");
  const userData = join(root, "user-data");
  for (const dir of [bin, project, userData]) mkdirSync(dir);
  const claude = join(bin, "claude");
  writeFileSync(
    claude,
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
  chmodSync(claude, 0o755);

  // After the launch: `launchElectronApp` resets the mock, which restores the fixture's host_path.
  app = await launchElectronApp({ userDataDir: userData, env: { PATH: `${bin}:/usr/bin:/bin` } });
  const pointed = await fetch(`${SERVER_URL}/api/__mock/project`, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ host_path: project }),
  });
  expect(pointed.ok).toBe(true);
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1280, height: 900 });
  await connectLauncher(page, SERVER_URL, TOKEN);
  await expect(page).toHaveURL(new URL("/", SERVER_URL).href, { timeout: 45_000 });

  await page.getByRole("link", { name: "Assistant", exact: true }).click();
  await expect(page.getByTestId("assistant-page")).toBeVisible();
  await expect(page.getByText("TI-Toolbox never sees your credentials")).toBeVisible();

  await page.getByRole("button", { name: "Start Claude Code" }).click();
  const terminal = page.getByTestId("assistant-terminal-claude");
  await expect(terminal).toContainText("stand-in claude args=--plugin-dir ", { timeout: 15_000 });
  await expect(terminal).toContainText(`agent-plugin`);
  await expect(terminal).toContainText(`cwd=${project}`);
  await expect(terminal).toContainText(`server=${SERVER_URL} token=present`);

  await terminal.click();
  await page.keyboard.type("hello");
  await page.keyboard.press("Enter");
  await expect(terminal).toContainText("got:hello");
  await expect(terminal).toContainText("Claude Code exited with code 0");
  await expect(page.getByRole("button", { name: "Start Claude Code" })).toBeVisible();

  await page.getByRole("radio", { name: "Codex" }).click();
  await expect(page.getByText("Codex is not installed")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Codex" })).toBeDisabled();

  // The token reached the CLI's environment and nowhere in the app's own log.
  const mainLog = readFileSync(join(userData, "logs", "main.log"), "utf8");
  expect(mainLog).toContain("assistant: started claude");
  expect(mainLog).not.toContain(TOKEN);
});
