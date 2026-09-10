/**
 * The Electron-backed `StackHost` and the one `StackManager` the app runs on.
 *
 * `stack.ts` deliberately imports neither `electron` nor anything that does (`./log`, `./health`),
 * so that `scripts/dev.ts` can drive the *same* attach-or-start code under plain Node. This file is
 * where the Electron half is bound back on: it is the only module in the stack path that touches
 * `app`, and it exists so that adding an Electron dependency to the stack lifecycle is a visible
 * edit here rather than an invisible one inside `stack.ts` that breaks `npm run dev` at runtime
 * with a `TypeError: Cannot read properties of undefined (reading 'isPackaged')` — a plain Node
 * `require("electron")` returns the *path to the binary*, not the API surface.
 */
import { app, net, dialog } from "electron";
import { waitForHealth } from "./health";
import { log } from "./log";
import { createStackManager, type StackHost } from "./stack";

export const electronStackHost: StackHost = {
  // Getters, not captured values: `app.isPackaged`/`getAppPath()` are only meaningful once the app
  // object exists, and this module is imported at the top of `index.ts`, before `whenReady`.
  get isPackaged() {
    return app.isPackaged;
  },
  get appPath() {
    return app.getAppPath();
  },
  get resourcesPath() {
    return process.resourcesPath;
  },
  async chooseRunningContainer(containers, composeFile) {
    const action = process.env.TIT_LAUNCH_EXISTING;
    const selector = process.env.TIT_LAUNCH_CONTAINER;
    if (action) {
      if (!["attach", "recreate"].includes(action)) throw new Error("TIT_LAUNCH_EXISTING must be attach or recreate.");
      const matches = selector ? containers.filter((c) => c.Id === selector || c.Names.some((name) => name.replace(/^\//, "") === selector)) : containers;
      if (matches.length !== 1) throw new Error("Select exactly one running container with TIT_LAUNCH_CONTAINER.");
      return { action: action === "attach" ? "attach" : "replace", containerId: matches[0]!.Id };
    }
    const selected = containers.length === 1 ? 0 : (await dialog.showMessageBox({
      type: "question", message: "Select a running TI-Toolbox container",
      detail: "Choose the container to attach to or replace. Other containers remain unchanged.",
      buttons: [...containers.map((c) => `${c.Image} — ${c.Labels["tit.host_project_dir"] || c.Names[0]?.replace(/^\//, "")}`), "Cancel"],
      cancelId: containers.length, defaultId: containers.length,
    })).response;
    if (selected >= containers.length) return null;
    const container = containers[selected]!;
    const { response } = await dialog.showMessageBox({
      type: "question", message: `${container.Image} is already running`,
      detail: `Current project: ${container.Labels["tit.host_project_dir"] || "unknown (legacy session)"}\nImage: ${container.Image}\n\nAttach using its current project and configuration, or stop and remove it (interrupting its jobs) and create a new container from ${composeFile}. Project files and named volumes are preserved.`,
      buttons: ["Attach", "Recreate", "Cancel"], defaultId: 1, cancelId: 2,
    });
    return response === 2 ? null : { action: response === 0 ? "attach" : "replace", containerId: container.Id };
  },
  log,
  waitForHealth,
  async fetchJson(url, headers) {
    const res = await net.fetch(url, { headers, signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`GET ${url} failed with HTTP ${res.status}`);
    return await res.json();
  },
};

export const stack = createStackManager(electronStackHost);
