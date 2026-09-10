/** Dev launch selects checkout code and UI before any build; no Docker or window. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ensureDevStack, nodeStackHost, REPO_DIR } from "../../scripts/devStack";
import { StackManager } from "../../src/main/stack";
import type { ContainerSummary } from "../../src/main/docker/stackApi";

const prompt = vi.hoisted(() => ({ question: vi.fn(), close: vi.fn() }));
vi.mock("node:readline/promises", () => ({ createInterface: () => prompt }));
const ttyDescriptor = Object.getOwnPropertyDescriptor(process.stdin, "isTTY");

const config = { projectDir: "/fixture/project", imageTag: "internal-fixture", port: 8765, mountRepo: true };

afterEach(() => {
  if (ttyDescriptor) Object.defineProperty(process.stdin, "isTTY", ttyDescriptor);
  else Reflect.deleteProperty(process.stdin, "isTTY");
  prompt.question.mockReset();
  prompt.close.mockReset();
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

describe("explicit noninteractive dev container choice", () => {
  const candidates: ContainerSummary[] = [
    { Id: "one", Names: ["/ti-toolbox-one"], Image: "idossha/ti-toolbox:dev", State: "running", Status: "Up", Labels: {} },
    { Id: "two", Names: ["/ti-toolbox-two"], Image: "idossha/ti-toolbox:dev", State: "running", Status: "Up", Labels: {} },
  ];
  it.each([["attach", "attach"], ["recreate", "replace"]])("honours %s only for the selected container", async (flag, action) => {
    vi.stubEnv("TIT_LAUNCH_EXISTING", flag);
    vi.stubEnv("TIT_LAUNCH_CONTAINER", "ti-toolbox-two");
    expect(await nodeStackHost.chooseRunningContainer!(candidates, "/fixture/docker-compose.yml")).toEqual({ action, containerId: "two" });
  });
  it("refuses ambiguous automation", async () => {
    vi.stubEnv("TIT_LAUNCH_EXISTING", "recreate");
    vi.stubEnv("TIT_LAUNCH_CONTAINER", "");
    await expect(nodeStackHost.chooseRunningContainer!(candidates, "/fixture/docker-compose.yml")).rejects.toThrow("exactly one");
  });
});

// Authored interaction fixtures pin the requested default and prevent verbose Docker metadata leaking
// into the selection list. Reproduce: npx vitest run tests/unit/dev-stack-start.test.ts.
describe("interactive dev container choice", () => {
  const candidates: ContainerSummary[] = [
    { Id: "private-id-one", Names: ["/ti-toolbox-one"], Image: "idossha/ti-toolbox:private-tag", State: "running", Status: "Up", Labels: { "ti-toolbox.project_dir": "/private/project" } },
    { Id: "private-id-two", Names: ["/ti-toolbox-two"], Image: "idossha/ti-toolbox:private-tag", State: "running", Status: "Up", Labels: {} },
  ];
  function interactive(...answers: string[]) {
    vi.stubEnv("TIT_LAUNCH_EXISTING", "");
    vi.stubEnv("TIT_LAUNCH_CONTAINER", "");
    Object.defineProperty(process.stdin, "isTTY", { configurable: true, value: true });
    answers.forEach((answer) => prompt.question.mockResolvedValueOnce(answer));
    return vi.spyOn(console, "log").mockImplementation(() => {});
  }
  it("recreates on Enter and displays the image with separate actions", async () => {
    const log = interactive("");
    expect(await nodeStackHost.chooseRunningContainer!([candidates[0]!], "/private/compose.yml"))
      .toEqual({ action: "replace", containerId: "private-id-one" });
    const output = log.mock.calls.flat().join("\n");
    expect(output).toContain("idossha/ti-toolbox:private-tag");
    expect(output).toContain("Recreate (default)");
    expect(output).toContain("Attach");
    expect(output).toContain("Available actions\n-----------------");
    expect(output).not.toMatch(/private-id|private\/|\/ti-toolbox-one|cancel/i);
    expect(prompt.question).toHaveBeenCalledTimes(1);
    expect(prompt.close).toHaveBeenCalledOnce();
  });
  it("attaches when option 2 is entered", async () => {
    interactive("2");
    expect(await nodeStackHost.chooseRunningContainer!([candidates[0]!], "/private/compose.yml"))
      .toEqual({ action: "attach", containerId: "private-id-one" });
    expect(prompt.close).toHaveBeenCalledOnce();
  });
  it("selects the numbered container before asking what to do", async () => {
    const log = interactive("2", "");
    expect(await nodeStackHost.chooseRunningContainer!(candidates, "/private/compose.yml"))
      .toEqual({ action: "replace", containerId: "private-id-two" });
    expect(log.mock.calls.flat().join("\n")).toContain("2. idossha/ti-toolbox:private-tag");
    expect(prompt.question).toHaveBeenNthCalledWith(1, "Select container number: ");
    expect(prompt.question).toHaveBeenCalledTimes(2);
    expect(prompt.close).toHaveBeenCalledOnce();
  });
});
