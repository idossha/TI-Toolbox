/** Dev launch selects checkout code and UI before any build; no Docker or window. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ensureDevStack, REPO_DIR } from "../../scripts/devStack";
import { StackManager } from "../../src/main/stack";

const config = { projectDir: "/fixture/project", imageTag: "internal-fixture", port: 8765, mountRepo: true };

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("dev stack options", () => {
  it.each([true, false])("uses the selected source mode (mountRepo=%s) despite a stale static environment", async (mountRepo) => {
    vi.stubEnv("TIT_STATIC_DIR", "/stale/bundle");
    vi.spyOn(console, "log").mockImplementation(() => {});
    const start = vi.spyOn(StackManager.prototype, "start").mockResolvedValue({ ok: true, url: "http://127.0.0.1:8765", token: "fixture", attached: true });
    await ensureDevStack({ ...config, mountRepo });
    expect(start).toHaveBeenCalledWith(config.projectDir, {
      preferredPort: 8765,
      imageTag: "internal-fixture",
      repoDir: mountRepo ? REPO_DIR : undefined,
      serverReload: mountRepo,
      staticDir: mountRepo ? "/ti-toolbox/desktop/out/renderer" : "/opt/ti-toolbox/ui",
      requireMatch: true,
      forceRecreate: false,
    });
  });
});
