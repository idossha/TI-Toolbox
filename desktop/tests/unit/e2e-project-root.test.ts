import { mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { projectHostRoot } from "../e2e/_helpers";

const fixture = mkdtempSync(join(tmpdir(), "tit-e2e-project-root-"));
afterAll(() => rmSync(fixture, { recursive: true, force: true }));

describe("real e2e host project selection", () => {
  it("requires an explicit root for a real server instead of choosing the maintainer dataset", () => {
    expect(() => projectHostRoot({ TIT_E2E_SERVER_URL: "http://127.0.0.1:9876", TIT_E2E_TOKEN: "fixture-real-token" }))
      .toThrow(/requires TIT_E2E_PROJECT_HOST/);
  });

  it("uses the explicitly supplied validation project", () => {
    expect(projectHostRoot({ TIT_E2E_PROJECT_HOST: fixture })).toBe(realpathSync(fixture));
  });

  it("preserves the mock suite's existing default", () => {
    expect(projectHostRoot({ TIT_E2E_SERVER_URL: "http://127.0.0.1:9876", TIT_E2E_TOKEN: "mock-token" }))
      .toBe("/Users/idohaber/datasets/000");
  });

  it("rejects relative paths, filesystem roots, and files", () => {
    expect(() => projectHostRoot({ TIT_E2E_PROJECT_HOST: "datasets/000" })).toThrow(/absolute/);
    expect(() => projectHostRoot({ TIT_E2E_PROJECT_HOST: "/" })).toThrow(/filesystem root/);
    const file = join(fixture, "file");
    writeFileSync(file, "fixture");
    expect(() => projectHostRoot({ TIT_E2E_PROJECT_HOST: file })).toThrow(/filesystem root or file/);
  });
});
