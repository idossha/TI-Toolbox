import type { NotificationPrefs, NotifyResult } from "./jobNotifications";

/** Host capabilities exposed by the sandboxed preload. Browser sessions have no bridge.
 * All filesystem access and native execution are checked in the main process.
 */
export interface TitSettings {
  /** Last server URL the user connected to. The token is never stored. */
  lastServerUrl?: string;
  /** Last project directory picked, so the launcher/project picker can default to it. */
  lastProjectDir?: string;
  /** Set only by the native Apple GPU consent flow. */
  appleGpuEnabled?: boolean;
  /** Job-completion notifications (Settings ▸ Project ▸ Notifications); absent means the defaults. */
  notifications?: NotificationPrefs;
}

export interface TitConnectArgs {
  url: string;
  token: string;
}

export type TitConnectResult = { ok: true } | { ok: false; error: string };

export interface TitSelectFileOptions {
  filters?: { name: string; extensions: string[] }[];
}

export interface TitSaveFileOptions {
  /** Suggested file name, e.g. `"participants.tsv"`. Basename only; any directory is stripped. */
  defaultName?: string;
  filters?: { name: string; extensions: string[] }[];
}

export type TitSaveFileResult =
  | { ok: true; path: string }
  | { ok: false; canceled: true }
  | { ok: false; canceled?: false; reason: string };

export type TitStackStartResult = { ok: true; attached: boolean } | { ok: false; error: string };
export type TitStackStopResult = { ok: true } | { ok: false; error: string };

export interface TitStackStatus {
  running: boolean;
  hostProjectDir?: string;
  port?: number;
  /** `docker ps` name of the container this app started or attached to. */
  containerName?: string;
  /** Image reference the container runs, tag included. */
  image?: string;
  /** Docker's own healthcheck verdict; `"none"` when the image declares no healthcheck. */
  health?: "starting" | "healthy" | "unhealthy" | "none";
}

/** Progress/lifecycle events from `stack.start`/`stack.stop`, forwarded live to the renderer. */
export type TitStackEvent =
  | { type: "progress"; stage: string; message: string }
  | { type: "started"; port: number; attached: boolean }
  | { type: "stopped" }
  | { type: "error"; message: string };

export interface TitStackBridge {
  /** Confirm and open a destination; without one, end the session and return to Overview. */
  switchProject(hostProjectDir?: string): Promise<TitStackStopResult>;
  /**
   * Discover-or-start the Docker stack for `hostProjectDir` and load its session (attach-or-start).
   * Launcher-only (ra_14 finding 4) — a server-served page must not be able to mount an arbitrary
   * host directory (plus docker.sock) into a fresh root container.
   */
  start(hostProjectDir: string): Promise<TitStackStartResult>;
  /**
   * Stop and remove the currently-attached stack's container, if any. Callable from the launcher
   * *and* from the connected app (Settings -> Docker): the page that calls it is served by the
   * container it stops, so it can only end its own session — no other project, no host path, no
   * new mount. Stopping from a server-served page returns the window to the launcher.
   */
  stop(): Promise<TitStackStopResult>;
  status(): Promise<TitStackStatus>;
  /** Subscribe to live progress; returns an unsubscribe function. */
  onEvent(callback: (event: TitStackEvent) => void): () => void;
}

export interface TitFastSurferStatus {
  preferenceEnabled: boolean;
  supported: boolean;
  installed: boolean;
  enabled: boolean;
  installing: boolean;
  directory?: string;
  error?: string;
  project?: string;
}

export interface TitFastSurferBridge {
  status(): Promise<TitFastSurferStatus>;
  /** Native consent and project validation happen in main; no renderer-supplied paths. */
  enable(): Promise<TitFastSurferStatus>;
  disable(): Promise<TitFastSurferStatus>;
}

export interface TitNativeTetravoxStatus {
  /** Installed native application advertises the live scene request protocol. */
  supportsSceneSave?: boolean;
  /** Always TI-Toolbox's own copy: the only TetraVox the app ever launches. */
  source?: "managed";
  executable?: string;
  supported: boolean;
  installed: boolean;
  installing: boolean;
  version: string;
  directory: string;
  error?: string;
}

export interface TitNativeTetravoxProgress {
  phase: "download" | "install" | "idle";
  received?: number;
  total?: number;
}

