import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mkdtempSync, rmSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const location = vi.hoisted(() => ({ directory: "" }));
vi.mock("electron", () => ({ app: { getPath: () => location.directory } }));
import { readSettings, updateSettings, setAppleGpuEnabled } from "./settings";

describe("user Apple GPU preference", () => {
  beforeEach(() => { location.directory = mkdtempSync(join(tmpdir(), "tit-user-settings-")); });
  afterEach(() => rmSync(location.directory, { recursive: true, force: true }));
  it("is off until native consent and survives project preference changes", () => {
    expect(readSettings().appleGpuEnabled).toBeUndefined();
    setAppleGpuEnabled(true);
    updateSettings({ lastProjectDir: "/project-a" });
    updateSettings({ lastProjectDir: "/project-b" });
    expect(readSettings()).toMatchObject({ appleGpuEnabled: true, lastProjectDir: "/project-b" });
    expect(JSON.parse(readFileSync(join(location.directory, "settings.json"), "utf8")).appleGpuEnabled).toBe(true);
    setAppleGpuEnabled(false);
    expect(readSettings().appleGpuEnabled).toBe(false);
  });
  it("cannot be enabled through the general renderer settings update", () => {
    updateSettings({ appleGpuEnabled: true });
    expect(readSettings().appleGpuEnabled).toBeUndefined();
  });
  it("ignores a TetraVox path an older version saved, and drops it on the next write", () => {
    // TI launches only its own TetraVox (decision 2026-09-22); a stale `tetravoxPath` must not
    // resurface through settings or the bridge.
    writeFileSync(join(location.directory, "settings.json"), JSON.stringify({ lastProjectDir: "/p", tetravoxPath: "/Applications/Tetravox.app" }));
    expect(readSettings()).toEqual({ lastProjectDir: "/p" });
    updateSettings({ lastProjectDir: "/q" });
    expect(JSON.parse(readFileSync(join(location.directory, "settings.json"), "utf8"))).toEqual({ lastProjectDir: "/q" });
  });
  it("merges a partial notification preference over the defaults and repairs bad values", () => {
    updateSettings({ notifications: { detail: "minimal" } });
    updateSettings({ notifications: { sound: false, events: "nonsense" } });
    // An old boolean `sound: false` is stored as the "none" choice.
    expect(readSettings().notifications).toEqual({ enabled: true, detail: "minimal", sound: "none", events: "all" });
  });

  it("stores a known sound and repairs an unknown one to the default", () => {
    updateSettings({ notifications: { sound: "tick" } });
    expect(readSettings().notifications?.sound).toBe("tick");
    updateSettings({ notifications: { sound: "file:///etc/passwd" } });
    expect(readSettings().notifications?.sound).toBe("pulse");
  });
});
