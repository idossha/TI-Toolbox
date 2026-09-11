import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
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
});