export interface TitBridge {
  /** Save the live native scene into the active project; the renderer supplies a name, never a path. */
  previewNativeTetravoxScene?(path: string): Promise<{ ok: boolean; reason?: string }>;
  saveNativeTetravoxScene?(name: string): Promise<{ ok: boolean; path?: string; reason?: string; cancelled?: boolean }>;
  nativeTetravoxStatus?(): Promise<TitNativeTetravoxStatus>;
  installNativeTetravox?(): Promise<TitNativeTetravoxStatus>;
  /** Replace TI-Toolbox's TetraVox with the newest official release; refused while it is open. */
  updateNativeTetravox?(): Promise<TitNativeTetravoxStatus>;
  /** The newest official TetraVox release, and whether it is newer than TI-Toolbox's copy. */
  checkNativeTetravoxUpdate?(): Promise<{ latest: string; newer: boolean }>;
  /** Initial setup progress. Returns an unsubscribe function. */
  onNativeTetravoxProgress?(listener: (progress: TitNativeTetravoxProgress) => void): () => void;
  /** Container scene path in the active project, or empty to open the application. */
  openNativeTetravox?(path: string): Promise<{ ok: boolean; reason?: string; cancelled?: boolean; status?: "launch-requested" }>;

  /** `process.platform` of the host. */
  platform(): NodeJS.Platform;
  /** Version of the desktop shell (package.json), not of the toolbox image. */
  appVersion(): Promise<string>;
  /** Open an http(s)/mailto URL in the host's default browser (scheme-checked in main). */
  openExternal(url: string): Promise<void>;
  /**
   * With arguments: wait for `<url>/api/health` (only allowed from the launcher page) and load
   * the session URL in this window. Without arguments: return to the launcher page.
   */
  connect(args?: TitConnectArgs): Promise<TitConnectResult>;
  getSettings(): Promise<TitSettings>;
  /**
   * Launcher-only (ra_14 finding 4) — see the numbered list above — except `notifications`, the
   * one key the connected app may also write (it seeds nothing and mounts nothing).
   */
  setSettings(partial: Partial<TitSettings>): Promise<TitSettings>;
  /**
   * Host directory picker for project selection, including switching. Requires an explicit native
   * picker selection; its result is a raw host path (`stack.start` needs one), never mapped into a
   * project — unlike `selectFile`, below.
   */
  selectDirectory(): Promise<string | undefined>;
  /**
   * Host file picker (`PathInput` `onBrowse` for a file field, ra_13 finding 8). Callable from any
   * page — the picked host path is mapped through the known project mount (`stack.getCurrent()`'s
   * mount, or `GET /api/project`'s `host_path`) before it is returned, so callers only ever get a
   * *container* path. Resolves to `undefined` both when the user cancels the dialog and when the
   * picked path falls outside every known mount (the reason is logged in main, not surfaced here —
   * there is no secret in a "no mount" case, only a path the caller has no way to use anyway).
   */
  selectFile(options?: TitSelectFileOptions): Promise<string | undefined>;
  /**
   * Save renderer-produced **text** to a host file the user picks.
   *
   * This exists because a renderer cannot save a file on its own here: an `<a download>` on a
   * `blob:` URL needs a
   * download handler, and this app has none, so the click did nothing at all and reported
   * success. The dialog is the *only* thing that decides where the bytes land: the renderer names
   * a suggested basename and never a directory, so this cannot be used to write to a path of the
   * renderer's choosing. Text only, by design — there is no binary path here to abuse.
   */
  saveFile(text: string, options?: TitSaveFileOptions): Promise<TitSaveFileResult>;
  /**
   * Open a path (as given by the server — a container path when a project is mounted, mapped to
   * the host path internally) with the OS default application. Host<->container mapping prefers
   * the stack this app itself started (`stack.getCurrent()`'s mount); when there is none (e.g. a
   * manually-typed server URL), main falls back to `GET /api/project`'s own `host_path` (fetched
   * with the bearer token, never exposed to the renderer). A path containing a literal `.`/`..`
   * segment, or one that does not map into a known mount, is refused outright — `{ok:false,
   * reason}` — rather than opened unresolved (ra_14 finding 3); `reason` is safe to show the user
   * (it never echoes the original path or any secret). `{ok:true}` means `shell.openPath` reported
   * no error; a resolved-but-nonexistent path still comes back as `{ok:false, reason}` with the
   * OS's own error text.
   */
  openPath(path: string): Promise<{ ok: boolean; reason?: string }>;
  /** Reveal a path in Finder/Explorer/the file manager — same mapping and rejection rules as `openPath`. */
  showItemInFolder(path: string): Promise<{ ok: boolean; reason?: string }>;
  /**
   * Show a native desktop notification and report what the OS said: shown, or why not (with a
   * one-line fix when macOS permission or the dev Electron's signature is the likely cause).
   */
  notify(title: string, body?: string, silent?: boolean): Promise<NotifyResult>;
  /**
   * Main asks this window to play a job banner's TI-Toolbox sound (main has no audio API). `sound`
   * is untrusted text: the player ignores anything not in `TI_SOUNDS`. Returns the unsubscribe.
   */
  onNotificationSound(listener: (sound: string, failed: boolean) => void): () => void;
  stack: TitStackBridge;
  fastsurfer?: TitFastSurferBridge;
}

declare global {
  interface Window {
    tit?: TitBridge;
  }
}
