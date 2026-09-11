import { describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import { runtimePaths, verifyDigest, probeFastSurfer } from "./fastsurferInstall";

describe("managed FastSurfer installation", () => {
  it("rejects modified downloads", () => {
    const bytes = Buffer.from("verified release");
    const hash = createHash("sha256").update(bytes).digest("hex");
    expect(() => verifyDigest(bytes, hash)).not.toThrow();
    expect(() => verifyDigest(Buffer.from("modified release"), hash)).toThrow("checksum");
  });
  it("keeps source and interpreter inside the user runtime directory", () => {
    const runtime = runtimePaths("/tmp/ti-test-user");
    expect(runtime.pythonPath.startsWith(runtime.directory + "/")).toBe(true);
    expect(runtime.sourceDir.startsWith(runtime.directory + "/")).toBe(true);
    expect(runtime.directory).toContain("/tmp/ti-test-user/runtimes/");
  });
  it("does not mistake a missing installation for ready", async () => {
    expect(await probeFastSurfer("/tmp/missing-ti-native-runtime")).toBe(false);
  });
});
