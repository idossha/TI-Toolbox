/**
 * The monitor-hijack rule, as a test.
 *
 * `src/main/window.ts` decides whether a launch may reach the screen and `tests/e2e/_helpers.ts`
 * decides what the E2E harness asks for. Both are pure functions of the environment precisely so
 * this can be asserted without launching anything — the regression these guard against (a test run
 * raising fifteen windows on a developer's desktop) is expensive to notice by hand and free to
 * notice here.
 */
import { describe, expect, it } from "vitest";
import { mayShowSystemUi, windowMode } from "../../src/main/window";
import { offscreenEnv } from "../e2e/_helpers";

describe("windowMode", () => {
  it("is normal for a user launch that sets nothing", () => {
    expect(windowMode({})).toBe("normal");
  });

  it("is offscreen when the harness asks for it", () => {
    expect(windowMode({ TIT_E2E_OFFSCREEN: "1" })).toBe("offscreen");
  });

  it("lets the headed opt-in win over offscreen", () => {
    expect(windowMode({ TIT_E2E_OFFSCREEN: "1", TIT_E2E_HEADED: "1" })).toBe("normal");
  });

  it("treats any value other than 1 as unset", () => {
    expect(windowMode({ TIT_E2E_OFFSCREEN: "0" })).toBe("normal");
    expect(windowMode({ TIT_E2E_OFFSCREEN: "true" })).toBe("normal");
  });

  it("suppresses dock icon and notification banners exactly when offscreen", () => {
    expect(mayShowSystemUi("offscreen")).toBe(false);
    expect(mayShowSystemUi("normal")).toBe(true);
  });
});

describe("offscreenEnv", () => {
  const darwin = process.platform === "darwin";

  it("asks for offscreen by default on darwin, and leaves other platforms alone", () => {
    expect(offscreenEnv({})).toEqual(darwin ? { TIT_E2E_OFFSCREEN: "1" } : {});
  });

  it("adds nothing when the developer asked for windows", () => {
    expect(offscreenEnv({ TIT_E2E_HEADED: "1" })).toEqual({});
  });

  it("honours an explicit setting on every platform", () => {
    expect(offscreenEnv({ TIT_E2E_OFFSCREEN: "1" })).toEqual({ TIT_E2E_OFFSCREEN: "1" });
    expect(offscreenEnv({ TIT_E2E_OFFSCREEN: "0" })).toEqual({ TIT_E2E_OFFSCREEN: "0" });
  });

  it("round-trips into a main-process decision", () => {
    expect(windowMode({ ...offscreenEnv({}) })).toBe(darwin ? "offscreen" : "normal");
    expect(windowMode({ TIT_E2E_HEADED: "1", ...offscreenEnv({ TIT_E2E_HEADED: "1" }) })).toBe("normal");
  });
});
