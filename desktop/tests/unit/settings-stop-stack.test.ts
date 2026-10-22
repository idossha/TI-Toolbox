/**
 * Settings ▸ Server ▸ "Stop Docker stack" (`window.tit.stack.stop()` from the connected page) closes
 * the project the way quitting and Close project do: running and queued jobs are confirmed and
 * cancelled before the container stops.
 *
 * The spec is `shared/quitPlan.ts`'s header — the running-jobs question "is now asked for EVERY
 * backend this app owns" — and `stack.ts`'s "Closing Electron stops its selected stack"; the
 * dialog copy ("1 active job", "Stop jobs and close project") is what `index.ts`'s close-project
 * path shows for Close project, pinned by `tests/e2e/launcher.spec.ts`. Runs the real `index.ts`
 * under the electron-mocked harness (`main-ipc-fakes.ts`); the jobs server and the stack are fakes
 * that record the order of what happened.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/settings-stop-stack.test.ts`.
 */
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { bootMain, cleanupMain, eventFrom, invoke, resetHarness, startProject, type FakeBrowserWindow, type HarnessState } from "./main-ipc-fakes";

vi.mock("electron", async () => (await import("./main-ipc-fakes")).electronModule());
vi.mock("../../src/main/jobsNotifier", async () => (await import("./main-ipc-fakes")).jobsNotifierModule());
vi.mock("../../src/main/stackHost", async () => (await import("./main-ipc-fakes")).stackHostModule());

let state: HarnessState;
let win: FakeBrowserWindow;
let dialogs: Array<{ message: string; buttons: string[]; detail: string }>;

/** Answer every native question with the button labelled `label`. */
function answer(label: string): void {
  state.dialog.showMessageBox.mockImplementation(async (...args: unknown[]) => {
    const options = args.at(-1) as { message: string; buttons: string[]; detail: string };
    dialogs.push(options);
    return { response: options.buttons.indexOf(label), checkboxChecked: false };
  });
}

beforeEach(async () => {
  state = resetHarness();
  dialogs = [];
  vi.stubEnv("TIT_E2E_OFFSCREEN", "1");
  for (const name of ["TIT_E2E_HEADED", "TIT_USER_DATA_DIR", "TIT_DEV_LAUNCHER", "TIT_DEV_PORT", "TIT_DEV_REPO_DIR", "TIT_DEV_SERVER_URL", "TIT_DEV_SERVER_TOKEN", "TIT_NATIVE_PROJECT_DIR", "TIT_LAUNCH_PROJECT_DIR", "TIT_LAUNCH_CONTAINER_ID", "ELECTRON_RENDERER_URL"]) vi.stubEnv(name, "");
  win = await bootMain();
  const dir = join(state.root, "project");
  mkdirSync(dir);
  await startProject(win, dir);
  state.events.length = 0;
});

afterEach(() => {
  cleanupMain();
  vi.unstubAllEnvs();
});

describe("Stop Docker stack from the connected app", () => {
  it("with a running job, asks first; Cancel keeps the container and the job", async () => {
    state.jobs.push({ id: "j1", state: "running" });
    answer("Cancel");
    const connectedUrl = win.webContents.mainFrame.url;

    const result = await invoke("tit:stack:stop", eventFrom(win));
    expect(result).toMatchObject({ ok: false });
    expect(dialogs).toHaveLength(1);
    expect(dialogs[0]!.message).toContain("1 active job");
    expect(dialogs[0]!.buttons).toContain("Stop jobs and close project");
    expect(state.stack.stop).not.toHaveBeenCalled();
    expect(state.events).not.toContain("fetch POST /api/jobs/j1/cancel");
    expect(state.jobs[0]!.state).toBe("running");
    expect(win.webContents.mainFrame.url).toBe(connectedUrl);
  });

  it("with a running job, confirming cancels it before the container stops, then returns to Overview", async () => {
    state.jobs.push({ id: "j1", state: "running" });
    answer("Stop jobs and close project");

    expect(await invoke("tit:stack:stop", eventFrom(win))).toEqual({ ok: true });
    expect(dialogs.map((d) => d.message)).toEqual([expect.stringContaining("1 active job")]);
    const cancel = state.events.indexOf("fetch POST /api/jobs/j1/cancel");
    const stop = state.events.indexOf("stack.stop");
    expect(cancel).toBeGreaterThanOrEqual(0);
    expect(stop).toBeGreaterThan(cancel);
    expect(state.stack.stop).toHaveBeenCalledTimes(1);
    expect(state.loads.at(-1)).toBe("app://launcher/");
  });

  it("with no active job, stops without a question and returns to Overview", async () => {
    state.jobs.push({ id: "done", state: "succeeded" });
    expect(await invoke("tit:stack:stop", eventFrom(win))).toEqual({ ok: true });
    expect(state.dialog.showMessageBox).not.toHaveBeenCalled();
    expect(state.events).toEqual(["fetch GET /api/jobs", "stack.stop"]);
    expect(state.loads.at(-1)).toBe("app://launcher/");
  });

  it("a server that cannot list its jobs still asks before stopping", async () => {
    state.jobs = "not a list" as unknown as HarnessState["jobs"];
    answer("Cancel");
    expect(await invoke("tit:stack:stop", eventFrom(win))).toMatchObject({ ok: false });
    expect(dialogs.map((d) => d.message)).toEqual(["Job status is unavailable"]);
    expect(state.stack.stop).not.toHaveBeenCalled();
  });
});
