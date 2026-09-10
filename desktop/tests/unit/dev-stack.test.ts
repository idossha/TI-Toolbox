/**
 * `describeMismatch` (`src/main/stack.ts`) — the decision `npm run dev` makes between attaching to
 * the running container and recreating it.
 *
 * The failure it prevents is the quiet one: a container that is up and healthy but was created
 * without the worktree mounted at `/ti-toolbox`, or without `TIT_SERVER_RELOAD`, serves the image's
 * own baked-in `tit`. Attaching to it looks like a successful `npm run dev`, and every Python edit
 * for the rest of the afternoon lands in a directory nothing imports. Each case below is one way
 * that container can differ, and each returns a sentence naming what differs.
 *
 * Also pins the packaged app's own behaviour: with no dev options, nothing mismatches, so
 * `stack.start()` from the launcher never recreates a user's running stack.
 */
import { describe, expect, it } from "vitest";
import { buildStackEnv } from "../../src/shared/compose";
import { describeMismatch, runningJobLabels } from "../../src/main/stack";

const REPO = "/Users/dev/TI-toolbox";
const devWant = { imageTag: "dev", repoDir: REPO, serverReload: true };
const mounts = [{ Type: "bind", Source: REPO, Destination: "/ti-toolbox" }];
const devState = { mounts, env: { TIT_REPO_DIR: REPO, TIT_SERVER_RELOAD: "1", PYTHONPATH: "/ti-toolbox" } };

