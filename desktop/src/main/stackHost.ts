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
import { app, net } from "electron";
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
  log,
  waitForHealth,
  async fetchJson(url, headers) {
    const res = await net.fetch(url, { headers, signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`GET ${url} failed with HTTP ${res.status}`);
    return await res.json();
  },
};

export const stack = createStackManager(electronStackHost);
