// Sandboxed preload: CJS, imports nothing but `electron`. Exposes `window.tit` (see
// src/shared/tit-bridge.d.ts). The token passed to `connect` goes straight to the main process.
import { contextBridge, ipcRenderer } from "electron";
import type {
  TitBridge,
  TitConnectArgs,
  TitSelectFileOptions,
  TitSaveFileOptions,
  TitSettings,
  TitStackEvent,
  TitStackStartResult,
  TitStackStatus,
  TitStackStopResult,
  TitViewerInfo,
  TitViewerOpenResult,
} from "../shared/tit-bridge";

const tit: TitBridge = {
  platform: () => process.platform,
  appVersion: () => ipcRenderer.invoke("tit:appVersion"),
  openExternal: (url: string) => ipcRenderer.invoke("tit:openExternal", String(url)),
  connect: (args?: TitConnectArgs) =>
    ipcRenderer.invoke("tit:connect", args ? { url: String(args.url), token: String(args.token) } : null),
  getSettings: () => ipcRenderer.invoke("tit:getSettings"),
  setSettings: (partial: Partial<TitSettings>) => ipcRenderer.invoke("tit:setSettings", partial),
  selectDirectory: () => ipcRenderer.invoke("tit:selectDirectory"),
  selectFile: (options?: TitSelectFileOptions) => ipcRenderer.invoke("tit:selectFile", options ?? {}),
  saveFile: (text: string, options?: TitSaveFileOptions) =>
    ipcRenderer.invoke("tit:saveFile", String(text), options ?? {}),
  openPath: (path: string) => ipcRenderer.invoke("tit:openPath", String(path)),
  showItemInFolder: (path: string) => ipcRenderer.invoke("tit:showItemInFolder", String(path)),
  notify: (title: string, body?: string) => ipcRenderer.invoke("tit:notify", String(title), body ? String(body) : undefined),
  stack: {
    start: (hostProjectDir: string): Promise<TitStackStartResult> => ipcRenderer.invoke("tit:stack:start", String(hostProjectDir)),
    stop: (): Promise<TitStackStopResult> => ipcRenderer.invoke("tit:stack:stop"),
    status: (): Promise<TitStackStatus> => ipcRenderer.invoke("tit:stack:status"),
    onEvent: (callback: (event: TitStackEvent) => void): (() => void) => {
      const listener = (_e: Electron.IpcRendererEvent, event: TitStackEvent) => callback(event);
      ipcRenderer.on("tit:stack:event", listener);
      return () => ipcRenderer.removeListener("tit:stack:event", listener);
    },
  },
  viewer: {
    probe: (): Promise<TitViewerInfo> => ipcRenderer.invoke("tit:viewer:probe"),
    open: (containerScenePath: string): Promise<TitViewerOpenResult> =>
      ipcRenderer.invoke("tit:viewer:open", String(containerScenePath)),
    setPath: (path: string): Promise<TitViewerInfo> => ipcRenderer.invoke("tit:viewer:setPath", String(path)),
  },
};

contextBridge.exposeInMainWorld("tit", tit);
