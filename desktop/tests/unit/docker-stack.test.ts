import { mkdtempSync, realpathSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { StackApi, type ContainerSummary } from "../../src/main/docker/stackApi";
import { decideAttach, resolveRepoDir, sameHostDir } from "../../src/main/stack";
import { DockerEngineError } from "../../src/main/docker/engine";
import { buildContainerPlan, parseComposeFile } from "../../src/shared/composeFile";
import { startFakeEngineApi, type FakeEngineApi } from "../e2e/fixtures/fake-engine-api.mjs";

/**
 * `StackApi` — the Engine API endpoints the stack lifecycle needs on top of the N0.3 job client —
 * against the same fake Engine API server (a real Unix socket, real HTTP) the client tests use.
 * `main/stack.ts` itself is exercised end to end in `tests/e2e/launcher.spec.ts`, since it needs
 * Electron; everything decidable without Electron is decided here or in `composeFile.test.ts`.
 */

const COMPOSE = `
services:
  tit:
    image: idossha/ti-toolbox:v3.0.0-dev
    platform: linux/amd64
    init: true
    volumes:
      - /host/project:/mnt/project
      - tit_cache:/opt/cache
    environment:
      TIT_SERVER_PORT: "18765"
      TIT_SERVER_TOKEN: sekret
    ports:
      - "127.0.0.1:18765:18765"
    networks:
      - ti_network
    healthcheck:
      test: ["CMD", "true"]
      interval: 10s
networks:
  ti_network:
    driver: bridge
volumes:
  tit_cache:
`;

const PROJECT = "ti-toolbox-deadbeef";
const LABELS = { "tit.project": PROJECT, "tit.stack": "ti-toolbox-v3" };

function plan() {
  return buildContainerPlan(parseComposeFile(COMPOSE, {}), { serviceName: "tit", projectName: PROJECT, labels: LABELS });
}

let fake: FakeEngineApi;
let api: StackApi;

beforeEach(async () => {
  fake = await startFakeEngineApi({ autoExit: false });
  api = new StackApi({ kind: "unix", socketPath: fake.socketPath }, "1.51");
});

afterEach(async () => {
  await fake.close();
});

describe("images", () => {
  it("reports a missing image as absent, not as an error", async () => {
    expect(await api.imageExists("idossha/ti-toolbox:v3.0.0-dev")).toBe(false);
  });

  it("reports an image the daemon already has", async () => {
    const local = await startFakeEngineApi({ images: ["idossha/ti-toolbox:v3.0.0-dev"] });
    const localApi = new StackApi({ kind: "unix", socketPath: local.socketPath }, "1.51");
    expect(await localApi.imageExists("idossha/ti-toolbox:v3.0.0-dev")).toBe(true);
    await local.close();
  });
});

describe("network and volume", () => {
  it("creates the network once and is idempotent on a second call", async () => {
    const p = plan();
    const first = await api.ensureNetwork(p.networkName as string, p.networkDriver);
    const second = await api.ensureNetwork(p.networkName as string, p.networkDriver);
    expect(second).toBe(first);
    expect([...fake.networks.values()].filter((n) => n.Name === p.networkName)).toHaveLength(1);
  });

  it("creates the named volume under its project-prefixed name", async () => {
    await api.ensureVolume(plan().namedVolumes[0] as string);
    await api.ensureVolume(plan().namedVolumes[0] as string);
    expect([...fake.volumes.keys()]).toEqual(["ti-toolbox-deadbeef_tit_cache"]);
  });
});

describe("container lifecycle", () => {
  it("creates the container with the plan's name, platform, labels and port binding", async () => {
    const p = plan();
    const created = await api.createContainer(p.body, { name: p.containerName, platform: p.platform });
    const container = fake.containers.get(created.Id);
    expect(container?.Name).toBe("ti-toolbox-deadbeef-tit-1");
    expect(container?.Platform).toBe("linux/amd64");
    expect(container?.Labels).toMatchObject(LABELS);
    expect(container?.publishedPort).toBe(18765);
    expect(container?.HostConfig?.Init).toBe(true);
  });

  it("refuses a second container with the same name (409), the way the real daemon does", async () => {
    const p = plan();
    await api.createContainer(p.body, { name: p.containerName });
    const err = await api.createContainer(p.body, { name: p.containerName }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(DockerEngineError);
    expect((err as DockerEngineError).kind).toBe("conflict");
  });

  it("finds this project's container by label and ignores another project's", async () => {
    const p = plan();
    await api.createContainer(p.body, { name: p.containerName });
    const other = buildContainerPlan(parseComposeFile(COMPOSE, {}), { serviceName: "tit", projectName: "ti-toolbox-c0ffee", labels: { "tit.project": "ti-toolbox-c0ffee" } });
    await api.createContainer(other.body, { name: other.containerName });

    const mine = await api.listContainers({ "tit.project": PROJECT });
    expect(mine).toHaveLength(1);
    expect(mine[0]?.Names).toEqual(["/ti-toolbox-deadbeef-tit-1"]);
    expect(await api.listContainers({ "tit.project": "ti-toolbox-nothing" })).toEqual([]);
  });

  it("inspect recovers the port and token from the container's own environment", async () => {
    const p = plan();
    const created = await api.createContainer(p.body, { name: p.containerName });
    const state = await api.inspect(created.Id, p.containerPort);
    expect(state.env.TIT_SERVER_TOKEN).toBe("sekret");
    expect(state.publishedPort).toBe(18765);
    expect(state.labels["tit.project"]).toBe(PROJECT);
    expect(state.running).toBe(false);
  });

  it("inspect works by container name as well as id, and 404s for an unknown one", async () => {
    const p = plan();
    await api.createContainer(p.body, { name: p.containerName });
    expect((await api.inspect(p.containerName)).Name).toBe(p.containerName);
    const err = await api.inspect("ti-toolbox-nothing-tit-1").catch((e: unknown) => e);
    expect((err as DockerEngineError).kind).toBe("not-found");
  });

  it("removes a container by id", async () => {
    const p = plan();
    const created = await api.createContainer(p.body, { name: p.containerName });
    await api.removeContainerById(created.Id, true);
    expect(fake.containers.size).toBe(0);
  });
});

// ---------------------------------------------------------------------------------------------
// The two pure decisions `main/stack.ts` makes before it touches Docker at all. Importing
// `stack.ts` here is safe for the same reason `nativeRuntime.test.ts` gives: outside an Electron
// runtime `"electron"` resolves to a plain string, so `app` is `undefined` and nothing below
// touches it.
// ---------------------------------------------------------------------------------------------

describe("resolveRepoDir — the dev bind mount is opt-in, by name, unpackaged only", () => {
  it("is undefined when nothing asks for it (the default, dev or packaged)", () => {
    expect(resolveRepoDir({}, false)).toBeUndefined();
    expect(resolveRepoDir({}, true)).toBeUndefined();
  });

  it("is undefined in a packaged app even when the environment names a repo", () => {
    // The regression this exists for: the old fallback (`app.getAppPath() + "/.."`) resolved to
    // `TI-Toolbox.app/Contents/Resources` in a packaged build and was mounted over the image's own
    // `/ti-toolbox` — the directory the image pip-installs `tit` from. The container would have
    // died on `ModuleNotFoundError: No module named 'tit'` at the first packaged launch.
    expect(resolveRepoDir({ TIT_DEV_REPO_DIR: "/Users/ido/repo" }, true)).toBeUndefined();
    expect(resolveRepoDir({ TIT_REPO_DIR: "/Users/ido/repo" }, true)).toBeUndefined();
  });

  it("honours TIT_DEV_REPO_DIR, and TIT_REPO_DIR as the same request, in an unpackaged run", () => {
    expect(resolveRepoDir({ TIT_DEV_REPO_DIR: "/Users/ido/repo" }, false)).toBe("/Users/ido/repo");
    expect(resolveRepoDir({ TIT_REPO_DIR: "/Users/ido/repo" }, false)).toBe("/Users/ido/repo");
    expect(resolveRepoDir({ TIT_DEV_REPO_DIR: "/dev/one", TIT_REPO_DIR: "/dev/two" }, false)).toBe("/dev/one");
  });

  it("treats an empty or whitespace value as no request at all", () => {
    expect(resolveRepoDir({ TIT_DEV_REPO_DIR: "" }, false)).toBeUndefined();
    expect(resolveRepoDir({ TIT_DEV_REPO_DIR: "   " }, false)).toBeUndefined();
  });
});

describe("sameHostDir / decideAttach — the hash is a name, not an identity", () => {
  const summary = (over: Partial<ContainerSummary>): ContainerSummary => ({
    Id: "c0ffee1234567890",
    Names: ["/ti-toolbox-deadbeef-tit-1"],
    Image: "idossha/ti-toolbox:dev",
    State: "running",
    Status: "Up 3 minutes",
    Labels: {},
    ...over,
  });

  let dir: string;
  let link: string;

  beforeEach(() => {
    dir = realpathSync(mkdtempSync(join(tmpdir(), "tit-hostdir-")));
    link = join(mkdtempSync(join(tmpdir(), "tit-hostlink-")), "project");
    symlinkSync(dir, link);
  });

  it("matches the same directory reached through a symlink", () => {
    expect(sameHostDir(link, dir)).toBe(true);
    expect(sameHostDir(dir, link)).toBe(true);
  });

  it("does not match a different directory, or a missing label", () => {
    expect(sameHostDir("/some/other/project", dir)).toBe(false);
    expect(sameHostDir(undefined, dir)).toBe(false);
    expect(sameHostDir("", dir)).toBe(false);
  });

  it("attaches to a running container whose recorded host directory is ours", () => {
    const decision = decideAttach([summary({ Labels: { "tit.host_project_dir": dir } })], dir);
    expect(decision.kind).toBe("attach");
  });

  it("REFUSES a running container that carries this project's name but another directory", () => {
    const decision = decideAttach([summary({ Labels: { "tit.host_project_dir": "/Users/ido/datasets/other" } })], dir);
    expect(decision.kind).toBe("refuse");
    expect(decision.kind === "refuse" && decision.reason).toContain("ti-toolbox-deadbeef-tit-1");
    expect(decision.kind === "refuse" && decision.reason).toContain("/Users/ido/datasets/other");
  });

  it("refuses a running container with no host-directory label at all — there is nothing to compare", () => {
    const decision = decideAttach([summary({ Labels: {} })], dir);
    expect(decision.kind).toBe("refuse");
    expect(decision.kind === "refuse" && decision.reason).toContain("unrecorded");
  });

  it("recreates (rather than refusing) when the only collision is a stopped container", () => {
    const decision = decideAttach([summary({ State: "exited", Labels: { "tit.host_project_dir": "/elsewhere" } })], dir);
    expect(decision.kind).toBe("recreate");
    expect(decision.kind === "recreate" && decision.warnings[0]).toContain("different host directory");
  });

  it("starts fresh when nothing carries the label", () => {
    expect(decideAttach([], dir).kind).toBe("none");
  });
});
