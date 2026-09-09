import { describe, expect, it } from "vitest";
import { automaticRunName, flexOutputFolder } from "../../src/renderer/pages/optimizer/plan";

describe("optimizer run folders", () => {
  const base = "/data/project/derivatives/SimNIBS/sub-101/flex-search/server-timestamp";
  it("uses local date/time and distinguishes simultaneous rows", () => {
    const date = new Date(2026, 8, 9, 0, 32, 38, 123);
    expect(automaticRunName("opt-1", date)).toBe("20260909_003238_123_1");
    expect(automaticRunName("opt-2", date)).not.toBe(automaticRunName("opt-1", date));
  });
  it("puts automatic and manual names under this subject's folder", () => {
    expect(flexOutputFolder(base, "", "20260909_003238_123_1")).toBe(base.replace("server-timestamp", "20260909_003238_123_1"));
    expect(flexOutputFolder(base, " manual ", "unused")).toBe(base.replace("server-timestamp", "manual"));
    expect(flexOutputFolder(base, "/data/explicit", "unused")).toBe("/data/explicit");
  });
  it("rejects traversal names and missing server roots", () => {
    expect(() => flexOutputFolder(base, "../other", "unused")).toThrow();
    expect(() => flexOutputFolder("missing", "", "auto")).toThrow();
  });
});