describe("describeMismatch", () => {
  it("accepts a container that already matches", () => {
    expect(describeMismatch(devState, "idossha/ti-toolbox:dev", devWant)).toBeNull();
  });

  it("reports a container with no repo mounted at /ti-toolbox", () => {
    const reason = describeMismatch({ env: { TIT_SERVER_RELOAD: "1" } }, "idossha/ti-toolbox:dev", devWant);
    expect(reason).toMatch(/mounts \(none\) at \/ti-toolbox/);
    expect(reason).toContain(REPO);
  });

  it("reports a container that mounts a DIFFERENT checkout (two worktrees, one project)", () => {
    const other = { ...devState, mounts: [{ Type: "bind", Source: "/Users/dev/other-worktree", Destination: "/ti-toolbox" }] };
    expect(describeMismatch(other, "idossha/ti-toolbox:dev", devWant)).toMatch(/other-worktree/);
  });

  it("rejects a matching marker with no actual checkout mount", () => {
    expect(describeMismatch({ env: devState.env }, "idossha/ti-toolbox:dev", devWant)).toMatch(/without the requested checkout bind/);
  });

  it("rejects a checkout that the installed package could shadow", () => {
    expect(describeMismatch({ ...devState, env: { ...devState.env, PYTHONPATH: "/opt/package:/ti-toolbox" } }, "idossha/ti-toolbox:dev", devWant)).toMatch(/PYTHONPATH/);
  });

  it("reports a container started without TIT_SERVER_RELOAD", () => {
    const stale = { mounts, env: { TIT_REPO_DIR: REPO, PYTHONPATH: "/ti-toolbox" } };
    expect(describeMismatch(stale, "idossha/ti-toolbox:dev", devWant)).toMatch(/TIT_SERVER_RELOAD=\(none\).*wants 1/);
  });

  it("reports a container serving the image's baked UI when this run wants the worktree's build", () => {
    // The failure this catches: `--project=real` e2e loads the page from the SERVER's origin, so a
    // container on the baked bundle silently tests whatever the last image build carried.
    const want = { ...devWant, staticDir: "/ti-toolbox/desktop/out/renderer" };
    const reason = describeMismatch(devState, "idossha/ti-toolbox:dev", want);
    expect(reason).toMatch(/serves its UI from the image's baked bundle/);
    expect(reason).toContain("/ti-toolbox/desktop/out/renderer");
  });

  it("accepts a container already serving the same static dir", () => {
    const want = { ...devWant, staticDir: "/ti-toolbox/desktop/out/renderer" };
    const state = { mounts, env: { ...devState.env, TIT_STATIC_DIR: "/ti-toolbox/desktop/out/renderer" } };
    expect(describeMismatch(state, "idossha/ti-toolbox:dev", want)).toBeNull();
  });

  it("reports a container running another image tag", () => {
    expect(describeMismatch(devState, "idossha/ti-toolbox:v3.0.0-dev", devWant)).toMatch(/runs idossha\/ti-toolbox:v3\.0\.0-dev.*wants tag dev/);
  });

  it("does NOT recreate over a published port — TIT_DEV_PORT is a starting point, not a promise", () => {
    // Measured 2026-09-03: 8766-8780 were held by another agent's mock servers, so a start asking
    // for 8766 landed on 8781. Comparing the port would have recreated that container (killing any
    // job in it) on every later `npm run dev`.
    expect(describeMismatch(devState, "idossha/ti-toolbox:dev", devWant)).toBeNull();
  });

  it("checks nothing the caller did not ask for — the packaged app's start never recreates", () => {
    // stack.start() from the launcher passes no options at all and no requireMatch, so this is
    // belt-and-braces: even if it did, a user's running container matches an empty request.
    expect(describeMismatch({ env: {} }, "idossha/ti-toolbox:2.5.0", {})).toBeNull();
  });

  it("reads exactly the two variables buildStackEnv writes", () => {
    // Derived, not transcribed: if buildStackEnv ever stopped recording the repo dir or the reload
    // flag on the container, this comparison would silently start passing for every container.
    const env = buildStackEnv({
      hostProjectDir: "/data/000",
      projectDirName: "000",
      userConfigDir: "/home/dev/.config/ti-toolbox",
      port: 8765,
      token: "t",
      timezone: "UTC",
      hostOs: "darwin",
      hostOsVersion: "24.6.0",
      hostArch: "arm64",
      repoDir: REPO,
      serverReload: true,
    });
    expect(describeMismatch({ mounts, env: { ...env, PYTHONPATH: "/ti-toolbox" } }, "idossha/ti-toolbox:dev", devWant)).toBeNull();
  });

  it("a packaged-app env (no repo, no reload) mismatches a dev request, and vice versa", () => {
    const packaged = buildStackEnv({
      hostProjectDir: "/data/000",
      projectDirName: "000",
      userConfigDir: "/home/dev/.config/ti-toolbox",
      port: 8765,
      token: "t",
      timezone: "UTC",
      hostOs: "darwin",
      hostOsVersion: "24.6.0",
      hostArch: "arm64",
    });
    expect(packaged.TIT_REPO_DIR).toBe("");
    expect(packaged.TIT_SERVER_RELOAD).toBe("");
    expect(describeMismatch({ env: packaged }, "idossha/ti-toolbox:dev", devWant)).toMatch(/\/ti-toolbox/);
    expect(describeMismatch({ env: packaged }, "idossha/ti-toolbox:dev", { imageTag: "dev" })).toBeNull();
  });
});

/**
 * The guard in front of a recreate. Recreating stops the container and mints a NEW bearer token, so
 * doing it under a running job kills that job (16 minutes for an emulated FEM solve on this
 * hardware) and logs out every other client holding the old token. This is the pure half of that
 * decision — what counts as "busy" in `GET /api/jobs`, and what to do with a body that is not a
 * job list at all (a proxy error page, an older server): refuse recreation, because an unreadable response cannot prove the container is idle.
 */
describe("runningJobLabels", () => {
  it("names every unfinished job and ignores the finished ones", () => {
    const body = [
      { id: "a1", kind: "sim", state: "running" },
      { id: "b2", kind: "pre", state: "queued" },
      { id: "c3", kind: "flex", state: "succeeded" },
      { id: "d4", kind: "ex", state: "failed" },
      { id: "e5", kind: "analyzer", state: "cancelled" },
    ];
    expect(runningJobLabels(body)).toEqual(["sim a1", "pre b2"]);
  });

  it("refuses to infer idle state from an unreadable body", () => {
    for (const body of [null, undefined, "<html>502</html>", { detail: "Unauthorized" }, 42]) {
      expect(() => runningJobLabels(body)).toThrow(/job list/);
    }
  });

  it("treats new unfinished states as busy and malformed jobs as unverifiable", () => {
    expect(runningJobLabels([{ id: "a", kind: "sim", state: "cancelling" }])).toEqual(["sim a"]);
    expect(() => runningJobLabels([null])).toThrow(/Invalid job/);
    expect(() => runningJobLabels([{}])).toThrow(/Invalid job/);
    expect(runningJobLabels([])).toEqual([]);
  });

  it("survives a job with no id or kind rather than throwing inside the guard", () => {
    expect(runningJobLabels([{ state: "running" }])).toEqual(["job ?"]);
  });
});
